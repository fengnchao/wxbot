#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把 wxbot 主循环以「脱离当前会话」的方式拉起来（进程组独立，不受启动它的 shell 影响）。

用法：
  wxbot_run.py            # 若已在运行则什么都不做
  wxbot_run.py --restart  # 先杀旧进程再起
  wxbot_run.py --status   # 只看状态
"""
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request

# 项目根 = 本脚本上级目录（scripts 的上一级），拉起的就是含 8765 外发服务的合并版 wxbot
WX = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))   # <repo>
PY = os.path.join(WX, ".venv", "Scripts", "python.exe")            # 本项目 uv 管理的解释器
# 数据家目录与看门狗/管理台保持同一套推导规则
HERMES_HOME = os.environ.get("HERMES_HOME") or os.path.join(WX, "data")
LOG = os.path.join(HERMES_HOME, "cache", "wxbot.log")               # 看板默认读取路径，保持不变
PORT = 8765
DETACHED = 0x00000008 | 0x00000200          # DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP


def port_up(port=PORT):
    """/health 需要 token，401 也算"在线"（说明服务在监听并做了鉴权）。"""
    req = urllib.request.Request(f"http://127.0.0.1:{port}/health")
    try:
        with urllib.request.urlopen(req, timeout=3) as r:
            return r.status == 200, r.read().decode()
    except urllib.error.HTTPError as e:
        if e.code in (200, 401, 403):
            return True, f"HTTP {e.code}（服务在监听）"
        return False, f"HTTP {e.code}"
    except Exception as e:
        return False, str(e)


def pids():
    out = subprocess.run(["powershell", "-NoProfile", "-Command",
                          "Get-CimInstance Win32_Process -Filter \"Name like '%python%'\" | "
                          "Where-Object { $_.CommandLine -match 'wxbot.main' } | "
                          "ForEach-Object { $_.ProcessId }"],
                         capture_output=True).stdout.decode("gbk", "replace")
    return [int(x) for x in out.split() if x.strip().isdigit()]


def kill_all():
    for pid in pids():
        subprocess.run(["taskkill", "/F", "/PID", str(pid)],
                       capture_output=True)
        print(f"  已终止 wxbot PID {pid}")
    time.sleep(2)


def start():
    os.makedirs(os.path.dirname(LOG), exist_ok=True)
    fh = open(LOG, "ab")
    env = dict(os.environ)
    env["HERMES_HOME"] = HERMES_HOME
    env["PYTHONIOENCODING"] = "utf-8"   # 否则中文日志按 cp936 写进文件变乱码
    env["PYTHONUTF8"] = "1"
    p = subprocess.Popen([PY, "-m", "wxbot.main"], cwd=WX,
                         env=env,
                         stdout=fh, stderr=subprocess.STDOUT,
                         creationflags=DETACHED, close_fds=True)
    print(f"  已启动 wxbot（PID {p.pid}），日志 {LOG}")
    for _ in range(15):
        time.sleep(1)
        up, detail = port_up()
        if up:
            print(f"  外发接口在线: {detail}")
            return 0
    print("  !! 15 秒内没起来，看日志")
    return 1


def main():
    if "--status" in sys.argv:
        up, detail = port_up()
        print(f"  进程: {pids() or '无'}")
        print(f"  端口 {PORT}: {'UP ' + detail if up else 'DOWN'}")
        return 0
    if "--restart" in sys.argv:
        kill_all()
    elif pids():
        up, _ = port_up()
        print(f"  已在运行（PID {pids()}），端口 {'UP' if up else 'DOWN'} —— 不做改动")
        return 0
    return start()


if __name__ == "__main__":
    sys.exit(main())
