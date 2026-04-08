"""
日度持仓估值明细 ORM 模型

对应数据库 position_daily_marks 表。
每行记录某一自然日、某一持仓标的的日终快照：
- 日终持仓数量
- CNY 收盘价（港美股已折算）
- 当日市值（CNY）
- 当日 leg 盈亏（相对上一有效日同标的市值）

唯一约束：(mark_date, asset_type, symbol)，支持 upsert 刷新。
"""

from sqlalchemy import Column, Integer, String, Date, Numeric, DateTime, Index, UniqueConstraint
from sqlalchemy.sql import func
from app.models.database import Base


class PositionDailyMark(Base):
    """
    日度持仓估值明细表

    字段说明：
    - mark_date: 估值日期（自然日）
    - asset_type: 资产大类（STOCK_A / STOCK_HK / STOCK_US / FUND / GOLD_SPOT）
    - symbol: 资产代码
    - quantity_eod: 日终持仓数量（当日所有流水处理后）
    - close_price_cny: 当日收盘价（CNY，港美股已乘汇率）
    - fx_rate: 汇率快照（A 股/基金/黄金为 1.0）
    - market_value_cny: 日终市值 = quantity_eod × close_price_cny
    - daily_pnl_cny: 当日 leg 盈亏 = market_value_cny - 上一有效日 market_value_cny
    - daily_pnl_percent: 当日 leg 盈亏比例（%），分母为上一有效日市值；可为 null
    - created_at / updated_at: 系统字段
    """

    __tablename__ = "position_daily_marks"

    id = Column(Integer, primary_key=True, autoincrement=True)

    # 维度键
    mark_date = Column(Date, nullable=False, index=True)
    asset_type = Column(String(20), nullable=False)
    symbol = Column(String(20), nullable=False)

    # 持仓与估值
    quantity_eod = Column(Numeric(precision=18, scale=6), nullable=False)
    close_price_cny = Column(Numeric(precision=18, scale=6), nullable=False)
    fx_rate = Column(Numeric(precision=10, scale=6), nullable=False, default=1)
    market_value_cny = Column(Numeric(precision=18, scale=2), nullable=False)

    # 日度盈亏（与上一有效日对比）
    daily_pnl_cny = Column(Numeric(precision=18, scale=2), nullable=False, default=0)
    daily_pnl_percent = Column(Numeric(precision=10, scale=4), nullable=True)  # 百分比值，如 1.23

    # 系统字段
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        UniqueConstraint("mark_date", "asset_type", "symbol", name="uq_daily_mark_date_type_symbol"),
        Index("idx_daily_mark_date", "mark_date"),
        Index("idx_daily_mark_symbol", "asset_type", "symbol"),
    )

    def __repr__(self):
        return (
            f"<PositionDailyMark("
            f"date={self.mark_date}, "
            f"symbol={self.symbol}, "
            f"mv={self.market_value_cny}, "
            f"pnl={self.daily_pnl_cny})>"
        )
