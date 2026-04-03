"""
持仓汇总查询 API

对应 /api/portfolio/* 路由
"""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from typing import Optional

from app.models.database import get_db
from app.pnl_engine import calculate_portfolio
from app.schemas.portfolio import PortfolioSummary

router = APIRouter()


@router.get("/summary", response_model=PortfolioSummary)
def get_portfolio_summary(
    asset_type: Optional[str] = Query(None, description="按资产大类过滤: STOCK_A, FUND, GOLD_SPOT, US_STOCK"),
    db: Session = Depends(get_db)
):
    """
    获取持仓汇总

    - 聚合计算总资产、总浮盈、已实现盈亏
    - 返回所有活跃持仓（持仓量 > 0）的详细信息
    - 支持按资产大类过滤

    示例：
    - GET /api/portfolio/summary — 查看全部持仓
    - GET /api/portfolio/summary?asset_type=STOCK_A — 仅查看 A 股持仓
    """
    return calculate_portfolio(db, asset_type_filter=asset_type)
