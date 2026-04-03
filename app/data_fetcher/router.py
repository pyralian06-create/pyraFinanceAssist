"""
数据获取路由器 - 多资产统一入口

职责：
1. 根据 asset_type 路由到具体的数据获取模块（stock_a / fund / gold）
2. 提供批量获取能力，优化 API 调用（A股 / ETF 一次拉取全市场，供多个持仓共用）
3. 统一错误处理和日志记录

使用示例：
  from app.data_fetcher import get_quote, get_quote_batch

  # 单个查询
  quote = get_quote('STOCK_A', 'sh600519')
  quote = get_quote('FUND', '510300')
  quote = get_quote('GOLD_SPOT', 'Au99.99')

  # 批量查询（推荐用于持仓汇总）
  positions = [('STOCK_A', 'sh600519'), ('FUND', '510300'), ('GOLD_SPOT', 'Au99.99')]
  quotes = get_quote_batch(positions)
"""

import logging
from typing import List, Tuple, Dict, Optional
from decimal import Decimal

from . import stock_a, fund, gold
from .schemas import QuoteData, HistoricalBar

logger = logging.getLogger(__name__)


def get_quote(asset_type: str, symbol: str) -> QuoteData:
    """
    获取单个资产的实时行情

    Args:
        asset_type: 资产类型 ("STOCK_A" | "FUND" | "GOLD_SPOT")
        symbol: 资产代码

    Returns:
        QuoteData: 实时行情

    Raises:
        ValueError: 资产类型不支持或获取失败
    """
    asset_type = asset_type.upper()

    try:
        if asset_type == "STOCK_A":
            return stock_a.get_quote(symbol)
        elif asset_type == "FUND":
            return fund.get_quote(symbol)
        elif asset_type == "GOLD_SPOT":
            return gold.get_quote(symbol)
        else:
            raise ValueError(f"不支持的资产类型: {asset_type}")

    except Exception as e:
        logger.error(f"❌ 获取 {asset_type} {symbol} 失败: {e}")
        raise


def get_quote_batch(positions: List[Tuple[str, str]]) -> Dict[Tuple[str, str], QuoteData]:
    """
    批量获取多个资产的实时行情（优化 API 调用）

    批量查询的优势：
    - A股 / ETF / LOF / 开放式基金的 API 一次返回全市场
    - 多个持仓同时查询时，只调用一次 API，其他查询直接过滤缓存数据
    - 显著减少 API 调用次数和网络延迟

    Args:
        positions: [(asset_type, symbol), ...] 列表

    Returns:
        {(asset_type, symbol): QuoteData, ...} 字典

    Example:
        positions = [('STOCK_A', 'sh600519'), ('FUND', '510300'), ('GOLD_SPOT', 'Au99.99')]
        quotes = get_quote_batch(positions)
        for (asset_type, symbol), quote in quotes.items():
            print(f"{symbol}: {quote.current_price}")
    """
    results = {}

    # 按 asset_type 分组
    grouped = {}
    for asset_type, symbol in positions:
        asset_type = asset_type.upper()
        if asset_type not in grouped:
            grouped[asset_type] = []
        grouped[asset_type].append(symbol)

    # 逐组处理
    for asset_type, symbols in grouped.items():
        logger.info(f"🔄 批量查询 {asset_type}: {len(symbols)} 个")

        if asset_type == "STOCK_A":
            # 一次拉取全市场，过滤多个 symbols
            try:
                df = stock_a._get_spot_data_cached()
                for symbol in symbols:
                    try:
                        quote = stock_a.get_quote(symbol)
                        results[(asset_type, symbol)] = quote
                    except ValueError as e:
                        logger.warning(f"⚠️ 跳过 {symbol}: {e}")

            except Exception as e:
                logger.error(f"❌ {asset_type} 批量查询失败: {e}")
                for symbol in symbols:
                    results[(asset_type, symbol)] = None

        elif asset_type == "FUND":
            # ETF / LOF / 开放式基金 需要分别处理
            try:
                # 预加载缓存
                try:
                    fund._get_etf_data_cached()
                except:
                    pass
                try:
                    fund._get_lof_data_cached()
                except:
                    pass
                try:
                    fund._get_open_fund_data_cached()
                except:
                    pass

                for symbol in symbols:
                    try:
                        quote = fund.get_quote(symbol)
                        results[(asset_type, symbol)] = quote
                    except ValueError as e:
                        logger.warning(f"⚠️ 跳过基金 {symbol}: {e}")

            except Exception as e:
                logger.error(f"❌ FUND 批量查询失败: {e}")
                for symbol in symbols:
                    results[(asset_type, symbol)] = None

        elif asset_type == "GOLD_SPOT":
            # 黄金通常只有一个品种，但支持批量查询接口
            for symbol in symbols:
                try:
                    quote = gold.get_quote(symbol)
                    results[(asset_type, symbol)] = quote
                except ValueError as e:
                    logger.warning(f"⚠️ 跳过黄金 {symbol}: {e}")

        else:
            logger.warning(f"⚠️ 跳过不支持的资产类型: {asset_type}")

    return results


def get_history(
    asset_type: str,
    symbol: str,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None
) -> List[HistoricalBar]:
    """
    获取资产的历史 K线 / 净值数据

    Args:
        asset_type: 资产类型 ("STOCK_A" | "FUND" | "GOLD_SPOT")
        symbol: 资产代码
        start_date: 开始日期（YYYYMMDD 格式），可选
        end_date: 结束日期（YYYYMMDD 格式），可选

    Returns:
        List[HistoricalBar]: 历史 K线列表

    Raises:
        ValueError: 获取失败
    """
    asset_type = asset_type.upper()

    try:
        if asset_type == "STOCK_A":
            return stock_a.get_history(symbol, start_date, end_date)
        elif asset_type == "FUND":
            return fund.get_history(symbol, start_date, end_date)
        elif asset_type == "GOLD_SPOT":
            # 黄金无日期过滤参数
            return gold.get_history(symbol)
        else:
            raise ValueError(f"不支持的资产类型: {asset_type}")

    except Exception as e:
        logger.error(f"❌ 获取 {asset_type} {symbol} 历史数据失败: {e}")
        raise
