from sqlalchemy import Column, String, Boolean, DateTime
from datetime import datetime
from app.models.database import Base

class MarketSymbol(Base):
    __tablename__ = "market_symbols"

    symbol = Column(String(20), primary_key=True, index=True)
    name = Column(String(100), nullable=False)
    asset_type = Column(String(20), nullable=False)  # STOCK_A, FUND_ETF, FUND_LOF, FUND_OPEN
    pinyin = Column(String(50), index=True)          # 简拼，如 gzmt
    is_active = Column(Boolean, default=True)        # 是否在市
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)
