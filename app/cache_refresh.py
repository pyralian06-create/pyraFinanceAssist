"""
缓存刷新协调模块

提供全局刷新互斥锁和 do_full_refresh() 函数，
供 main.py（定时刷新）和 api/portfolio.py（手动刷新）共用。
"""

import logging
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed

from app.data_fetcher.stock_a import _cache_manager as stock_cache_manager
from app.data_fetcher.fund import _cache_etf, _cache_lof

logger = logging.getLogger(__name__)

# 手动和自动刷新共用的互斥锁
_refresh_lock = threading.Lock()


def do_full_refresh(source: str = "auto") -> None:
    """
    执行全量缓存刷新（A股 + ETF + LOF 并发刷新）

    Args:
        source: 触发来源 "auto" 或 "manual"，仅用于日志

    Raises:
        RuntimeError: 当前已有刷新任务运行中
    """
    acquired = _refresh_lock.acquire(blocking=False)
    if not acquired:
        raise RuntimeError("缓存刷新已在进行中")

    try:
        logger.info(f"🔄 [{source}] 开始全量缓存刷新...")

        with ThreadPoolExecutor(max_workers=3) as executor:
            futures = {
                executor.submit(stock_cache_manager.refresh_sync): "A股",
                executor.submit(_cache_etf.refresh_sync): "ETF",
                executor.submit(_cache_lof.refresh_sync): "LOF",
            }
            for future in as_completed(futures):
                name = futures[future]
                try:
                    future.result()
                except Exception as e:
                    logger.error(f"❌ [{source}] {name}刷新失败: {e}")

        logger.info(f"✅ [{source}] 全量缓存刷新完成")
    finally:
        _refresh_lock.release()
