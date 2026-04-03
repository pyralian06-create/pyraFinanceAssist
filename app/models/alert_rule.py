"""
盯盘告警规则 ORM 模型

对应数据库 alert_rules 表，记录用户设定的监控规则。
"""

from sqlalchemy import Column, Integer, String, Numeric, Boolean, DateTime, Text
from sqlalchemy.sql import func
from app.models.database import Base


class AlertRule(Base):
    """
    告警规则表

    字段说明：
    - asset_type: 资产大类 (用于路由取价接口)
    - symbol: 资产代码
    - metric: 监控指标 (PRICE, VOLUME, CHANGE_PCT)
    - operator: 比较运算符 (>, <, >=, <=, ==)
    - threshold: 触发阈值
    - is_active: 规则是否启用 (1=启用, 0=禁用)
    - description: 规则描述 (如: "贵州茅台跌破 1500 时推送")
    - created_at: 规则创建时间
    - updated_at: 最后修改时间
    """

    __tablename__ = "alert_rules"

    id = Column(Integer, primary_key=True, index=True)

    # 资产标识
    asset_type = Column(String(20), nullable=False, index=True)
    symbol = Column(String(20), nullable=False, index=True)

    # 监控规则
    # metric 枚举：PRICE(价格), VOLUME(成交量), CHANGE_PCT(涨跌幅%)
    metric = Column(String(20), nullable=False)
    # operator 枚举：>, <, >=, <=, ==
    operator = Column(String(5), nullable=False)
    # threshold 例：1500.00, 100000000 (成交量), 5.0 (涨跌幅%)
    threshold = Column(Numeric(precision=18, scale=6), nullable=False)

    # 状态控制
    is_active = Column(Boolean, default=True, index=True)

    # 描述信息
    description = Column(Text, nullable=True)

    # 系统字段
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    def __repr__(self):
        return (
            f"<AlertRule(id={self.id}, "
            f"symbol={self.symbol}, "
            f"metric={self.metric} "
            f"{self.operator} {self.threshold}, "
            f"active={self.is_active})>"
        )
