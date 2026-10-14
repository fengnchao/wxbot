"""
调试脚本：检查窗口、消息列表、输入框，以及每条消息被判断成谁发的。
默认脱敏（文字显示为 ***(长度)），加 --raw 显示真实内容（仅本地查看）。

用法（在项目根目录运行，聊天窗口要完整显示在屏幕上）：
  python tools/debug_read.py
  python tools/debug_read.py --raw
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from wxbot.dpi import set_dpi_aware  # noqa: E402

set_dpi_aware()

import uiautomation as auto  # noqa: E402

from wxbot.config import load_config  # noqa: E402
from wxbot.wechat.chat_window import ChatWindow  # noqa: E402
from wxbot.wechat.locator import find, matches  # noqa: E402


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--raw", action="store_true")
    args = p.parse_args()
    show = (lambda t: t) if args.raw else (lambda t: f"***({len(t)})")

    cfg = load_config()
    for name in cfg["bot"]["bound_users"]:
        print(f"\n===== 绑定对象 {show(name)} =====")
        chat = ChatWindow(name, cfg["wechat"])
        win = chat._window()
        print(f"1. 独立窗口: {'找到' if win else '没找到 ← 检查名字是否和窗口标题一致、窗口是否已打开'}")
        if not win:
            continue
        lst = chat._message_list()
        print(f"2. 消息列表: {'找到' if lst else '没找到 ← [wechat.message_list] 配置不对'}")
        edit = find(win, cfg["wechat"]["input"])
        print(f"3. 输入框:   {'找到' if edit else '没找到 ← [wechat.input] 配置不对'}")
        if not lst:
            continue
        list_rect = lst.BoundingRectangle
        print("4. 消息条目（左/右 = 两侧非背景像素数）:")
        for item in lst.GetChildren():
            text = item.Name or ""
            is_text = matches(item, cfg["wechat"].get("text_item", {}))
            scores = chat.side_scores(item, list_rect) if is_text else None
            sender = chat._classify(item, text, list_rect)
            score_str = f"左={scores[0]:<5} 右={scores[1]:<5}" if scores else " " * 16
            print(f"   [{sender:6}] {score_str} {item.ClassName:<26} {show(text)}")


if __name__ == "__main__":
    with auto.UIAutomationInitializerInThread():
        main()
