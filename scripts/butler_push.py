#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Hermes cron → butler 投递脚本：把一条内容交给 butler，由 butler 记外发日志 + 转发 wxbot 代发。

链路：
  Hermes cron 到点触发 → 本脚本 POST butler /v1/push（Bearer server.token）
    → butler 记「外发」流水日志（看板 8788 可见）+ 转发
    → wxbot 8765 外发服务代发 → 微信用户收到

推送方式（--type）：
  1 = 指定用户发送（默认）：发给 --contact 指定的那个人
  2 = 群发：按 butler 的「用户分组」字典（messageType → 绑定用户，看板 8788 可维护）
      发给所有绑定该类型的用户；此时 --contact 可省略/忽略，--message-type 必填
消息类别（--message-type）：1 = 新闻消息  2 = 问候消息  3 = 其他

为什么是脚本而不是 Hermes 原生投递：Hermes 的 weixin 适配器是腾讯 iLink Bot API（云端、
有会话窗口限制），webhook 平台是入站用途；Hermes 没有「把 cron 输出 POST 到 butler 任意
URL」的原生 deliver 目标。所以由 Hermes cron 触发这个轻量投递脚本来落地「投给 butler」。

用法：
  butler_push.py --contact 101 --text "定时提醒内容"          # 指定用户发送（默认 type=1）
  butler_push.py --contact 101 --text -                       # 正文从 stdin 整段读（agent 生成的内容）
  butler_push.py --type 2 --message-type 1 --text -           # 群发：发给绑定「新闻消息」的用户们
  butler_push.py --contact 101 --text "..." --url http://127.0.0.1:8770 --token <server.token>

token 默认从项目根 config.butler.toml 的 [server].token 读；也可用 --token 或环境变量
BUTLER_TOKEN 覆盖。

退出码：0 = butler 回 {ok:true}（已发出）；非 0 = 失败（stderr 打 JSON 原因）。

—— Hermes 侧配置说明（不改 Hermes 代码，只在其 cron 里加一个任务）——
在 D:\\ai\\hermes 新建一个 cron 任务，其 delivery/no_agent 步骤以【绝对路径】调用本脚本，例如：
  D:\\work\\code\\wxbot\\.venv\\Scripts\\python.exe ^
    D:\\work\\code\\wxbot\\scripts\\butler_push.py --contact 101 --text -
正文可由 agent 任务生成后经 stdin 传入，或用 --text 固定模板。
"""
import argparse
import json
import os
import sys
import urllib.error
import urllib.request

try:
    import tomllib  # Python 3.11+
except ModuleNotFoundError:  # pragma: no cover
    import tomli as tomllib

HERE = os.path.dirname(os.path.abspath(__file__))          # ...\wxbot\scripts
ROOT = os.path.dirname(HERE)                                # ...\wxbot
BUTLER_CONF = os.path.join(ROOT, "config.butler.toml")
DEFAULT_URL = "http://127.0.0.1:8770"


def token_from_config():
    """从 config.butler.toml 的 [server].token 读；读不到返回空串。"""
    try:
        with open(BUTLER_CONF, "rb") as fh:
            raw = tomllib.load(fh)
        return str((raw.get("server") or {}).get("token") or "").strip()
    except Exception:
        return ""


def resolve_token(explicit):
    return (explicit or os.environ.get("BUTLER_TOKEN") or token_from_config()).strip()


def main():
    ap = argparse.ArgumentParser(description="把一条内容投给 butler（记外发日志 + 转发 wxbot 代发）")
    ap.add_argument("--contact", default="", help="目标微信窗口标题（type=1 必填；须在 wxbot 已打开为独立窗口）")
    ap.add_argument("--text", required=True, help="正文；填 - 则从 stdin 整段读")
    ap.add_argument("--type", type=int, default=1, choices=(1, 2),
                    help="1=指定用户发送（默认，发给 --contact）/ 2=群发（按 messageType 字典发给绑定用户）")
    ap.add_argument("--message-type", type=int, default=None, dest="message_type",
                    metavar="N", help="消息类别：1=新闻消息 2=问候消息 3=其他（群发必填）")
    ap.add_argument("--url", default=DEFAULT_URL, help=f"butler 地址（默认 {DEFAULT_URL}）")
    ap.add_argument("--token", default="", help="butler server.token（默认从 config.butler.toml 读）")
    ap.add_argument("--timeout", type=float, default=150, help="HTTP 超时秒（默认 150）")
    a = ap.parse_args()

    def fail(msg, code=2):
        print(json.dumps({"ok": False, "error": msg}, ensure_ascii=False), file=sys.stderr)
        return code

    if a.type == 1 and not a.contact.strip():
        return fail("type=1（指定用户发送）必须给 --contact")
    if a.type == 2 and a.message_type is None:
        return fail("type=2（群发）必须给 --message-type（1=新闻消息 2=问候消息 3=其他）")

    text = sys.stdin.read() if a.text == "-" else a.text
    text = (text or "").strip()
    if not text:
        return fail("缺少正文（--text 为空且 stdin 无内容）")

    token = resolve_token(a.token)
    if not token:
        return fail("butler server.token 未配置（config.butler.toml 或 --token）")

    url = a.url.rstrip("/") + "/v1/push"
    headers = {"Content-Type": "application/json", "Authorization": f"Bearer {token}"}
    body = {"text": text, "type": a.type}
    if a.contact.strip():
        body["contact"] = a.contact.strip()
    if a.message_type is not None:
        body["messageType"] = a.message_type
    req = urllib.request.Request(url, data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
                                 headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=a.timeout) as r:
            res = json.loads(r.read().decode("utf-8", "replace"))
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", "replace")[:300]
        print(json.dumps({"ok": False, "error": f"butler HTTP {e.code}: {detail}"},
                         ensure_ascii=False), file=sys.stderr)
        return 1
    except Exception as e:
        print(json.dumps({"ok": False, "error": f"butler 不可用: {type(e).__name__}: {e}"},
                         ensure_ascii=False), file=sys.stderr)
        return 1

    meta = res.get("meta") or {}
    if res.get("reply") is None and meta.get("ok"):
        out = {"ok": True, "type": meta.get("type", a.type), "detail": meta.get("detail", "sent")}
        if meta.get("contact"):
            out["contact"] = meta["contact"]
        if meta.get("targets") is not None:
            out["targets"] = meta["targets"]
        print(json.dumps(out, ensure_ascii=False))
        return 0
    print(json.dumps({"ok": False, "error": f"butler 返回: {res}"}, ensure_ascii=False),
          file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
