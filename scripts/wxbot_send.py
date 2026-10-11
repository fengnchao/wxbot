#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把一条消息经 wxbot 发到微信（走 UI 自动化，不受 iLink 会话窗口限制）。

用法：
  wxbot_send.py --profile <profile_id> --text "要发的内容"        # 等发出为止
  wxbot_send.py --profile <profile_id> --to "101" --text "..."   # 直接指定联系人
  wxbot_send.py --status                                          # 看通道配置与 wxbot 是否在线

退出码：0 = 已发出；1 = 失败（调用方应回退到别的通道）。

配置文件 scripts/wxbot_channel.json：
{
  "url": "http://127.0.0.1:8765",
  "token": "<与 wxbot config.toml 的 [outbound].token 相同>",
  "timeout": 90,
  "profile_to_contact": { "<profile_id>": "<微信窗口标题>" }
}
"""
import argparse
import io
import json
import os
import sys
import urllib.error
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
CONF = os.path.join(HERE, "wxbot_channel.json")


def load_conf():
    if not os.path.exists(CONF):
        return {}
    try:
        return json.load(io.open(CONF, encoding="utf-8"))
    except Exception as e:
        print(f"配置文件读取失败 {CONF}: {e}", file=sys.stderr)
        return {}


def contact_for(conf, profile, explicit=None):
    if explicit:
        return explicit
    return (conf.get("profile_to_contact") or {}).get(profile, "")


def post(conf, contact, text, timeout=None):
    url = str(conf.get("url", "http://127.0.0.1:8765")).rstrip("/")
    tok = str(conf.get("token", "") or "")
    headers = {"Content-Type": "application/json"}
    if tok:
        headers["X-Wxbot-Token"] = tok
    body = {"contact": contact, "text": text, "wait": True,
            "timeout": float(timeout or conf.get("timeout") or 90)}
    req = urllib.request.Request(url + "/send",
                                 data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
                                 headers=headers, method="POST")
    with urllib.request.urlopen(req, timeout=float(timeout or conf.get("timeout") or 90) + 10) as r:
        return r.status, json.loads(r.read().decode("utf-8", "replace"))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--profile", default="")
    ap.add_argument("--to", default="")
    ap.add_argument("--text", default="")
    ap.add_argument("--timeout", type=float, default=0)
    ap.add_argument("--status", action="store_true")
    a = ap.parse_args()

    conf = load_conf()
    if a.status:
        print(f"配置文件: {CONF}（{'存在' if os.path.exists(CONF) else '不存在'}）")
        print(f"  url   = {conf.get('url')}")
        print(f"  token = {'已设置' if conf.get('token') else '未设置'}")
        print(f"  映射  = {conf.get('profile_to_contact')}")
        try:
            req = urllib.request.Request(str(conf.get("url", "")).rstrip("/") + "/health",
                                         headers={"X-Wxbot-Token": str(conf.get("token", ""))})
            with urllib.request.urlopen(req, timeout=5) as r:
                print(f"  wxbot = 在线 {r.read().decode()}")
        except Exception as e:
            print(f"  wxbot = 不在线（{type(e).__name__}: {e}）")
        return 0

    if not a.text:
        print("缺少 --text", file=sys.stderr)
        return 1
    contact = contact_for(conf, a.profile, a.to or None)
    if not contact:
        print(f"没有为 profile {a.profile!r} 配联系人（scripts/wxbot_channel.json）", file=sys.stderr)
        return 1
    try:
        code, res = post(conf, contact, a.text, a.timeout)
    except Exception as e:
        print(f"wxbot 发送失败: {type(e).__name__}: {e}", file=sys.stderr)
        return 1
    if code == 200 and res.get("ok"):
        print(f"已发出 → {contact}")
        return 0
    print(f"wxbot 返回 HTTP {code}: {res}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
