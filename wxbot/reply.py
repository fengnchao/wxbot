"""Backend-neutral complete reply, safe to pass between queue workers."""
from dataclasses import dataclass


@dataclass(frozen=True)
class Reply:
    text: str | None
    parts: tuple[str, ...]
    mention_name: str = ''

    @classmethod
    def from_text(cls, text):
        return cls(text, (text,)) if isinstance(text, str) and text.strip() else cls(None, ())
