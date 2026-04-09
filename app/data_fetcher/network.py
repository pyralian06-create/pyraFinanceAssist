"""
国内行情数据源网络策略

开启系统/全局 HTTP 代理时，国内站点（新浪、东方财富等）常被错误路由到境外节点导致失败；
而关闭代理时，yfinance（美股/港股）又可能无法访问。

解决：仅在调用 AkShare 国内接口的代码块内临时「直连」——
清除环境变量中的代理，并 monkeypatch urllib.request.getproxies，避免 macOS 注入系统代理。

已包裹：`stock_a`、`fund`、`gold`、汇率 `fx.currency_boc_safe`、全市场名录 `market_info` 同步等。
美股/港股 **行情**（yfinance）不使用此上下文，继续走系统代理。
"""

from __future__ import annotations

import os
import urllib.request
from contextlib import contextmanager
from typing import Dict, Iterator

_PROXY_ENV_KEYS = (
    "HTTP_PROXY",
    "HTTPS_PROXY",
    "http_proxy",
    "https_proxy",
    "ALL_PROXY",
    "all_proxy",
    "SOCKS_PROXY",
    "SOCKS5_PROXY",
    "socks_proxy",
    "socks5_proxy",
    "FTP_PROXY",
    "ftp_proxy",
)

_original_getproxies = urllib.request.getproxies


@contextmanager
def domestic_direct_connection() -> Iterator[None]:
    """
    临时关闭进程内代理，供 AkShare 国内数据源使用。
    退出后恢复环境变量与 getproxies 行为。
    """
    saved: Dict[str, str] = {}
    for k in _PROXY_ENV_KEYS:
        if k in os.environ:
            saved[k] = os.environ.pop(k)

    urllib.request.getproxies = lambda: {}
    try:
        yield
    finally:
        urllib.request.getproxies = _original_getproxies
        for k, v in saved.items():
            os.environ[k] = v
