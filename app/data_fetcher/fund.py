"""
基金数据获取模块（ETF / LOF / 开放式基金）

基金类型自动识别逻辑：
  - 6 位数代码 1xxxxx 或 5xxxxx → ETF（交易所交易基金）
  - 其他 6 位数代码 → 首先尝试 LOF，失败则当作开放式基金
  - 实际建议：前端明确指定基金类型，或在 symbol 中包含类型标记

三种基金类型的数据源：
  - ETF: fund_etf_spot_em() / fund_etf_hist_em()
  - LOF: fund_lof_spot_em() / fund_lof_hist_em()
  - 开放式基金: fund_open_fund_daily_em() / fund_open_fund_info_em()
       注意：开放式基金仅提供 T+1 净值，无实时市价
"""

import logging
from decimal import Decimal
from datetime import datetime, date
from typing import Optional, List, Tuple
import pandas as pd

try:
    import akshare as ak
except ImportError:
    ak = None

from .schemas import QuoteData, HistoricalBar

logger = logging.getLogger(__name__)

# 缓存：每类基金的全市场数据 + 时间戳
_cache_etf = {"timestamp": None, "data": None}
_cache_lof = {"timestamp": None, "data": None}
_cache_open = {"timestamp": None, "data": None}
_CACHE_EXPIRE_SECONDS = 60


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

    first_char = symbol[0]

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


def _get_etf_data_cached() -> pd.DataFrame:
    """获取 ETF 全市场数据（缓存 60s）"""
    global _cache_etf

    now = datetime.now()
    if (_cache_etf["timestamp"] is not None and
        (now - _cache_etf["timestamp"]).total_seconds() < _CACHE_EXPIRE_SECONDS and
        _cache_etf["data"] is not None):
        return _cache_etf["data"]

    logger.info("🔄 拉取 ETF 实时行情...")
    try:
        df = ak.fund_etf_spot_em()
        _cache_etf["timestamp"] = now
        _cache_etf["data"] = df
        logger.info(f"✅ 获取 {len(df)} 只 ETF")
        return df
    except Exception as e:
        logger.error(f"❌ 获取 ETF 行情失败: {e}")
        raise


def _get_lof_data_cached() -> pd.DataFrame:
    """获取 LOF 全市场数据（缓存 60s）"""
    global _cache_lof

    now = datetime.now()
    if (_cache_lof["timestamp"] is not None and
        (now - _cache_lof["timestamp"]).total_seconds() < _CACHE_EXPIRE_SECONDS and
        _cache_lof["data"] is not None):
        return _cache_lof["data"]

    logger.info("🔄 拉取 LOF 实时行情...")
    try:
        df = ak.fund_lof_spot_em()
        _cache_lof["timestamp"] = now
        _cache_lof["data"] = df
        logger.info(f"✅ 获取 {len(df)} 只 LOF")
        return df
    except Exception as e:
        logger.error(f"❌ 获取 LOF 行情失败: {e}")
        raise


def _get_open_fund_data_cached() -> pd.DataFrame:
    """获取开放式基金全市场数据（缓存 60s）"""
    global _cache_open

    now = datetime.now()
    if (_cache_open["timestamp"] is not None and
        (now - _cache_open["timestamp"]).total_seconds() < _CACHE_EXPIRE_SECONDS and
        _cache_open["data"] is not None):
        return _cache_open["data"]

    logger.info("🔄 拉取开放式基金实时净值...")
    try:
        df = ak.fund_open_fund_daily_em()
        _cache_open["timestamp"] = now
        _cache_open["data"] = df
        logger.info(f"✅ 获取 {len(df)} 只开放式基金")
        return df
    except Exception as e:
        logger.error(f"❌ 获取开放式基金失败: {e}")
        raise


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


def _get_etf_quote(symbol: str) -> QuoteData:
    """从 ETF 数据获取报价"""
    df = _get_etf_data_cached()
    row = df[df['代码'] == symbol]

    if row.empty:
        raise ValueError(f"ETF {symbol} 不存在")

    row = row.iloc[0]

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


def _get_lof_quote(symbol: str) -> QuoteData:
    """从 LOF 数据获取报价"""
    df = _get_lof_data_cached()
    row = df[df['代码'] == symbol]

    if row.empty:
        raise ValueError(f"LOF {symbol} 不存在")

    row = row.iloc[0]

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


def _get_open_fund_quote(symbol: str) -> QuoteData:
    """
    从开放式基金数据获取报价

    注意：开放式基金仅提供 T+1 净值，无实时市价、无成交量、无 previous_close
    """
    df = _get_open_fund_data_cached()
    row = df[df['基金代码'] == symbol]

    if row.empty:
        raise ValueError(f"开放式基金 {symbol} 不存在")

    row = row.iloc[0]

    # 动态列名：当日单位净值列名为 "YYYY-MM-DD-单位净值"
    nav_col = None
    for col in row.index:
        if isinstance(col, str) and col.endswith('-单位净值'):
            nav_col = col
            break

    if nav_col is None:
        raise ValueError(f"基金 {symbol} 无净值数据")

    current_nav = Decimal(str(row[nav_col]))
    change_pct = float(row.get('日增长率', 0)) if pd.notna(row.get('日增长率')) else 0.0

    return QuoteData(
        symbol=symbol,
        name=str(row.get('基金简称', '')),
        current_price=current_nav,
        previous_close=current_nav / (1 + change_pct / 100) if change_pct != 0 else current_nav,
        change_amount=Decimal(str(row.get('日增长值', 0))),
        change_pct=change_pct,
        volume=None,  # 开放式基金无成交量
        timestamp=datetime.now(),
        asset_type="FUND"
    )


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
