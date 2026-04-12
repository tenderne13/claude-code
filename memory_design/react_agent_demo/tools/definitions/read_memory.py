"""读取单条记忆工具."""

from __future__ import annotations

from memory.memory_store import MemoryStore
from tools.base_tool import BaseTool


class ReadMemoryTool(BaseTool):
    """读取单个记忆文件的完整内容."""

    name = "read_memory"
    description = "根据文件名读取一条长期记忆。"
    input_schema = {
        "type": "object",
        "properties": {"filename": {"type": "string"}},
        "required": ["filename"],
        "additionalProperties": False,
    }

    def __init__(self, store: MemoryStore) -> None:
        self.store = store

    def execute(self, payload: dict[str, object]) -> dict[str, object]:
        filename = str(payload["filename"])
        entry = self.store.read_memory(filename)
        if entry is None:
            return {"ok": False, "error": f"未找到记忆文件: {filename}"}
        return {
            "ok": True,
            "item": {
                "name": entry.name,
                "type": entry.memory_type,
                "description": entry.description,
                "file": entry.path.name,
                "body": entry.body,
            },
        }

