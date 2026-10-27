"""Server-side authenticated user administration proxy; no browser credentials."""
import json
from urllib.error import HTTPError
from urllib.parse import urlsplit
from urllib.request import Request, HTTPRedirectHandler, ProxyHandler, build_opener


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None

def request_user_admin(config, path, payload=None):
    if urlsplit(path).path not in ('/v1/users', '/v1/users/memory', '/v1/users/audit'):
        return 400, {'error': '未知用户接口'}
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
        req = Request('http://127.0.0.1:' + str(int(server.get('port') or 8770)) + path,
            data=None if payload is None else json.dumps(payload, ensure_ascii=False).encode('utf-8'),
            headers={'Authorization': 'Bearer ' + token, 'Accept': 'application/json', 'Content-Type': 'application/json'})
        try:
            response = build_opener(ProxyHandler({}), _NoRedirect()).open(req, timeout=15)
        except HTTPError as exc:
            response = exc
        with response:
            body = response.read(8 << 20)
            result = json.loads(body.decode('utf-8'))
            if not isinstance(result, dict):
                raise ValueError('Invalid response')
            return response.status, scrub(result)
    except Exception as exc:
        return 503, {'error': 'Butler 用户管理暂不可用（' + type(exc).__name__ + '）'}
