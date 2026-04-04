"""
缓存管理模块（简化版）

仅提供定时刷新功能，缓存永不清空。
"""

import logging
import threading
import time
from datetime import datetime
from typing import Optional, Callable, Any
from app.config import settings

logger = logging.getLogger(__name__)


class CacheManager:
    """
    缓存管理器 - 定时刷新

    设计简化：
    - 启动时立即刷新
    - 定期刷新（配置化）
    - 失败时继续使用旧数据
    """

    def __init__(self, name: str):
        self.name = name
        self._data = None
        self._last_update_time = None
        self._lock = threading.Lock()
        self._load_func = None
        self._refreshing = False  # 防止并发刷新同一缓存

    def get_data(self) -> Optional[Any]:
        """获取缓存数据"""
        with self._lock:
            return self._data

    def get_update_time(self) -> Optional[datetime]:
        """获取缓存最后更新时间"""
        with self._lock:
            return self._last_update_time

    def set_load_func(self, load_func: Callable[[], Any]) -> None:
        """设置加载函数"""
        with self._lock:
            self._load_func = load_func

    def refresh_sync(self) -> None:
        """
        同步刷新缓存（在调用者线程执行，会阻塞）

        - 先检查是否已有刷新在进行，若有则跳过
        - 失败时保留旧数据，异常向上抛出
        """
        if self._load_func is None:
            logger.warning(f"⚠️ {self.name}未设置加载函数")
            return

        with self._lock:
            if self._refreshing:
                logger.warning(f"⚠️ {self.name}已在刷新中，跳过")
                return
            self._refreshing = True

        try:
            logger.info(f"🔄 {self.name}刷新中...")
            start_time = time.time()

            data = self._load_func()  # 失败时异常向上抛出
            elapsed = time.time() - start_time

            with self._lock:
                self._data = data
                self._last_update_time = datetime.now()

            logger.info(f"✅ {self.name}刷新完成: {len(data) if hasattr(data, '__len__') else 'OK'}, 耗时 {elapsed:.1f}s")
        finally:
            with self._lock:
                self._refreshing = False
