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
from app.data_fetcher.stock_a import get_cache_data, _cache_manager as stock_cache_manager
from app.data_fetcher.fund import _cache_etf, _cache_lof
from app.cache_refresh import do_full_refresh

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

    # 检查缓存是否就绪
    if get_cache_data() is None:
        logger.warning("📊 portfolio/summary 请求时缓存未就绪，返回 202")
        raise HTTPException(
            status_code=202,
            detail="系统正在初始化行情数据，请稍候几分钟后重试"
        )

    result = calculate_portfolio(db, asset_type_filter=asset_type)

    # 获取缓存数据更新时间（取最旧的时间，作为保守估计）
    cache_update_time = stock_cache_manager.get_update_time()
    etf_update_time = _cache_etf.get_update_time()
    lof_update_time = _cache_lof.get_update_time()

    # 取最旧的更新时间（最保守的数据时间）
    update_times = [t for t in [cache_update_time, etf_update_time, lof_update_time] if t is not None]
    if update_times:
        result.data_update_time = min(update_times)

    elapsed = time.time() - start_time

    logger.info(f"✅ portfolio/summary 响应完成，耗时 {elapsed:.3f}s" +
                (f"（资产类型: {asset_type}）" if asset_type else ""))

    return result


@router.get("/market-cache")
def get_market_cache(
    skip: int = Query(0, ge=0, description="跳过前 N 条记录（分页）"),
    limit: int = Query(50, ge=1, le=500, description="返回最多 N 条记录（分页）")
):
    """
    获取全市场行情缓存数据

    - 返回当前缓存中的所有 A 股行情数据
    - 支持分页查询
    - 如果缓存还在加载，返回初始化提示

    示例：
    - GET /api/portfolio/market-cache — 查看前 50 只股票
    - GET /api/portfolio/market-cache?skip=50&limit=100 — 分页查询
    """
    start_time = time.time()

    cache_df = get_cache_data()
    if cache_df is None:
        logger.info("📊 market-cache 请求时缓存未就绪，返回 202")
        raise HTTPException(
            status_code=202,
            detail="系统正在初始化行情数据，请稍候几分钟后重试"
        )

    # 分页处理
    total_count = len(cache_df)
    paginated_df = cache_df.iloc[skip : skip + limit]

    # 转换为字典列表返回
    result = {
        "total": total_count,
        "skip": skip,
        "limit": limit,
        "returned": len(paginated_df),
        "data": paginated_df[['代码', '名称', '最新价', '昨收', '涨跌额', '涨跌幅', '成交量']].to_dict(orient='records')
    }

    elapsed = time.time() - start_time
    logger.info(f"✅ market-cache 返回 {len(paginated_df)} 条记录 (总计 {total_count} 条)，耗时 {elapsed:.3f}s")
    return result


@router.get("/cache-status")
def get_cache_status():
    """
    获取缓存刷新状态（A股、ETF、LOF）

    返回每个数据源的刷新进度：
    - is_refreshing: 是否正在刷新
    - is_ready: 缓存是否已加载（可用于查询）
    - last_update_time: 最后更新时间
    - elapsed_seconds: 当前刷新已耗时（进行中才有值）
    - progress: 刷新过程中的进度信息（来自ak库日志）
    """
    return {
        "stock_a": stock_cache_manager.get_status(),
        "etf": _cache_etf.get_status(),
        "lof": _cache_lof.get_status(),
    }


@router.post("/refresh-cache", status_code=200)
def manual_refresh_cache():
    """
    手动触发全量缓存刷新（A股 + ETF + LOF）

    - 与定时刷新互斥，同时只能有一个刷新任务运行
    - 同步等待所有缓存刷新完成后返回
    - 如果当前已有刷新进行中，返回 409
    """
    start_time = time.time()

    try:
        do_full_refresh(source="manual")
    except RuntimeError as e:
        raise HTTPException(status_code=409, detail=str(e))

    elapsed = time.time() - start_time

    cache_update_time = stock_cache_manager.get_update_time()
    etf_update_time = _cache_etf.get_update_time()
    lof_update_time = _cache_lof.get_update_time()
    update_times = [t for t in [cache_update_time, etf_update_time, lof_update_time] if t is not None]

    logger.info(f"✅ 手动缓存刷新完成，耗时 {elapsed:.1f}s")
    return {
        "message": "缓存刷新完成",
        "elapsed_seconds": round(elapsed, 1),
        "data_update_time": min(update_times).isoformat() if update_times else None,
    }
