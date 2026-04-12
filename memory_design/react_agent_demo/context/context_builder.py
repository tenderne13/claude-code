"""上下文构建器."""

from __future__ import annotations

from dataclasses import dataclass

from config.settings import DEFAULT_TOP_K, SYSTEM_PROMPT_TEMPLATE
from context.formatters import format_recalled_memory
from memory.memory_entry import MemoryEntry
from memory.memory_store import MemoryStore
from utils.sanitizer import sanitize_text


@dataclass(slots=True)
class BuiltContext:
    """一次构建后的上下文快照."""

    system_prompt: str
    index_text: str
    recalled_memories: list[MemoryEntry]
    user_question: str


class ContextBuilder:
    """负责拼装系统提示词、索引与召回记忆."""

    def __init__(self, store: MemoryStore, top_k: int = DEFAULT_TOP_K) -> None:
        self.store = store
        self.top_k = top_k

    def build(self, question: str) -> BuiltContext:
        """构建完整上下文，用于打印和驱动 Agent 决策."""

        question = sanitize_text(question)
        self.store.ensure()
        recalled = self.store.search(question, limit=self.top_k)
        index_text = sanitize_text(self.store.index_path.read_text(encoding="utf-8").strip())
        recalled_text = "\n\n".join(format_recalled_memory(entry) for entry in recalled) if recalled else "无命中记忆。"
        system_prompt = "\n\n".join([SYSTEM_PROMPT_TEMPLATE, "以下是长期记忆索引 MEMORY.md：", index_text, "以下是召回到的相关记忆：", recalled_text])
        return BuiltContext(
            system_prompt=system_prompt,
            index_text=index_text,
            recalled_memories=recalled,
            user_question=question,
        )
