"""命令路由：/ 开头的走命令，其他交给模型。新增命令在 COMMANDS 里加一项即可。"""
from .base import Processor


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

    def handle(self, contact: str, text: str) -> str | None:
        text = text.strip()
        if text.startswith(self.prefix):
            name, *args = text[len(self.prefix):].split()
            cmd = self.commands.get(name.lower()) if name else None
            return cmd(contact, args) if cmd else f"未知命令，发送 {self.prefix}help 查看"
        return self.model.handle(contact, text)
