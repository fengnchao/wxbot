"""Split final user-visible prose without cutting URLs or code."""
from __future__ import annotations

import re

_FENCE_START = re.compile(r'(?m)^ {0,3}(?P<marker>`{3,}|~{3,})(?P<info>[^\r\n]*)(?:\r?\n|$)')
_INLINE_OR_URL = re.compile(
    r'(?P<ticks>`+)(?!`)[\s\S]*?(?<!`)(?P=ticks)(?!`)|'
    r'https?://[^\s<>`。？！，”’）】》」』]+')
_TERMINALS = frozenset('。？！!?')
_CLOSERS = frozenset('”’"\'）)]】》」』')


def _protected_ranges(text):
    fences = {m.start(): m for m in _FENCE_START.finditer(text)
              if m['marker'][0] != '`' or '`' not in m['info']}
    ranges, i = {}, 0
    while i < len(text):
        fence = fences.get(i)
        if fence:
            marker = fence['marker']
            close = re.compile(r'(?m)^ {0,3}' + re.escape(marker[0]) +
                               r'{' + str(len(marker)) + r',}[ \t]*(?=\r?$)')
            end = close.search(text, fence.end())
            ranges[i] = end.end() if end else len(text)
            i = ranges[i]
        else:
            token = _INLINE_OR_URL.match(text, i)
            if token:
                ranges[i] = token.end()
                i = token.end()
            else:
                i += 1
    return ranges


def validate_chunk_chars(value):
    if type(value) is not int or not 100 <= value <= 2000:
        raise ValueError('reply.chunk_chars 必须是 100–2000 的整数')
    return value


def split_reply(text: str | None, chunk_chars: int = 500) -> list[str]:
    """Preserve prose verbatim; protect URLs/code even if a token exceeds the soft limit."""
    limit = validate_chunk_chars(chunk_chars)
    if not text or not text.strip():
        return []
    protected = _protected_ranges(text)
    units, i = [], 0
    while i < len(text):
        end = protected.get(i, i + 1)
        units.append((i, end))
        i = end
    parts, start, cursor = [], 0, 0
    while cursor < len(units):
        end_cursor = cursor
        while end_cursor < len(units) and units[end_cursor][1] - start <= limit:
            end_cursor += 1
        if end_cursor == len(units):
            parts.append(text[start:])
            break
        if end_cursor == cursor:
            end_cursor += 1  # An indivisible URL/code span.
        end = units[end_cursor - 1][1]
        if end - start <= limit:
            # Prefer a boundary in the latter half, avoiding tiny bubbles.
            boundaries = [(n + 1, b) for n, (a, b) in enumerate(units[cursor:end_cursor], cursor)
                          if b - a == 1 and b - start >= limit // 2
                          and text[a] in _TERMINALS | frozenset('\r\n')]
            paragraphs = [pair for pair in boundaries if text[pair[1]-1] in '\r\n']
            if paragraphs or boundaries:
                end_cursor, end = (paragraphs or boundaries)[-1]
        part = text[start:end]
        if not part.strip() and parts:
            parts[-1] += part
        else:
            parts.append(part)
        start, cursor = end, end_cursor
    if parts and not parts[-1].strip() and len(parts) > 1:
        parts[-2] += parts.pop()
    return parts
