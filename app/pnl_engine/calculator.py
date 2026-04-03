"""
持仓与盈亏计算引擎 (PnL Calculator)

使用加权平均成本法：
1. 按时间序处理每笔交易
2. 计算当前持仓数量、加权平均成本、已实现盈亏
3. 结合最新行情计算浮动盈亏
"""

from dataclasses import dataclass
from decimal import Decimal
from typing import Dict, List, Tuple, Optional
from sqlalchemy.orm import Session
import logging

from app.models.trade import Trade
from app.data_fetcher import get_quote_batch
from app.schemas.portfolio import PositionDetail, PortfolioSummary


logger = logging.getLogger(__name__)


@dataclass
class _PositionState:
    """内部：按标的维护的持仓状态"""
    asset_type: str
    symbol: str
    holding_quantity: Decimal = Decimal('0')
    total_cost: Decimal = Decimal('0')  # 总成本（含手续费）
    realized_pnl: Decimal = Decimal('0')  # 已实现盈亏


def _process_trades(trades: List[Trade]) -> Dict[Tuple[str, str], _PositionState]:
    """
    处理交易列表，计算每只资产的持仓状态

    Args:
        trades: 按 trade_date 排序的交易列表

    Returns:
        Dict, key=(asset_type, symbol), value=_PositionState
    """
    states: Dict[Tuple[str, str], _PositionState] = {}

    for trade in trades:
        key = (trade.asset_type, trade.symbol)

        # 首次出现该标的，初始化状态
        if key not in states:
            states[key] = _PositionState(
                asset_type=trade.asset_type,
                symbol=trade.symbol
            )

        state = states[key]
        price = Decimal(str(trade.price))
        quantity = Decimal(str(trade.quantity))
        commission = Decimal(str(trade.commission or 0))

        if trade.trade_type == 'BUY':
            # 买入：增加成本和持仓
            state.total_cost += price * quantity + commission
            state.holding_quantity += quantity

        elif trade.trade_type == 'SELL':
            # 卖出：计算已实现盈亏，减少持仓
            if state.holding_quantity > Decimal('0'):
                avg_cost = state.total_cost / state.holding_quantity
                realized = (price - avg_cost) * quantity - commission
                state.realized_pnl += realized

                # 按卖出比例减少总成本
                state.total_cost -= avg_cost * quantity
                state.holding_quantity -= quantity

                # 防止浮点错误导致持仓数量为负小数
                if state.holding_quantity < Decimal('0'):
                    logger.warning(
                        f"{key}: 持仓数量变为负值，已夹紧到 0 "
                        f"(原值: {state.holding_quantity})"
                    )
                    state.holding_quantity = Decimal('0')

        elif trade.trade_type == 'DIVIDEND':
            # 分红：增加已实现盈亏，不影响持仓
            state.realized_pnl += price * quantity

    return states


def _build_position_detail(
    state: _PositionState,
    current_price: Optional[Decimal]
) -> PositionDetail:
    """
    基于持仓状态和当前价格生成持仓详情

    Args:
        state: 持仓状态
        current_price: 当前市价（若为 None，使用平均成本）

    Returns:
        PositionDetail 对象
    """
    if state.holding_quantity <= Decimal('0'):
        # 无持仓，不应该调用此函数
        raise ValueError(f"持仓数量必须 > 0, 实际: {state.holding_quantity}")

    avg_cost = state.total_cost / state.holding_quantity

    # 若无行情数据，降级为平均成本
    price = current_price if current_price is not None else avg_cost

    # 计算浮动盈亏
    floating_pnl = (price - avg_cost) * state.holding_quantity

    # 计算盈亏比例（%）
    cost_basis = avg_cost * state.holding_quantity
    if cost_basis > Decimal('0'):
        pnl_pct = floating_pnl / cost_basis * 100
    else:
        pnl_pct = Decimal('0')

    return PositionDetail(
        asset_type=state.asset_type,
        symbol=state.symbol,
        holding_quantity=state.holding_quantity,
        avg_cost=avg_cost,
        current_price=price,
        floating_pnl=floating_pnl,
        pnl_percent=f"{pnl_pct:+.2f}%"
    )


def calculate_portfolio(
    db: Session,
    asset_type_filter: Optional[str] = None
) -> PortfolioSummary:
    """
    计算整体持仓汇总（供 /api/portfolio/summary 调用）

    步骤：
    1. 查询数据库中的所有交易
    2. 按时间序处理，计算各标的持仓数量、平均成本、已实现盈亏
    3. 筛选活跃持仓（holding_quantity > 0）
    4. 批量拉取活跃持仓的最新行情
    5. 计算浮动盈亏和盈亏比例
    6. 汇总整体资产价值和盈亏

    Args:
        db: SQLAlchemy session
        asset_type_filter: 可选，过滤资产类型（如 'STOCK_A'）

    Returns:
        PortfolioSummary 对象，包含所有持仓明细和汇总数据
    """
    # 1. 从数据库查询交易记录，按交易时间排序
    query = db.query(Trade).order_by(Trade.trade_date)
    if asset_type_filter:
        query = query.filter(Trade.asset_type == asset_type_filter)
    trades = query.all()

    # 2. 处理交易，计算持仓状态
    states = _process_trades(trades)

    # 3. 筛选活跃持仓
    active_positions = [
        (state.asset_type, state.symbol)
        for state in states.values()
        if state.holding_quantity > Decimal('0')
    ]

    # 4. 批量获取行情
    quotes = get_quote_batch(active_positions) if active_positions else {}

    # 5. 构建持仓明细列表
    positions: List[PositionDetail] = []
    for (asset_type, symbol), state in states.items():
        # 跳过已卖出的持仓
        if state.holding_quantity <= Decimal('0'):
            continue

        # 获取当前价格（若失败则为 None）
        key = (asset_type, symbol)
        quote = quotes.get(key)
        current_price = quote.current_price if quote is not None else None

        # 生成持仓明细
        position = _build_position_detail(state, current_price)
        positions.append(position)

    # 6. 汇总
    total_assets = sum(
        (p.current_price * p.holding_quantity for p in positions),
        Decimal('0')
    )
    total_floating_pnl = sum(
        (p.floating_pnl for p in positions),
        Decimal('0')
    )
    total_realized_pnl = sum(
        (state.realized_pnl for state in states.values()),
        Decimal('0')
    )

    # 计算总盈亏比例
    if total_assets > Decimal('0'):
        total_pnl_pct = total_floating_pnl / (total_assets - total_floating_pnl) * 100
    else:
        total_pnl_pct = Decimal('0')

    return PortfolioSummary(
        total_assets=total_assets,
        total_pnl=total_floating_pnl,
        total_pnl_percent=f"{total_pnl_pct:+.2f}%",
        realized_pnl=total_realized_pnl,
        positions=positions
    )
