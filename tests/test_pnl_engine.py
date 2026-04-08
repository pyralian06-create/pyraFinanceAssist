"""
PnL 计算引擎单元测试

测试加权平均成本法的正确性和边界情况处理
"""

import pytest
from datetime import datetime, timedelta
from decimal import Decimal
from unittest.mock import patch, MagicMock

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session

from app.models.database import Base
from app.models.trade import Trade
from app.pnl_engine import calculate_portfolio
from app.schemas.portfolio import PositionDetail, PortfolioSummary
from app.data_fetcher.schemas import QuoteData


@pytest.fixture
def test_db():
    """创建内存数据库用于测试"""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine)
    db = SessionLocal()
    yield db
    db.close()


@pytest.fixture
def mock_quote_data():
    """创建模拟行情数据"""
    def _create_quote(symbol: str, current_price: Decimal) -> QuoteData:
        return QuoteData(
            symbol=symbol,
            name=f"Mock {symbol}",
            current_price=current_price,
            previous_close=current_price - Decimal('1'),
            change_amount=Decimal('1'),
            change_pct=0.5,
            volume=1000000.0,
            timestamp=datetime.now(),
            asset_type="STOCK_A"
        )
    return _create_quote


class TestBasicTrades:
    """基础交易场景测试"""

    def test_empty_portfolio(self, test_db):
        """测试无交易时返回全零持仓汇总"""
        result = calculate_portfolio(test_db)

        assert result.total_assets == Decimal('0')
        assert result.total_pnl == Decimal('0')
        assert result.realized_pnl == Decimal('0')
        assert len(result.positions) == 0
        assert result.total_pnl_percent == "+0.00%"

    def test_single_buy(self, test_db, mock_quote_data):
        """测试单个买入交易"""
        # 记录交易：买入 100 股，单价 100，手续费 50
        trade = Trade(
            asset_type="STOCK_A",
            symbol="sh600519",
            trade_date=datetime.now(),
            trade_type="BUY",
            price=Decimal('100'),
            quantity=Decimal('100'),
            commission=Decimal('50')
        )
        test_db.add(trade)
        test_db.commit()

        # Mock 行情数据：当前价 110
        with patch('app.pnl_engine.calculator.get_quote_batch_direct') as mock_quotes:
            mock_quotes.return_value = {
                ('STOCK_A', 'sh600519'): mock_quote_data('sh600519', Decimal('110'))
            }

            result = calculate_portfolio(test_db)

        # 验证
        assert len(result.positions) == 1
        pos = result.positions[0]
        assert pos.symbol == 'sh600519'
        assert pos.holding_quantity == Decimal('100')
        assert pos.avg_cost == Decimal('100.5')  # (100*100 + 50) / 100
        assert pos.current_price == Decimal('110')
        assert pos.floating_pnl == Decimal('950')  # (110 - 100.5) * 100
        assert "+9.45%" in pos.pnl_percent  # 950 / 10050 * 100

    def test_buy_and_sell(self, test_db, mock_quote_data):
        """测试买入和卖出（计算已实现盈亏）"""
        trades = [
            # 买入 100 股 @ 100
            Trade(
                asset_type="STOCK_A",
                symbol="sh600519",
                trade_date=datetime.now(),
                trade_type="BUY",
                price=Decimal('100'),
                quantity=Decimal('100'),
                commission=Decimal('50')
            ),
            # 卖出 50 股 @ 120
            Trade(
                asset_type="STOCK_A",
                symbol="sh600519",
                trade_date=datetime.now() + timedelta(days=1),
                trade_type="SELL",
                price=Decimal('120'),
                quantity=Decimal('50'),
                commission=Decimal('25')
            ),
        ]
        for trade in trades:
            test_db.add(trade)
        test_db.commit()

        # Mock 行情：当前价 125，剩余 50 股
        with patch('app.pnl_engine.calculator.get_quote_batch_direct') as mock_quotes:
            mock_quotes.return_value = {
                ('STOCK_A', 'sh600519'): mock_quote_data('sh600519', Decimal('125'))
            }

            result = calculate_portfolio(test_db)

        # 验证
        assert len(result.positions) == 1
        pos = result.positions[0]
        assert pos.holding_quantity == Decimal('50')  # 100 - 50

        # 平均成本计算
        # 卖出 50 股：realized_pnl = (120 - 100.5) * 50 - 25 = 975 - 25 = 950
        assert result.realized_pnl == Decimal('950')

        # 剩余 50 股的浮动盈亏
        # avg_cost = (100*100 + 50 - 100.5*50) / 50 = (10000 + 50 - 5025) / 50 = 5025 / 50 = 100.5
        # floating_pnl = (125 - 100.5) * 50 = 1225
        assert pos.floating_pnl == Decimal('1225')

    def test_dividend(self, test_db, mock_quote_data):
        """测试分红处理"""
        trades = [
            # 买入 100 股
            Trade(
                asset_type="STOCK_A",
                symbol="sh600519",
                trade_date=datetime.now(),
                trade_type="BUY",
                price=Decimal('100'),
                quantity=Decimal('100'),
                commission=Decimal('50')
            ),
            # 分红：每股 2 元，总共 200 元
            Trade(
                asset_type="STOCK_A",
                symbol="sh600519",
                trade_date=datetime.now() + timedelta(days=30),
                trade_type="DIVIDEND",
                price=Decimal('2'),
                quantity=Decimal('100'),
                commission=Decimal('0')
            ),
        ]
        for trade in trades:
            test_db.add(trade)
        test_db.commit()

        with patch('app.pnl_engine.calculator.get_quote_batch_direct') as mock_quotes:
            mock_quotes.return_value = {
                ('STOCK_A', 'sh600519'): mock_quote_data('sh600519', Decimal('100'))
            }

            result = calculate_portfolio(test_db)

        # 分红应记入已实现盈亏
        assert result.realized_pnl == Decimal('200')
        # 持仓不变
        assert len(result.positions) == 1
        assert result.positions[0].holding_quantity == Decimal('100')


class TestWeightedAverageCost:
    """加权平均成本法测试"""

    def test_weighted_average_cost_calculation(self, test_db, mock_quote_data):
        """测试加权平均成本的正确性"""
        trades = [
            # 买入 100 股 @ 100
            Trade(
                asset_type="STOCK_A",
                symbol="sh600519",
                trade_date=datetime.now(),
                trade_type="BUY",
                price=Decimal('100'),
                quantity=Decimal('100'),
                commission=Decimal('0')
            ),
            # 买入 100 股 @ 110
            Trade(
                asset_type="STOCK_A",
                symbol="sh600519",
                trade_date=datetime.now() + timedelta(days=1),
                trade_type="BUY",
                price=Decimal('110'),
                quantity=Decimal('100'),
                commission=Decimal('0')
            ),
        ]
        for trade in trades:
            test_db.add(trade)
        test_db.commit()

        with patch('app.pnl_engine.calculator.get_quote_batch_direct') as mock_quotes:
            mock_quotes.return_value = {
                ('STOCK_A', 'sh600519'): mock_quote_data('sh600519', Decimal('120'))
            }

            result = calculate_portfolio(test_db)

        # 验证加权平均成本
        pos = result.positions[0]
        assert pos.holding_quantity == Decimal('200')
        # avg_cost = (100*100 + 110*100) / 200 = 21000 / 200 = 105
        assert pos.avg_cost == Decimal('105')
        assert pos.floating_pnl == Decimal('3000')  # (120 - 105) * 200

    def test_multiple_assets(self, test_db, mock_quote_data):
        """测试多个资产的组合持仓"""
        trades = [
            # A 股：sh600519
            Trade(
                asset_type="STOCK_A",
                symbol="sh600519",
                trade_date=datetime.now(),
                trade_type="BUY",
                price=Decimal('100'),
                quantity=Decimal('100'),
                commission=Decimal('0')
            ),
            # 基金：510300
            Trade(
                asset_type="FUND",
                symbol="510300",
                trade_date=datetime.now(),
                trade_type="BUY",
                price=Decimal('3.5'),
                quantity=Decimal('1000'),
                commission=Decimal('0')
            ),
        ]
        for trade in trades:
            test_db.add(trade)
        test_db.commit()

        with patch('app.pnl_engine.calculator.get_quote_batch_direct') as mock_quotes:
            mock_quotes.return_value = {
                ('STOCK_A', 'sh600519'): mock_quote_data('sh600519', Decimal('110')),
                ('FUND', '510300'): mock_quote_data('510300', Decimal('3.7')),
            }

            result = calculate_portfolio(test_db)

        # 验证两个持仓
        assert len(result.positions) == 2

        # 总资产 = 100*110 + 1000*3.7 = 11000 + 3700 = 14700
        assert result.total_assets == Decimal('14700')

        # 总浮盈 = (110-100)*100 + (3.7-3.5)*1000 = 1000 + 200 = 1200
        assert result.total_pnl == Decimal('1200')


class TestQuoteFallback:
    """行情失败降级测试"""

    def test_quote_failure_fallback(self, test_db):
        """测试行情拉取失败时使用平均成本降级"""
        trade = Trade(
            asset_type="STOCK_A",
            symbol="sh600519",
            trade_date=datetime.now(),
            trade_type="BUY",
            price=Decimal('100'),
            quantity=Decimal('100'),
            commission=Decimal('0')
        )
        test_db.add(trade)
        test_db.commit()

        # Mock 返回 None（行情拉取失败）
        with patch('app.pnl_engine.calculator.get_quote_batch_direct') as mock_quotes:
            mock_quotes.return_value = {
                ('STOCK_A', 'sh600519'): None
            }

            result = calculate_portfolio(test_db)

        # 应该降级为使用平均成本
        pos = result.positions[0]
        assert pos.current_price == Decimal('100')  # 等于平均成本
        assert pos.floating_pnl == Decimal('0')  # 无浮动盈亏

    def test_partial_quote_failure(self, test_db, mock_quote_data):
        """测试部分行情失败"""
        trades = [
            Trade(
                asset_type="STOCK_A",
                symbol="sh600519",
                trade_date=datetime.now(),
                trade_type="BUY",
                price=Decimal('100'),
                quantity=Decimal('100'),
                commission=Decimal('0')
            ),
            Trade(
                asset_type="STOCK_A",
                symbol="sh000001",
                trade_date=datetime.now(),
                trade_type="BUY",
                price=Decimal('50'),
                quantity=Decimal('200'),
                commission=Decimal('0')
            ),
        ]
        for trade in trades:
            test_db.add(trade)
        test_db.commit()

        # 只返回一个行情
        with patch('app.pnl_engine.calculator.get_quote_batch_direct') as mock_quotes:
            mock_quotes.return_value = {
                ('STOCK_A', 'sh600519'): mock_quote_data('sh600519', Decimal('120')),
                ('STOCK_A', 'sh000001'): None,  # 失败
            }

            result = calculate_portfolio(test_db)

        assert len(result.positions) == 2

        # sh600519 有行情
        pos1 = next(p for p in result.positions if p.symbol == 'sh600519')
        assert pos1.current_price == Decimal('120')
        assert pos1.floating_pnl == Decimal('2000')

        # sh000001 无行情，使用平均成本
        pos2 = next(p for p in result.positions if p.symbol == 'sh000001')
        assert pos2.current_price == Decimal('50')
        assert pos2.floating_pnl == Decimal('0')


class TestAssetTypeFilter:
    """资产类型过滤测试"""

    def test_filter_by_asset_type(self, test_db, mock_quote_data):
        """测试按资产类型过滤持仓"""
        trades = [
            Trade(
                asset_type="STOCK_A",
                symbol="sh600519",
                trade_date=datetime.now(),
                trade_type="BUY",
                price=Decimal('100'),
                quantity=Decimal('100'),
                commission=Decimal('0')
            ),
            Trade(
                asset_type="FUND",
                symbol="510300",
                trade_date=datetime.now(),
                trade_type="BUY",
                price=Decimal('3.5'),
                quantity=Decimal('1000'),
                commission=Decimal('0')
            ),
        ]
        for trade in trades:
            test_db.add(trade)
        test_db.commit()

        # 只查询 A 股
        with patch('app.pnl_engine.calculator.get_quote_batch_direct') as mock_quotes:
            mock_quotes.return_value = {
                ('STOCK_A', 'sh600519'): mock_quote_data('sh600519', Decimal('110')),
            }

            result = calculate_portfolio(test_db, asset_type_filter='STOCK_A')

        # 只返回 A 股
        assert len(result.positions) == 1
        assert result.positions[0].asset_type == 'STOCK_A'
        assert result.total_assets == Decimal('11000')  # 100 * 110

        # 查询基金
        with patch('app.pnl_engine.calculator.get_quote_batch_direct') as mock_quotes:
            mock_quotes.return_value = {
                ('FUND', '510300'): mock_quote_data('510300', Decimal('3.7')),
            }

            result = calculate_portfolio(test_db, asset_type_filter='FUND')

        assert len(result.positions) == 1
        assert result.positions[0].asset_type == 'FUND'
        assert result.total_assets == Decimal('3700')  # 1000 * 3.7


class TestEdgeCases:
    """边界情况测试"""

    def test_zero_commission(self, test_db, mock_quote_data):
        """测试无手续费的情况"""
        trade = Trade(
            asset_type="STOCK_A",
            symbol="sh600519",
            trade_date=datetime.now(),
            trade_type="BUY",
            price=Decimal('100'),
            quantity=Decimal('100'),
            commission=Decimal('0')
        )
        test_db.add(trade)
        test_db.commit()

        with patch('app.pnl_engine.calculator.get_quote_batch_direct') as mock_quotes:
            mock_quotes.return_value = {
                ('STOCK_A', 'sh600519'): mock_quote_data('sh600519', Decimal('110'))
            }

            result = calculate_portfolio(test_db)

        pos = result.positions[0]
        assert pos.avg_cost == Decimal('100')  # 无手续费
        assert pos.floating_pnl == Decimal('1000')  # (110-100)*100

    def test_fractional_quantity(self, test_db, mock_quote_data):
        """测试小数股份（基金、黄金）"""
        trade = Trade(
            asset_type="FUND",
            symbol="005827",
            trade_date=datetime.now(),
            trade_type="BUY",
            price=Decimal('1.456'),
            quantity=Decimal('1030.21'),  # 小数份额
            commission=Decimal('1.5')
        )
        test_db.add(trade)
        test_db.commit()

        with patch('app.pnl_engine.calculator.get_quote_batch_direct') as mock_quotes:
            mock_quotes.return_value = {
                ('FUND', '005827'): mock_quote_data('005827', Decimal('1.5'))
            }

            result = calculate_portfolio(test_db)

        pos = result.positions[0]
        assert pos.holding_quantity == Decimal('1030.21')
        # avg_cost = (1.456 * 1030.21 + 1.5) / 1030.21
        expected_cost = (Decimal('1.456') * Decimal('1030.21') + Decimal('1.5')) / Decimal('1030.21')
        assert abs(pos.avg_cost - expected_cost) < Decimal('0.0001')

    def test_large_numbers(self, test_db, mock_quote_data):
        """测试大数字处理（精度）"""
        trade = Trade(
            asset_type="STOCK_A",
            symbol="sh000001",
            trade_date=datetime.now(),
            trade_type="BUY",
            price=Decimal('50000'),
            quantity=Decimal('1000'),
            commission=Decimal('100000')
        )
        test_db.add(trade)
        test_db.commit()

        with patch('app.pnl_engine.calculator.get_quote_batch_direct') as mock_quotes:
            mock_quotes.return_value = {
                ('STOCK_A', 'sh000001'): mock_quote_data('sh000001', Decimal('55000'))
            }

            result = calculate_portfolio(test_db)

        pos = result.positions[0]
        # avg_cost = (50000 * 1000 + 100000) / 1000 = 50100
        assert pos.avg_cost == Decimal('50100')
        # floating_pnl = (55000 - 50100) * 1000 = 4900000
        assert pos.floating_pnl == Decimal('4900000')
        assert result.total_assets == Decimal('55000000')  # 55000 * 1000
