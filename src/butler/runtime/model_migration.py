"""Explicit offline conversion of this installation's direct model configuration."""
from contextlib import ExitStack
from pathlib import Path
import secrets
import time

import tomlkit

from common.config_lock import config_lock
from butler.runtime.migration import _replace


def migrate_model_connection(root):
    root = Path(root).resolve()
    wx_path, bt_path = root / 'config.wxbot.toml', root / 'config.butler.toml'
    if not wx_path.exists():
        return {'changed': False}
    with ExitStack() as stack:
        for path in sorted((wx_path, bt_path)):
            stack.enter_context(config_lock(path))
        wx_bytes = wx_path.read_bytes()
        wx = tomlkit.parse(wx_bytes.decode('utf-8-sig'))
        mode = wx.get('installation', {}).get('mode', 'local')
        model = dict(wx.get('model', {}))
        if mode == 'external' or model.get('backend', 'butler') == 'butler':
            return {'changed': False}
        backend = model.get('backend')
        if backend not in {'hermes', 'openai', 'responses', 'openclaw', 'cursor', 'ollama', 'echo'}:
            raise ValueError('Unsupported direct backend; configuration was preserved')
        bt_bytes = bt_path.read_bytes()
        bt = tomlkit.parse(bt_bytes.decode('utf-8-sig'))
        if bt.get('model') and dict(bt['model']) != model:
            raise ValueError('Butler already has a different model configuration; resolve it before migrating')
        server = bt.setdefault('server', {})
        host, port = server.get('host', '127.0.0.1'), server.get('port', 8770)
        if host not in {'127.0.0.1', 'localhost'} or not isinstance(port, int) or isinstance(port, bool) or not 1 <= port <= 65535:
            raise ValueError('Local Butler requires a valid loopback listener')
        token = server.get('token') or secrets.token_urlsafe(32)
        server['token'] = token
        bt.setdefault('agent', {})['provider'] = backend
        bt['model'] = model
        wx.setdefault('installation', {})['mode'] = 'local'
        wx['model'] = {'backend': 'butler'}
        wx.setdefault('butler', {}).update(url=f'http://{host}:{port}', token=token)
        suffix = '.model-backup-' + str(time.time_ns())
        for path, body in ((wx_path, wx_bytes), (bt_path, bt_bytes)):
            with path.with_name(path.name + suffix).open('xb') as out:
                out.write(body)
        _replace(bt_path, tomlkit.dumps(bt))
        try:
            _replace(wx_path, tomlkit.dumps(wx))
        except BaseException:
            _replace(bt_path, bt_bytes.decode('utf-8-sig'))
            raise
    return {'changed': True, 'provider': backend, 'mode': 'local',
            'note': 'Configurations converted; services were not started. Keep backups private.'}
