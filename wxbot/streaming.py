"""Incremental final-answer sentence boundaries; never splits protected tokens."""
import re


class SentenceBuffer:
    limit = 262144

    def __init__(self):
        self.pending = ''

    def feed(self, text):
        self.pending += text
        if len(self.pending) > self.limit:
            raise ValueError('stream sentence exceeds buffer limit')
        return self._take(False)

    def finish(self):
        return self._take(True)

    def _take(self, final):
        text = self.pending
        protected = set()
        for match in re.finditer(r'```[\s\S]*?(?:```|$)|`[^`]*(?:`|$)|(?:https?://|www\.)[^\s]+', text):
            protected.update(range(match.start(), match.end()))
        parts, start, i = [], 0, 0
        while i < len(text):
            if i in protected or text[i] not in '。！？!?':
                i += 1
                continue
            end = i + 1
            while end < len(text) and text[end] in '。！？!?”’\"\'）)]】》」』':
                end += 1
            if end == len(text) and not final:
                break
            parts.append(text[start:end])
            start = i = end
        if final and text[start:]:
            parts.append(text[start:])
            start = len(text)
        self.pending = text[start:]
        return parts
