"""记忆搜索逻辑."""

from __future__ import annotations

from memory.memory_entry import MemoryEntry
from utils.tokenizer import tokenize


class MemorySearch:
    """基于关键词重叠的简单召回器."""

    def search(self, query: str, entries: list[MemoryEntry], limit: int) -> list[MemoryEntry]:
        """按 demo_memory_cli.py 的规则进行检索和打分."""

        query_tokens = tokenize(query)
        scored: list[MemoryEntry] = []
        for entry in entries:
            haystack = "\n".join([entry.name, entry.description, entry.body])
            memory_tokens = tokenize(haystack)
            overlap = len(query_tokens & memory_tokens)
            bonus = 0
            for token in query_tokens:
                if token and token in haystack.lower():
                    bonus += len(token)
            if overlap == 0 and bonus == 0:
                continue
            entry.score = overlap * 10 + bonus
            scored.append(entry)
        scored.sort(key=lambda item: (-item.score, item.path.name))
        return scored[:limit]
