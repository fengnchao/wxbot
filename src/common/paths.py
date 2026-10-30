"""Repository root shared by every package.

Packages live in ``src/``, while runtime files (``config.*.toml``, ``data/``,
``web/dist``) stay at the repository root. Anchoring paths on module depth
breaks whenever a module moves, so all packages resolve the root here.
"""
from __future__ import annotations

import os
from pathlib import Path

_MARKER = 'pyproject.toml'


def _discover(start: Path) -> Path:
    for parent in start.parents:
        if (parent / _MARKER).is_file():
            return parent
    return start.parents[1]


def _root() -> Path:
    override = os.environ.get('WXBOT_ROOT')
    if override:
        return Path(override).expanduser().resolve()
    return _discover(Path(__file__).resolve())


REPO_ROOT = _root()
