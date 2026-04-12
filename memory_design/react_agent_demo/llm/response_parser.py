"""响应解析器."""

from __future__ import annotations

import re
from typing import Any

from llm.types import LLMDecision, LLMTurn, ToolCall


class ResponseParser:
    """将字典响应解析为结构化决策."""

    def parse(self, raw: dict[str, Any]) -> LLMDecision:
        """解析原始决策数据."""

        return LLMDecision(
            thought=str(raw["thought"]),
            action_name=str(raw["action_name"]) if raw.get("action_name") else None,
            action_input=dict(raw["action_input"]) if raw.get("action_input") else None,
            final_answer=str(raw["final_answer"]) if raw.get("final_answer") else None,
        )

    def parse_http_turn(self, raw: dict[str, Any]) -> LLMTurn:
        """解析 HTTP 模型返回，抽取文本和工具调用."""

        content = raw.get("content", [])
        assistant_texts: list[str] = []
        tool_calls: list[ToolCall] = []
        if isinstance(content, list):
            for block in content:
                if not isinstance(block, dict):
                    continue
                if block.get("type") == "text" and isinstance(block.get("text"), str):
                    text = block["text"].strip()
                    if text:
                        assistant_texts.append(text)
                if block.get("type") == "tool_use":
                    tool_calls.append(
                        ToolCall(
                            id=str(block.get("id", "")),
                            name=str(block.get("name", "")),
                            input=dict(block.get("input", {})) if isinstance(block.get("input"), dict) else {},
                        )
                    )
        assistant_text = "\n".join(assistant_texts).strip()
        if not assistant_text:
            assistant_text = self._extract_text_fallback(raw)
        extracted_final = self._extract_final_answer(assistant_text)
        final_answer = None if tool_calls else (extracted_final or assistant_text)
        thought = self._extract_thought(assistant_text) or assistant_text or ("模型返回了工具调用。" if tool_calls else "模型未返回可解析内容。")
        return LLMTurn(
            thought=thought,
            assistant_text=assistant_text,
            tool_calls=tool_calls,
            final_answer=final_answer,
            raw_response=raw,
        )

    def _extract_text_fallback(self, raw: dict[str, Any]) -> str:
        """兼容不同接口返回格式，尽量抽取文本结果."""

        choices = raw.get("choices")
        if isinstance(choices, list) and choices:
            first = choices[0]
            if isinstance(first, dict):
                message = first.get("message")
                if isinstance(message, dict):
                    message_content = message.get("content")
                    if isinstance(message_content, str):
                        return message_content.strip()
                    if isinstance(message_content, list):
                        texts = [
                            item.get("text", "").strip()
                            for item in message_content
                            if isinstance(item, dict) and isinstance(item.get("text"), str) and item.get("text", "").strip()
                        ]
                        if texts:
                            return "\n".join(texts)
                text = first.get("text")
                if isinstance(text, str):
                    return text.strip()
        output_text = raw.get("output_text")
        if isinstance(output_text, str):
            return output_text.strip()
        result = raw.get("result")
        if isinstance(result, str):
            return result.strip()
        return ""

    def _extract_final_answer(self, text: str) -> str | None:
        """从结构化 ReAct 文本中提取最终回答部分."""

        patterns = [
            r"\*\*Final Answer\*\*:\s*(.+)$",
            r"##\s*Final Answer\s*(.+)$",
            r"Final Answer:\s*(.+)$",
            r"##\s*最终答案\s*(.+)$",
            r"最终答案[:：]\s*(.+)$",
        ]
        for pattern in patterns:
            match = re.search(pattern, text, flags=re.DOTALL)
            if match:
                return match.group(1).strip()
        return None

    def _extract_thought(self, text: str) -> str | None:
        """优先提取 Thought 段，避免日志过长."""

        patterns = [
            r"\*\*Thought\*\*:\s*(.+?)(?:\n\s*\*\*Action\*\*|\Z)",
            r"##\s*Thought\s*(.+?)(?:\n\s*##\s*Action|\Z)",
            r"Thought:\s*(.+?)(?:\n\s*Action:|\Z)",
            r"##\s*思考\s*(.+?)(?:\n\s*##\s*行动|\Z)",
            r"思考[:：]\s*(.+?)(?:\n\s*行动[:：]|\Z)",
        ]
        for pattern in patterns:
            match = re.search(pattern, text, flags=re.DOTALL)
            if match:
                return match.group(1).strip()
        return None
