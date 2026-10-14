"""
探测脚本：打印微信窗口的控件树，用来确认控件能不能读到、怎么定位。

默认【脱敏模式】：控件里的文字一律显示为 ***(长度)，不会带出聊天内容，
可以放心把输出贴给别人分析。加 --raw 才显示真实文字（只在本地自己看）。

用法：
  python tools/probe.py --list                 # 列出所有顶层窗口
  python tools/probe.py --window 微信          # 打印指定窗口的控件树
  python tools/probe.py --window 张三 --depth 12 --raw
本脚本只读取本机界面，不联网、不发送任何数据。
"""
import argparse
import re
import sys

import uiautomation as auto


def mask(text: str, raw: bool) -> str:
    if raw:
        return text
    return f"***({len(text)})" if text else ""


def list_windows(raw: bool) -> None:
    root = auto.GetRootControl()
    for w in root.GetChildren():
        rect = w.BoundingRectangle
        print(f"[{w.ControlTypeName}] name={mask(w.Name, raw)!r} class={w.ClassName!r} "
              f"pid={w.ProcessId} rect=({rect.left},{rect.top},{rect.right},{rect.bottom})")


def dump(window_name: str, depth: int, raw: bool) -> None:
    win = auto.WindowControl(searchDepth=1, Name=window_name)
    if not win.Exists(3):
        print(f"找不到标题为 {window_name!r} 的窗口，先用 --list 看看窗口名", file=sys.stderr)
        sys.exit(1)
    count = 0
    for ctrl, d in auto.WalkControl(win, includeTop=True, maxDepth=depth):
        rect = ctrl.BoundingRectangle
        aid = ctrl.AutomationId
        print(f"{'  ' * d}[{ctrl.ControlTypeName}] "
              f"name={mask(ctrl.Name, raw)!r} class={ctrl.ClassName!r}"
              f"{f' aid={aid!r}' if aid else ''} "
              f"rect=({rect.left},{rect.top},{rect.right},{rect.bottom})")
        count += 1
    print(f"\n共 {count} 个控件")


def main() -> None:
    p = argparse.ArgumentParser(description="微信控件树探测（默认脱敏）")
    p.add_argument("--list", action="store_true", help="列出所有顶层窗口")
    p.add_argument("--window", help="要探测的窗口标题，例如 微信 或 好友名")
    p.add_argument("--depth", type=int, default=10, help="最大遍历深度")
    p.add_argument("--raw", action="store_true", help="显示真实文字（不脱敏，仅本地查看）")
    args = p.parse_args()

    if args.list:
        list_windows(args.raw)
    elif args.window:
        dump(args.window, args.depth, args.raw)
    else:
        p.print_help()


if __name__ == "__main__":
    main()
