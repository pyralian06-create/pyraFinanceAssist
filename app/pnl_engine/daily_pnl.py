"""
日度持仓盈亏计算管线 (Daily PnL Engine)

核心职责：
1. 对指定日期区间，按日历日循环重放交易流水，计算每日每标的持仓快照。
2. 结合历史 K 线（CNY 折算后）计算日终市值与 leg 日度盈亏。
3. 将结果 upsert 写入 position_daily_marks 表（持久化）。
4. 提供聚合查询：GROUP BY mark_date → 组合日曲线（金额+百分比）。

币种口径：
- A 股、基金、黄金：原始价格即为人民币，fx_rate=1.0。
- STOCK_HK（港股）：历史收盘价 × HKD/CNY 汇率。
- STOCK_US（美股）：历史收盘价 × USD/CNY 汇率。
汇率来源：app/services/fx.py（AkShare 中间价，缺失时前向填充）。
"""

import logging
from datetime import date, timedelta
from decimal import Decimal
from typing import Dict, List, Optional, Tuple

from sqlalchemy.orm import Session
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from app.models.trade import Trade
from app.models.position_daily_mark import PositionDailyMark
from app.data_fetcher.router import get_history, get_quote_batch_direct
from app.pnl_engine.position_state import process_trades_up_to
from app.services.fx import get_fx_rate_for_asset, preload_fx_rates

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────
# 内部工具
# ──────────────────────────────────────────────

def _build_close_map(
    asset_type: str,
    symbol: str,
    start: date,
    end: date,
) -> Dict[date, Decimal]:
    """
    拉取单标的历史收盘价，返回 {date: close_raw} 字典（原始货币，未折汇率）。
    start/end 为 YYYYMMDD 字符串格式传给 get_history。
    """
    start_str = start.strftime("%Y%m%d")
    end_str = end.strftime("%Y%m%d")
    try:
        bars = get_history(asset_type, symbol, start_str, end_str)
    except Exception as e:
        logger.warning(f"⚠️ 无法拉取 {asset_type} {symbol} 历史数据: {e}")
        return {}
    return {bar.date: bar.close for bar in bars}


def _forward_fill(
    close_map: Dict[date, Decimal],
    target_date: date,
) -> Optional[Decimal]:
    """
    对 target_date 取价，若缺失则前向填充（取最近过去有价的日期）。
    全无数据时返回 None。
    """
    if target_date in close_map:
        return close_map[target_date]
    past = sorted(d for d in close_map if d <= target_date)
    if past:
        return close_map[past[-1]]
    return None


# ──────────────────────────────────────────────
# 主计算函数
# ──────────────────────────────────────────────

def rebuild_daily_marks(
    db: Session,
    start: date,
    end: date,
    asset_type_filter: Optional[str] = None,
) -> int:
    """
    重算并 upsert [start, end] 区间内所有 leg 的日度估值记录。

    Args:
        db: SQLAlchemy session
        start: 计算起始日期（含）
        end: 计算结束日期（含）
        asset_type_filter: 可选，仅计算该资产大类

    Returns:
        写入（upsert）的行数
    """
    logger.info(f"🔄 rebuild_daily_marks [{start} → {end}]")

    # 1. 拉全量交易（按时间排序），过滤器可选
    q = db.query(Trade).order_by(Trade.trade_date)
    if asset_type_filter:
        q = q.filter(Trade.asset_type == asset_type_filter)
    all_trades = q.all()

    if not all_trades:
        logger.info("  无交易记录，跳过")
        return 0

    # 2. 确定涉及的所有标的
    all_symbols: List[Tuple[str, str]] = list({
        (t.asset_type, t.symbol) for t in all_trades
    })

    # 3. 预加载汇率（港美股）
    preload_fx_rates(start, end)

    # 4. 预拉取每标的的历史收盘价（原始货币）
    close_maps: Dict[Tuple[str, str], Dict[date, Decimal]] = {}
    for asset_type, symbol in all_symbols:
        close_maps[(asset_type, symbol)] = _build_close_map(asset_type, symbol, start, end)

    # 5. 前一日市值缓存（用于计算 daily_pnl）
    # key = (asset_type, symbol), value = market_value_cny（上一有效日）
    prev_mv: Dict[Tuple[str, str], Decimal] = {}

    # 尝试从数据库读取 start-1 日的已有记录作为 prev_mv 基准
    prev_date = start - timedelta(days=1)
    existing_prev = db.query(PositionDailyMark).filter(
        PositionDailyMark.mark_date == prev_date
    ).all()
    for row in existing_prev:
        key = (row.asset_type, row.symbol)
        prev_mv[key] = Decimal(str(row.market_value_cny))

    # 6. 日历循环
    upsert_count = 0
    current = start
    while current <= end:
        # 6a. 计算截至当日的持仓快照
        states = process_trades_up_to(all_trades, current)
        active_states = {
            k: v for k, v in states.items()
            if v.holding_quantity > Decimal("0")
        }

        # 6b. 对每个活跃 leg 计算估值
        day_mv: Dict[Tuple[str, str], Decimal] = {}

        for key, state in active_states.items():
            asset_type, symbol = key
            close_raw = _forward_fill(close_maps.get(key, {}), current)

            if close_raw is None:
                logger.debug(f"  {current} {asset_type} {symbol}: 无收盘价，跳过")
                continue

            fx = get_fx_rate_for_asset(asset_type, current)
            close_cny = close_raw * fx
            mv = state.holding_quantity * close_cny
            day_mv[key] = mv

            prev = prev_mv.get(key, Decimal("0"))
            leg_pnl = mv - prev
            if prev > Decimal("0"):
                leg_pct = leg_pnl / prev * 100
            else:
                leg_pct = None

            # 6c. upsert 写入 position_daily_marks
            stmt = (
                sqlite_insert(PositionDailyMark)
                .values(
                    mark_date=current,
                    asset_type=asset_type,
                    symbol=symbol,
                    quantity_eod=float(state.holding_quantity),
                    close_price_cny=float(close_cny),
                    fx_rate=float(fx),
                    market_value_cny=float(mv),
                    daily_pnl_cny=float(leg_pnl),
                    daily_pnl_percent=float(leg_pct) if leg_pct is not None else None,
                )
                .on_conflict_do_update(
                    index_elements=["mark_date", "asset_type", "symbol"],
                    set_=dict(
                        quantity_eod=float(state.holding_quantity),
                        close_price_cny=float(close_cny),
                        fx_rate=float(fx),
                        market_value_cny=float(mv),
                        daily_pnl_cny=float(leg_pnl),
                        daily_pnl_percent=float(leg_pct) if leg_pct is not None else None,
                    ),
                )
            )
            db.execute(stmt)
            upsert_count += 1

        db.commit()

        # 6d. 本日市值作为下一日的 prev_mv（仅覆盖有数据的 leg）
        prev_mv.update(day_mv)

        # 对当日已清仓的标的清零 prev_mv
        for key in list(prev_mv.keys()):
            if key not in active_states:
                prev_mv[key] = Decimal("0")

        current += timedelta(days=1)

    logger.info(f"✅ rebuild_daily_marks 完成，共写入 {upsert_count} 行")
    return upsert_count


# ──────────────────────────────────────────────
# 查询函数
# ──────────────────────────────────────────────

def query_portfolio_daily_series(
    db: Session,
    start: date,
    end: date,
) -> List[Dict]:
    """
    从 position_daily_marks 按日期聚合，返回组合日曲线。

    返回格式（按日期升序）：
    [
      {
        "date": date,
        "market_value": Decimal,
        "daily_pnl": Decimal,
        "daily_pnl_percent": float | None,
        "cumulative_pnl": Decimal,
      },
      ...
    ]
    """
    from sqlalchemy import func as sqlfunc

    rows = (
        db.query(
            PositionDailyMark.mark_date,
            sqlfunc.sum(PositionDailyMark.market_value_cny).label("total_mv"),
            sqlfunc.sum(PositionDailyMark.daily_pnl_cny).label("total_pnl"),
        )
        .filter(
            PositionDailyMark.mark_date >= start,
            PositionDailyMark.mark_date <= end,
        )
        .group_by(PositionDailyMark.mark_date)
        .order_by(PositionDailyMark.mark_date)
        .all()
    )

    result = []
    cumulative = Decimal("0")
    for row in rows:
        total_mv = Decimal(str(row.total_mv or 0))
        total_pnl = Decimal(str(row.total_pnl or 0))
        prev_mv = total_mv - total_pnl  # 组合前日市值近似
        pnl_pct = float(total_pnl / prev_mv * 100) if prev_mv > Decimal("0") else None
        cumulative += total_pnl
        result.append({
            "date": row.mark_date,
            "market_value": total_mv,
            "daily_pnl": total_pnl,
            "daily_pnl_percent": round(pnl_pct, 4) if pnl_pct is not None else None,
            "cumulative_pnl": cumulative,
        })
    return result


def query_leg_daily_series(
    db: Session,
    start: date,
    end: date,
    symbol: Optional[str] = None,
    asset_type: Optional[str] = None,
) -> List[PositionDailyMark]:
    """
    查询 leg 明细，支持按 symbol / asset_type 过滤。
    """
    q = (
        db.query(PositionDailyMark)
        .filter(
            PositionDailyMark.mark_date >= start,
            PositionDailyMark.mark_date <= end,
        )
        .order_by(PositionDailyMark.mark_date, PositionDailyMark.symbol)
    )
    if symbol:
        q = q.filter(PositionDailyMark.symbol == symbol)
    if asset_type:
        q = q.filter(PositionDailyMark.asset_type == asset_type)
    return q.all()


def get_today_pnl(db: Session, today: Optional[date] = None) -> Optional[Dict]:
    """
    获取今日（或指定日期）相对上一有效日收盘的盈亏。
    若数据库中无今日记录，尝试用实时行情临时估算。

    Returns:
        {
          "date": date,
          "market_value": Decimal,
          "daily_pnl": Decimal,
          "daily_pnl_percent": float | None,
        }
        或 None（无持仓）
    """
    from datetime import date as date_cls
    from app.models.trade import Trade as TradeModel
    from app.pnl_engine.position_state import process_trades

    if today is None:
        today = date_cls.today()

    # 先查库中今日聚合
    from sqlalchemy import func as sqlfunc
    row = (
        db.query(
            sqlfunc.sum(PositionDailyMark.market_value_cny).label("total_mv"),
            sqlfunc.sum(PositionDailyMark.daily_pnl_cny).label("total_pnl"),
        )
        .filter(PositionDailyMark.mark_date == today)
        .one_or_none()
    )
    if row and row.total_mv:
        total_mv = Decimal(str(row.total_mv))
        total_pnl = Decimal(str(row.total_pnl or 0))
        prev_mv = total_mv - total_pnl
        pnl_pct = float(total_pnl / prev_mv * 100) if prev_mv > Decimal("0") else None
        return {
            "date": today,
            "market_value": total_mv,
            "daily_pnl": total_pnl,
            "daily_pnl_percent": round(pnl_pct, 4) if pnl_pct is not None else None,
            "_from_db": True,
        }

    # 库中无今日数据 → 用实时行情临时估算
    all_trades = db.query(TradeModel).order_by(TradeModel.trade_date).all()
    states = process_trades(all_trades)
    active = [(at, sym) for (at, sym), s in states.items() if s.holding_quantity > Decimal("0")]
    if not active:
        return None

    quotes = get_quote_batch_direct(active)

    # 查上一有效日市值（从库中取最近一条）
    prev_row = (
        db.query(
            sqlfunc.sum(PositionDailyMark.market_value_cny).label("total_mv"),
        )
        .filter(PositionDailyMark.mark_date < today)
        .order_by(PositionDailyMark.mark_date.desc())
        .first()
    )
    prev_total_mv = Decimal(str(prev_row.total_mv)) if prev_row and prev_row.total_mv else Decimal("0")

    total_mv_today = Decimal("0")
    for (at, sym), state in states.items():
        if state.holding_quantity <= Decimal("0"):
            continue
        quote = quotes.get((at, sym))
        if quote is None:
            continue
        fx = get_fx_rate_for_asset(at, today)
        price_cny = quote.current_price * fx
        total_mv_today += state.holding_quantity * price_cny

    daily_pnl = total_mv_today - prev_total_mv
    pnl_pct = float(daily_pnl / prev_total_mv * 100) if prev_total_mv > Decimal("0") else None
    return {
        "date": today,
        "market_value": total_mv_today,
        "daily_pnl": daily_pnl,
        "daily_pnl_percent": round(pnl_pct, 4) if pnl_pct is not None else None,
    }


def get_today_pnl_legs(db: Session, positions: list, today: Optional[date] = None) -> List[Dict]:
    """
    基于已获取的实时持仓数据，计算每个标的今日盈亏明细。

    复用 calculate_portfolio 返回的 positions（PositionDetail 列表），避免重复拉取行情。
    对比各标的在 position_daily_marks 中最近一条记录（昨日市值 CNY）作为基准。

    Args:
        db: SQLAlchemy session
        positions: calculate_portfolio 返回的 PositionDetail 列表（含 current_price）
        today: 计算日期，默认为今天

    Returns:
        每条为一个标的的今日盈亏字典，按当前市值降序排列
    """
    from datetime import date as date_cls

    if today is None:
        today = date_cls.today()

    result: List[Dict] = []
    for pos in positions:
        if pos.holding_quantity <= Decimal("0"):
            continue

        # 折算今日市值为 CNY
        fx = get_fx_rate_for_asset(pos.asset_type, today)
        price_cny = pos.current_price * fx
        mv_today = pos.holding_quantity * price_cny

        # 从 position_daily_marks 取该标的最近一日市值作为昨日基准
        prev_row = (
            db.query(PositionDailyMark)
            .filter(
                PositionDailyMark.asset_type == pos.asset_type,
                PositionDailyMark.symbol == pos.symbol,
                PositionDailyMark.mark_date < today,
            )
            .order_by(PositionDailyMark.mark_date.desc())
            .first()
        )
        prev_mv = Decimal(str(prev_row.market_value_cny)) if prev_row else Decimal("0")

        leg_pnl = mv_today - prev_mv
        leg_pct = float(leg_pnl / prev_mv * 100) if prev_mv > Decimal("0") else None

        result.append({
            "symbol": pos.symbol,
            "asset_type": pos.asset_type,
            "name": pos.name or "",
            "quantity": pos.holding_quantity,
            "current_price_cny": price_cny,
            "market_value_cny": mv_today,
            "prev_market_value_cny": prev_mv,
            "daily_pnl_cny": leg_pnl,
            "daily_pnl_percent": round(leg_pct, 4) if leg_pct is not None else None,
        })

    result.sort(key=lambda x: x["market_value_cny"], reverse=True)
    return result
