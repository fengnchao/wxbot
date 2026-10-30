"""Local relay configuration editor; no lifecycle or delivery operations."""
import json
from pathlib import Path
import re
from urllib.error import HTTPError
from urllib.request import Request, HTTPRedirectHandler, ProxyHandler, build_opener

from butler.telegram_relay.settings import Settings


def read_status(path):
    """Read a bounded, credential-free snapshot published by wxbot."""
    path = Path(path)
    try:
        if path.stat().st_size > 262144:
            raise ValueError('Snapshot too large')
        raw = json.loads(path.read_text(encoding='utf-8'))
        if not isinstance(raw, dict):
            raise ValueError('Invalid snapshot')
        result = {key: raw[key] for key in ('enabled', 'current', 'counts', 'channels', 'at', 'phase', 'error') if key in raw}
        if type(raw.get('ui_hold')) is bool:
            result['ui_hold'] = raw['ui_hold']
        if isinstance(raw.get('tasks'), list):
            fields = ('id', 'channel', 'state', 'source_id', 'submitted', 'updated', 'error')
            result['tasks'] = [{key: task[key] for key in fields if key in task and
                                (task[key] is None or isinstance(task[key], (str, int, float, bool)))}
                               for task in raw['tasks'][:50] if isinstance(task, dict)]
        return result
    except FileNotFoundError:
        return {'state': 'unavailable'}
    except (OSError, ValueError, UnicodeError):
        return {'state': 'unavailable', 'error': '无法读取 Telegram 转发运行快照'}


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def request_resolution(config, payload):
    """Forward one explicit local review action; never send credentials to a redirect."""
    if (not isinstance(payload, dict) or set(payload) != {'id', 'action', 'acknowledge'} or
            not isinstance(payload.get('id'), str) or not (re.fullmatch(r'[a-f0-9]{32}', payload['id']) or payload['id'] == 'desktop') or
            payload.get('action') not in ('forwarded', 'retry', 'cancelled') or payload.get('acknowledge') is not True):
        return 400, {'error': '请明确确认任务 ID 和处置方式，并先核对 Telegram 残留窗口'}
    if payload['id'] == 'desktop' and payload['action'] == 'forwarded':
        return 400, {'error': '桌面界面核对不能标记为消息已转发'}
    server = config.get('server') or {}
    token = str(server.get('token') or '')
    if not token:
        return 503, {'error': 'Butler 管理凭据未配置'}

    def scrub(value):
        if isinstance(value, str):
            return value.replace(token, '[redacted]')
        if isinstance(value, dict):
            return {key: scrub(item) for key, item in value.items() if key.lower() not in ('token', 'authorization')}
        if isinstance(value, list):
            return [scrub(item) for item in value]
        return value

    try:
        port = int(server.get('port') or 8770)
        if not 1 <= port <= 65535:
            raise ValueError('Invalid port')
        request = Request('http://127.0.0.1:' + str(port) + '/v1/telegram-relay/resolve',
            data=json.dumps(payload, ensure_ascii=False).encode('utf-8'),
            headers={'Authorization': 'Bearer ' + token, 'Accept': 'application/json', 'Content-Type': 'application/json'})
        try:
            response = build_opener(ProxyHandler({}), _NoRedirect()).open(request, timeout=15)
        except HTTPError as exc:
            response = exc
        with response:
            result = json.loads(response.read(1 << 20).decode('utf-8'))
            if not isinstance(result, dict):
                raise ValueError('Invalid response')
            return response.status, scrub(result)
    except Exception as exc:
        return 503, {'error': 'Butler 转发核对暂不可用（' + type(exc).__name__ + '）'}


class TelegramRelayAdmin:
    def __init__(self, settings_path, status_path):
        self.settings = Settings(settings_path, status_reader=lambda: read_status(status_path))

    def read(self):
        data = self.settings.status()
        version, runtime = data.pop('version'), data.pop('runtime')
        return {'settings': data, 'version': version, 'runtime': runtime,
                'note': '保存由现有服务下次读取生效，不自动启动或重启。首次启用建立基线；结果不确定的任务保留待核对。'}

    def update(self, payload):
        if not isinstance(payload, dict) or set(payload) != {'settings', 'version'}:
            raise ValueError('需要 settings 和 version')
        self.settings.update(payload['settings'], payload['version'])
        return self.read()
