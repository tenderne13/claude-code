"""LLM 决策结构定义."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(slots=True)
class ToolCall:
    """模型发起的一次工具调用."""

    id: str
    name: str
    input: dict[str, object]


@dataclass(slots=True)
class LLMDecision:
    """单步决策结果."""

    thought: str
    action_name: str | None = None
    action_input: dict[str, object] | None = None
    final_answer: str | None = None


@dataclass(slots=True)
class LLMClientConfig:
    """LLM 客户端运行配置."""

    mode: str = "http"
    model: str = "kimi-k2.5"
    base_url: str = ""
    api_key: str | None = None
    max_tokens: int = 2048
    timeout: int = 60


@dataclass(slots=True)
class LLMTurn:
    """一次模型返回的统一抽象."""

    thought: str
    assistant_text: str = ""
    tool_calls: list[ToolCall] = field(default_factory=list)
    final_answer: str | None = None
    raw_response: dict[str, object] | None = None
