"""搜索记忆工具."""

from __future__ import annotations

from memory.memory_store import MemoryStore
from memory.memory_tools import format_memory_summary
from tools.base_tool import BaseTool


class SearchMemoriesTool(BaseTool):
    """按关键词搜索记忆."""

    name = "search_memories"
    description = "按关键词搜索最相关的长期记忆。"
    input_schema = {
        "type": "object",
        "properties": {
            "query": {"type": "string"},
            "limit": {"type": "integer", "default": 5},
        },
        "required": ["query"],
        "additionalProperties": False,
    }

    def __init__(self, store: MemoryStore) -> None:
        self.store = store

    def execute(self, payload: dict[str, object]) -> dict[str, object]:
        query = str(payload["query"])
        limit = int(payload.get("limit", 5))
        entries = self.store.search_memories(query, limit=limit)
        return {
            "ok": True,
            "items": [
                {
                    **format_memory_summary(entry),
                    "score": entry.score,
                }
                for entry in entries
            ],
            "count": len(entries),
        }
