"""
头像采样校准：把当前群聊窗口里每一行消息的头像截成两版并排放大，
左列是自动边界检测，右列是旧的固定 36px 采样，用来确认头像是否被完整框住。

用法：
  1. 把微信停在一个群聊窗口，保持窗口可见、不被遮挡、不在最小化状态
  2. python tools/avatar_calibration.py
  3. 打开输出 PNG 对比；左列应该看到完整头像，右列通常能看出右下被切

只读取本机屏幕像素，不发送消息、不修改配置。
"""
import sys
from pathlib import Path

import uiautomation as auto
from PIL import Image, ImageDraw, ImageGrab

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from wxbot.dpi import set_dpi_aware
from wxbot.wechat.chat_window import ChatWindow
from wxbot.wechat.locator import find

MESSAGE_LIST = {"control_type": "ListControl", "automation_id": "chat_message_list"}
ZOOM = 4


def locate():
    """独立聊天窗口优先；主窗口模式下取当前打开的会话。"""
    chat = auto.WindowControl(searchDepth=1, ClassName="mmui::ChatSingleWindow")
    if chat.Exists(1):
        return chat
    main = auto.WindowControl(searchDepth=1, ClassName="mmui::MainWindow")
    return main if main.Exists(1) else None


def main() -> None:
    set_dpi_aware()
    win = locate()
    if win is None:
        print("没有找到微信聊天窗口，请先打开一个群聊", file=sys.stderr)
        sys.exit(1)
    lst = find(win, MESSAGE_LIST, max_depth=32)
    if lst is None:
        print("窗口里没有消息列表，确认当前停在一个会话上", file=sys.stderr)
        sys.exit(1)
    list_rect = lst.BoundingRectangle
    window = ChatWindow(win.Name, {"message_list": MESSAGE_LIST, "group_sender": {}})
    window._win = win
    scale = window._avatar_scale()
    print(f"窗口={win.Name} DPI缩放={scale:.2f} 列表=({list_rect.left},{list_rect.top},"
          f"{list_rect.right},{list_rect.bottom})")

    rows = []
    for item in lst.GetChildren():
        cls = item.ClassName or ""
        if not (cls.startswith("mmui::Chat") and cls.endswith("ItemView")):
            continue
        rect = item.BoundingRectangle
        if rect.top < list_rect.top or rect.bottom > list_rect.bottom or rect.left < list_rect.left:
            continue
        rows.append(item)
    if not rows:
        print("消息列表里没有可见的完整行", file=sys.stderr)
        sys.exit(1)

    size = round(36 * scale)
    old_left = round(12 * scale)
    tiles = []
    for index, item in enumerate(rows[-8:]):
        rect = item.BoundingRectangle
        found, _ = window._avatar_box(item, list_rect, scale)
        left = max(rect.left, list_rect.left) + old_left
        top = rect.top
        legacy = ImageGrab.grab(bbox=(left, top, left + size, top + size), all_screens=True)
        if found is None:
            box = (left, top, left + size, top + size)
            label = "自动:失败"
        else:
            box = found
            label = "自动:%dpx 偏移(%+d,%+d)" % (found[2] - found[0], found[0] - left, found[1] - top)
        auto_shot = ImageGrab.grab(bbox=box, all_screens=True)
        pair = Image.new("RGB", (size * ZOOM * 2 + 12, size * ZOOM + 16), (18, 22, 28))
        pair.paste(auto_shot.resize((size * ZOOM, size * ZOOM), Image.Resampling.NEAREST), (0, 0))
        pair.paste(legacy.resize((size * ZOOM, size * ZOOM), Image.Resampling.NEAREST), (size * ZOOM + 12, 0))
        draw = ImageDraw.Draw(pair)
        draw.text((2, size * ZOOM + 2), "行%d %s" % (index, label), fill=(160, 175, 190))
        draw.rectangle([0, 0, size * ZOOM - 1, size * ZOOM - 1], outline=(255, 90, 90))
        tiles.append(pair)
        print("行%d 自动框=%s 旧框=(%d,%d,%d,%d) 行高=%d"
              % (index, found, left, top, left + size, top + size, rect.bottom - rect.top))

    height = sum(t.height + 4 for t in tiles)
    canvas = Image.new("RGB", (max(t.width for t in tiles), height), (10, 13, 17))
    y = 0
    for tile in tiles:
        canvas.paste(tile, (0, y))
        y += tile.height + 4
    out = Path("cache/avatar-calibration.png")
    out.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(out)
    print(f"已保存 {out}（左=自动检测，右=旧固定采样）")


if __name__ == "__main__":
    main()
