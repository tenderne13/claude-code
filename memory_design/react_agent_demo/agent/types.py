"""Agent 类型定义."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class AgentStep:
    """一条 ReAct 执行步骤."""

    step_type: str
    content: str
    tool_name: str | None = None
    tool_input: dict[str, object] | None = None
    tool_result: dict[str, object] | None = None

