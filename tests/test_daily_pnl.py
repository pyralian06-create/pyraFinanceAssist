"""
每日持仓盈亏引擎单元测试

测试策略：
- 使用 SQLite 内存库，无需真实 AkShare 网络请求
- 用 mock 伪造 get_history / get_fx_rate_for_asset
- 验证 rebuild_daily_marks 写入的 leg 数据与人工计算一致
- 验证 query_portfolio_daily_series 的聚合结果
"""

import pytest
from datetime import date, datetime
from decimal import Decimal
from typing import Dict, List
from unittest.mock import patch, MagicMock

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.models.database import Base
from app.models.trade import Trade
from app.models.position_daily_mark import PositionDailyMark
from app.pnl_engine.position_state import process_trades, process_trades_up_to
from app.pnl_engine.daily_pnl import (
    rebuild_daily_marks,
    query_portfolio_daily_series,
    query_leg_daily_series,
)
from app.data_fetcher.schemas import HistoricalBar


# ──────────────────────────────────────────────
# Fixtures
# ──────────────────────────────────────────────

@pytest.fixture
def db():
    """内存 SQLite，含所有 ORM 表。"""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()


def make_trade(
    asset_type: str,
    symbol: str,
    trade_date: date,
    trade_type: str,
    price: float,
    quantity: float,
    commission: float = 0.0,
) -> Trade:
    """构造 Trade ORM 对象（不 add 到 session）。"""
    t = Trade()
    t.asset_type = asset_type
    t.symbol = symbol
    t.trade_date = datetime.combine(trade_date, datetime.min.time())
    t.trade_type = trade_type
    t.price = Decimal(str(price))
    t.quantity = Decimal(str(quantity))
    t.commission = Decimal(str(commission))
    t.notes = None
    return t


def make_history(symbol: str, close_map: Dict[date, float]) -> List[HistoricalBar]:
    """根据 {date: close} 字典构造 HistoricalBar 列表。"""
    bars = []
    for d, c in sorted(close_map.items()):
        bar = HistoricalBar(
            date=d,
            open=Decimal(str(c)),
            close=Decimal(str(c)),
            high=Decimal(str(c)),
            low=Decimal(str(c)),
            volume=1_000_000.0,
            change_pct=0.0,
        )
        bars.append(bar)
    return bars


# ──────────────────────────────────────────────
# process_trades 基础测试
# ──────────────────────────────────────────────

class TestProcessTrades:
    def test_single_buy(self):
        trades = [
            make_trade("STOCK_A", "sh600519", date(2024, 1, 2), "BUY", 1700, 100, 5),
        ]
        states = process_trades(trades)
        s = states[("STOCK_A", "sh600519")]
        assert s.holding_quantity == Decimal("100")
        # total_cost = 1700 * 100 + 5 = 170005
        assert s.total_cost == Decimal("170005")

    def test_buy_then_sell_partial(self):
        trades = [
            make_trade("STOCK_A", "sh600519", date(2024, 1, 2), "BUY", 1700, 100, 0),
            make_trade("STOCK_A", "sh600519", date(2024, 1, 3), "SELL", 1800, 50, 0),
        ]
        states = process_trades(trades)
        s = states[("STOCK_A", "sh600519")]
        assert s.holding_quantity == Decimal("50")
        # realized = (1800 - 1700) * 50 = 5000
        assert s.realized_pnl == Decimal("5000")

    def test_process_trades_up_to_cutoff(self):
        trades = [
            make_trade("STOCK_A", "sh600519", date(2024, 1, 2), "BUY", 1700, 100),
            make_trade("STOCK_A", "sh600519", date(2024, 1, 5), "BUY", 1750, 50),
        ]
        # 截止 1-3，只有第一笔
        states = process_trades_up_to(trades, date(2024, 1, 3))
        s = states[("STOCK_A", "sh600519")]
        assert s.holding_quantity == Decimal("100")

        # 截止 1-6，两笔都有
        states2 = process_trades_up_to(trades, date(2024, 1, 6))
        s2 = states2[("STOCK_A", "sh600519")]
        assert s2.holding_quantity == Decimal("150")


# ──────────────────────────────────────────────
# rebuild_daily_marks 集成测试（mock 行情与汇率）
# ──────────────────────────────────────────────

D0 = date(2024, 1, 2)   # 买入日
D1 = date(2024, 1, 3)
D2 = date(2024, 1, 4)   # 加仓日


class TestRebuildDailyMarks:
    """验证 leg 写入逻辑、前向填充、加仓场景。"""

    def _setup_trades(self, db):
        t1 = make_trade("STOCK_A", "sh600519", D0, "BUY", 100.0, 10, 0)
        t2 = make_trade("STOCK_A", "sh600519", D2, "BUY", 110.0, 5, 0)
        db.add(t1)
        db.add(t2)
        db.commit()

    def test_basic_leg_values(self, db):
        self._setup_trades(db)

        # 模拟收盘价：D0=100, D1=105, D2=110（加仓日）
        close_prices = {D0: 100.0, D1: 105.0, D2: 110.0}

        def fake_history(asset_type, symbol, start_str, end_str):
            return make_history(symbol, close_prices)

        with patch("app.pnl_engine.daily_pnl.get_history", side_effect=fake_history), \
             patch("app.pnl_engine.daily_pnl.preload_fx_rates"), \
             patch("app.pnl_engine.daily_pnl.get_fx_rate_for_asset", return_value=Decimal("1.0")):
            count = rebuild_daily_marks(db, D0, D2)

        assert count >= 3  # 3 天都有 leg

        # D0：qty=10，close=100 → mv=1000，prev=0 → pnl=1000
        leg_d0 = db.query(PositionDailyMark).filter_by(
            mark_date=D0, symbol="sh600519"
        ).first()
        assert leg_d0 is not None
        assert float(leg_d0.market_value_cny) == pytest.approx(1000.0)
        assert float(leg_d0.daily_pnl_cny) == pytest.approx(1000.0)

        # D1：qty=10，close=105 → mv=1050，prev=1000 → pnl=50
        leg_d1 = db.query(PositionDailyMark).filter_by(
            mark_date=D1, symbol="sh600519"
        ).first()
        assert float(leg_d1.market_value_cny) == pytest.approx(1050.0)
        assert float(leg_d1.daily_pnl_cny) == pytest.approx(50.0)

        # D2：qty=10+5=15（加仓后），close=110 → mv=1650，prev=1050 → pnl=600
        leg_d2 = db.query(PositionDailyMark).filter_by(
            mark_date=D2, symbol="sh600519"
        ).first()
        assert float(leg_d2.market_value_cny) == pytest.approx(1650.0)
        assert float(leg_d2.daily_pnl_cny) == pytest.approx(600.0)

    def test_forward_fill_on_holiday(self, db):
        """若某日无 K 线（休市），收盘价前向填充，leg pnl 应为 0。"""
        t1 = make_trade("STOCK_A", "sh600519", D0, "BUY", 100.0, 10, 0)
        db.add(t1)
        db.commit()

        # D1 无数据（休市），D2 有数据
        close_prices = {D0: 100.0, D2: 100.0}

        def fake_history(asset_type, symbol, start_str, end_str):
            return make_history(symbol, close_prices)

        with patch("app.pnl_engine.daily_pnl.get_history", side_effect=fake_history), \
             patch("app.pnl_engine.daily_pnl.preload_fx_rates"), \
             patch("app.pnl_engine.daily_pnl.get_fx_rate_for_asset", return_value=Decimal("1.0")):
            rebuild_daily_marks(db, D0, D2)

        # D1 前向填充 close=100，mv=1000，prev=1000 → pnl=0
        leg_d1 = db.query(PositionDailyMark).filter_by(
            mark_date=D1, symbol="sh600519"
        ).first()
        assert leg_d1 is not None
        assert float(leg_d1.market_value_cny) == pytest.approx(1000.0)
        assert float(leg_d1.daily_pnl_cny) == pytest.approx(0.0)

    def test_upsert_idempotent(self, db):
        """相同区间重算两次，结果应一致（upsert 不重复）。"""
        t1 = make_trade("STOCK_A", "sh600519", D0, "BUY", 100.0, 10, 0)
        db.add(t1)
        db.commit()

        def fake_history(asset_type, symbol, start_str, end_str):
            return make_history(symbol, {D0: 100.0, D1: 105.0})

        kwargs = dict(
            get_history=fake_history,
            preload_fx_rates=MagicMock(),
            get_fx_rate_for_asset=MagicMock(return_value=Decimal("1.0")),
        )
        with patch("app.pnl_engine.daily_pnl.get_history", side_effect=fake_history), \
             patch("app.pnl_engine.daily_pnl.preload_fx_rates"), \
             patch("app.pnl_engine.daily_pnl.get_fx_rate_for_asset", return_value=Decimal("1.0")):
            rebuild_daily_marks(db, D0, D1)
            rebuild_daily_marks(db, D0, D1)  # 重复重算

        total = db.query(PositionDailyMark).count()
        assert total == 2  # D0 + D1 各一行，无重复

    def test_hk_stock_fx_conversion(self, db):
        """港股 leg 的市值应乘以 HKD/CNY 汇率。"""
        t1 = make_trade("STOCK_HK", "00700", D0, "BUY", 300.0, 100, 0)
        db.add(t1)
        db.commit()

        def fake_history(asset_type, symbol, start_str, end_str):
            return make_history(symbol, {D0: 300.0})

        fx_rate = Decimal("0.92")

        with patch("app.pnl_engine.daily_pnl.get_history", side_effect=fake_history), \
             patch("app.pnl_engine.daily_pnl.preload_fx_rates"), \
             patch("app.pnl_engine.daily_pnl.get_fx_rate_for_asset", return_value=fx_rate):
            rebuild_daily_marks(db, D0, D0)

        leg = db.query(PositionDailyMark).filter_by(mark_date=D0, symbol="00700").first()
        assert leg is not None
        expected_mv = 300.0 * 100 * float(fx_rate)
        assert float(leg.market_value_cny) == pytest.approx(expected_mv)
        assert float(leg.fx_rate) == pytest.approx(float(fx_rate))


# ──────────────────────────────────────────────
# query_portfolio_daily_series 聚合测试
# ──────────────────────────────────────────────

class TestQueryPortfolioDailySeries:
    def _insert_marks(self, db, rows):
        for r in rows:
            mark = PositionDailyMark()
            mark.mark_date = r["date"]
            mark.asset_type = r.get("asset_type", "STOCK_A")
            mark.symbol = r["symbol"]
            mark.quantity_eod = Decimal(str(r["qty"]))
            mark.close_price_cny = Decimal(str(r["close"]))
            mark.fx_rate = Decimal("1.0")
            mark.market_value_cny = Decimal(str(r["mv"]))
            mark.daily_pnl_cny = Decimal(str(r["pnl"]))
            mark.daily_pnl_percent = r.get("pct")
            db.add(mark)
        db.commit()

    def test_aggregation_two_symbols(self, db):
        """两个标的同一天的 leg 应被加总为组合日盈亏。"""
        self._insert_marks(db, [
            {"date": D0, "symbol": "sh600519", "qty": 10, "close": 100, "mv": 1000, "pnl": 1000},
            {"date": D0, "symbol": "sh000001", "qty": 20, "close": 50, "mv": 1000, "pnl": 500},
        ])
        series = query_portfolio_daily_series(db, D0, D0)
        assert len(series) == 1
        row = series[0]
        assert float(row["market_value"]) == pytest.approx(2000.0)
        assert float(row["daily_pnl"]) == pytest.approx(1500.0)

    def test_cumulative_pnl_accumulates(self, db):
        """累计盈亏应为各日 daily_pnl 的逐日累加。"""
        self._insert_marks(db, [
            {"date": D0, "symbol": "sh600519", "qty": 10, "close": 100, "mv": 1000, "pnl": 100},
            {"date": D1, "symbol": "sh600519", "qty": 10, "close": 110, "mv": 1100, "pnl": 100},
            {"date": D2, "symbol": "sh600519", "qty": 10, "close": 90,  "mv": 900,  "pnl": -200},
        ])
        series = query_portfolio_daily_series(db, D0, D2)
        assert len(series) == 3
        assert float(series[0]["cumulative_pnl"]) == pytest.approx(100.0)
        assert float(series[1]["cumulative_pnl"]) == pytest.approx(200.0)
        assert float(series[2]["cumulative_pnl"]) == pytest.approx(0.0)

    def test_empty_range_returns_empty(self, db):
        """区间无数据应返回空列表。"""
        series = query_portfolio_daily_series(db, D0, D2)
        assert series == []
