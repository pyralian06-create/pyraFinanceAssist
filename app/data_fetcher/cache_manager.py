"""
缓存管理模块（简化版）

仅提供定时刷新功能，缓存永不清空。
支持从 ak 库 tqdm 进度条中捕获刷新进度（全局共享）。
"""

import logging
import threading
import time
import io
from datetime import datetime
from typing import Optional, Callable, Any, Dict
from app.config import settings

# 全局进度字典 + 锁（所有线程共享，HTTP 请求线程也能看到）
_progress_lock = threading.Lock()
_progress_map: Dict[str, str] = {}


class _StderrCapture(io.StringIO):
    """捕获 stderr 以提取 tqdm 进度条信息（全局共享）"""

    def __init__(self, cache_name: str, original_stderr):
        super().__init__()
        self.cache_name = cache_name
        self.original_stderr = original_stderr

    def write(self, s):
        """拦截 stderr 写入，提取进度信息（存到全局字典）"""
        if s:
            # tqdm 使用 \r（回车符）覆盖同一行，所以去掉 \r 后查看内容
            # 例如: "  7%|6         | 4/58 [00:32<07:22,  8.19s/it]\r"
            content = s.replace('\r', '').strip()

            if content:
                # 检查是否看起来像 tqdm 进度条
                # 特征：包含 % 和 | 和 /（百分比、进度条、计数）
                if '%' in content and '|' in content and '/' in content:
                    # 存储到全局进度字典（所有线程可见）
                    progress_text = content[:150]  # 限制长度
                    with _progress_lock:
                        _progress_map[self.cache_name] = progress_text

        # 同时写到原始 stderr（保持正常输出）
        self.original_stderr.write(s)
        return len(s)

    def flush(self):
        """刷新输出"""
        self.original_stderr.flush()

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

        # 保存原始 stderr，用进度捕获器替换
        import sys
        original_stderr = sys.stderr
        stderr_capture = _StderrCapture(self.name, original_stderr)
        sys.stderr = stderr_capture

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
            sys.stderr = original_stderr
            # 清理全局进度字典中该缓存的进度记录
            with _progress_lock:
                _progress_map.pop(self.name, None)
            with self._lock:
                self._refreshing = False
                self._refresh_start_time = None
