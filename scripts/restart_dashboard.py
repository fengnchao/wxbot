#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""重启微信收件日志服务：杀掉监听端口的进程，交给看门狗拉起。"""
import os
import signal
import subprocess
import sys
import time

PORT = 8788
# 本脚本在 scripts/ 下，看门狗在仓库根下的 heartbeat/。
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WATCHDOG = os.path.join(_ROOT, "heartbeat", "wechat_inbox_watchdog.py")


def listening_pids(port=PORT):
    out = subprocess.run(["netstat", "-ano"], capture_output=True).stdout
    txt = out.decode("gbk", errors="replace")
    pids = set()
    for line in txt.splitlines():
        if f":{port}" in line and "LISTENING" in line.upper():
            parts = line.split()
            if parts:
                pids.add(parts[-1])
    return pids


def main():
    pids = listening_pids()
    print(f"监听 {PORT} 的 PID: {pids or '无'}")
    for p in pids:
        try:
            os.kill(int(p), signal.SIGTERM)
            print(f"  已终止 {p}")
        except Exception as e:
            print(f"  终止 {p} 失败: {e}")
    time.sleep(2)
    left = listening_pids()
    if left:
        print(f"!! 仍有残留: {left}")
        return 1
    print("已掉线，交给看门狗拉起…")
    r = subprocess.run([sys.executable, WATCHDOG], capture_output=True, text=True)
    print("  看门狗:", (r.stdout or "").strip() or "(静默)")
    time.sleep(1)
    up = bool(listening_pids())
    print("结果:", "UP" if up else "!! DOWN")
    return 0 if up else 1


if __name__ == "__main__":
    sys.exit(main())
