"""工具注册中心."""

from __future__ import annotations

from tools.base_tool import BaseTool


class ToolRegistry:
    """集中管理可用工具."""

    def __init__(self) -> None:
        self._tools: dict[str, BaseTool] = {}

    def register(self, tool: BaseTool) -> None:
        """注册工具."""

        self._tools[tool.name] = tool

    def get(self, name: str) -> BaseTool:
        """按名称获取工具."""

        if name not in self._tools:
            raise KeyError(f"未注册的工具: {name}")
        return self._tools[name]

    def list_definitions(self) -> list[dict[str, object]]:
        """导出所有工具定义，便于注入 LLM 上下文."""

        return [
            {
                "name": tool.name,
                "description": tool.description,
                "input_schema": tool.input_schema,
            }
            for tool in self._tools.values()
        ]

