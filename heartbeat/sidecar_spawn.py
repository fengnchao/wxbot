#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把常驻服务"托管式"拉起来：经 WMI（Win32_Process.Create）创建进程，脱离调用者的 Job Object。

为什么不用 subprocess.Popen(DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP)：
  实测（2026-10-10）从 agent 终端 / cron tick 里起的 8788 与 8765 两个服务都在几分钟内**无声消失**
  —— 没有 traceback、没有退出码，端口直接没了。DETACHED 标志只影响控制台/进程组，
  逃不出调用者的 Windows Job Object：创建它的人一结束，job 关闭，里面的进程连坐回收。
  WMI 创建的进程挂在 WmiPrvSE.exe 下、不属于任何调用者的 job，因此能活过会话结束。

用法:
  sidecar_spawn.py "<repo>\\scripts\\wxbot_startup.bat"     # 打印新进程 PID
"""
import argparse
import subprocess
import sys

PS_TMPL = (
    "$r = Invoke-CimMethod -ClassName Win32_Process -MethodName Create "
    "-Arguments @{{ CommandLine = 'cmd /c \"{cmd}\"' }}; "
    "if ($r.ReturnValue -eq 0) {{ \"OK \" + $r.ProcessId }} else {{ \"ERR \" + $r.ReturnValue }}"
)


def spawn_via_wmi(command: str) -> str:
    ps = PS_TMPL.format(cmd=command)
    out = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", ps],
                         capture_output=True, text=True, encoding="utf-8", errors="replace")
    return (out.stdout or out.stderr or "").strip()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("command", help="要拉起的载体（通常是一个 .bat：它负责 cd / 环境变量 / 重定向日志）")
    a = ap.parse_args()
    res = spawn_via_wmi(a.command)
    print(res)
    return 0 if res.startswith("OK") else 1


if __name__ == "__main__":
    sys.exit(main())
