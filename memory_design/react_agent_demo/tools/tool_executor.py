"""工具统一执行器."""

from __future__ import annotations

from typing import Any

from tools.registry import ToolRegistry


class ToolExecutor:
    """负责实际调用工具，并统一异常格式."""

    def __init__(self, registry: ToolRegistry) -> None:
        self.registry = registry

    def execute(self, tool_name: str, payload: dict[str, Any]) -> dict[str, Any]:
        """执行指定工具."""

        try:
            return self.registry.get(tool_name).execute(payload)
        except Exception as exc:  # noqa: BLE001
            return {"ok": False, "error": str(exc), "tool": tool_name}

