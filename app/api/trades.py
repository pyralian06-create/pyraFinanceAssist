"""
交易流水管理 API

对应 /api/trades/* 路由
"""

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import Response
from sqlalchemy.orm import Session
from typing import Optional, List

from app.models.database import get_db
from app.models.trade import Trade
from app.schemas.trade import TradeCreate, TradeResponse, TradeUpdate
from app.services.daily_refresh import trigger_rebuild_from

router = APIRouter()


@router.post("/", response_model=TradeResponse, status_code=status.HTTP_201_CREATED)
@router.post("", response_model=TradeResponse, status_code=status.HTTP_201_CREATED)  # 支持不带斜杠
def create_trade(
    trade: TradeCreate,
    db: Session = Depends(get_db)
):
    """
    创建交易记录

    支持三种交易类型：
    - BUY: 买入（持仓数量增加）
    - SELL: 卖出（持仓数量减少）
    - DIVIDEND: 分红（现金收入，不影响持仓）

    示例请求体：
    ```json
    {
        "asset_type": "STOCK_A",
        "symbol": "sh600519",
        "trade_date": "2024-01-15T10:30:00",
        "trade_type": "BUY",
        "price": 1700.50,
        "quantity": 100,
        "commission": 5.00,
        "notes": "定投计划"
    }
    ```
    """
    db_trade = Trade(
        asset_type=trade.asset_type.upper(),
        symbol=trade.symbol,
        trade_date=trade.trade_date,
        trade_type=trade.trade_type.upper(),
        price=trade.price,
        quantity=trade.quantity,
        commission=trade.commission,
        notes=trade.notes
    )
    db.add(db_trade)
    db.commit()
    db.refresh(db_trade)
    trigger_rebuild_from(db_trade.trade_date.date())
    return db_trade


@router.get("/", response_model=List[TradeResponse])
@router.get("", response_model=List[TradeResponse])  # 支持不带斜杠的路由
def list_trades(
    asset_type: Optional[str] = Query(None, description="按资产大类过滤"),
    symbol: Optional[str] = Query(None, description="按标的代码过滤"),
    db: Session = Depends(get_db)
):
    """
    查询交易流水列表

    支持组合过滤：
    - GET /api/trades 或 /api/trades/ — 全部交易
    - GET /api/trades?asset_type=STOCK_A — A 股交易
    - GET /api/trades?symbol=sh600519 — 特定标的交易
    - GET /api/trades?asset_type=STOCK_A&symbol=sh600519 — 同时过滤
    """
    query = db.query(Trade).order_by(Trade.trade_date.desc())

    if asset_type:
        query = query.filter(Trade.asset_type == asset_type.upper())

    if symbol:
        query = query.filter(Trade.symbol == symbol)

    return query.all()


@router.get("/{trade_id}", response_model=TradeResponse)
def get_trade(
    trade_id: int,
    db: Session = Depends(get_db)
):
    """获取单条交易记录"""
    trade = db.query(Trade).filter(Trade.id == trade_id).first()
    if not trade:
        raise HTTPException(status_code=404, detail=f"交易记录 {trade_id} 不存在")
    return trade


@router.patch("/{trade_id}", response_model=TradeResponse)
def update_trade(
    trade_id: int,
    trade_update: TradeUpdate,
    db: Session = Depends(get_db)
):
    """
    部分更新交易记录

    只能修改以下字段（用于纠正数据错误）：
    - trade_type: 交易类型
    - price: 单价
    - quantity: 数量
    - commission: 手续费
    - notes: 备注

    资产标识（asset_type, symbol, trade_date）不允许修改

    示例：修正手续费错误
    ```json
    {"commission": 8.50}
    ```
    """
    trade = db.query(Trade).filter(Trade.id == trade_id).first()
    if not trade:
        raise HTTPException(status_code=404, detail=f"交易记录 {trade_id} 不存在")

    # 只更新非 None 字段
    update_data = trade_update.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        if value is not None:
            setattr(trade, field, value)

    db.commit()
    db.refresh(trade)
    trigger_rebuild_from(trade.trade_date.date())
    return trade


@router.delete("/{trade_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_trade(
    trade_id: int,
    db: Session = Depends(get_db)
):
    """
    删除交易记录

    删除后无法恢复，请谨慎操作
    """
    trade = db.query(Trade).filter(Trade.id == trade_id).first()
    if not trade:
        raise HTTPException(status_code=404, detail=f"交易记录 {trade_id} 不存在")

    rebuild_start = trade.trade_date.date()
    db.delete(trade)
    db.commit()
    trigger_rebuild_from(rebuild_start)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/batch", response_model=List[TradeResponse], status_code=status.HTTP_201_CREATED)
def create_trades_batch(
    trades: List[TradeCreate],
    db: Session = Depends(get_db)
):
    """
    批量创建交易记录

    一次提交多笔流水，全部成功才提交（事务），任一失败则全部回滚。
    重算区间取所有流水中最早的 trade_date，统一触发一次后台重算。

    示例请求体：
    ```json
    [
        {"asset_type": "STOCK_A", "symbol": "sh600519", "trade_date": "2024-01-15T10:00:00",
         "trade_type": "BUY", "price": 1700.0, "quantity": 100},
        {"asset_type": "FUND", "symbol": "510300", "trade_date": "2024-01-16T09:30:00",
         "trade_type": "BUY", "price": 4.5, "quantity": 1000}
    ]
    ```
    """
    if not trades:
        raise HTTPException(status_code=400, detail="至少需要一条交易记录")

    db_trades = [
        Trade(
            asset_type=t.asset_type.upper(),
            symbol=t.symbol,
            trade_date=t.trade_date,
            trade_type=t.trade_type.upper(),
            price=t.price,
            quantity=t.quantity,
            commission=t.commission,
            notes=t.notes,
        )
        for t in trades
    ]
    db.add_all(db_trades)
    db.commit()
    for t in db_trades:
        db.refresh(t)

    earliest = min(t.trade_date.date() for t in db_trades)
    trigger_rebuild_from(earliest)
    return db_trades
