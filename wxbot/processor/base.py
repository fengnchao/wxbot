"""消息处理器：收到对方的一条消息，返回要回复的文字（返回 None 表示不回复）。"""


class Processor:
    def handle(self, contact: str, text: str) -> str | None:
        raise NotImplementedError

    def reset(self, contact: str) -> None:
        pass


class EchoProcessor(Processor):
    """调试用：原样返回。"""

    def handle(self, contact: str, text: str) -> str | None:
        return f"收到：{text}"
