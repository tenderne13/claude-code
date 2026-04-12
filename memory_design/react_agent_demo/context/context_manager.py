"""上下文状态管理."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(slots=True)
class ContextManager:
    """维护当前会话的用户问题、历史消息与工具观察结果."""

    history: list[dict[str, object]] = field(default_factory=list)
    observations: list[dict[str, object]] = field(default_factory=list)

    def add_user_message(self, text: str) -> None:
        self.history.append({"role": "user", "content": text})

    def add_assistant_message(self, text: str) -> None:
        self.history.append({"role": "assistant", "content": text})

    def add_observation(self, observation: dict[str, object]) -> None:
        self.observations.append(observation)

