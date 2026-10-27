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

    def handle(self, contact: str, text: str, *, context: str = "", member_key: str = "", member_name: str = "") -> str | None:
        return self.handle_reply(contact, text, context=context, member_key=member_key, member_name=member_name).text

    def handle_reply(self, contact: str, text: str, *, context: str = "", request_id=None,
                     member_key: str = "", member_name: str = "", avatar='', group_context_seq=None) -> Reply:
        text = text.strip()
        if self.prefix and text.startswith(self.prefix):
            words = text[len(self.prefix):].split()
            name, args = (words[0], words[1:]) if words else ('', [])
            cmd = self.commands.get(name.lower()) if name else None
            if name.lower() == 'reset':
                self.model.reset(contact, channel_type='group' if (context.startswith('[群聊发言人：') or member_key) else 'dm',
                                 member_key=member_key,**({'avatar':avatar}if avatar else {}))
                return Reply.from_text('已清空对话记录。')
            return Reply.from_text(cmd(contact, args) if cmd else f"未知命令，发送 {self.prefix}help 查看")
        if context:
            text = f"{context}\n{text}"
        extra = {}
        if avatar:
            extra['avatar'] = avatar
        if group_context_seq is not None:
            extra['group_context_seq'] = group_context_seq
        return self.model.handle_reply(contact, text, request_id=request_id,
                                       member_key=member_key, member_name=member_name, **extra)

    def archive_group(self, contact, source_id, text, member_key, member_name, avatar=''):
        archive = getattr(self.model, 'archive_group', None)
        if archive is None:
            return None
        return archive(contact, source_id, text, member_key, member_name, avatar=avatar)

    def observe_users(self, contact, channel_type, messages):
        observe = getattr(self.model, 'observe_users', None)
        return observe(contact, channel_type, messages) if observe is not None else None

    def archive_group_messages(self, contact, source_id, messages):
        archive = getattr(self.model, 'archive_group_messages', None)
        if archive is not None:
            return archive(contact, source_id, messages)
        # Compatibility for model adapters exposing only the old batch API.
        return self.archive_group(contact, source_id, '\n'.join(m['text'] for m in messages),
                                  messages[0]['member_key'], messages[0]['member_name'],
                                  avatar=messages[0].get('avatar', ''))
