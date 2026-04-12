"""消息构建器."""

from __future__ import annotations

from typing import Any

from context.context_builder import BuiltContext
from utils.sanitizer import sanitize_value


class MessageBuilder:
    """为展示目的构造一个可读的消息摘要."""

    def build_preview(self, context: BuiltContext, tool_names: list[str]) -> dict[str, object]:
        """输出一份可打印的“模型实际看到的内容”摘要."""

        return sanitize_value({
            "question": context.user_question,
            "tools": tool_names,
            "recalled_memories": [entry.path.name for entry in context.recalled_memories],
            "system_prompt_preview": context.system_prompt[:1000],
        })

    def build_initial_messages(self, context: BuiltContext) -> list[dict[str, Any]]:
        """对齐 demo_memory_cli.py 的首轮用户消息结构."""

        content: list[dict[str, str]] = [
            {"type": "text", "text": "<system-reminder>\n以下是长期记忆索引 MEMORY.md：\n" + context.index_text + "\n</system-reminder>"}
        ]
        if context.recalled_memories:
            recalled_text = "\n\n".join(
                [
                    "\n".join(
                        [
                            f"## {entry.name}",
                            f"path: {entry.path.name}",
                            f"type: {entry.memory_type}",
                            f"description: {entry.description}",
                            entry.body.strip(),
                        ]
                    ).strip()
                    for entry in context.recalled_memories
                ]
            )
            content.append({"type": "text", "text": "<system-reminder>\n以下是召回到的相关记忆：\n" + recalled_text + "\n</system-reminder>"})
        content.append({"type": "text", "text": context.user_question})
        return sanitize_value([{"role": "user", "content": content}])

    def build_payload(
        self,
        messages: list[dict[str, Any]],
        model: str,
        max_tokens: int,
        tools: list[dict[str, Any]],
        system_prompt: str,
    ) -> dict[str, Any]:
        """构造 HTTP 模型请求载荷."""

        return sanitize_value({
            "model": model,
            "messages": messages,
            "system": [
                {"type": "text", "text": "x-demo-billing-header: cc_version=demo; cc_entrypoint=python-cli;"},
                {"type": "text", "text": system_prompt},
            ],
            "tools": tools,
            "max_tokens": max_tokens,
            "thinking": {"type": "adaptive"},
            "metadata": {"source": "react-agent-demo"},
        })
