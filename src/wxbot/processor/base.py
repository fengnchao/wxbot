"""消息处理器：收到对方的一条消息，返回要回复的文字（返回 None 表示不回复）。"""
from ..reply import Reply


class Processor:
    def handle(self, contact: str, text: str) -> str | None:
        raise NotImplementedError

    def handle_reply(self, contact: str, text: str, *, request_id=None, member_key="", member_name="",channel_type='dm',on_event=None,**kwargs) -> Reply:
        from common.model_stream import bind,emit,answer
        with bind(on_event):
            emit('backend',provider=getattr(self,'backend',self.__class__.__name__),model=getattr(self,'model',''),streaming=False)
            reply=Reply.from_text(self.handle(contact, text))
            answer(reply.text)
            emit('complete')
            return reply

    def reset(self, contact: str, *, channel_type='dm', member_key="") -> None:
        pass


class EchoProcessor(Processor):
    """调试用：原样返回。"""

    def handle(self, contact: str, text: str) -> str | None:
        return f"收到：{text}"
