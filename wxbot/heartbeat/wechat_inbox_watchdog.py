#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
微信收件日志服务的看门狗。

端口没在监听就把它拉起来；正常时**不输出任何东西**（这样 Hermes cron 的
no_agent 模式不会给任何人发消息 —— 静默是设计，不是 bug）。

用法（手动）:
    python D:\\bot\\kmg\\wechat_inbox_watchdog.py
    python D:\\bot\\kmg\\wechat_inbox_watchdog.py --status

cron 跑的是 $HERMES_HOME/scripts/wechat_inbox_watchdog.py（一层转发 shim）——
调度器只允许 scripts/ 目录内的脚本，真身在这里。
"""
import argparse
import os
import socket
import subprocess
import sys
import time

HOST = "127.0.0.1"
PORT = 8788
HERMES_HOME = os.environ.get("HERMES_HOME", r"D:\ai\hermes")
PAUSE_FLAG = os.path.join(HERMES_HOME, "cache", "wechat_stack_paused.flag")
PYW = os.path.join(HERMES_HOME, "hermes-agent", "venv", "Scripts", "pythonw.exe")

# 本项目自身的位置（2026-10-11 从 $HERMES_HOME/scripts 与 $HERMES_HOME/tools/wechat-inbox 搬来）。
# 一律**自定位**：整个 D:\bot 树以后再搬，这些常量都不用改。
HERE = os.path.dirname(os.path.abspath(__file__))        # D:\bot\kmg
BOT_ROOT = os.path.dirname(HERE)                         # D:\bot
LOG_SVC = os.path.join(BOT_ROOT, "log")                  # 日志服务（wechat-inbox）
SERVER = os.path.join(LOG_SVC, "server.py")
SPAWNER = os.path.join(HERE, "sidecar_spawn.py")
LAUNCHER = os.path.join(LOG_SVC, "wechat_inbox_startup.bat")

# Windows: 脱离父进程 + 独立进程组，父进程死了它也不受牵连
CREATE_NEW_PROCESS_GROUP = 0x00000200
DETACHED_PROCESS = 0x00000008


def is_alive(timeout=2.0) -> bool:
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(timeout)
    try:
        s.connect((HOST, PORT))
        return True
    except OSError:
        return False
    finally:
        s.close()


def spawn() -> bool:
    if not os.path.exists(SERVER):
        return False
    # 经 WMI 拉起（脱离调用者的 Job Object）—— 否则从终端/cron tick 起的进程会被回收：
    # 实测 2026-10-10 两个服务都在几分钟内无声消失（无 traceback、端口直接没了）。
    launcher, spawner = LAUNCHER, SPAWNER
    if os.path.exists(launcher) and os.path.exists(spawner):
        try:
            r = subprocess.run([sys.executable, spawner, launcher],
                               capture_output=True, text=True, timeout=90)
            if (r.stdout or "").strip().startswith("OK"):
                return True
        except Exception:
            pass
    # 兜底：老办法（DETACHED_PROCESS）
    if not os.path.exists(PYW):
        pyw = sys.executable
    else:
        pyw = PYW
    if not os.path.exists(SERVER):
        return False
    env = dict(os.environ)
    env["HERMES_HOME"] = HERMES_HOME
    flags = DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP
    subprocess.Popen(
        [pyw, SERVER, "--host", HOST, "--port", str(PORT)],
        cwd=os.path.dirname(SERVER),
        env=env,
        creationflags=flags,
        close_fds=True,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    return True


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--status", action="store_true", help="只报告状态，不重启")
    args = ap.parse_args()

    # 桌面「停止」快捷方式会置暂停标志 -> 静默退出，别把服务又拉起来
    if not args.status and os.path.exists(PAUSE_FLAG):
        return 0

    if args.status:
        print(f"port {PORT}: {'UP' if is_alive() else 'DOWN'}")
        return 0

    if is_alive():
        return 0  # 静默 —— 看门狗正常工作时不该有任何输出

    ok = spawn()
    time.sleep(3)
    back = is_alive()
    stamp = time.strftime("%Y-%m-%d %H:%M:%S")
    if back:
        print(f"[wechat-inbox watchdog] {stamp}  端口 {PORT} 已掉线，重启成功")
        return 0
    print(f"[wechat-inbox watchdog] {stamp}  端口 {PORT} 已掉线，重启{'失败' if ok else '失败(脚本/解释器缺失)'}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
