"""记忆工具的结果格式化辅助函数."""

from __future__ import annotations

from memory.memory_entry import MemoryEntry


def format_memory_summary(entry: MemoryEntry) -> dict[str, str]:
    """将记忆条目转换为便于打印和序列化的摘要."""

    return {
        "name": entry.name,
        "type": entry.memory_type,
        "description": entry.description,
        "file": entry.path.name,
    }

