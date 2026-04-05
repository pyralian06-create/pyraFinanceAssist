"""
A股 数据获取模块

负责从 AkShare 获取 A股 实时行情和历史 K线数据。
使用直接查询方式，不使用大内存缓存。
"""

import logging
from decimal import Decimal
from datetime import datetime
from typing import Optional, List
import pandas as pd

try:
    import akshare as ak
except ImportError:
    ak = None

from .schemas import QuoteData, HistoricalBar

logger = logging.getLogger(__name__)


def _normalize_symbol(symbol: str) -> str:
    """
    A股 symbol 格式转换

    项目格式：sh600519 或 sz000001 (带前缀)
    AkShare stock_zh_a_spot_em() 返回格式：600519 或 000001 (不带前缀)
    """
    if symbol.lower().startswith(('sh', 'sz')):
        return symbol[2:]  # 去掉前缀
    return symbol


def get_quote(symbol: str) -> QuoteData:
    """获取 A股 实时行情（直连查询）"""
    return get_quote_direct(symbol)


def get_quote_direct(symbol: str) -> QuoteData:
    """直接查询单个 A股 实时行情（不依赖缓存，按需调用）

    使用 stock_bid_ask_em：24h可用，交易时为实时价，非交易时为最新收盘。
    """
    if ak is None:
        raise ImportError("akshare not installed")

    norm_symbol = _normalize_symbol(symbol)

    try:
        logger.info(f"📈 直查 A股 {symbol}...")
        df = ak.stock_bid_ask_em(symbol=norm_symbol)

        # 转换为 item→value 字典
        items = dict(zip(df['item'], df['value']))

        current_price = Decimal(str(items['最新']))
        prev_close = Decimal(str(items.get('昨收', 0)))
        change_amount = current_price - prev_close
        change_pct = float(items.get('涨幅', 0))

        quote = QuoteData(
            symbol=symbol,
            name="",  # bid_ask 接口不返回股票名称
            current_price=current_price,
            previous_close=prev_close,
            change_amount=change_amount,
            change_pct=change_pct,
            volume=None,
            timestamp=datetime.now(),
            asset_type="STOCK_A"
        )
        logger.info(f"✅ {symbol}: ¥{quote.current_price} ({quote.change_pct:+.2f}%)")
        return quote

    except Exception as e:
        logger.error(f"❌ 直查 {symbol} 失败: {e}")
        raise ValueError(f"无法获取 A股 {symbol} 实时行情: {e}")


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
