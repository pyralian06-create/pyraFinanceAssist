"""
盯盘告警 Schema

AlertRuleCreate: 创建告警规则
AlertRuleResponse: 返回告警规则
AlertRuleUpdate: 修改告警规则（支持启用/停用）
"""

from pydantic import BaseModel, Field
from decimal import Decimal
from datetime import datetime
from typing import Optional


class AlertRuleCreate(BaseModel):
    """创建告警规则的请求体"""

    asset_type: str = Field(
        ...,
        description="资产大类: STOCK_A, FUND, GOLD_SPOT, US_STOCK"
    )
    symbol: str = Field(..., description="资产代码")
    metric: str = Field(
        ...,
        description="监控指标: PRICE(价格), VOLUME(成交量), CHANGE_PCT(涨跌幅%)"
    )
    operator: str = Field(
        ...,
        description="比较运算符: >, <, >=, <="
    )
    threshold: Decimal = Field(..., decimal_places=6, description="触发阈值")
    description: Optional[str] = Field(
        default=None,
        description="规则描述，如'贵州茅台跌破 1500'"
    )


class AlertRuleResponse(BaseModel):
    """返回的告警规则"""

    id: int
    asset_type: str
    symbol: str
    metric: str
    operator: str
    threshold: Decimal
    is_active: bool
    description: Optional[str]
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class AlertRuleUpdate(BaseModel):
    """修改告警规则的请求体（所有字段可选）"""

    metric: Optional[str] = None
    operator: Optional[str] = None
    threshold: Optional[Decimal] = None
    description: Optional[str] = None
    is_active: Optional[bool] = None  # 快速启用/禁用规则


class AlertRuleToggle(BaseModel):
    """启用/禁用规则的快捷请求"""

    is_active: bool = Field(..., description="True=启用, False=禁用")
