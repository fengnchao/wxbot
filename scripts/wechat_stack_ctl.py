#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""微信机器人栈一键启停（wxbot + 收件日志服务）。

栈成员：
  wxbot         UI 自动化机器人，外发接口 127.0.0.1:8765
  wechat-inbox  收件日志服务，监听 127.0.0.1:8788

停止 = 置「暂停标志」+ 杀掉两个服务进程。
       置标志是为了让 Hermes 看门狗 cron（每 5 分钟）保持静默、不把服务又拉起来。
启动 = 清「暂停标志」+ 经 WMI（sidecar_spawn.py）拉起两个服务
       —— 必须走 WMI：从终端/脚本用 Popen(DETACHED) 起的进程会被 Job Object 回收。

用法:
  python wechat_stack_ctl.py start
  python wechat_stack_ctl.py stop
  python wechat_stack_ctl.py status
"""
import os
import socket
import subprocess
import sys
import time
from pathlib import Path

# 仓库根：脚本在 scripts/ 下，按自身位置推导，避免写死部署路径。
BOT = os.environ.get("BOT_HOME") or str(Path(__file__).resolve().parents[1])
# HERMES_HOME 是外部 agent 家目录（看门狗/暂停标志/日志），保持可覆盖。
HERMES_HOME = os.environ.get("HERMES_HOME", r"D:\ai\hermes")
PAUSE_FLAG = os.path.join(HERMES_HOME, "cache", "wechat_stack_paused.flag")
SPAWNER = os.path.join(BOT, "heartbeat", "sidecar_spawn.py")
PY = sys.executable

SERVICES = [
    {"name": "wxbot", "port": 8765,
     "launcher": os.path.join(BOT, "scripts", "wxbot_startup.bat"),
     "match": "wxbot.main"},
    {"name": "wechat-inbox", "port": 8788,
     "launcher": os.path.join(BOT, "log", "wechat_inbox_startup.bat"),
     "match": None},
]


def port_up(port, timeout=2.0):
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(timeout)
    try:
        s.connect(("127.0.0.1", port))
        return True
    except OSError:
        return False
    finally:
        s.close()


def listening_pids(port):
    try:
        out = subprocess.run(["netstat", "-ano"], capture_output=True).stdout
    except Exception:
        return set()
    txt = out.decode("gbk", errors="replace")
    pids = set()
    for line in txt.splitlines():
        if f":{port}" in line and "LISTENING" in line.upper():
            parts = line.split()
            if parts and parts[-1].isdigit():
                pids.add(parts[-1])
    return pids


def proc_pids(match):
    if not match:
        return set()
    ps = ("Get-CimInstance Win32_Process -Filter \"Name like '%python%'\" | "
          f"Where-Object {{ $_.CommandLine -match '{match}' }} | "
          "ForEach-Object { $_.ProcessId }")
    try:
        out = subprocess.run(["powershell", "-NoProfile", "-Command", ps],
                             capture_output=True).stdout.decode("gbk", "replace")
    except Exception:
        return set()
    return {x for x in out.split() if x.strip().isdigit()}


def kill_pids(pids, label):
    killed = []
    for pid in sorted(pids):
        r = subprocess.run(["taskkill", "/F", "/PID", pid], capture_output=True)
        if r.returncode == 0:
            killed.append(pid)
        else:
            sys.stdout.write(f"    ! 终止 {label} PID {pid} 失败（可能已退出）\n")
    return killed


def spawn(launcher):
    """经 sidecar_spawn.py（WMI）拉起载体 bat，返回是否 OK。"""
    if not os.path.exists(SPAWNER):
        return False
    try:
        r = subprocess.run([PY, SPAWNER, launcher],
                           capture_output=True, text=True, timeout=90)
    except Exception as e:
        sys.stdout.write(f"    ! spawn 异常: {e}\n")
        return False
    return (r.stdout or "").strip().startswith("OK")


def do_stop():
    # 1) 先置标志，避免看门狗在杀进程的间隙把服务拉回来
    os.makedirs(os.path.dirname(PAUSE_FLAG), exist_ok=True)
    with open(PAUSE_FLAG, "w", encoding="utf-8") as fh:
        fh.write(time.strftime("%Y-%m-%d %H:%M:%S") + " paused\n")
    print(f"[暂停标志] 已置 {PAUSE_FLAG}")
    print("           （看门狗 cron 将保持静默，不再自动拉起）")

    # 2) 逐个停服务
    for svc in SERVICES:
        pids = listening_pids(svc["port"]) | proc_pids(svc["match"])
        if pids:
            killed = kill_pids(pids, svc["name"])
            print(f"[停止] {svc['name']}: 终止 PID {', '.join(killed) or '无'}")
        else:
            print(f"[停止] {svc['name']}: 本来就没在跑")

    time.sleep(1)
    still = [s["name"] for s in SERVICES if port_up(s["port"])]
    print()
    if still:
        print("结果: !! 仍在监听 -> " + ", ".join(still))
        return 1
    print("结果: 已全部停止（8765 / 8788 均 DOWN）")
    return 0


def do_start():
    # 1) 清标志，恢复看门狗守护
    if os.path.exists(PAUSE_FLAG):
        try:
            os.remove(PAUSE_FLAG)
            print(f"[暂停标志] 已清除 {PAUSE_FLAG}")
        except Exception as e:
            print(f"! 清除标志失败: {e}")
    else:
        print("[暂停标志] 本来就没有")

    # 2) 拉起没在跑的服务
    rc = 0
    for svc in SERVICES:
        if port_up(svc["port"]):
            print(f"[启动] {svc['name']}: 已在运行（{svc['port']} UP），跳过")
            continue
        ok = spawn(svc["launcher"])
        up = False
        for _ in range(30):
            time.sleep(1)
            if port_up(svc["port"]):
                up = True
                break
        if up:
            print(f"[启动] {svc['name']}: 已拉起（{svc['port']} UP）")
        else:
            print(f"[启动] {svc['name']}: !! 30 秒内没起来（spawn {'OK' if ok else '失败'}）"
                  f" —— 检查日志 {os.path.join(HERMES_HOME, 'cache', 'wxbot.log')}")
            rc = 1
    print()
    print("结果:", "两个服务都在线" if rc == 0 else "有服务没起来，见上面提示")
    return rc


def do_status():
    print(f"暂停标志: {'存在（栈处于手动停止状态，看门狗静默）' if os.path.exists(PAUSE_FLAG) else '不存在（看门狗守护中）'}")
    for svc in SERVICES:
        up = port_up(svc["port"])
        pids = listening_pids(svc["port"]) | proc_pids(svc["match"])
        print(f"  {svc['name']:14s} 端口 {svc['port']}: "
              f"{'UP ' if up else 'DOWN'}  PID {', '.join(sorted(pids)) or '-'}")
    return 0


def main():
    cmd = (sys.argv[1] if len(sys.argv) > 1 else "status").lower()
    if cmd == "start":
        return do_start()
    if cmd == "stop":
        return do_stop()
    if cmd == "status":
        return do_status()
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main())
