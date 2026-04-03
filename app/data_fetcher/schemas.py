"""
数据获取模块 - 统一数据结构

定义所有资产类型的统一输出格式，以便上层模块（PnL 计算、告警引擎）无需关心具体数据源。
"""

from dataclasses import dataclass, field
from decimal import Decimal
from datetime import datetime, date
from typing import Optional


@dataclass
class QuoteData:
    """
    实时行情数据 - 统一输出格式

    用途：
    - 持仓价值计算（current_price）
    - 盈亏计算（current_price vs cost）
    - 实时告警（PRICE / VOLUME / CHANGE_PCT）

    注意：
    - volume 对黄金为 None（SGE 不公布成交量）
    - change_pct 单位为百分比（如 2.35 表示 +2.35%）
    """

    symbol: str              # 资产代码（如 600519, 510300, Au99.99）
    name: str                # 资产名称
    current_price: Decimal   # 当前价格（股票元，基金元，黄金元/克）
    previous_close: Decimal  # 昨日收盘价（用于计算涨跌幅验证）
    change_amount: Decimal   # 涨跌额（昨收 - 当前价）
    change_pct: float        # 涨跌幅 %（如 2.35 = +2.35%）
    volume: Optional[float]  # 成交量（黄金为 None）
    timestamp: datetime      # 数据时间戳（取自 API）

    asset_type: str = field(default="")  # STOCK_A / FUND / GOLD_SPOT（由 router 填充）


@dataclass
class HistoricalBar:
    """
    历史 OHLCV 数据 - 用于图表展示和技术面分析

    注意：
    - volume 对黄金可能为 None
    - change_pct 需要在存储时计算或由 API 提供
    """

    date: date               # 交易日期
    open: Decimal            # 开盘价
    close: Decimal           # 收盘价（用于计算持仓成本、盈亏）
    high: Decimal            # 最高价
    low: Decimal             # 最低价
    volume: Optional[float]  # 成交量（黄金无此数据时为 None）
    change_pct: Optional[float]  # 日涨跌幅 %（可选，由 API 或程序计算）


@dataclass
class CachedData:
    """内部使用：缓存的 API 响应（带过期时间）"""
    fetch_time: datetime
    data: any  # DataFrame or list
