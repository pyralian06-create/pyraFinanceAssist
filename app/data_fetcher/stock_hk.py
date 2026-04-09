"""
港股数据获取模块

负责从 Yahoo Finance（yfinance）获取港股实时行情和历史 K线数据。
使用个股直接查询方式，无需全市场下载。

Symbol 格式：4-5 位数字（如 0700 腾讯、9988 阿里巴巴）
yfinance 内部会追加 .HK 前缀
"""

import logging
from decimal import Decimal
from datetime import datetime
from typing import Optional, List
import pandas as pd

try:
    import yfinance as yf
except ImportError:
    yf = None

from .schemas import QuoteData, HistoricalBar
from .yfinance_retry import run_with_backoff

logger = logging.getLogger(__name__)


def get_quote(symbol: str) -> QuoteData:
    """获取港股实时行情（直连查询）"""
    return get_quote_direct(symbol)


def get_quote_direct(symbol: str) -> QuoteData:
    """直接查询单个港股实时行情（yfinance）

    Args:
        symbol: 港股代码（如 0700 腾讯、9988 阿里）

    Returns:
        QuoteData 对象

    Raises:
        ValueError: 查询失败
    """
    if yf is None:
        raise ImportError("yfinance not installed")

    def _once() -> QuoteData:
        logger.info(f"📈 直查港股 {symbol}...")
        ticker = yf.Ticker(f"{symbol}.HK")
        info = ticker.fast_info

        current_price = Decimal(str(info.last_price))
        prev_close = Decimal(str(info.previous_close))
        change_amount = current_price - prev_close
        change_pct = float((change_amount / prev_close * 100)) if prev_close > 0 else 0.0

        quote = QuoteData(
            symbol=symbol,
            name="",
            current_price=current_price,
            previous_close=prev_close,
            change_amount=change_amount,
            change_pct=change_pct,
            volume=info.volume if hasattr(info, 'volume') and info.volume else None,
            timestamp=datetime.now(),
            asset_type="STOCK_HK"
        )
        logger.info(f"✅ {symbol}: HK${quote.current_price} ({quote.change_pct:+.2f}%)")
        return quote

    try:
        return run_with_backoff(f"港股 {symbol}", _once)
    except Exception as e:
        logger.error(f"❌ 直查港股 {symbol} 失败: {e}")
        raise ValueError(f"无法获取港股 {symbol} 实时行情: {e}")


def get_history(
    symbol: str,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    adjust: str = ""
) -> List[HistoricalBar]:
    """
    获取港股历史 K线数据

    Args:
        symbol: 港股代码（如 0700）
        start_date: 开始日期（YYYYMMDD 格式，如 20250101）
        end_date: 结束日期（YYYYMMDD 格式）
        adjust: 复权方式（保留以兼容接口，yfinance 不支持此参数）

    Returns:
        List[HistoricalBar]: 历史 K线列表（从旧到新排序）

    Raises:
        ValueError: 代码不存在或获取失败
    """
    if yf is None:
        raise ImportError("yfinance not installed")

    def _once() -> List[HistoricalBar]:
        logger.info(f"📊 拉取港股 {symbol} 历史数据 ({start_date or '*'} 至 {end_date or '*'})...")

        ticker = yf.Ticker(f"{symbol}.HK")

        start = start_date[:4] + "-" + start_date[4:6] + "-" + start_date[6:8] if start_date else None
        end = end_date[:4] + "-" + end_date[4:6] + "-" + end_date[6:8] if end_date else None

        df = ticker.history(start=start, end=end)

        if df.empty:
            logger.warning(f"⚠️ 港股 {symbol} 无历史数据")
            return []

        bars = []
        for date, row in df.iterrows():
            bar = HistoricalBar(
                date=date.date() if hasattr(date, 'date') else date,
                open=Decimal(str(row['Open'])) if pd.notna(row.get('Open')) else Decimal('0'),
                close=Decimal(str(row['Close'])) if pd.notna(row.get('Close')) else Decimal('0'),
                high=Decimal(str(row['High'])) if pd.notna(row.get('High')) else Decimal('0'),
                low=Decimal(str(row['Low'])) if pd.notna(row.get('Low')) else Decimal('0'),
                volume=float(row['Volume']) if pd.notna(row.get('Volume')) else None,
                change_pct=None
            )
            bars.append(bar)

        logger.info(f"✅ 获取 {len(bars)} 条 K线")
        return bars

    try:
        return run_with_backoff(f"港股历史 {symbol}", _once)
    except Exception as e:
        logger.error(f"❌ 获取港股 {symbol} 历史数据失败: {e}")
        raise ValueError(f"无法获取港股 {symbol} 历史数据: {e}")
