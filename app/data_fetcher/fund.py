"""
基金数据获取模块（ETF / LOF / 开放式基金）

缓存策略：
  - ETF：启动时加载全市场并缓存，后续秒级查询
  - LOF：启动时加载全市场并缓存，后续秒级查询
  - 开放式基金：加载已持仓的基金，新基金按需单独查询

基金类型自动识别逻辑：
  - 6 位数代码 1xxxxx 或 5xxxxx → ETF（交易所交易基金）
  - 其他 6 位数代码 → 首先尝试 LOF，失败则当作开放式基金

三种基金类型的数据源：
  - ETF: fund_etf_spot_em() / fund_etf_hist_em()（全市场缓存）
  - LOF: fund_lof_spot_em() / fund_lof_hist_em()（全市场缓存）
  - 开放式基金: fund_open_fund_daily_em() / fund_open_fund_info_em()（按需查询）
       注意：开放式基金仅提供 T+1 净值，无实时市价
"""

import logging
from decimal import Decimal
from datetime import datetime
from typing import Optional, List, Dict
import pandas as pd
import socket

try:
    import akshare as ak
except ImportError:
    ak = None

from .schemas import QuoteData, HistoricalBar
from .cache_manager import CacheManager

logger = logging.getLogger(__name__)

# 缓存管理器
_cache_etf = CacheManager("ETF全市场行情")
_cache_lof = CacheManager("LOF全市场行情")
_cache_open_funds: Dict[str, QuoteData] = {}  # 按 symbol 缓存已加载的开放式基金


def _fetch_etf_spot() -> pd.DataFrame:
    """获取全市场 ETF 行情数据"""
    socket.setdefaulttimeout(60)
    return ak.fund_etf_spot_em()


def _fetch_lof_spot() -> pd.DataFrame:
    """获取全市场 LOF 行情数据"""
    socket.setdefaulttimeout(60)
    return ak.fund_lof_spot_em()


def init_cache_loaders() -> None:
    """初始化基金缓存加载函数（应用启动时调用）"""
    _cache_etf.set_load_func(_fetch_etf_spot)
    _cache_lof.set_load_func(_fetch_lof_spot)


def _detect_fund_type(symbol: str) -> str:
    """
    根据代码模式检测基金类型

    Args:
        symbol: 6位基金代码

    Returns:
        "ETF" / "LOF" / "OPEN"
    """
    if not symbol.isdigit() or len(symbol) != 6:
        # 无法判断，默认按开放式基金处理
        return "OPEN"

    # SZ 深交所 ETF: 159xxx
    if symbol.startswith('159') or symbol.startswith('16') or symbol.startswith('18'):
        # 159xxx 是深交所ETF / QDII, 16xxxx/18xxxx 可能是LOF
        # 简化：159xxx 当作 ETF，其他当作 LOF
        if symbol.startswith('159'):
            return "ETF"
        else:
            return "LOF"

    # SH 上交所: 5xxxxx 通常是 ETF / LOF，但逻辑复杂
    # 简化：501xxx - 513xxx 通常是 ETF，其他可能是 LOF
    if symbol.startswith('5'):
        # 501-513 是上交所 ETF
        if 500 < int(symbol[:3]) < 520:
            return "ETF"
        else:
            return "LOF"

    # 其他情况（0xxxxx, 2xxxxx, 3xxxxx 等）: 开放式基金
    return "OPEN"




def get_quote(symbol: str, fund_type: Optional[str] = None) -> QuoteData:
    """
    获取基金实时行情（ETF / LOF / 开放式基金）

    Args:
        symbol: 基金代码（如 510300, 159915, 005827）
        fund_type: 基金类型（"ETF" / "LOF" / "OPEN"），不指定则自动识别

    Returns:
        QuoteData: 实时行情数据

    Raises:
        ValueError: 代码不存在或获取失败
    """
    if ak is None:
        raise ImportError("akshare not installed")

    if fund_type is None:
        fund_type = _detect_fund_type(symbol)

    logger.info(f"📈 查询基金 {symbol} ({fund_type})...")

    try:
        if fund_type == "ETF":
            return _get_etf_quote(symbol)
        elif fund_type == "LOF":
            return _get_lof_quote(symbol)
        else:  # "OPEN"
            return _get_open_fund_quote(symbol)
    except Exception as e:
        logger.error(f"❌ 获取基金 {symbol} 失败: {e}")
        raise ValueError(f"无法获取基金 {symbol}: {e}")


def get_quote_direct(symbol: str, fund_type: Optional[str] = None) -> QuoteData:
    """直接查询单个基金行情（不依赖缓存）

    - ETF: stock_bid_ask_em → 实时价（ETF在交易所上市，可用股票接口）
    - LOF / 开放式基金: fund_open_fund_info_em → T+1 净值（数据源限制，无法实时）
    """
    if ak is None:
        raise ImportError("akshare not installed")

    if fund_type is None:
        fund_type = _detect_fund_type(symbol)

    logger.info(f"📈 直查基金 {symbol} ({fund_type})...")
    try:
        if fund_type == "ETF":
            return _get_etf_quote_direct(symbol)
        else:  # LOF 或 OPEN，用净值接口
            return _get_nav_quote_direct(symbol)
    except Exception as e:
        logger.error(f"❌ 直查基金 {symbol} 失败: {e}")
        raise ValueError(f"无法获取基金 {symbol}: {e}")


def _get_etf_quote_direct(symbol: str) -> QuoteData:
    """ETF 直查实时价（通过 stock_bid_ask_em，ETF在交易所上市行为同股票）"""
    df = ak.stock_bid_ask_em(symbol=symbol)
    items = dict(zip(df['item'], df['value']))

    current_price = Decimal(str(items['最新']))
    prev_close = Decimal(str(items.get('昨收', 0)))
    change_amount = current_price - prev_close
    change_pct = float(items.get('涨幅', 0))

    return QuoteData(
        symbol=symbol, name="",
        current_price=current_price,
        previous_close=prev_close,
        change_amount=change_amount,
        change_pct=change_pct,
        volume=None,
        timestamp=datetime.now(), asset_type="FUND"
    )


def _get_nav_quote_direct(symbol: str) -> QuoteData:
    """LOF / 开放式基金直查净值（T+1，数据源本身限制，无法实时）"""
    df = ak.fund_open_fund_info_em(symbol=symbol, indicator='单位净值走势')
    if df.empty:
        raise ValueError(f"基金 {symbol} 无数据")
    row = df.iloc[-1]
    nav = Decimal(str(row['单位净值']))
    change_pct = float(row.get('日增长率', 0)) if pd.notna(row.get('日增长率')) else 0.0
    prev_nav = nav / Decimal(str(1 + change_pct / 100)) if change_pct != 0 else nav
    return QuoteData(
        symbol=symbol, name="", current_price=nav,
        previous_close=prev_nav,
        change_amount=nav - prev_nav,
        change_pct=change_pct,
        volume=None, timestamp=datetime.now(), asset_type="FUND"
    )


def _get_etf_quote(symbol: str) -> QuoteData:
    """查询单个 ETF 实时行情（仅从缓存查询）"""
    try:
        logger.info(f"📈 查询 ETF {symbol}...")

        cache_df = _cache_etf.get_data()
        if cache_df is None:
            raise ValueError("ETF缓存尚未初始化，请稍候")

        match = cache_df[cache_df['代码'] == symbol]
        if match.empty:
            raise ValueError(f"ETF {symbol} 不存在或无数据")

        row = match.iloc[0]
        return QuoteData(
            symbol=symbol,
            name=str(row.get('名称', '')),
            current_price=Decimal(str(row.get('最新价', 0))),
            previous_close=Decimal(str(row.get('昨收', 0))),
            change_amount=Decimal(str(row.get('涨跌额', 0))),
            change_pct=float(row.get('涨跌幅', 0)),
            volume=float(row.get('成交量', 0)) if pd.notna(row.get('成交量')) else None,
            timestamp=datetime.now(),
            asset_type="FUND"
        )
    except Exception as e:
        logger.error(f"❌ 获取 ETF {symbol} 失败: {e}")
        raise


def _get_lof_quote(symbol: str) -> QuoteData:
    """查询单个 LOF 实时行情（仅从缓存查询）"""
    try:
        logger.info(f"📈 查询 LOF {symbol}...")

        cache_df = _cache_lof.get_data()
        if cache_df is None:
            raise ValueError("LOF缓存尚未初始化，请稍候")

        match = cache_df[cache_df['代码'] == symbol]
        if match.empty:
            raise ValueError(f"LOF {symbol} 不存在或无数据")

        row = match.iloc[0]
        return QuoteData(
            symbol=symbol,
            name=str(row.get('名称', '')),
            current_price=Decimal(str(row.get('最新价', 0))),
            previous_close=Decimal(str(row.get('昨收', 0))),
            change_amount=Decimal(str(row.get('涨跌额', 0))),
            change_pct=float(row.get('涨跌幅', 0)),
            volume=float(row.get('成交量', 0)) if pd.notna(row.get('成交量')) else None,
            timestamp=datetime.now(),
            asset_type="FUND"
        )
    except Exception as e:
        logger.error(f"❌ 获取 LOF {symbol} 失败: {e}")
        raise


def _load_open_fund_quote_sync(symbol: str) -> QuoteData:
    """
    同步加载单个开放式基金净值（用于缓存预加载）

    返回 QuoteData，并自动存入 _cache_open_funds
    """
    try:
        logger.info(f"📈 加载开放式基金 {symbol}...")
        df = ak.fund_open_fund_info_em(
            symbol=symbol,
            indicator='单位净值走势',
            period='1年'
        )

        if df.empty:
            raise ValueError(f"开放式基金 {symbol} 不存在")

        row = df.iloc[-1]
        current_nav = Decimal(str(row.get('单位净值', 0)))
        change_pct = float(row.get('日增长率', 0)) if pd.notna(row.get('日增长率')) else 0.0
        change_amount = Decimal(str(row.get('日增长值', 0))) if pd.notna(row.get('日增长值')) else Decimal('0')

        quote = QuoteData(
            symbol=symbol,
            name=str(row.get('基金简称', '')),
            current_price=current_nav,
            previous_close=current_nav / (1 + change_pct / 100) if change_pct != 0 else current_nav,
            change_amount=change_amount,
            change_pct=change_pct,
            volume=None,
            timestamp=datetime.now(),
            asset_type="FUND"
        )

        return quote
    except Exception as e:
        logger.error(f"❌ 加载开放式基金 {symbol} 失败: {e}")
        raise


def _get_open_fund_quote(symbol: str) -> QuoteData:
    """
    查询单个开放式基金实时净值

    优先从缓存查询，缓存中没有则即时加载并存入缓存

    注意：开放式基金仅提供 T+1 净值，无实时市价、无成交量
    """
    # 优先从缓存查询
    if symbol in _cache_open_funds:
        logger.info(f"📈 从缓存查询开放式基金 {symbol}")
        return _cache_open_funds[symbol]

    # 缓存中没有，即时加载
    quote = _load_open_fund_quote_sync(symbol)
    _cache_open_funds[symbol] = quote
    return quote


def get_history(
    symbol: str,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    fund_type: Optional[str] = None
) -> List[HistoricalBar]:
    """
    获取基金历史净值数据

    Args:
        symbol: 基金代码
        start_date: 开始日期（YYYYMMDD 格式）
        end_date: 结束日期（YYYYMMDD 格式）
        fund_type: 基金类型（不指定则自动识别）

    Returns:
        List[HistoricalBar]: 历史净值列表

    Raises:
        ValueError: 获取失败
    """
    if ak is None:
        raise ImportError("akshare not installed")

    if fund_type is None:
        fund_type = _detect_fund_type(symbol)

    try:
        if fund_type == "ETF":
            return _get_etf_history(symbol, start_date, end_date)
        elif fund_type == "LOF":
            return _get_lof_history(symbol, start_date, end_date)
        else:  # "OPEN"
            return _get_open_fund_history(symbol)
    except Exception as e:
        logger.error(f"❌ 获取基金 {symbol} 历史数据失败: {e}")
        raise ValueError(f"无法获取基金 {symbol} 历史数据: {e}")


def _get_etf_history(symbol: str, start_date: Optional[str], end_date: Optional[str]) -> List[HistoricalBar]:
    """ETF 历史数据"""
    logger.info(f"📊 拉取 ETF {symbol} 历史数据...")
    df = ak.fund_etf_hist_em(
        symbol=symbol,
        period='daily',
        start_date=start_date or '19700101',
        end_date=end_date or '20500101'
    )

    bars = []
    for _, row in df.iterrows():
        bar = HistoricalBar(
            date=pd.to_datetime(row['日期']).date() if isinstance(row['日期'], str) else row['日期'],
            open=Decimal(str(row['开盘'])),
            close=Decimal(str(row['收盘'])),
            high=Decimal(str(row['最高'])),
            low=Decimal(str(row['最低'])),
            volume=float(row['成交量']) if pd.notna(row.get('成交量')) else None,
            change_pct=float(row.get('涨跌幅', None)) if pd.notna(row.get('涨跌幅')) else None
        )
        bars.append(bar)

    return bars


def _get_lof_history(symbol: str, start_date: Optional[str], end_date: Optional[str]) -> List[HistoricalBar]:
    """LOF 历史数据"""
    logger.info(f"📊 拉取 LOF {symbol} 历史数据...")
    df = ak.fund_lof_hist_em(
        symbol=symbol,
        period='daily',
        start_date=start_date or '19700101',
        end_date=end_date or '20500101'
    )

    bars = []
    for _, row in df.iterrows():
        bar = HistoricalBar(
            date=pd.to_datetime(row['日期']).date() if isinstance(row['日期'], str) else row['日期'],
            open=Decimal(str(row['开盘'])),
            close=Decimal(str(row['收盘'])),
            high=Decimal(str(row['最高'])),
            low=Decimal(str(row['最低'])),
            volume=float(row['成交量']) if pd.notna(row.get('成交量')) else None,
            change_pct=float(row.get('涨跌幅', None)) if pd.notna(row.get('涨跌幅')) else None
        )
        bars.append(bar)

    return bars


def _get_open_fund_history(symbol: str) -> List[HistoricalBar]:
    """
    开放式基金历史净值数据

    注意：
    - AkShare 返回的 period 参数有限（'1月', '3月', '6月', '1年', '3年', '5年', '今年来', '成立来'）
    - 这里使用 '成立来' 获取全部历史
    - 返回的列名可能因版本而异
    """
    logger.info(f"📊 拉取开放式基金 {symbol} 历史净值...")
    df = ak.fund_open_fund_info_em(
        symbol=symbol,
        indicator='单位净值走势',
        period='成立来'
    )

    bars = []
    for _, row in df.iterrows():
        # 开放式基金 API 返回结构：净值日期, 单位净值, 累计净值, 日增长率, ...
        bar = HistoricalBar(
            date=pd.to_datetime(row['净值日期']).date() if isinstance(row.get('净值日期'), str) else row.get('净值日期'),
            open=Decimal(str(row.get('单位净值', 0))),  # 开放式无 OHLC，使用净值作 close
            close=Decimal(str(row.get('单位净值', 0))),
            high=Decimal(str(row.get('单位净值', 0))),
            low=Decimal(str(row.get('单位净值', 0))),
            volume=None,  # 开放式基金无成交量
            change_pct=float(row.get('日增长率', 0)) if pd.notna(row.get('日增长率')) else None
        )
        bars.append(bar)

    return bars
