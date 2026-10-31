"""Validated per-contact, one-way HTTP message delivery."""
from dataclasses import dataclass
import math
from urllib.parse import urlsplit

import requests


@dataclass(frozen=True)
class MessageRoute:
    contact: str
    url: str
    code: str
    enabled: bool = True
    timeout: float = 10


def load_message_routes(rows) -> tuple[MessageRoute, ...]:
    if not isinstance(rows, list):
        raise ValueError('message_routes 必须是 JSON 数组 / TOML 表数组')
    routes, names = [], set()
    for index, row in enumerate(rows):
        prefix = f'message_routes[{index}]'
        if not isinstance(row, dict) or set(row) - {'contact', 'url', 'code', 'enabled', 'timeout'}:
            raise ValueError(prefix + ' 包含无效字段')
        for key in ('contact', 'url', 'code'):
            value = row.get(key)
            if (not isinstance(value, str) or not value.strip() or value != value.strip()
                    or any(ord(c) < 32 for c in value)):
                raise ValueError(prefix + '.' + key + ' 必须是非空、无首尾空格的单行文本')
        contact, url, code = row['contact'], row['url'], row['code']
        if len(contact) > 200 or contact in names:
            raise ValueError(prefix + '.contact 名称过长或重复')
        names.add(contact)
        try:
            parts = urlsplit(url)
            valid = (parts.scheme in {'http', 'https'} and bool(parts.hostname) and parts.port != 0
                     and not parts.username and not parts.password and not parts.fragment)
        except ValueError:
            valid = False
        if not valid:
            raise ValueError(prefix + '.url 必须是无内嵌凭据的 HTTP/HTTPS 接口地址')
        enabled, timeout = row.get('enabled', True), row.get('timeout', 10)
        if type(enabled) is not bool:
            raise ValueError(prefix + '.enabled 必须是布尔值')
        if type(timeout) not in (int, float) or not math.isfinite(timeout) or timeout <= 0:
            raise ValueError(prefix + '.timeout 必须是有限正数（秒）')
        routes.append(MessageRoute(contact, url, code, enabled, timeout))
    return tuple(routes)


class ForwardingError(Exception):
    def __init__(self, message, status=0):
        super().__init__(message)
        self.status = status


def _target(route: MessageRoute) -> str:
    parts = urlsplit(route.url)
    return f'{parts.hostname}:{parts.port or (443 if parts.scheme == "https" else 80)}'


def _failure_detail(exc: requests.RequestException) -> str:
    """最内层连接失败原因（errno/strerror）；不取异常文本，避免带出 URL 查询串。"""
    if isinstance(exc, requests.Timeout):
        return '连接未建立或超时'
    cause = exc.args[0] if exc.args else exc
    for _ in range(5):
        inner = getattr(cause, 'reason', None)
        if inner is None:
            break
        cause = inner
    code = getattr(cause, 'winerror', None) or getattr(cause, 'errno', None)
    text = getattr(cause, 'strerror', None) or type(cause).__name__
    return f'WinError {code}: {text}' if code else text


def forward_message(route: MessageRoute, text: str) -> int:
    """Only acknowledge 2xx headers; never follow redirects or consume a reply."""
    try:
        with requests.post(route.url, json={'code': route.code, 'text': text},
                           timeout=route.timeout, allow_redirects=False, stream=True) as response:
            if not 200 <= response.status_code < 300:
                raise ForwardingError(f'消息转发失败（HTTP {response.status_code}；目标 {_target(route)}）',
                                      response.status_code)
            return response.status_code
    except requests.RequestException as exc:
        raise ForwardingError(f'消息转发失败（{type(exc).__name__}；{_failure_detail(exc)}'
                              f'；目标 {_target(route)}）') from None
