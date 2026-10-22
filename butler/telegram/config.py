"""Strict, side-effect-free configuration; credentials never appear in repr."""
from dataclasses import dataclass, field
from pathlib import Path
import re
import tomllib


@dataclass(frozen=True)
class TelegramConfig:
    enabled: bool
    sources: tuple[str, ...]
    session_path: Path
    state_path: Path
    butler_config: Path
    api_id: int = field(repr=False)
    api_hash: str = field(repr=False)
    proxy: dict | None = field(default=None, repr=False)
    scan_interval: int = 10


def _int(value, name, low, high):
    if type(value) is not int or not low <= value <= high:
        raise ValueError(name + ' 超出允许范围')
    return value


def load(path, *, butler_config=None):
    path = Path(path).resolve()
    try:
        raw = tomllib.loads(path.read_text(encoding='utf-8-sig'))
    except (OSError, ValueError):
        raise ValueError('Telegram 配置不存在、不可读或格式无效') from None
    cfg = raw.get('telegram', {})
    if not isinstance(cfg, dict):
        raise ValueError('telegram 配置须为表')
    enabled = cfg.get('enabled', False)
    if type(enabled) is not bool:
        raise ValueError('enabled 须为布尔值')
    sources = cfg.get('sources', ['@zaobaosg'])
    if not isinstance(sources, list) or not sources:
        raise ValueError('sources 须为非空来源列表')
    normalized = []
    for source in sources:
        if not isinstance(source, str) or not re.fullmatch(r'@?[A-Za-z][A-Za-z0-9_]{3,31}', source):
            raise ValueError('来源须为 Telegram 公开用户名')
        normalized.append(source.lstrip('@').lower())
    def resolve(value):
        if not isinstance(value, str) or not value.strip():
            raise ValueError('路径不能为空')
        p = Path(value).expanduser()
        return (p if p.is_absolute() else path.parent / p).resolve()
    api_id = _int(cfg.get('api_id', 0), 'api_id', 0, 2147483647)
    api_hash = cfg.get('api_hash', '')
    if not isinstance(api_hash, str):
        raise ValueError('api_hash 须为字符串')
    proxy = None
    if 'proxy' in raw:
        p = raw['proxy']
        if not isinstance(p, dict) or p.get('type') not in ('socks5', 'socks4', 'http'):
            raise ValueError('proxy.type 须为 socks5 / socks4 / http')
        if not isinstance(p.get('host'), str) or not p['host'].strip():
            raise ValueError('代理地址不能为空')
        proxy = {'proxy_type': p['type'], 'addr': p['host'],
                 'port': _int(p.get('port'), 'proxy.port', 1, 65535), 'rdns': True}
        for key in ('username', 'password'):
            if key in p:
                if not isinstance(p[key], str):
                    raise ValueError('代理凭据格式无效')
                proxy[key] = p[key]
    return TelegramConfig(enabled, tuple(dict.fromkeys(normalized)),
        resolve(cfg.get('session', 'data/telegram/account')),
        resolve(cfg.get('state_dir', 'data/telegram')),
        Path(butler_config).resolve() if butler_config else resolve(cfg.get('butler_config', 'config.butler.toml')),
        api_id, api_hash, proxy, _int(cfg.get('scan_interval', 10), 'scan_interval', 1, 3600))
