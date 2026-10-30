"""Path-only recursive discovery, with large audio subtrees deferred."""
from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
from typing import Callable, Iterator

from game_formats.formats import SUPPORTED_SUFFIXES

DEFERRED = {"audiostreams", "a1_audio"}
SKIP = {".history", ".backup", ".git", "__pycache__"}


@dataclass(frozen=True)
class DiscoveryEntry:
    kind: str
    path: str
    parent: str


def discover(directory: str, cancelled: Callable[[], bool] = lambda: False) -> Iterator[DiscoveryEntry]:
    """Never open payloads; an explicitly selected audio root is traversed normally."""
    for base, directories, names in os.walk(directory, followlinks=False):
        if cancelled():
            return
        descend = []
        for name in sorted(directories, key=str.casefold):
            path = os.path.join(base, name)
            if name.lower() in SKIP or os.path.islink(path):
                continue
            kind = "deferred" if name.lower() in DEFERRED else "directory"
            yield DiscoveryEntry(kind, path, base)
            if kind != "deferred":
                descend.append(name)
        directories[:] = descend
        for name in sorted(names, key=str.casefold):
            if cancelled():
                return
            if name.lower().endswith(SUPPORTED_SUFFIXES) or name.lower() in {"lighttoc", "streamsetconfig"}:
                yield DiscoveryEntry("file", os.path.join(base, name), base)
