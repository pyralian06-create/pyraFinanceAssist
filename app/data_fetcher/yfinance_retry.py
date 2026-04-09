"""
Yahoo Finance（yfinance）易触发 Too Many Requests，对单次调用做指数退避重试。
"""

from __future__ import annotations

import logging
import time
from typing import Callable, TypeVar

logger = logging.getLogger(__name__)

T = TypeVar("T")

_MAX_RETRIES = 6
_BASE_DELAY_SEC = 2.0


def is_yahoo_rate_limited(exc: BaseException) -> bool:
    s = str(exc).lower()
    return (
        "rate limit" in s
        or "too many requests" in s
        or "429" in s
        or "expecting value" in s  # 偶发 JSON 空响应
    )


def run_with_backoff(label: str, fn: Callable[[], T]) -> T:
    """失败且疑似限流时指数退避重试，否则立即抛出。"""
    for attempt in range(_MAX_RETRIES):
        try:
            return fn()
        except Exception as e:
            if is_yahoo_rate_limited(e) and attempt < _MAX_RETRIES - 1:
                delay = _BASE_DELAY_SEC * (2**attempt)
                logger.warning(
                    f"⚠️ {label} Yahoo 限流/不稳定，{delay:.1f}s 后重试 "
                    f"({attempt + 1}/{_MAX_RETRIES}): {e}"
                )
                time.sleep(delay)
            else:
                raise
