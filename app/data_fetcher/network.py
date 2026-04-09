"""
国内行情数据源网络策略

开启系统/全局 HTTP 代理时，国内站点（新浪、东方财富等）常被错误路由到境外节点导致失败；
而关闭代理时，yfinance（美股/港股）又可能无法访问。

解决：仅在调用 AkShare 国内接口的代码块内临时「直连」——
清除环境变量中的代理，并 monkeypatch urllib.request.getproxies，避免 macOS 注入系统代理。

已包裹：`stock_a`、`fund`、`gold`、汇率 `fx.currency_boc_safe`、全市场名录等。
港股/美股名录（东财 ``stock_*_spot_em``）在 ``market_info`` 中使用
``domestic_direct_connection(read_timeout=EASTMONEY_LIST_READ_TIMEOUT)`` 避免读超时。
美股/港股 **行情**（yfinance）不使用此上下文，继续走系统代理。
"""

from __future__ import annotations

import os
import urllib.request
from contextlib import contextmanager
from typing import Dict, Iterator, Optional

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

# AkShare 东财 stock_*_spot_em 全量名单等分页拉取耗时久，默认 read timeout=15 易失败
EASTMONEY_LIST_READ_TIMEOUT = 180.0
_CONNECT_TIMEOUT_SEC = 15.0


@contextmanager
def domestic_direct_connection(read_timeout: Optional[float] = None) -> Iterator[None]:
    """
    临时关闭进程内代理，供 AkShare 国内数据源使用。
    退出后恢复环境变量与 getproxies 行为。

    :param read_timeout: 若设置，会临时 monkeypatch ``requests.Session.request``，
        将 ``timeout`` 设为 ``(15, read_timeout)`` 秒，避免东财大列表接口 Read timed out。
        不传则不改 requests 超时（保持 AkShare 默认，多为 15s 读超时）。
    """
    saved: Dict[str, str] = {}
    for k in _PROXY_ENV_KEYS:
        if k in os.environ:
            saved[k] = os.environ.pop(k)

    urllib.request.getproxies = lambda: {}

    _orig_session_request = None
    if read_timeout is not None:
        import requests

        _orig_session_request = requests.Session.request

        def _session_request(self, method, url, **kwargs):  # type: ignore[no-untyped-def]
            kwargs["timeout"] = (_CONNECT_TIMEOUT_SEC, float(read_timeout))
            return _orig_session_request(self, method, url, **kwargs)

        requests.Session.request = _session_request  # type: ignore[method-assign]

    try:
        yield
    finally:
        if _orig_session_request is not None:
            import requests

            requests.Session.request = _orig_session_request  # type: ignore[method-assign]
        urllib.request.getproxies = _original_getproxies
        for k, v in saved.items():
            os.environ[k] = v
