"""
交易流水 ORM 模型

对应数据库 trades 表，记录所有买卖、分红交易。
注意：quantity 和 price 使用 Numeric 类型以支持高精度（基金份额、黄金克重）。
"""

from sqlalchemy import Column, Integer, String, DateTime, Numeric, Text
from sqlalchemy.sql import func
from datetime import datetime
from app.models.database import Base


class Trade(Base):
    """
    交易流水表

    字段说明：
    - asset_type: 资产大类 (STOCK_A, FUND, GOLD_SPOT, US_STOCK)
    - symbol: 资产代码 (sh600519, 005827, AU9999 等)
    - trade_date: 交易发生时间
    - trade_type: BUY(买入), SELL(卖出), DIVIDEND(分红)
    - price: 交易单价（黄金元/克，基金为净值，股票为股价）
    - quantity: 交易数量（支持小数，用于基金份额和黄金克数）
    - commission: 手续费 + 税费
    - notes: 备注
    - created_at: 记录创建时间
    """

    __tablename__ = "trades"

    id = Column(Integer, primary_key=True, index=True)

    # 资产标识
    asset_type = Column(String(20), nullable=False, index=True)
    symbol = Column(String(20), nullable=False, index=True)

    # 交易信息
    trade_date = Column(DateTime, nullable=False, index=True)
    trade_type = Column(String(10), nullable=False)  # BUY, SELL, DIVIDEND

    # 价格和数量：使用 Numeric 保证精度
    # precision=18: 总共 18 位数字
    # scale=6: 小数点后 6 位 (支持基金份额如 1030.123456)
    price = Column(Numeric(precision=18, scale=6), nullable=False)
    quantity = Column(Numeric(precision=18, scale=6), nullable=False)

    # 费用
    commission = Column(Numeric(precision=18, scale=6), default=0)

    # 备注
    notes = Column(Text, nullable=True)

    # 系统字段
    created_at = Column(DateTime, server_default=func.now())

    def __repr__(self):
        return (
            f"<Trade(id={self.id}, "
            f"asset_type={self.asset_type}, "
            f"symbol={self.symbol}, "
            f"trade_type={self.trade_type}, "
            f"price={self.price}, "
            f"quantity={self.quantity})>"
        )
