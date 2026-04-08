"""
持仓状态计算（共享核心逻辑）

将 _PositionState 数据类与 _process_trades 抽取到独立模块，
供 calculator.py（实时持仓）与 daily_pnl.py（历史回放）共同复用，
避免循环依赖。
"""

from dataclasses import dataclass
from decimal import Decimal
from typing import Dict, List, Optional, Tuple
import logging

logger = logging.getLogger(__name__)


@dataclass
class PositionState:
    """按标的维护的持仓状态（加权平均成本法）。"""
    asset_type: str
    symbol: str
    holding_quantity: Decimal = Decimal("0")
    total_cost: Decimal = Decimal("0")   # 含手续费的总成本
    realized_pnl: Decimal = Decimal("0")


def process_trades(trades) -> Dict[Tuple[str, str], PositionState]:
    """
    按时间序处理交易列表，计算每只资产的持仓状态。

    Args:
        trades: 已按 trade_date 升序排列的 Trade ORM 对象列表，
                或任何具有 asset_type / symbol / trade_type /
                price / quantity / commission 属性的对象列表。

    Returns:
        Dict, key=(asset_type, symbol), value=PositionState
    """
    states: Dict[Tuple[str, str], PositionState] = {}

    for trade in trades:
        key = (trade.asset_type, trade.symbol)

        if key not in states:
            states[key] = PositionState(
                asset_type=trade.asset_type,
                symbol=trade.symbol,
            )

        state = states[key]
        price = Decimal(str(trade.price))
        quantity = Decimal(str(trade.quantity))
        commission = Decimal(str(trade.commission or 0))

        if trade.trade_type == "BUY":
            state.total_cost += price * quantity + commission
            state.holding_quantity += quantity

        elif trade.trade_type == "SELL":
            if state.holding_quantity > Decimal("0"):
                avg_cost = state.total_cost / state.holding_quantity
                realized = (price - avg_cost) * quantity - commission
                state.realized_pnl += realized
                state.total_cost -= avg_cost * quantity
                state.holding_quantity -= quantity
            if state.holding_quantity < Decimal("0"):
                logger.warning(
                    f"{key}: 持仓数量变为负值，已夹紧到 0 (原值: {state.holding_quantity})"
                )
                state.holding_quantity = Decimal("0")
                state.total_cost = Decimal("0")

        elif trade.trade_type == "DIVIDEND":
            state.realized_pnl += price * quantity

    return states


def process_trades_up_to(trades, cutoff_date) -> Dict[Tuple[str, str], PositionState]:
    """
    仅处理 trade_date.date() <= cutoff_date 的交易。

    Args:
        trades: 全量交易列表（已按 trade_date 升序）。
        cutoff_date: datetime.date 截止日。

    Returns:
        同 process_trades，但只含截至日期前的持仓状态。
    """
    filtered = [t for t in trades if t.trade_date.date() <= cutoff_date]
    return process_trades(filtered)
