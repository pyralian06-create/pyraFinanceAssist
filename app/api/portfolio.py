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

    result = calculate_portfolio(db, asset_type_filter=asset_type)

    # 直查数据即为最新，设置为当前时间
    from datetime import datetime as _dt
    result.data_update_time = _dt.now()

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


@router.get("/symbol-search")
def search_symbols(
    q: str = Query(..., min_length=1, description="搜索关键词（代码或名称）"),
    asset_type: str = Query("STOCK_A", description="资产类型: STOCK_A | FUND"),
    limit: int = Query(15, ge=1, le=50, description="返回结果最多数量")
):
    """
    按代码或名称模糊搜索标的（用于交易录入时验证代码）

    支持资产类型：
    - STOCK_A: 搜索 A股全市场缓存
    - FUND: 合并搜索 ETF + LOF 缓存

    返回：
    - 缓存未就绪返回 HTTP 202
    - 否则返回匹配结果列表 [{code, name, price, fund_type}, ...]
    """
    asset_type = asset_type.upper()
    q_clean = q.strip().lower()

    if asset_type == "STOCK_A":
        df = get_cache_data()
        if df is None:
            raise HTTPException(
                status_code=202,
                detail="A股缓存未就绪，请稍候后重试或直接输入代码"
            )

        # 代码匹配：去掉用户可能输入的 sh/sz 前缀后匹配
        q_code = q_clean.lstrip("shsz")
        mask = (
            df['代码'].astype(str).str.contains(q_code, case=False, na=False) |
            df['名称'].astype(str).str.contains(q, case=False, na=False)
        )
        matched = df[mask].head(limit)

        results = []
        for _, row in matched.iterrows():
            results.append({
                "code": str(row["代码"]),
                "name": str(row.get("名称", "")),
                "price": float(row.get("最新价", 0)) if pd.notna(row.get("最新价")) else 0,
                "fund_type": None
            })

        logger.info(f"✅ A股搜索 '{q}' → {len(results)} 条结果")
        return {"results": results}

    elif asset_type == "FUND":
        etf_df = _cache_etf.get_data()
        lof_df = _cache_lof.get_data()

        if etf_df is None and lof_df is None:
            raise HTTPException(
                status_code=202,
                detail="基金缓存未就绪，请稍候后重试或直接输入代码"
            )

        results = []

        # 搜索 ETF 缓存
        if etf_df is not None:
            mask = (
                etf_df['代码'].astype(str).str.contains(q_clean, case=False, na=False) |
                etf_df['名称'].astype(str).str.contains(q, case=False, na=False)
            )
            for _, row in etf_df[mask].iterrows():
                results.append({
                    "code": str(row["代码"]),
                    "name": str(row.get("名称", "")),
                    "price": float(row.get("最新价", 0)) if pd.notna(row.get("最新价")) else 0,
                    "fund_type": "ETF"
                })
                if len(results) >= limit:
                    break

        # 搜索 LOF 缓存（如果还有配额）
        if len(results) < limit and lof_df is not None:
            mask = (
                lof_df['代码'].astype(str).str.contains(q_clean, case=False, na=False) |
                lof_df['名称'].astype(str).str.contains(q, case=False, na=False)
            )
            for _, row in lof_df[mask].iterrows():
                if len(results) >= limit:
                    break
                results.append({
                    "code": str(row["代码"]),
                    "name": str(row.get("名称", "")),
                    "price": float(row.get("最新价", 0)) if pd.notna(row.get("最新价")) else 0,
                    "fund_type": "LOF"
                })

        logger.info(f"✅ 基金搜索 '{q}' → {len(results)} 条结果")
        return {"results": results[:limit]}

    else:
        raise HTTPException(
            status_code=400,
            detail=f"symbol-search 不支持资产类型 '{asset_type}'，仅支持 STOCK_A | FUND"
        )
