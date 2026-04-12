"""工具基类定义."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class BaseTool(ABC):
    """所有工具都遵循统一接口，便于注册和调度."""

    name: str
    description: str
    input_schema: dict[str, Any]

    @abstractmethod
    def execute(self, payload: dict[str, Any]) -> dict[str, Any]:
        """执行工具逻辑并返回结构化结果."""

