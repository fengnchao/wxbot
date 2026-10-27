"""Validated, versioned relay settings; configuration carries no credentials."""
from dataclasses import asdict, dataclass, field
import hashlib
import math
import os
from pathlib import Path
import re
import tempfile
import tomllib

import tomlkit


class SettingsConflict(ValueError):
    """A writer used an obsolete settings version."""


@dataclass(frozen=True)
class Channel:
    key: str
    name: str
    username: str = ''
    chat_id: int = 0
    enabled: bool = False


@dataclass(frozen=True)
class RelaySettings:
    enabled: bool = False
    window_title: str = 'Telegram'
    bot_username: str = ''
    bot_id: int = 0
    poll_interval: float = 5.0
    include_images: bool = False
    include_text: bool = True
    include_source: bool = True
    include_time: bool = True
    first_run: str = 'baseline'
    image_failure_policy: str = 'hold'
    album_quiet_seconds: float = 2.0
    max_album_wait: float = 15.0
    admin_contacts: list[str] = field(default_factory=list)
    channels: list[Channel] = field(default_factory=list)
    desktop: dict[str, str] = field(default_factory=dict)


def _text(value, name, limit=256):
    if not isinstance(value, str) or len(value) > limit or any(ord(c) < 32 for c in value):
        raise ValueError('Invalid ' + name)
    return value.strip()


def _username(value, name):
    value = _text(value, name).lstrip('@')
    if value and not re.fullmatch(r'[A-Za-z][A-Za-z0-9_]{3,31}', value):
        raise ValueError('Invalid ' + name)
    return value


def validate(raw):
    defaults = asdict(RelaySettings())
    if not isinstance(raw, dict) or set(raw) - set(defaults):
        raise ValueError('Unknown relay settings fields')
    data = defaults | raw
    for key in ('enabled', 'include_images', 'include_text', 'include_source', 'include_time'):
        if type(data[key]) is not bool:
            raise ValueError('Invalid ' + key)
    if data['first_run'] != 'baseline' or data['image_failure_policy'] != 'hold':
        raise ValueError('Only baseline history and hold-on-image-failure are supported')
    data['window_title'] = _text(data['window_title'], 'window_title')
    data['bot_username'] = _username(data['bot_username'], 'bot_username')
    if type(data['bot_id']) is not int or not 0 <= data['bot_id'] <= 2**63 - 1:
        raise ValueError('Invalid bot_id')
    for key, low, high in (('poll_interval', .5, 3600), ('album_quiet_seconds', .1, 60), ('max_album_wait', .1, 300)):
        value = data[key]
        if type(value) not in (int, float) or not math.isfinite(value) or not low <= value <= high:
            raise ValueError('Invalid ' + key)
        data[key] = float(value)
    if data['max_album_wait'] < data['album_quiet_seconds']:
        raise ValueError('max_album_wait must cover album_quiet_seconds')
    admins = data['admin_contacts']
    if not isinstance(admins, list) or len(admins) > 100:
        raise ValueError('Invalid admin_contacts')
    data['admin_contacts'] = [_text(v, 'admin contact') for v in admins]
    if any(not v for v in data['admin_contacts']) or len(set(data['admin_contacts'])) != len(admins):
        raise ValueError('Empty or duplicate admin contact')
    desktop = data['desktop']
    if not isinstance(desktop, dict) or len(desktop) > 40:
        raise ValueError('Invalid desktop selectors')
    for key, value in desktop.items():
        if (not isinstance(key, str) or not re.fullmatch(r'[a-z][a-z0-9_]{0,63}', key)
                or any(word in key for word in ('token', 'secret', 'password', 'credential'))):
            raise ValueError('Invalid desktop selector key')
        _text(value, 'desktop selector', 512)
    data['desktop'] = dict(desktop)
    channels = data['channels']
    if not isinstance(channels, list) or len(channels) > 100:
        raise ValueError('Invalid channels')
    result, keys, identities = [], set(), set()
    for item in channels:
        if not isinstance(item, dict) or set(item) - {'key', 'name', 'username', 'chat_id', 'enabled'}:
            raise ValueError('Invalid channel fields')
        key = _text(item.get('key'), 'channel key', 64)
        name = _text(item.get('name'), 'channel name')
        username = _username(item.get('username', ''), 'channel username')
        chat_id, enabled = item.get('chat_id', 0), item.get('enabled', False)
        if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]{0,63}', key) or not name or key in keys:
            raise ValueError('Invalid or duplicate channel key/name')
        if type(chat_id) is not int or not -(2**63) < chat_id <= 0 or type(enabled) is not bool:
            raise ValueError('Invalid channel chat_id/enabled')
        if enabled and not (username or chat_id):
            raise ValueError('Enabled channel needs username or chat_id')
        channel_identities = ({('id', chat_id)} if chat_id else set()) | ({('username', username.lower())} if username else set())
        if channel_identities & identities:
            raise ValueError('Duplicate channel identity')
        keys.add(key)
        identities.update(channel_identities)
        result.append(Channel(key, name, username, chat_id, enabled))
    data['channels'] = result
    if data['enabled'] and not (data['window_title'] and data['bot_username'] and data['bot_id'] and any(c.enabled for c in result)):
        raise ValueError('Enabled relay needs window, current bot username/id and an identified channel')
    return RelaySettings(**data)


def load(path, missing_ok=True):
    try:
        content = Path(path).read_bytes()
    except FileNotFoundError:
        if missing_ok:
            return RelaySettings()
        raise
    return validate(tomllib.loads(content.decode('utf-8-sig')))


class Settings:
    def __init__(self, path, *, status_reader=None):
        self.path = Path(path)
        self.status_reader = status_reader

    def read(self):
        try:
            content = self.path.read_bytes()
        except FileNotFoundError:
            content = b''
        cfg = validate(tomllib.loads(content.decode('utf-8-sig'))) if content else RelaySettings()
        return asdict(cfg) | {'version': hashlib.sha256(content).hexdigest()}

    def status(self):
        result = self.read()
        result['runtime'] = self.status_reader() if self.status_reader else {'state': 'unavailable'}
        return result

    def update(self, payload, version):
        # Shared file lock also serializes dashboard and ToolService processes.
        from log.config_editor import config_lock
        with config_lock(self.path):
            current = self.read()
            if not isinstance(version, str) or version != current.pop('version'):
                raise SettingsConflict('Relay settings changed; refresh before saving')
            if not isinstance(payload, dict):
                raise ValueError('Relay settings must be an object')
            config = validate(current | payload)
            content = tomlkit.dumps(asdict(config)).encode('utf-8')
            self.path.parent.mkdir(parents=True, exist_ok=True)
            temporary = None
            try:
                with tempfile.NamedTemporaryFile(dir=self.path.parent, prefix='.' + self.path.name,
                                                 suffix='.tmp', delete=False) as fh:
                    temporary = Path(fh.name)
                    fh.write(content)
                    fh.flush()
                    os.fsync(fh.fileno())
                os.replace(temporary, self.path)
            finally:
                if temporary and temporary.exists():
                    temporary.unlink()
            return self.read()
