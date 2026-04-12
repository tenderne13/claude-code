"""新增或更新记忆工具."""

from __future__ import annotations

from memory.memory_store import MemoryStore
from tools.base_tool import BaseTool


class UpsertMemoryTool(BaseTool):
    """创建或更新长期记忆."""

    name = "upsert_memory"
    description = "创建或覆盖一条长期记忆并更新 MEMORY.md。"
    input_schema = {
        "type": "object",
        "properties": {
            "memory_type": {"type": "string"},
            "name": {"type": "string"},
            "description": {"type": "string"},
            "body": {"type": "string"},
            "filename": {"type": "string"},
        },
        "required": ["memory_type", "name", "description", "body"],
        "additionalProperties": False,
    }

    def __init__(self, store: MemoryStore) -> None:
        self.store = store

    def execute(self, payload: dict[str, object]) -> dict[str, object]:
        file_path = self.store.upsert_memory(
            memory_type=str(payload["memory_type"]),
            name=str(payload["name"]),
            description=str(payload["description"]),
            body=str(payload["body"]),
            filename=str(payload["filename"]) if "filename" in payload else None,
        )
        return {"ok": True, "file": file_path.name}

