from sqlalchemy import Column, String, Boolean, DateTime, Integer, PrimaryKeyConstraint, Index
from datetime import datetime
from app.models.database import Base

class MarketSymbol(Base):
    __tablename__ = "market_symbols"

    id = Column(Integer, primary_key=True, autoincrement=True)  # 自增主键
    symbol = Column(String(20), nullable=False)
    asset_type = Column(String(20), nullable=False)  # STOCK_A, FUND_ETF, FUND_LOF, FUND_OPEN
    name = Column(String(100), nullable=False)
    pinyin = Column(String(50), index=True)          # 简拼，如 gzmt
    is_active = Column(Boolean, default=True)        # 是否在市
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)

    # 约束与索引
    __table_args__ = (
        # 联合唯一约束：(asset_type, symbol) 不能重复
        PrimaryKeyConstraint('id', name='pk_market_symbols_id'),
        # 复合索引：用于高效查询 (asset_type, symbol)
        Index('idx_asset_symbol', 'asset_type', 'symbol', unique=True),
        # 单列索引：用于按代码查询
        Index('idx_symbol', 'symbol'),
    )
