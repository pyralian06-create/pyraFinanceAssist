"""
持仓与盈亏分析模块 (PnL & Position Engine)

功能：系统的"计算大脑"，负责基于历史流水和当前行情推算账户状态
- 成本计算：动态计算每只资产的持仓量和加权平均成本
- 盈亏计算：结合最新价实时计算浮动盈亏（Floating PnL）和盈亏比例
- 汇总分析：计算整体账户规模、历史实现盈亏、按资产分类过滤
"""

from app.pnl_engine.calculator import calculate_portfolio
from app.pnl_engine.daily_pnl import (
    rebuild_daily_marks,
    query_portfolio_daily_series,
    query_leg_daily_series,
    get_today_pnl,
    get_today_pnl_legs,
)

__all__ = [
    "calculate_portfolio",
    "rebuild_daily_marks",
    "query_portfolio_daily_series",
    "query_leg_daily_series",
    "get_today_pnl",
    "get_today_pnl_legs",
]
