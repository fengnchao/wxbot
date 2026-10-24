"""Local bot credentials are separate from personal Telegram API credentials."""
from dataclasses import dataclass, field
from pathlib import Path
import re
import tomllib

ROOT = Path(__file__).resolve().parents[2]
DEFAULT = ROOT / 'config.telegram-bot.toml'


@dataclass(frozen=True)
class Config:
    token: str = field(repr=False)
    allowed_users: tuple[int, ...]
    state_dir: Path
    butler_config: Path
    proxy_url: str = field(default='', repr=False)


def load(path=DEFAULT):
    path = Path(path).resolve()
    raw = tomllib.loads(path.read_text(encoding='utf-8-sig'))['telegram_bot']
    token = raw.get('token', '').strip()
    if not re.fullmatch(r'[0-9]+:[A-Za-z0-9_-]{20,}', token):
        raise ValueError('请在 config.telegram-bot.toml 填写新的 Bot Token')
    users = raw.get('allowed_user_ids', [])
    if not isinstance(users, list) or any(type(x) is not int or x <= 0 for x in users):
        raise ValueError('allowed_user_ids 必须是正整数列表')
    def resolve(value):
        return (path.parent / value).resolve()
    proxy = raw.get('proxy_url', '')
    if not isinstance(proxy, str) or (proxy and not proxy.startswith(('http://', 'https://'))):
        raise ValueError('proxy_url 仅支持 HTTP/HTTPS 代理')
    return Config(token, tuple(users), resolve(raw.get('state_dir', 'data/telegram-bot')),
                  resolve(raw.get('butler_config', 'config.butler.toml')), proxy)
