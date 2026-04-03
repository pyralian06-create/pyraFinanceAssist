"""
A股 数据获取模块

负责从 AkShare 获取 A股 实时行情和历史 K线数据。

注意：
- get_quote() 调用 stock_zh_a_spot_em()，拉取全市场 → 我们缓存 60s
- get_history() 调用 stock_zh_a_hist(symbol)，仅拉取单个股票 → 不慢，无需缓存
"""

import logging
from decimal import Decimal
from datetime import datetime, date
from typing import Optional, List
import pandas as pd

try:
    import akshare as ak
except ImportError:
    ak = None

from .schemas import QuoteData, HistoricalBar

logger = logging.getLogger(__name__)

# 全局缓存：（获取时间, DataFrame）
# 注意：仅用于 spot_em（全市场），history 按单个股票查询，无需缓存
_cache_spot = {"timestamp": None, "data": None}
_CACHE_EXPIRE_SECONDS = 60  # 实时行情缓存 60 秒


def _normalize_symbol(symbol: str) -> str:
    """
    A股 symbol 格式转换

    项目格式：sh600519 (带前缀)
    AkShare 格式：600519 (不带前缀)
    """
    if symbol.lower().startswith(('sh', 'sz')):
        return symbol[2:]  # 去掉前缀
    return symbol


def _get_spot_data_cached() -> pd.DataFrame:
    """
    获取 A股 全市场实时行情，带缓存

    注意：stock_zh_a_spot_em() 一次拉取 ~5000 只股票，较慢，所以缓存 60s
    同时调用多个 get_quote() 时，只真正执行一次 API 调用

    Returns:
        DataFrame with columns: 代码, 名称, 最新价, 昨收, 涨跌额, 涨跌幅, 成交量, ...
    """
    global _cache_spot

    now = datetime.now()

    # 缓存有效
    if (_cache_spot["timestamp"] is not None and
        (now - _cache_spot["timestamp"]).total_seconds() < _CACHE_EXPIRE_SECONDS and
        _cache_spot["data"] is not None):
        return _cache_spot["data"]

    # 缓存过期，重新获取
    logger.info("🔄 拉取 A股 全市场实时行情...")
    try:
        df = ak.stock_zh_a_spot_em()
        _cache_spot["timestamp"] = now
        _cache_spot["data"] = df
        logger.info(f"✅ 获取 {len(df)} 只 A股 行情")
        return df
    except Exception as e:
        logger.error(f"❌ 获取 A股 行情失败: {e}")
        raise


def get_quote(symbol: str) -> QuoteData:
    """
    获取 A股 实时行情

    Args:
        symbol: A股 代码（如 sh600519 或 600519）

    Returns:
        QuoteData: 实时行情数据

    Raises:
        ValueError: 代码不存在或获取失败
    """
    if ak is None:
        raise ImportError("akshare not installed")

    norm_symbol = _normalize_symbol(symbol)
    df = _get_spot_data_cached()

    # 查询该代码
    row = df[df['代码'] == norm_symbol]
    if row.empty:
        raise ValueError(f"A股代码 {symbol} 不存在")

    row = row.iloc[0]

    # 从 API 返回的行数据构造 QuoteData
    # 列名可能因 AkShare 版本而异，使用 get() 容错
    quote = QuoteData(
        symbol=symbol,
        name=str(row.get('名称', '')),
        current_price=Decimal(str(row.get('最新价', 0))),
        previous_close=Decimal(str(row.get('昨收', 0))),
        change_amount=Decimal(str(row.get('涨跌额', 0))),
        change_pct=float(row.get('涨跌幅', 0)),  # 已是百分比
        volume=float(row.get('成交量', 0)) if pd.notna(row.get('成交量')) else None,
        timestamp=datetime.now(),
        asset_type="STOCK_A"
    )

    return quote


def get_history(
    symbol: str,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    adjust: str = ""
) -> List[HistoricalBar]:
    """
    获取 A股 历史 K线数据

    注意：stock_zh_a_hist(symbol) 仅查询单个股票，响应速度快，无需缓存

    Args:
        symbol: A股 代码（如 sh600519 或 600519）
        start_date: 开始日期（YYYYMMDD 格式，如 20250101），默认无限制
        end_date: 结束日期（YYYYMMDD 格式），默认无限制
        adjust: 复权方式
                "" (默认): 原始价格，与成本计算一致 ← **建议用这个**
                "qfq": 前复权（向前调整历史价格，图表更清晰）
                "hfq": 后复权（向后调整历史价格，与当前价接近）

    Returns:
        List[HistoricalBar]: 历史 K线列表（从旧到新排序）

    Raises:
        ValueError: 代码不存在或获取失败
    """
    if ak is None:
        raise ImportError("akshare not installed")

    norm_symbol = _normalize_symbol(symbol)

    try:
        logger.info(f"📊 拉取 {symbol} 历史数据 ({start_date or '*'} 至 {end_date or '*'})...")
        df = ak.stock_zh_a_hist(
            symbol=norm_symbol,
            period='daily',
            start_date=start_date or '19700101',
            end_date=end_date or '20500101',
            adjust=adjust
        )

        if df.empty:
            logger.warning(f"⚠️ {symbol} 无历史数据")
            return []

        # 转换为 HistoricalBar 列表
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

        logger.info(f"✅ 获取 {len(bars)} 条 K线")
        return bars

    except Exception as e:
        logger.error(f"❌ 获取 {symbol} 历史数据失败: {e}")
        raise ValueError(f"无法获取 {symbol} 历史数据: {e}")
