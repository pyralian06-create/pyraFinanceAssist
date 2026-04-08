"""
日度盈亏 Pydantic Schema

PositionDailyMarkRow: 单标的日度估值明细（对应 position_daily_marks 表）
DailyPnLRow: 组合层按日聚合盈亏（由 leg 汇总而来）
TodayPnLResponse: 今日盈亏快速查询响应
DailyPnLResponse: /api/portfolio/daily-pnl 完整响应
"""

from pydantic import BaseModel
from decimal import Decimal
from datetime import date
from typing import List, Optional


class PositionDailyMarkRow(BaseModel):
    """单标的日度估值明细（leg 级别）"""
    mark_date: date
    asset_type: str
    symbol: str
    quantity_eod: Decimal
    close_price_cny: Decimal
    fx_rate: Decimal
    market_value_cny: Decimal
    daily_pnl_cny: Decimal
    daily_pnl_percent: Optional[float] = None  # 百分比值，如 1.23 表示 +1.23%

    class Config:
        from_attributes = True


class DailyPnLRow(BaseModel):
    """组合层：单日聚合盈亏（由各 leg 加总得到）"""
    date: date
    market_value: Decimal           # 当日总持仓市值（CNY）
    daily_pnl: Decimal              # 当日组合盈亏金额（CNY）
    daily_pnl_percent: Optional[float] = None  # 当日收益率 %（可能为 null）
    cumulative_pnl: Decimal         # 累计盈亏（从序列首日累加）


class TodayPnLResponse(BaseModel):
    """今日盈亏快速响应"""
    date: date
    market_value: Decimal
    daily_pnl: Decimal
    daily_pnl_percent: Optional[float] = None
    source: str = "db"  # "db" 表示从库读取，"realtime" 表示实时估算


class DailyPnLResponse(BaseModel):
    """GET /api/portfolio/daily-pnl 完整响应"""
    start: date
    end: date
    series: List[DailyPnLRow]       # 按日期升序的组合曲线
    total_days: int                 # 序列天数
    has_data: bool                  # 是否有任何数据
