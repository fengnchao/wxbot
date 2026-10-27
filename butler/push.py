"""管家 → wxbot 外发：把一条主动推送投给 wxbot 的 8765 服务代发。

链路：Hermes cron → scripts/butler_push.py → butler POST /v1/push → 本函数
      → wxbot POST {wxbot_url}/send（X-Wxbot-Token）→ 主循环代发 → 微信用户。

契约与 wxbot/outbound.py、scripts/wxbot_deliver.py 完全一致：
  POST {cfg.wxbot_url}/send，头 X-Wxbot-Token，body {contact,text,wait:True,timeout}，响应 {ok}。
任何异常/超时都吞掉并如实返回 (False, 详情)，绝不把通道异常抛回主流程。
"""
from __future__ import annotations

import json
import urllib.error
import urllib.request

from common.media_bundle import validate_items, validate_request_id


def push_to_wxbot(cfg, contact: str, text: str, log=None) -> tuple[bool, str]:
    """把 text 投给 wxbot 代发给 contact（窗口标题）。返回 (ok, detail)。"""
    log = log or (lambda *a, **k: None)
    url = (cfg.wxbot_url or "").rstrip("/")
    if not url:
        return False, "wxbot_url 未配置"
    headers = {"Content-Type": "application/json"}
    if cfg.wxbot_token:
        headers["X-Wxbot-Token"] = cfg.wxbot_token
    timeout = float(cfg.wxbot_timeout or 120)
    body = {"contact": contact, "text": text, "wait": True, "timeout": timeout}
    req = urllib.request.Request(
        url + "/send",
        data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
        headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout + 15) as r:
            res = json.loads(r.read().decode("utf-8", "replace"))
            ok = bool(res.get("ok"))
            return ok, str(res.get("detail") or ("sent" if ok else f"HTTP {r.status}"))
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", "replace")[:200]
        log("wxbot 外发 HTTP %s: %s", e.code, detail)
        return False, f"HTTP {e.code}: {detail}"
    except Exception as e:
        log("wxbot 外发失败: %s: %s", type(e).__name__, e)
        return False, f"{type(e).__name__}: {e}"


def push_bundle_to_wxbot(cfg, contact, items, request_id, log=None):
    """Wait for every ordered item; never log payloads or transport secrets."""
    try:
        items = validate_items(items)
        validate_request_id(request_id)
        url = (cfg.wxbot_url or '').rstrip('/')
        if not url:
            return False, 'wxbot_url 未配置'
        timeout = float(cfg.wxbot_timeout or 120)
        headers = {'Content-Type': 'application/json'}
        if cfg.wxbot_token:
            headers['X-Wxbot-Token'] = cfg.wxbot_token
        request = urllib.request.Request(url + '/send-bundle',
            data=json.dumps({'contact': contact, 'items': items, 'request_id': request_id,
                             'wait': True, 'timeout': timeout}, ensure_ascii=False).encode('utf-8'),
            headers=headers, method='POST')
        with urllib.request.urlopen(request, timeout=timeout + 15) as response:
            result = json.loads(response.read().decode('utf-8'))
        ok = (isinstance(result, dict) and result.get('ok') is True
              and result.get('request_id') == request_id and result.get('contact') == contact)
        return ok, str(result.get('detail') or ('sent' if ok else '图文包回执未确认')) if isinstance(result, dict) else '图文包回执无效'
    except urllib.error.HTTPError as exc:
        return False, f'wxbot HTTP {exc.code}；图文包未确认'
    except Exception:
        return False, 'wxbot 图文包连接或回执异常；结果未知，不自动重发'
