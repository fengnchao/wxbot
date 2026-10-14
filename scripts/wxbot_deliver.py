#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""经 wxbot 投递一条提醒/推送；wxbot 不可用时**转入补发队列**，不丢消息。

为什么需要它：iLink 通道主动推送受会话窗口限制（实测 ≈40 分钟，且 bot 自己发消息不能续期），
而 wxbot 走本机微信客户端 UI 自动化，没有 token、也就没有过期——所以**定时提醒应该走这里**。

用法：
  wxbot_deliver.py --profile <p> --text "要发的内容" [--job-id X --job-name Y]
  wxbot_deliver.py --profile <p> --text -              # 正文从 stdin 整段读
  wxbot_deliver.py --check [--profile <p>]             # 只查通道状态

退出码（配合 no_agent cron 的语义设计）：
  0  = 已发出          → stdout 为空，cron 不会再投递一遍（避免重复）
  1  = wxbot 不可用    → 内容已入补发队列，stdout 为空（等下次有机会补发）
  2  = 该 Profile 没接 wxbot → stdout 打原文，交回默认投递

关键约定：**数据根**（HERMES_HOME）与**本脚本位置**分开取 —— 脚本在 <项目根>/scripts，
数据仍在 $HERMES_HOME（2026-10-11 搬出 Hermes 之后改的）。
"""
import argparse
import io
import json
import os
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent                          # D:\bot\scripts
# 数据（档案/补发队列/日志）仍在 Hermes 家里；本脚本自己搬到了 D:\bot\scripts
HOME = Path(os.environ.get("HERMES_HOME") or r"D:\ai\hermes")
CONF = HERE / "wxbot_channel.json"


def load_conf():
    if not CONF.exists():
        return {}
    try:
        return json.loads(CONF.read_text(encoding="utf-8"))
    except Exception:
        return {}


def profile_root(profile):
    return HOME if profile in ("", "default") else HOME / "profiles" / profile


def enqueue(profile, job_id, job_name, text, error):
    """把内容交给该 Profile 的补发队列（复用技能自带脚本，schema 一致）。"""
    script = profile_root(profile) / "skills" / "messaging" / "wechat-reminder" / "scripts" / "pending_delivery.py"
    if not script.exists():
        return False
    try:
        r = subprocess.run([sys.executable, str(script), "--home", str(profile_root(profile)),
                            "enqueue", job_id, job_name, text, error],
                           capture_output=True, text=True, timeout=60)
        return r.returncode == 0
    except Exception:
        return False


def send(conf, contact, text, timeout):
    url = str(conf.get("url", "http://127.0.0.1:8765")).rstrip("/")
    headers = {"Content-Type": "application/json"}
    tok = str(conf.get("token", "") or "")
    if tok:
        headers["X-Wxbot-Token"] = tok
    body = {"contact": contact, "text": text, "wait": True, "timeout": float(timeout)}
    req = urllib.request.Request(url + "/send",
                                 data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
                                 headers=headers, method="POST")
    with urllib.request.urlopen(req, timeout=float(timeout) + 15) as r:
        return r.status, json.loads(r.read().decode("utf-8", "replace"))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--profile", default="")
    ap.add_argument("--text", default="")
    ap.add_argument("--job-id", default="wxbot-deliver")
    ap.add_argument("--job-name", default="提醒")
    ap.add_argument("--timeout", type=float, default=0)
    ap.add_argument("--check", action="store_true")
    a = ap.parse_args()

    conf = load_conf()
    contact = (conf.get("profile_to_contact") or {}).get(a.profile, "")

    if a.check:
        print(f"配置文件: {CONF}（{'存在' if CONF.exists() else '不存在'}）")
        print(f"  映射: {conf.get('profile_to_contact')}")
        print(f"  profile {a.profile!r} → 联系人 {contact or '（未映射）'}")
        try:
            req = urllib.request.Request(str(conf.get("url", "")).rstrip("/") + "/health",
                                         headers={"X-Wxbot-Token": str(conf.get("token", ""))})
            with urllib.request.urlopen(req, timeout=5) as r:
                print(f"  wxbot: 在线 {r.read().decode()}")
                return 0
        except urllib.error.HTTPError as e:
            if e.code in (200, 401, 403):
                print(f"  wxbot: 在线（HTTP {e.code}，服务在监听）")
                return 0
            print(f"  wxbot: 异常 HTTP {e.code}")
            return 1
        except Exception as e:
            print(f"  wxbot: 不在线（{type(e).__name__}: {e}）")
            return 1

    text = sys.stdin.read() if a.text == "-" else a.text
    text = (text or "").strip()
    if not text:
        print("缺少正文", file=sys.stderr)
        return 2

    if not contact:
        print(text)                      # 交回原通道
        return 2

    timeout = a.timeout or float(conf.get("timeout") or 60)
    try:
        code, res = send(conf, contact, text, timeout)
        if code == 200 and res.get("ok"):
            return 0                     # 静默：cron 不要再投递
        err = f"wxbot HTTP {code}: {str(res)[:120]}"
    except Exception as e:
        err = f"wxbot 不可用: {type(e).__name__}: {e}"

    if enqueue(a.profile, a.job_id, a.job_name, text, err):
        return 1                         # 已入队，静默
    print(text)                          # 队列也不可用 → 交回原通道，至少不丢
    return 2


if __name__ == "__main__":
    sys.exit(main())
