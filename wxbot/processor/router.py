"""命令路由：/ 开头的走命令，其他交给模型。新增命令在 COMMANDS 里加一项即可。"""
from .base import Processor
from ..reply import Reply


class Router:
    def __init__(self, model: Processor, prefix: str = "/"):
        self.model = model
        self.prefix = prefix
        self.commands = {
            "ping": lambda contact, args: "pong",
            "reset": self._reset,
            "help": self._help,
        }

    def _reset(self, contact, args):
        self.model.reset(contact)
        return "已清空对话记录。"

    def _help(self, contact, args):
        names = "、".join(self.prefix + n for n in self.commands)
        return f"可用命令：{names}\n其他消息会交给 AI 回复。"

    def handle(self, contact: str, text: str, *, context: str = "") -> str | None:
        return self.handle_reply(contact, text, context=context).text

    def handle_reply(self, contact: str, text: str, *, context: str = "", request_id=None) -> Reply:
        text = text.strip()
        if self.prefix and text.startswith(self.prefix):
            words = text[len(self.prefix):].split()
            name, args = (words[0], words[1:]) if words else ('', [])
            cmd = self.commands.get(name.lower()) if name else None
            if name.lower() == 'reset':
                self.model.reset(contact, channel_type='group' if context.startswith('[群聊发言人：') else 'dm')
                return Reply.from_text('已清空对话记录。')
            return Reply.from_text(cmd(contact, args) if cmd else f"未知命令，发送 {self.prefix}help 查看")
        if context:
            text = f"{context}\n{text}"
        return self.model.handle_reply(contact, text, request_id=request_id)
