"""
外汇汇率服务

职责：
- 获取港元（HKD）和美元（USD）对人民币（CNY）的历史与实时汇率
- 数据源：AkShare（currency_boc_safe 中间价接口）
- 汇率缓存：内存字典，按日期键；重启后自动从 AkShare 重拉

使用规则：
- A股、基金、黄金的 price 已为人民币，fx_rate = 1.0
- STOCK_HK（港股）：HKD → CNY
- STOCK_US（美股）：USD → CNY

缺某日汇率时前向填充（使用最近一个有效值）。
"""

import logging
from datetime import date, timedelta
from decimal import Decimal
from typing import Dict, Optional

from app.data_fetcher.network import domestic_direct_connection

logger = logging.getLogger(__name__)

# 资产类型 → 货币代码映射
ASSET_CURRENCY: Dict[str, str] = {
    "STOCK_A": "CNY",
    "FUND": "CNY",
    "GOLD_SPOT": "CNY",
    "STOCK_HK": "HKD",
    "STOCK_US": "USD",
}

# 内存汇率缓存：currency -> {date -> rate}
_rate_cache: Dict[str, Dict[date, Decimal]] = {}


def _load_rates_akshare(currency: str, start: date, end: date) -> Dict[date, Decimal]:
    """
    从 AkShare 拉取指定货币对 CNY 的历史汇率（银行间中间价）。
    currency: 'HKD' 或 'USD'
    返回 {date: rate} 字典，date 为拉取区间内有值的日期。
    """
    try:
        import akshare as ak
        import pandas as pd

        # 人民币汇率中间价（外汇局）
        with domestic_direct_connection():
            df = ak.currency_boc_safe()
        # df 列名含 '美元' '港元' 等，行为日期
        col_map = {"HKD": "港元", "USD": "美元"}
        col = col_map.get(currency)
        if col is None or col not in df.columns:
            logger.warning(f"⚠️ AkShare currency_boc_safe 未找到列 '{col}'，回退静态汇率")
            return {}

        # 日期列转 date，汇率列转 Decimal
        df["日期"] = pd.to_datetime(df["日期"]).dt.date
        df = df[(df["日期"] >= start) & (df["日期"] <= end)]
        result: Dict[date, Decimal] = {}
        for _, row in df.iterrows():
            try:
                # 中间价单位：100 外币 → CNY，需除以 100
                result[row["日期"]] = Decimal(str(row[col])) / 100
            except Exception:
                pass
        logger.info(f"✅ 已加载 {currency}/CNY 汇率 {len(result)} 条")
        return result
    except Exception as e:
        logger.error(f"❌ 拉取 {currency}/CNY 汇率失败: {e}")
        return {}


# 静态备用汇率（当 AkShare 不可用或区间无数据时兜底）
_FALLBACK_RATES: Dict[str, Decimal] = {
    "HKD": Decimal("0.917"),   # 近似值，仅在无法拉取时使用
    "USD": Decimal("7.25"),
}


def _ensure_cache(currency: str, start: date, end: date) -> None:
    """确保 currency 在 [start, end] 区间的汇率已加载到缓存。"""
    cached = _rate_cache.get(currency, {})
    # 若缓存已覆盖区间则跳过（简单判断首尾是否存在）
    if cached and min(cached) <= start and max(cached) >= end:
        return
    new_rates = _load_rates_akshare(currency, start, end)
    if currency not in _rate_cache:
        _rate_cache[currency] = {}
    _rate_cache[currency].update(new_rates)


def get_fx_rate(currency: str, target_date: date) -> Decimal:
    """
    获取指定日期的 currency→CNY 汇率。
    若缺该日数据，前向填充（取最近过去有值的日期）。
    currency = 'CNY' 直接返回 1.0。
    """
    if currency == "CNY":
        return Decimal("1.0")

    # 确保有至少 ±30 天的缓存窗口
    _ensure_cache(currency, target_date - timedelta(days=60), target_date + timedelta(days=5))
    cache = _rate_cache.get(currency, {})

    # 精确命中
    if target_date in cache:
        return cache[target_date]

    # 前向填充：找最近一个 <= target_date 的有效日期
    past_dates = sorted(d for d in cache if d <= target_date)
    if past_dates:
        return cache[past_dates[-1]]

    # 兜底：使用静态值并打警告
    fallback = _FALLBACK_RATES.get(currency, Decimal("1.0"))
    logger.warning(f"⚠️ {currency}/CNY 无缓存数据（{target_date}），使用静态汇率 {fallback}")
    return fallback


def get_fx_rate_for_asset(asset_type: str, target_date: date) -> Decimal:
    """根据资产类型获取对应 CNY 汇率。"""
    currency = ASSET_CURRENCY.get(asset_type, "CNY")
    return get_fx_rate(currency, target_date)


def preload_fx_rates(start: date, end: date) -> None:
    """
    批量预加载 HKD 和 USD 的汇率数据到内存缓存。
    在 rebuild_daily_marks 开始前调用，避免循环内重复拉取。
    """
    for currency in ("HKD", "USD"):
        _ensure_cache(currency, start, end)
        logger.info(f"✅ {currency}/CNY 汇率预加载完成")
