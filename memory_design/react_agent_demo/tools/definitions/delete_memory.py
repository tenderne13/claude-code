"""删除记忆工具."""

from __future__ import annotations

from memory.memory_store import MemoryStore
from tools.base_tool import BaseTool


class DeleteMemoryTool(BaseTool):
    """删除长期记忆."""

    name = "delete_memory"
    description = "删除一条长期记忆，并同步移除索引项。"
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
        deleted = self.store.delete_memory(filename)
        return {"ok": deleted, "file": filename}

