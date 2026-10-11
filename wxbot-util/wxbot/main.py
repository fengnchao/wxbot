"""
主循环：轮询每个绑定联系人的独立窗口 → 发现对方新消息 → 本地处理 → 发送回复。

运行：python -m wxbot.main
"""
import random
import time

from .dpi import set_dpi_aware

set_dpi_aware()

import uiautomation as auto  # noqa: E402

from .config import load_config
from .log import log
from .processor.base import EchoProcessor
from .processor.ollama import OllamaProcessor
from .processor.openai_compat import OpenAICompatProcessor
from .processor.router import Router
from .state import new_messages
from .wechat.chat_window import ChatWindow


def build_processor(cfg: dict) -> Router:
    mcfg = cfg.get("model", {})
    backend = mcfg.get("backend", "ollama")
    if backend == "echo":
        model = EchoProcessor()
    elif backend in ("hermes", "openai"):
        model = OpenAICompatProcessor(mcfg)
    else:
        model = OllamaProcessor(mcfg)
    return Router(model, cfg["bot"].get("command_prefix", "/"))


def run() -> None:
    cfg = load_config()
    bcfg = cfg["bot"]
    router = build_processor(cfg)
    chats = {name: ChatWindow(name, cfg["wechat"]) for name in bcfg["bound_users"]}
    snapshots: dict[str, list] = {}
    warned: set[str] = set()

    log.info("已绑定：%s。请在微信里把这些聊天打开为独立窗口。按 Ctrl+C 退出。", "、".join(chats))

    while True:
        for name, chat in chats.items():
            if not chat.available():
                if name not in warned:
                    log.warning("[%s] 没找到独立聊天窗口，请双击会话打开", name)
                    warned.add(name)
                snapshots.pop(name, None)
                continue
            warned.discard(name)

            msgs = chat.read_messages()
            if name not in snapshots:
                snapshots[name] = msgs          # 首次读取：只记录，不回复历史消息
                log.info("[%s] 已连接，当前 %d 条消息", name, len(msgs))
                continue

            fresh = [m for m in new_messages(snapshots[name], msgs) if m.sender == "other"]
            snapshots[name] = msgs

            for m in fresh:
                log.info("[%s] 收到: %s", name, m.text)
                reply = router.handle(name, m.text)
                if not reply:
                    continue
                time.sleep(random.uniform(bcfg.get("reply_delay_min", 0.8), bcfg.get("reply_delay_max", 2.5)))
                if chat.send(reply):
                    log.info("[%s] 回复: %s", name, reply[:60])

            if fresh:
                time.sleep(0.5)
                snapshots[name] = chat.read_messages()   # 把自己刚发的也纳入快照

        time.sleep(bcfg.get("poll_interval", 1.5))


def main() -> None:
    with auto.UIAutomationInitializerInThread():
        try:
            run()
        except KeyboardInterrupt:
            log.info("已退出")


if __name__ == "__main__":
    main()
