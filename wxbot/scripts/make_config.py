# -*- coding: utf-8 -*-
"""从 wxbot 的 config.toml 生成管家的 config.toml（密钥只落盘，不打印）。"""
import secrets
import sys
import tomllib
from pathlib import Path

WX = Path(r"D:\ai\wxbot\config.toml")
OUT = Path(r"D:\bot\config.toml")

wx = tomllib.load(open(WX, "rb"))
h = wx.get("hermes", {})
ob = wx.get("outbound", {})
contacts = wx.get("contacts", [])

token = ob.get("token") or ""
# 管家自己的接口 token：独立生成（不与 wxbot 的 outbound token 共用，泄一个不牵另一个）
srv_token = secrets.token_hex(16)

lines = [
    "# 由 scripts/make_config.py 生成（值取自 wxbot/config.toml）。不要提交。",
    "",
    "[server]",
    'host = "127.0.0.1"',
    "port = 8770",
    'token = "%s"' % srv_token,
    "",
    "[hermes]",
    'url = "%s"' % (h.get("url") or "http://127.0.0.1:8642"),
    'api_key = "%s"' % (h.get("api_key") or ""),
    'model = "%s"' % (h.get("model") or "hermes-agent"),
    "timeout = %d" % int(h.get("timeout") or 600),
    'root = "%s"' % (h.get("root") or "D:/ai/hermes"),
    "send_identity = %s" % ("true" if h.get("send_identity", True) else "false"),
    "",
    "[wxbot]",
    'url = "http://127.0.0.1:%s"' % (ob.get("port") or 8765),
    'token = "%s"' % token,
    "timeout = 120",
    "",
    "[dispatch]",
    "actions_enabled = true",
    'script_dir = "%s/scripts"' % (h.get("root") or "D:/ai/hermes"),
    "respond_after_action = false",
    "",
]
for c in contacts:
    lines += [
        "[[contacts]]",
        'name = "%s"' % c.get("name", ""),
        'profile = "%s"' % c.get("profile", "default"),
        'uid = "%s"' % c.get("uid", c.get("name", "")),
        'label = "%s"' % c.get("label", ""),
        "",
    ]

OUT.write_text("\n".join(lines), encoding="utf-8")
print("已写入 %s" % OUT)
print("  联系人 %d 个：%s" % (len(contacts), ", ".join(c.get("name", "?") for c in contacts)))
print("  接口 token：长度 %d（新生成，未打印）" % len(srv_token))
print("  hermes key：长度 %d（搬运）" % len(h.get("api_key") or ""))
print("  wxbot token：长度 %d（搬运）" % len(token))
sys.exit(0)
