from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy.orm import Session
from typing import List, Optional
from app.models.database import get_db
from app.models.market_symbol import MarketSymbol
from pydantic import BaseModel
from datetime import datetime

router = APIRouter()

class MarketSymbolSchema(BaseModel):
    symbol: str
    name: str
    asset_type: str
    pinyin: Optional[str]
    is_active: bool
    updated_at: datetime

    class Config:
        from_attributes = True

@router.get("/search", response_model=List[MarketSymbolSchema])
def search_market_symbols(
    q: str = Query(..., min_length=1, description="查询关键词 (代码, 名称 或 拼音)"),
    limit: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db)
):
    """
    模糊搜索市场标的 (代码, 名称 或 拼音)
    """
    query = db.query(MarketSymbol)
    
    # 模糊匹配 symbol, name 或 pinyin
    search_filter = (
        MarketSymbol.symbol.like(f"{q}%")
        | MarketSymbol.name.like(f"%{q}%")
        | MarketSymbol.pinyin.like(f"%{q}%")
    )
    # 港股库内为 5 位（如 00700），用户常搜 4 位（0700）→ 前缀匹配不到，补港股等值匹配
    if q.isdigit() and 1 <= len(q) <= 5:
        search_filter = search_filter | (
            (MarketSymbol.asset_type == "STOCK_HK")
            & (MarketSymbol.symbol == q.zfill(5))
        )
    
    # 优先返回活跃的标的
    results = query.filter(search_filter).order_by(
        MarketSymbol.is_active.desc(), 
        MarketSymbol.symbol.asc()
    ).limit(limit).all()
    
    return results

@router.get("/validate/{symbol}", response_model=MarketSymbolSchema)
def validate_symbol(
    symbol: str,
    db: Session = Depends(get_db)
):
    """
    验证代码是否存在并返回基本信息
    """
    result = db.query(MarketSymbol).filter(MarketSymbol.symbol == symbol).first()
    if not result:
        raise HTTPException(status_code=404, detail=f"标的代码 {symbol} 未找到")
    return result
