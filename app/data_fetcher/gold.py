"""
黄金现货数据获取模块（上海黄金交易所）

数据源：AkShare → 上海黄金交易所 (SGE)
  - 实时报价：spot_quotations_sge()，仅交易时间有效
  - 历史数据：spot_hist_sge()，全量历史记录

重要限制：
  - SGE 仅提供价格，无成交量数据 → VOLUME 告警不可用
  - 交易时间外（21:00-09:00）实时 API 可能返回空
  - 如需实时数据外的交易小时外数据，使用 spot_hist_sge() 最后一行

支持的品种代码：
  - Au99.99: 上海黄金基础交易品种（最常用）
  - Au99.95: 高纯度黄金
  - Au(T+D): 黄金延期（类似期货）
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

from .network import domestic_direct_connection
from .schemas import QuoteData, HistoricalBar

logger = logging.getLogger(__name__)

# 缓存：历史数据 + 时间戳
_cache_hist = {"timestamp": None, "data": None}
_CACHE_EXPIRE_SECONDS = 300  # 历史数据缓存 5 分钟


def get_quote(symbol: str = 'Au99.99') -> QuoteData:
    """
    获取黄金实时报价

    实现策略：
    1. 尝试调用 spot_quotations_sge() 获取实时 tick（仅交易时间）
    2. 如果返回空（非交易时间），fallback 到 spot_hist_sge() 的最后一行

    Args:
        symbol: 黄金品种代码，默认 Au99.99（上海黄金）
                其他选项：Au99.95, Au(T+D)

    Returns:
        QuoteData: 实时/最新报价

    Raises:
        ValueError: 无法获取数据
    """
    if ak is None:
        raise ImportError("akshare not installed")

    logger.info(f"📈 查询黄金 {symbol}...")

    try:
        # 尝试实时 API
        logger.debug(f"  → 尝试获取实时报价...")
        with domestic_direct_connection():
            df_tick = ak.spot_quotations_sge(symbol=symbol)

        if df_tick is not None and not df_tick.empty:
            # 取最后一行（最新报价）
            row = df_tick.iloc[-1]
            return _parse_quotation_row(symbol, row)

        # 实时 API 返回空，使用 fallback
        logger.info(f"  ⚠️ 实时报价空（非交易时间），使用历史最后一行...")
        hist = get_history(symbol)
        if not hist:
            raise ValueError(f"黄金 {symbol} 无数据")

        last_bar = hist[-1]
        # 构造 QuoteData
        return QuoteData(
            symbol=symbol,
            name=f"黄金 {symbol}",
            current_price=last_bar.close,
            previous_close=hist[-2].close if len(hist) >= 2 else last_bar.close,
            change_amount=last_bar.close - (hist[-2].close if len(hist) >= 2 else last_bar.close),
            change_pct=last_bar.change_pct if last_bar.change_pct is not None else 0.0,
            volume=None,  # SGE 无成交量
            timestamp=datetime.now(),
            asset_type="GOLD_SPOT"
        )

    except Exception as e:
        logger.error(f"❌ 获取黄金 {symbol} 失败: {e}")
        raise ValueError(f"无法获取黄金 {symbol}: {e}")


def _parse_quotation_row(symbol: str, row: pd.Series) -> QuoteData:
    """
    从 spot_quotations_sge() 返回行解析 QuoteData

    列名可能包含：品种, 时间, 现价, 更新时间
    """
    # 获取历史用于计算 previous_close 和 change
    hist = get_history(symbol)
    prev_close = hist[-1].close if hist else Decimal(str(row.get('现价', 0)))

    current_price = Decimal(str(row.get('现价', 0)))
    change_amount = current_price - prev_close
    change_pct = float((change_amount / prev_close * 100)) if prev_close != 0 else 0.0

    return QuoteData(
        symbol=symbol,
        name=f"黄金 {symbol}",
        current_price=current_price,
        previous_close=prev_close,
        change_amount=change_amount,
        change_pct=change_pct,
        volume=None,  # SGE 无成交量
        timestamp=datetime.now(),
        asset_type="GOLD_SPOT"
    )


def get_history(symbol: str = 'Au99.99') -> List[HistoricalBar]:
    """
    获取黄金历史数据（全量历史）

    注意：
    - spot_hist_sge() 无日期过滤参数，返回该品种全部历史（通常数千条）
    - 结果在内存中缓存 5 分钟，避免频繁 API 调用
    - 返回的 DataFrame 列名：date, open, close, low, high（无 volume）
    - change_pct 需要手动计算

    Args:
        symbol: 黄金品种代码，默认 Au99.99

    Returns:
        List[HistoricalBar]: 历史 K线列表（从旧到新排序）

    Raises:
        ValueError: 获取失败
    """
    if ak is None:
        raise ImportError("akshare not installed")

    global _cache_hist

    # 检查缓存
    now = datetime.now()
    if (_cache_hist["timestamp"] is not None and
        (now - _cache_hist["timestamp"]).total_seconds() < _CACHE_EXPIRE_SECONDS and
        _cache_hist["data"] is not None):
        logger.debug("📦 使用缓存的黄金历史数据")
        return _cache_hist["data"]

    try:
        logger.info(f"📊 拉取黄金 {symbol} 全部历史数据...")
        with domestic_direct_connection():
            df = ak.spot_hist_sge(symbol=symbol)

        if df.empty:
            logger.warning(f"⚠️ 黄金 {symbol} 无历史数据")
            return []

        # 转换为 HistoricalBar 列表
        bars = []
        prev_close = None

        for _, row in df.iterrows():
            open_price = Decimal(str(row.get('open', 0)))
            close_price = Decimal(str(row.get('close', 0)))
            high_price = Decimal(str(row.get('high', 0)))
            low_price = Decimal(str(row.get('low', 0)))

            # 计算涨跌幅
            change_pct = None
            if prev_close is not None and prev_close != 0:
                change_pct = float((close_price - prev_close) / prev_close * 100)

            bar = HistoricalBar(
                date=pd.to_datetime(row['date']).date() if isinstance(row.get('date'), str) else row['date'],
                open=open_price,
                close=close_price,
                high=high_price,
                low=low_price,
                volume=None,  # SGE 不提供成交量
                change_pct=change_pct
            )
            bars.append(bar)
            prev_close = close_price

        logger.info(f"✅ 获取 {len(bars)} 条黄金历史数据")

        # 缓存结果
        _cache_hist["timestamp"] = now
        _cache_hist["data"] = bars

        return bars

    except Exception as e:
        logger.error(f"❌ 获取黄金 {symbol} 历史数据失败: {e}")
        raise ValueError(f"无法获取黄金 {symbol} 历史数据: {e}")
