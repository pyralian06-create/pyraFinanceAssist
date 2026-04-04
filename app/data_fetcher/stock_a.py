"""
A股 数据获取模块

负责从 AkShare 获取 A股 实时行情和历史 K线数据。

注意：
- get_quote() 从缓存查询，首次加载全市场 ~5-6分钟，后续秒级响应
- get_history() 调用 stock_zh_a_hist(symbol)，仅拉取单个股票 → 不慢，无需缓存
- 缓存在程序启动时开始后台加载
"""

import logging
from decimal import Decimal
from datetime import datetime, date
from typing import Optional, List
import pandas as pd
import socket

try:
    import akshare as ak
except ImportError:
    ak = None

from .schemas import QuoteData, HistoricalBar
from .cache_manager import CacheManager

logger = logging.getLogger(__name__)

# 使用通用缓存管理器
_cache_manager = CacheManager("A股全市场行情")


def _normalize_symbol(symbol: str) -> str:
    """
    A股 symbol 格式转换

    项目格式：sh600519 或 sz000001 (带前缀)
    AkShare stock_zh_a_spot_em() 返回格式：600519 或 000001 (不带前缀)
    """
    if symbol.lower().startswith(('sh', 'sz')):
        return symbol[2:]  # 去掉前缀
    return symbol


def _fetch_spot() -> pd.DataFrame:
    """从 AkShare 获取全市场 A股行情"""
    socket.setdefaulttimeout(60)
    return ak.stock_zh_a_spot_em()


def init_cache_loader() -> None:
    """初始化缓存加载函数（应用启动时调用）"""
    _cache_manager.set_load_func(_fetch_spot)


def get_cache_data() -> Optional[pd.DataFrame]:
    """获取缓存的全市场行情数据"""
    return _cache_manager.get_data()


def get_quote(symbol: str) -> QuoteData:
    """
    获取 A股 实时行情（仅从缓存查询）

    Args:
        symbol: A股 代码（如 sh600519 或 600519）

    Returns:
        QuoteData: 实时行情数据

    Raises:
        ValueError: 缓存不可用或代码不存在
    """
    if ak is None:
        raise ImportError("akshare not installed")

    norm_symbol = _normalize_symbol(symbol)

    try:
        logger.info(f"📈 查询 A股 {symbol}...")
        df = get_cache_data()

        if df is None:
            raise ValueError("行情缓存尚未初始化，请稍候")

        # 从缓存中过滤出该股票
        match = df[df['代码'] == norm_symbol]

        if match.empty:
            raise ValueError(f"A股代码 {symbol} 不存在或无数据")

        row = match.iloc[0]

        # 从缓存数据构造 QuoteData
        quote = QuoteData(
            symbol=symbol,
            name=str(row.get('名称', '')),
            current_price=Decimal(str(row.get('最新价', 0))),
            previous_close=Decimal(str(row.get('昨收', 0))),
            change_amount=Decimal(str(row.get('涨跌额', 0))),
            change_pct=float(row.get('涨跌幅', 0)),
            volume=float(row.get('成交量', 0)) if pd.notna(row.get('成交量')) else None,
            timestamp=datetime.now(),
            asset_type="STOCK_A"
        )

        logger.info(f"✅ {symbol}: ¥{quote.current_price} ({quote.change_pct:+.2f}%)")
        return quote

    except Exception as e:
        logger.error(f"❌ 获取 {symbol} 失败: {e}")
        raise ValueError(f"无法获取 A股 {symbol} 行情: {e}")


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
