"""
持仓与盈亏 Schema

PositionDetail: 单个持仓的详细信息（含盈亏计算）
PortfolioSummary: 整体持仓汇总（核心 API 返回体）
"""

from pydantic import BaseModel
from decimal import Decimal
from typing import List, Optional
from datetime import datetime


class PositionDetail(BaseModel):
    """
    单个资产的持仓详情

    字段说明：
    - holding_quantity: 当前持有数量（加总所有未卖出的购买）
    - avg_cost: 加权平均成本 = 总成本 / 持有数量
    - current_price: 当前市场价格（由 data_fetcher 提供）
    - floating_pnl: 浮动盈亏 = (current_price - avg_cost) * holding_quantity
    - pnl_percent: 盈亏比例 = floating_pnl / (avg_cost * holding_quantity) * 100%
    """

    asset_type: str
    symbol: str
    name: Optional[str] = None  # 资产名称（从行情缓存获取）
    holding_quantity: Decimal  # 持仓数量
    avg_cost: Decimal  # 加权平均成本
    current_price: Decimal  # 当前市价
    floating_pnl: Decimal  # 浮动盈亏 (金额)
    pnl_percent: str  # 盈亏比例 (字符串，如 "1.23%")

    class Config:
        from_attributes = True


class PortfolioSummary(BaseModel):
    """
    整体持仓汇总

    这是 GET /api/portfolio/summary 的核心返回体
    """

    total_assets: Decimal  # 总资产 = sum(持仓市值)
    total_pnl: Decimal  # 总盈亏 = sum(所有持仓的浮动盈亏)
    total_pnl_percent: str  # 总盈亏比例
    realized_pnl: Decimal  # 已实现盈亏 (已卖出部分)
    positions: List[PositionDetail]  # 所有持仓明细
    today_pnl_cny: Optional[Decimal] = None   # 今日盈亏金额（CNY，相对上一有效日收盘）
    today_pnl_percent: Optional[float] = None  # 今日收益率 %
    data_update_time: Optional[datetime] = None  # 行情数据最后更新时间

    class Config:
        json_schema_extra = {
            "example": {
                "total_assets": 150000.00,
                "total_pnl": 5000.00,
                "total_pnl_percent": "3.33%",
                "realized_pnl": 1000.00,
                "positions": [
                    {
                        "asset_type": "STOCK_A",
                        "symbol": "sh600519",
                        "holding_quantity": 100,
                        "avg_cost": 1680.0,
                        "current_price": 1700.0,
                        "floating_pnl": 2000.0,
                        "pnl_percent": "1.19%"
                    }
                ]
            }
        }
