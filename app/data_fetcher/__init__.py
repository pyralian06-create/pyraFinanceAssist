"""
数据接入模块 (Data Fetcher)

功能：系统的"数据泵"，负责与外部数据源打交道
- 多源路由：根据 asset_type 分发到不同的 AkShare 接口
- 实时行情：获取最新价、成交量等
- 历史 K 线：拉取日线/分钟线数据（可选）
- 统一接口：屏蔽 API 差异，向内部提供一致的数据结构

公开 API：
  from app.data_fetcher import get_quote, get_quote_batch, get_history
  from app.data_fetcher.schemas import QuoteData, HistoricalBar

使用示例：
  # 单个查询
  quote = get_quote('STOCK_A', 'sh600519')
  quote = get_quote('FUND', '510300')
  quote = get_quote('GOLD_SPOT', 'Au99.99')

  # 批量查询（持仓汇总时使用）
  positions = [('STOCK_A', 'sh600519'), ('FUND', '510300')]
  quotes = get_quote_batch(positions)

  # 历史数据
  bars = get_history('STOCK_A', 'sh600519', start_date='20250101', end_date='20251231')
"""

from .router import get_quote, get_quote_batch, get_history, get_quote_direct, get_quote_batch_direct
from .schemas import QuoteData, HistoricalBar

__all__ = [
    'get_quote',
    'get_quote_batch',
    'get_history',
    'get_quote_direct',
    'get_quote_batch_direct',
    'QuoteData',
    'HistoricalBar',
]
