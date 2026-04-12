"""列出全部记忆工具."""

from __future__ import annotations

from memory.memory_store import MemoryStore
from memory.memory_tools import format_memory_summary
from tools.base_tool import BaseTool


class ListMemoriesTool(BaseTool):
    """列出当前所有记忆摘要."""

    name = "list_memories"
    description = "列出 MEMORY.md 中登记的全部记忆。"
    input_schema = {
        "type": "object",
        "properties": {},
        "additionalProperties": False,
    }

    def __init__(self, store: MemoryStore) -> None:
        self.store = store

    def execute(self, payload: dict[str, object]) -> dict[str, object]:
        entries = self.store.list_memories()
        return {"ok": True, "items": [format_memory_summary(entry) for entry in entries], "count": len(entries)}

