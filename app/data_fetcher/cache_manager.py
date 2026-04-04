"""
缓存管理模块（简化版）

仅提供定时刷新功能，缓存永不清空。
支持从 ak 库日志中捕获刷新进度。
"""

import logging
import threading
import time
from datetime import datetime
from typing import Optional, Callable, Any
from app.config import settings


class _ProgressCapture(logging.Handler):
    """捕获 ak 库日志以提取进度信息"""

    def __init__(self, cache_manager):
        super().__init__()
        self.cache_manager = cache_manager

    def emit(self, record):
        """捕获日志并更新进度"""
        try:
            msg = record.getMessage()
            # 从 ak 库和数据获取日志中提取关键进度信息
            if any(keyword in msg for keyword in ['正在', '获取', '加载', '完成', 'Processing', 'Fetching']):
                self.cache_manager._refresh_progress = msg[:200]  # 保留最近的日志（最多200字）
        except:
            pass

logger = logging.getLogger(__name__)


class CacheManager:
    """
    缓存管理器 - 定时刷新

    设计简化：
    - 启动时立即刷新
    - 定期刷新（配置化）
    - 失败时继续使用旧数据
    - 刷新过程可查询进度
    """

    def __init__(self, name: str):
        self.name = name
        self._data = None
        self._last_update_time = None
        self._lock = threading.Lock()
        self._load_func = None
        self._refreshing = False  # 防止并发刷新同一缓存
        self._refresh_start_time = None  # 刷新开始时间
        self._refresh_progress = ""  # 刷新过程中的进度信息

    def get_data(self) -> Optional[Any]:
        """获取缓存数据"""
        with self._lock:
            return self._data

    def get_update_time(self) -> Optional[datetime]:
        """获取缓存最后更新时间"""
        with self._lock:
            return self._last_update_time

    def get_status(self) -> dict:
        """
        获取缓存状态信息（无锁读取，查询不阻塞刷新）

        Returns:
            {
                "name": "缓存名称",
                "is_refreshing": bool,
                "last_update_time": ISO8601 时间或 None,
                "is_ready": bool,
                "elapsed_seconds": 刷新耗时（进行中才有值）,
                "progress": "刷新过程信息（如来自ak库的日志）"
            }
        """
        elapsed_seconds = None
        if self._refreshing and self._refresh_start_time:
            elapsed_seconds = round(time.time() - self._refresh_start_time, 1)

        return {
            "name": self.name,
            "is_refreshing": self._refreshing,
            "last_update_time": self._last_update_time.isoformat() if self._last_update_time else None,
            "is_ready": self._data is not None,
            "elapsed_seconds": elapsed_seconds,
            "progress": self._refresh_progress,
        }

    def set_load_func(self, load_func: Callable[[], Any]) -> None:
        """设置加载函数"""
        with self._lock:
            self._load_func = load_func

    def refresh_sync(self) -> None:
        """
        同步刷新缓存（在调用者线程执行，会阻塞）

        - 先检查是否已有刷新在进行，若有则跳过
        - 失败时保留旧数据，异常向上抛出
        - 捕获进度日志供状态查询使用
        """
        if self._load_func is None:
            logger.warning(f"⚠️ {self.name}未设置加载函数")
            return

        with self._lock:
            if self._refreshing:
                logger.warning(f"⚠️ {self.name}已在刷新中，跳过")
                return
            self._refreshing = True

        # 添加进度捕获器
        progress_handler = _ProgressCapture(self)
        akshare_logger = logging.getLogger("akshare")
        akshare_logger.addHandler(progress_handler)

        try:
            logger.info(f"🔄 {self.name}刷新中...")
            self._refresh_progress = ""
            self._refresh_start_time = time.time()

            data = self._load_func()  # 失败时异常向上抛出
            elapsed = time.time() - self._refresh_start_time

            with self._lock:
                self._data = data
                self._last_update_time = datetime.now()

            logger.info(f"✅ {self.name}刷新完成: {len(data) if hasattr(data, '__len__') else 'OK'}, 耗时 {elapsed:.1f}s")
        finally:
            akshare_logger.removeHandler(progress_handler)
            with self._lock:
                self._refreshing = False
                self._refresh_progress = ""
                self._refresh_start_time = None
