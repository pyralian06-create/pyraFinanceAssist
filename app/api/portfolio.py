"""
持仓汇总查询 API

对应 /api/portfolio/* 路由

端点列表：
  GET  /summary              - 实时持仓快照（加权成本 + 浮动盈亏）
  GET  /today-pnl            - 今日相对上一收盘的盈亏
  GET  /daily-pnl            - 历史区间组合日曲线（从 position_daily_marks 聚合）
  GET  /daily-pnl/legs       - 历史区间 leg 明细（按标的）
  POST /daily-pnl/refresh    - 重算并写入指定区间 leg 数据
"""

import logging
import time
from datetime import date, timedelta
from fastapi import APIRouter, Depends, Query, HTTPException, BackgroundTasks
from sqlalchemy.orm import Session
from typing import Optional, List
from decimal import Decimal

from app.models.database import get_db
from app.pnl_engine import (
    calculate_portfolio,
    rebuild_daily_marks,
    query_portfolio_daily_series,
    query_leg_daily_series,
    get_today_pnl,
    get_today_pnl_legs,
)
from app.schemas.portfolio import PortfolioSummary
from app.schemas.daily_pnl import (
    DailyPnLRow,
    DailyPnLResponse,
    TodayPnLResponse,
    TodayLegPnLRow,
    PositionDailyMarkRow,
)

logger = logging.getLogger(__name__)
router = APIRouter()


# ─────────────────────────────────────────────────────────────
# 1. 实时持仓快照
# ─────────────────────────────────────────────────────────────

@router.get("/summary", response_model=PortfolioSummary)
def get_portfolio_summary(
    asset_type: Optional[str] = Query(None, description="按资产大类过滤: STOCK_A, FUND, GOLD_SPOT, STOCK_US"),
    db: Session = Depends(get_db)
):
    """
    获取实时持仓汇总

    - 聚合计算总资产、总浮盈、已实现盈亏
    - 返回所有活跃持仓（持仓量 > 0）的详细信息
    - 支持按资产大类过滤

    示例：
    - GET /api/portfolio/summary
    - GET /api/portfolio/summary?asset_type=STOCK_A
    """
    start_time = time.time()

    result = calculate_portfolio(db, asset_type_filter=asset_type)

    # 复用已拉取的 positions 现价，计算今日盈亏（仅做 DB 查询，不重复请求行情）
    if result.positions:
        legs = get_today_pnl_legs(db, result.positions)
        if legs:
            total_today_pnl = sum(Decimal(str(leg["daily_pnl_cny"])) for leg in legs)
            total_prev_mv = sum(Decimal(str(leg["prev_market_value_cny"])) for leg in legs)
            result.today_pnl_cny = total_today_pnl
            result.today_pnl_percent = (
                round(float(total_today_pnl / total_prev_mv * 100), 4)
                if total_prev_mv > Decimal("0") else None
            )

    from datetime import datetime as _dt
    result.data_update_time = _dt.now()

    elapsed = time.time() - start_time
    logger.info(f"✅ portfolio/summary 响应完成，耗时 {elapsed:.3f}s" +
                (f"（资产类型: {asset_type}）" if asset_type else ""))
    return result


# ─────────────────────────────────────────────────────────────
# 2. 今日盈亏
# ─────────────────────────────────────────────────────────────

@router.get("/today-pnl", response_model=TodayPnLResponse)
def get_today_pnl_endpoint(
    db: Session = Depends(get_db)
):
    """
    获取今日盈亏（相对上一有效交易日收盘）

    - 若今日已有 position_daily_marks 记录，从库中聚合（source=db）
    - 否则实时拉取行情估算（source=realtime）
    - 金额与百分比两个维度均返回
    """
    result = get_today_pnl(db)
    if result is None:
        raise HTTPException(status_code=404, detail="暂无持仓数据")

    source = "db" if result.get("_from_db") else "realtime"
    return TodayPnLResponse(
        date=result["date"],
        market_value=result["market_value"],
        daily_pnl=result["daily_pnl"],
        daily_pnl_percent=result["daily_pnl_percent"],
        source=source,
    )


# ─────────────────────────────────────────────────────────────
# 2b. 今日各持仓盈亏明细（实时，按标的拆分）
# ─────────────────────────────────────────────────────────────

@router.get("/today-pnl/legs", response_model=List[TodayLegPnLRow])
def get_today_pnl_legs_endpoint(
    db: Session = Depends(get_db)
):
    """
    获取今日各持仓实时盈亏明细（按标的拆分，金额均为人民币）

    - 实时行情由 calculate_portfolio 统一拉取，本接口直接复用，不重复请求
    - 与上一有效日 position_daily_marks 记录对比得出今日盈亏
    - 无历史基准时 prev_market_value_cny=0，daily_pnl_cny 仍正常展示
    - 按当前市值降序返回
    """
    portfolio = calculate_portfolio(db)
    if not portfolio.positions:
        return []

    legs = get_today_pnl_legs(db, portfolio.positions)
    return [TodayLegPnLRow(**leg) for leg in legs]


# ─────────────────────────────────────────────────────────────
# 3. 历史日曲线（聚合）
# ─────────────────────────────────────────────────────────────

@router.get("/daily-pnl", response_model=DailyPnLResponse)
def get_daily_pnl(
    start: Optional[date] = Query(None, description="开始日期 YYYY-MM-DD，默认为 90 天前"),
    end: Optional[date] = Query(None, description="结束日期 YYYY-MM-DD，默认为今天"),
    db: Session = Depends(get_db),
):
    """
    获取历史区间组合日收益曲线

    数据来源：position_daily_marks 表（GROUP BY mark_date 聚合）。
    若所请求区间无数据，返回 has_data=false；可先调用 POST /daily-pnl/refresh 生成数据。

    返回字段：
    - date: 日期
    - market_value: 当日组合总市值（CNY）
    - daily_pnl: 当日盈亏金额（CNY）
    - daily_pnl_percent: 当日收益率 %
    - cumulative_pnl: 从序列首日起的累计盈亏（CNY）
    """
    today = date.today()
    if end is None:
        end = today
    if start is None:
        start = end - timedelta(days=90)

    if start > end:
        raise HTTPException(status_code=400, detail="start 不能晚于 end")

    rows = query_portfolio_daily_series(db, start, end)
    series = [
        DailyPnLRow(
            date=r["date"],
            market_value=r["market_value"],
            daily_pnl=r["daily_pnl"],
            daily_pnl_percent=r["daily_pnl_percent"],
            cumulative_pnl=r["cumulative_pnl"],
        )
        for r in rows
    ]

    return DailyPnLResponse(
        start=start,
        end=end,
        series=series,
        total_days=len(series),
        has_data=len(series) > 0,
    )


# ─────────────────────────────────────────────────────────────
# 4. Leg 明细
# ─────────────────────────────────────────────────────────────

@router.get("/daily-pnl/legs", response_model=List[PositionDailyMarkRow])
def get_daily_pnl_legs(
    start: Optional[date] = Query(None, description="开始日期，默认 30 天前"),
    end: Optional[date] = Query(None, description="结束日期，默认今天"),
    symbol: Optional[str] = Query(None, description="按标的代码过滤"),
    asset_type: Optional[str] = Query(None, description="按资产大类过滤"),
    db: Session = Depends(get_db),
):
    """
    查询 leg 级别日度估值明细

    每行对应一个标的在某日的：持仓量、CNY 收盘价、市值、当日 leg 盈亏。
    支持按标的 / 资产类型过滤。
    """
    today = date.today()
    if end is None:
        end = today
    if start is None:
        start = end - timedelta(days=30)

    legs = query_leg_daily_series(db, start, end, symbol=symbol, asset_type=asset_type)
    return legs


# ─────────────────────────────────────────────────────────────
# 5. 触发重算
# ─────────────────────────────────────────────────────────────

@router.post("/daily-pnl/refresh")
def refresh_daily_pnl(
    start: Optional[date] = Query(None, description="起始日期，默认第一笔交易日"),
    end: Optional[date] = Query(None, description="结束日期，默认今天"),
    asset_type: Optional[str] = Query(None, description="仅重算某资产大类，留空为全部"),
    background_tasks: BackgroundTasks = BackgroundTasks(),
    db: Session = Depends(get_db),
):
    """
    重算并写入 position_daily_marks 数据

    - 从交易流水重放，按日计算 leg 估值，upsert 入库
    - 历史 K 线从 AkShare 实时拉取，港美股自动换算 CNY
    - 区间较长时（如半年+）耗时可能较高，建议非高峰调用
    """
    today = date.today()
    if end is None:
        end = today
    if start is None:
        # 默认从第一笔交易起算
        from app.models.trade import Trade
        first_trade = db.query(Trade).order_by(Trade.trade_date).first()
        if first_trade is None:
            raise HTTPException(status_code=404, detail="暂无交易记录")
        start = first_trade.trade_date.date()

    if start > end:
        raise HTTPException(status_code=400, detail="start 不能晚于 end")

    start_t = time.time()
    count = rebuild_daily_marks(db, start, end, asset_type_filter=asset_type)
    elapsed = time.time() - start_t

    return {
        "message": "重算完成",
        "start": str(start),
        "end": str(end),
        "rows_upserted": count,
        "elapsed_seconds": round(elapsed, 2),
    }
