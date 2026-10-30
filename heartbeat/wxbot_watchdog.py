#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
wxbot 看门狗（cron no_agent 任务用）。

职责：
  1. 外发接口 127.0.0.1:8765 掉线 → 重新拉起 wxbot 主循环；
  2. 进程活着但目标聊天窗口没了（UI 自动化前提不满足）→ 报一次（状态变化才报，不刷屏）。

正常时**不输出任何东西** —— cron no_agent 模式下 stdout 为空 = 不投递任何消息（静默是设计）。

用法（手动）:
    python heartbeat\\wxbot_watchdog.py
    python heartbeat\\wxbot_watchdog.py --status

注意：cron 跑的是 $HERMES_HOME/scripts/wxbot_watchdog.py（一层转发 shim），
因为调度器只允许 scripts/ 目录内的脚本（scheduler.py::_run_job_script）。
"""
import argparse
import json
import os
import re
import subprocess
import sys
import time
import urllib.error
import urllib.request

# 一律**自定位**：仓库根 = heartbeat/ 的上一层；换机器/换目录都不用改常量。
HERE = os.path.dirname(os.path.abspath(__file__))        # <repo>/heartbeat
WX = os.path.dirname(HERE)                               # <repo>
HERMES_HOME = os.environ.get("HERMES_HOME") or os.path.join(WX, "data")
VENV_PY = os.path.join(WX, ".venv", "Scripts", "python.exe")
PY = VENV_PY if os.path.exists(VENV_PY) else sys.executable
LOG = os.path.join(HERMES_HOME, "cache", "wxbot.log")
STATE = os.path.join(HERMES_HOME, "cache", "wxbot_watchdog_state.json")
PAUSE_FLAG = os.path.join(HERMES_HOME, "cache", "wechat_stack_paused.flag")
PORT = 8765
DETACHED = 0x00000008 | 0x00000200   # DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP

RE_MISSING = re.compile(r"没找到独立聊天窗口|没找到微信主窗口")
RE_CONNECTED = re.compile(r"\[主窗口\] 已连接微信主窗口|窗口已连接|\[\S+\] 已连接，当前")


def port_up(timeout=3.0):
    """/health 需要 token，401 也算「在线」（服务在监听并做了鉴权）。"""
    req = urllib.request.Request(f"http://127.0.0.1:{PORT}/health")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return True, f"HTTP {r.status}"
    except urllib.error.HTTPError as e:
        if e.code in (200, 401, 403):
            return True, f"HTTP {e.code}（服务在监听）"
        return False, f"HTTP {e.code}"
    except Exception as e:
        return False, str(e)


def pids():
    out = subprocess.run(
        ["powershell", "-NoProfile", "-Command",
         "Get-CimInstance Win32_Process -Filter \"Name like '%python%'\" | "
         "Where-Object { $_.CommandLine -match 'wxbot.main' } | "
         "ForEach-Object { $_.ProcessId }"],
        capture_output=True).stdout.decode("gbk", "replace")
    return [int(x) for x in out.split() if x.strip().isdigit()]


def log_lines(n=300):
    if not os.path.exists(LOG):
        return []
    with open(LOG, "rb") as fh:
        raw = fh.read()
    out = []
    for ln in raw.splitlines()[-n:]:
        try:
            out.append(ln.decode("utf-8"))
        except UnicodeDecodeError:
            out.append(ln.decode("gbk", "replace"))
    return out


def window_state():
    """窗口可用性：最后一条「已连接」是否晚于最后一条「没找到独立聊天窗口」。"""
    lines = log_lines()
    last_missing = last_connected = -1
    for i, ln in enumerate(lines):
        if RE_MISSING.search(ln):
            last_missing = i
        elif RE_CONNECTED.search(ln):
            last_connected = i
    if last_missing < 0:
        return "ok"          # 没出现过「找不到窗口」的记录
    return "ok" if last_connected > last_missing else "no_window"


def spawn():
    """拉起 wxbot 主循环（日志追加到 LOG）。

    优先经 WMI（sidecar_spawn.py → wxbot_startup.bat）创建，脱离调用者的 Job Object ——
    实测从 agent 终端 / cron tick 里用 Popen(DETACHED) 起的进程会在几分钟内无声消失。
    """
    launcher = os.path.join(WX, "scripts", "wxbot_startup.bat")
    # sidecar_spawn 跟本脚本同一个目录（heartbeat/）→ 自定位
    spawner = os.path.join(HERE, "sidecar_spawn.py")
    if os.path.exists(launcher) and os.path.exists(spawner):
        try:
            subprocess.run([PY, spawner, launcher], capture_output=True, text=True, timeout=90)
        except Exception:
            pass
        for _ in range(20):
            time.sleep(1)
            if port_up()[0]:
                return True
        return False
    # 兜底：DETACHED_PROCESS
    os.makedirs(os.path.dirname(LOG), exist_ok=True)
    fh = open(LOG, "ab")
    env = dict(os.environ)
    env["HERMES_HOME"] = HERMES_HOME
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONUTF8"] = "1"
    subprocess.Popen([PY, "-m", "wxbot.main"], cwd=WX, env=env,
                     stdout=fh, stderr=subprocess.STDOUT,
                     creationflags=DETACHED, close_fds=True)
    # 等它把 8765 监听起来
    for _ in range(20):
        time.sleep(1)
        up, _detail = port_up()
        if up:
            return True
    return False


def load_state():
    try:
        with open(STATE, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except Exception:
        return {}


def save_state(d):
    try:
        with open(STATE, "w", encoding="utf-8") as fh:
            json.dump(d, fh, ensure_ascii=False)
    except Exception:
        pass


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--status", action="store_true", help="只报告，不重启")
    args = ap.parse_args()

    # 桌面「停止」快捷方式会置暂停标志 -> 静默退出，别把服务又拉起来
    if not args.status and os.path.exists(PAUSE_FLAG):
        return 0

    up, detail = port_up()
    ws = window_state()

    if args.status:
        print(f"  进程: {pids() or '无'}")
        print(f"  端口 {PORT}: {'UP ' + detail if up else 'DOWN'}")
        print(f"  聊天窗口: {ws}")
        return 0

    if not up:
        stamp = time.strftime("%Y-%m-%d %H:%M:%S")
        ok = spawn()
        back, detail2 = port_up() if ok else (False, "进程没起来")
        save_state({"state": "restarted" if back else "down", "ts": stamp})
        if back:
            print(f"[wxbot 看门狗] {stamp}  8765 掉线，已重启成功（{detail2}）")
            return 0
        print(f"[wxbot 看门狗] {stamp}  8765 掉线，重启失败（{detail2}）——查 {LOG}")
        return 1

    # 端口在，但窗口可能没了 —— 只在状态变化时报一次
    prev = load_state().get("state")
    if ws == "no_window" and prev != "no_window":
        save_state({"state": "no_window", "ts": time.strftime("%Y-%m-%d %H:%M:%S")})
        print("[wxbot 看门狗] 进程在跑但微信收发窗口不可用 —— 请打开微信主窗口；独立窗口模式需打开绑定聊天窗口")
        return 0
    if ws == "ok" and prev != "ok":
        save_state({"state": "ok", "ts": time.strftime("%Y-%m-%d %H:%M:%S")})
    return 0


if __name__ == "__main__":
    sys.exit(main())
