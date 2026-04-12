"""记忆条目定义."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(slots=True)
class MemoryEntry:
    """一条长期记忆的标准结构."""

    memory_type: str
    path: Path
    name: str
    description: str
    body: str
    score: int = 0

