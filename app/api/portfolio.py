"""
持仓汇总查询 API

对应 /api/portfolio/* 路由
"""

import logging
import time
from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy.orm import Session
from typing import Optional, Dict, List
import pandas as pd

from app.models.database import get_db
from app.pnl_engine import calculate_portfolio
from app.schemas.portfolio import PortfolioSummary

logger = logging.getLogger(__name__)
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
    start_time = time.time()

    result = calculate_portfolio(db, asset_type_filter=asset_type)

    # 直查数据即为最新，设置为当前时间
    from datetime import datetime as _dt
    result.data_update_time = _dt.now()

    elapsed = time.time() - start_time

    logger.info(f"✅ portfolio/summary 响应完成，耗时 {elapsed:.3f}s" +
                (f"（资产类型: {asset_type}）" if asset_type else ""))

    return result
