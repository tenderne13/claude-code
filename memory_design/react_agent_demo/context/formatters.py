"""上下文格式化工具."""

from __future__ import annotations

from memory.memory_entry import MemoryEntry


def format_recalled_memory(entry: MemoryEntry) -> str:
    """将召回记忆格式化为注入上下文的文本块."""

    return "\n".join(
        [
            f"## {entry.name}",
            f"path: {entry.path.name}",
            f"type: {entry.memory_type}",
            f"description: {entry.description}",
            entry.body.strip(),
        ]
    ).strip()

