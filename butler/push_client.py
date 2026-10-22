"""Submit news to the existing Butler contract; unknown results never retry."""
import requests


def push_news(cfg, contact, text):
    if not cfg.token:
        return {'state': 'not_submitted', 'reason': 'Butler Token 未配置'}
    host = cfg.host
    if host in ('0.0.0.0', '::'):
        host = '127.0.0.1'
    if ':' in host and not host.startswith('['):
        host = '[' + host + ']'
    url = f'http://{host}:{cfg.port}/v1/push'
    try:
        with requests.Session() as session:
            session.trust_env = False
            response = session.post(url,
                json={'type': 1, 'messageType': 1, 'contact': contact, 'text': text},
                headers={'Authorization': 'Bearer ' + cfg.token},
                timeout=(5, max(150, float(cfg.wxbot_timeout or 120) + 30)), allow_redirects=False)
        if response.status_code in (400, 401, 403, 404):
            return {'state': 'not_submitted', 'reason': f'Butler 拒绝请求：HTTP {response.status_code}'}
        if not 200 <= response.status_code < 300:
            return {'state': 'uncertain', 'reason': f'HTTP {response.status_code}：结果未知，不自动重发'}
        response.raise_for_status()
        result = response.json()
        meta = result.get('meta') if isinstance(result, dict) else None
        if isinstance(meta, dict) and meta.get('ok') is True and meta.get('contact') == contact:
            return {'state': 'sent', 'reason': 'Butler 确认微信发送成功'}
        return {'state': 'uncertain', 'reason': 'Butler 未确认发送成功，请在收发队列核对'}
    except (requests.RequestException, ValueError) as exc:
        return {'state': 'uncertain', 'reason': type(exc).__name__ + '：结果未知，不自动重发'}
