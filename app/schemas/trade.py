"""
交易流水 Pydantic Schema

用途：
- TradeCreate: 接收 POST /api/trades 请求体，做数据验证
- TradeResponse: 返回交易流水时的序列化格式
"""

from pydantic import BaseModel, Field
from datetime import datetime
from decimal import Decimal
from typing import Optional


class TradeCreate(BaseModel):
    """
    创建交易记录的请求体

    Pydantic 会自动：
    1. 验证字段类型
    2. 尝试类型转换 (如 "1700.5" → Decimal)
    3. 返回验证错误
    """

    asset_type: str = Field(
        ...,
        description="资产大类: STOCK_A, FUND, GOLD_SPOT, US_STOCK"
    )
    symbol: str = Field(..., description="资产代码，如 sh600519, 005827")
    trade_date: datetime = Field(..., description="交易日期时间")
    trade_type: str = Field(
        ...,
        description="交易类型: BUY, SELL, DIVIDEND"
    )
    price: Decimal = Field(..., decimal_places=6, description="单价")
    quantity: Decimal = Field(..., decimal_places=6, description="数量（支持小数）")
    commission: Decimal = Field(
        default=Decimal("0"),
        decimal_places=6,
        description="手续费+税费"
    )
    notes: Optional[str] = Field(default=None, description="备注")


class TradeResponse(BaseModel):
    """
    返回的交易记录（ORM 模型转 JSON）

    Config.from_attributes 允许从 SQLAlchemy ORM 对象直接读取字段
    """

    id: int
    asset_type: str
    symbol: str
    trade_date: datetime
    trade_type: str
    price: Decimal
    quantity: Decimal
    commission: Decimal
    notes: Optional[str]
    created_at: datetime

    class Config:
        from_attributes = True  # 允许从 ORM 对象序列化


class TradeUpdate(BaseModel):
    """编辑交易记录的请求体（所有字段可选）"""

    trade_type: Optional[str] = None
    price: Optional[Decimal] = None
    quantity: Optional[Decimal] = None
    commission: Optional[Decimal] = None
    notes: Optional[str] = None
