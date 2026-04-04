"""
缓存管理模块（简化版）

仅提供定时刷新功能，缓存永不清空。
支持从 ak 库 tqdm 进度条中捕获刷新进度（全局共享）。
"""

import logging
import sys
import threading
import time
from datetime import datetime
from typing import Optional, Callable, Any, Dict
from app.config import settings

# 全局进度字典 + 锁（所有线程共享，HTTP 请求线程也能看到）
_progress_lock = threading.Lock()
_progress_map: Dict[str, str] = {}

# 线程ID → cache_name 映射，供分发代理使用
_thread_cache_map: Dict[int, str] = {}
_thread_cache_lock = threading.Lock()


class _DispatchingStderr:
    """
    全局 stderr 分发代理（替换 sys.stderr 一次）

    根据 threading.current_thread().ident 将 tqdm 输出路由到对应的 cache_name，
    解决多线程并发刷新时 sys.stderr 被覆盖导致进度混用的问题。
    """

    def __init__(self, original_stderr):
        self._original = original_stderr

    def write(self, s):
        if s:
            thread_id = threading.current_thread().ident
            with _thread_cache_lock:
                cache_name = _thread_cache_map.get(thread_id)

            if cache_name:
                content = s.replace('\r', '').strip()
                if content and '%' in content and '|' in content and '/' in content:
                    with _progress_lock:
                        _progress_map[cache_name] = content[:150]

        self._original.write(s)
        return len(s)

    def flush(self):
        self._original.flush()

    def fileno(self):
        return self._original.fileno()


# 安装全局分发代理（模块加载时执行一次）
_original_stderr = sys.stderr
if not isinstance(sys.stderr, _DispatchingStderr):
    sys.stderr = _DispatchingStderr(_original_stderr)

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
                "progress": "tqdm 进度条（全局共享）"
            }
        """
        elapsed_seconds = None
        if self._refreshing and self._refresh_start_time:
            elapsed_seconds = round(time.time() - self._refresh_start_time, 1)

        # 从全局进度字典获取进度（所有线程可见）
        progress = ""
        with _progress_lock:
            progress = _progress_map.get(self.name, "")

        return {
            "name": self.name,
            "is_refreshing": self._refreshing,
            "last_update_time": self._last_update_time.isoformat() if self._last_update_time else None,
            "is_ready": self._data is not None,
            "elapsed_seconds": elapsed_seconds,
            "progress": progress,
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
        - 捕获 tqdm 进度条供状态查询使用（全局共享，HTTP 请求线程可见）
        """
        if self._load_func is None:
            logger.warning(f"⚠️ {self.name}未设置加载函数")
            return

        with self._lock:
            if self._refreshing:
                logger.warning(f"⚠️ {self.name}已在刷新中，跳过")
                return
            self._refreshing = True

        # 注册当前线程 → cache_name 映射，供全局分发代理路由进度
        thread_id = threading.current_thread().ident
        with _thread_cache_lock:
            _thread_cache_map[thread_id] = self.name

        try:
            logger.info(f"🔄 {self.name}刷新中...")
            self._refresh_start_time = time.time()

            data = self._load_func()  # 失败时异常向上抛出
            elapsed = time.time() - self._refresh_start_time

            with self._lock:
                self._data = data
                self._last_update_time = datetime.now()

            logger.info(f"✅ {self.name}刷新完成: {len(data) if hasattr(data, '__len__') else 'OK'}, 耗时 {elapsed:.1f}s")
        finally:
            # 清理线程映射和进度记录
            with _thread_cache_lock:
                _thread_cache_map.pop(thread_id, None)
            with _progress_lock:
                _progress_map.pop(self.name, None)
            with self._lock:
                self._refreshing = False
                self._refresh_start_time = None
