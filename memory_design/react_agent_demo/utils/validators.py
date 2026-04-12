"""输入校验工具."""

from __future__ import annotations

from config.settings import VALID_MEMORY_TYPES


def validate_memory_type(memory_type: str) -> str:
    """校验记忆类型是否合法."""

    if memory_type not in VALID_MEMORY_TYPES:
        raise ValueError(f"memory_type 必须是 {', '.join(VALID_MEMORY_TYPES)} 之一")
    return memory_type

