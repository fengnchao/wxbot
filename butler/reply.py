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


def split_reply(text: str | None) -> list[str]:
    if not text or not text.strip():
        return []
    protected = _protected_ranges(text)
    result, start, i = [], 0, 0
    while i < len(text):
        if i in protected:
            i = protected[i]
            continue
        ch = text[i]
        if ch in _TERMINALS or ch in '\r\n':
            i += 1
            while i < len(text) and text[i] in _TERMINALS | _CLOSERS:
                i += 1
            part = text[start:i].strip()
            if part:
                result.append(part)
            start = i
        else:
            i += 1
    tail = text[start:].strip()
    if tail:
        result.append(tail)
    joined, prefix = [], ''
    for part in result:
        if all(ch in _TERMINALS | _CLOSERS for ch in part):
            if joined:
                joined[-1] += part
            else:
                prefix += part
        else:
            joined.append(prefix + part)
            prefix = ''
    return joined or ([prefix] if prefix else [])
