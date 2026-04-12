"""演示用 LLM 客户端."""

from __future__ import annotations

import json
import re
import urllib.error
import urllib.request
from typing import Any

from context.context_builder import BuiltContext
from llm.message_builder import MessageBuilder
from llm.response_parser import ResponseParser
from llm.types import LLMClientConfig, LLMDecision, LLMTurn, ToolCall
from utils.logger import Logger
from utils.sanitizer import sanitize_value


class LLMClient:
    """支持 Mock 和真实 HTTP 两种模式的 LLM 客户端."""

    def __init__(self, config: LLMClientConfig, logger: Logger | None = None) -> None:
        self.config = config
        self.message_builder = MessageBuilder()
        self.response_parser = ResponseParser()
        self.logger = logger

    def next_turn(
        self,
        question: str,
        context: BuiltContext,
        conversation: list[dict[str, Any]],
        observations: list[dict[str, object]],
        tools: list[dict[str, object]],
    ) -> LLMTurn:
        """根据配置选择 Mock 或 HTTP 模式."""

        if self.config.mode == "http":
            return self._next_turn_http(context, conversation, tools)
        return self._next_turn_mock(question, observations)

    def _next_turn_mock(
        self,
        question: str,
        observations: list[dict[str, object]],
    ) -> LLMTurn:
        """规则驱动的 Mock 模式，用于稳定演示."""

        normalized = question.lower()
        if not observations:
            if any(keyword in question for keyword in ("列出", "有哪些", "所有记忆")):
                decision = LLMDecision(
                    thought="用户明确想查看当前记忆总览，我应先调用 list_memories 获取完整目录。",
                    action_name="list_memories",
                    action_input={},
                )
                return self._decision_to_turn(decision)
            if any(keyword in question for keyword in ("删除记忆", "忘记", "删除")) and ".md" in question:
                filename = question.split()[-1]
                decision = LLMDecision(
                    thought="用户看起来希望删除指定记忆文件，我先调用 delete_memory。",
                    action_name="delete_memory",
                    action_input={"filename": filename},
                )
                return self._decision_to_turn(decision)
            if any(keyword in question for keyword in ("记住", "保存偏好", "写入记忆")):
                memory_name = self._infer_memory_name(question)
                decision = LLMDecision(
                    thought="用户在要求写入长期记忆，我先调用 upsert_memory 保存一条 user 记忆。",
                    action_name="upsert_memory",
                    action_input={
                        "memory_type": "user",
                        "name": memory_name,
                        "description": question[:40],
                        "body": question,
                        "filename": self._infer_memory_filename(question),
                    },
                )
                return self._decision_to_turn(decision)
            decision = LLMDecision(
                thought="我需要先搜索与问题最相关的记忆，再决定是否继续读取详情。",
                action_name="search_memories",
                action_input={"query": question, "limit": 3},
            )
            return self._decision_to_turn(decision)

        last_observation = observations[-1]
        last_tool = str(last_observation.get("tool_name", ""))
        result = last_observation.get("result", {})
        if last_tool == "search_memories":
            items = result.get("items", []) if isinstance(result, dict) else []
            if items:
                first = items[0]
                if isinstance(first, dict) and "file" in first:
                    decision = LLMDecision(
                        thought="搜索已经找到候选记忆。为了给出更准确答案，我继续读取最相关的记忆正文。",
                        action_name="read_memory",
                        action_input={"filename": str(first["file"])},
                    )
                    return self._decision_to_turn(decision)
            return self._decision_to_turn(LLMDecision(thought="没有检索到相关记忆，我直接基于现有上下文给出说明。", final_answer="当前没有命中相关长期记忆，可以先通过 remember 命令补充后再演示召回。"))
        if last_tool == "read_memory" and isinstance(result, dict) and result.get("ok"):
            item = result.get("item", {})
            if isinstance(item, dict):
                return self._decision_to_turn(LLMDecision(
                    thought="我已经拿到最相关记忆正文，现在可以总结并回答用户问题。",
                    final_answer=f"根据记忆 `{item.get('file', '')}`：{item.get('body', '')}",
                ))
        if last_tool == "list_memories" and isinstance(result, dict):
            count = result.get("count", 0)
            items = result.get("items", [])
            names = "、".join(item["name"] for item in items[:5] if isinstance(item, dict)) if isinstance(items, list) else ""
            return self._decision_to_turn(LLMDecision(
                thought="目录已经拿到，我直接汇总数量和名称给用户。",
                final_answer=f"当前共有 {count} 条记忆。{('示例包括：' + names) if names else ''}",
            ))
        if last_tool == "upsert_memory" and isinstance(result, dict) and result.get("ok"):
            return self._decision_to_turn(LLMDecision(thought="写入已经成功，可以结束循环。", final_answer=f"长期记忆已写入：{result.get('file', '')}"))
        if last_tool == "delete_memory" and isinstance(result, dict):
            if result.get("ok"):
                return self._decision_to_turn(LLMDecision(thought="删除成功，可以告知用户结果。", final_answer=f"记忆已删除：{result.get('file', '')}"))
            return self._decision_to_turn(LLMDecision(thought="删除失败，没有找到目标文件。", final_answer=f"删除失败，未找到记忆：{result.get('file', '')}"))
        fallback = "我已经完成必要的工具调用。"
        if "lang" in normalized:
            fallback = "我已经拿到足够信息来回答编程语言偏好问题。"
        return self._decision_to_turn(LLMDecision(thought=fallback, final_answer="演示流程已完成，但当前规则未命中特定总结模板。"))

    def _infer_memory_name(self, question: str) -> str:
        """为显式写入场景生成更清晰的记忆标题."""

        normalized = question.lower()
        if any(keyword in normalized for keyword in ("java", "python", "编程语言")):
            return "编程语言偏好"
        if any(keyword in question for keyword in ("饮食", "茴香", "大蒜", "韭菜", "香菜", "菜")):
            return "饮食偏好"
        if any(keyword in normalized for keyword in ("emoji",)) or any(keyword in question for keyword in ("表情", "emoji")):
            return "输出风格约束"
        cleaned = re.sub(r"\s+", " ", question).strip(" ：:，,。.；;")
        return cleaned[:24] or "用户偏好"

    def _infer_memory_filename(self, question: str) -> str:
        """为显式写入场景生成稳定的详细记忆文件名."""

        normalized = question.lower()
        if any(keyword in normalized for keyword in ("java", "python", "编程语言")):
            return "user_programming_preference.md"
        if any(keyword in question for keyword in ("饮食", "茴香", "大蒜", "韭菜", "香菜", "菜")):
            return "user_dietary_preference.md"
        if any(keyword in normalized for keyword in ("emoji",)) or any(keyword in question for keyword in ("表情", "emoji")):
            return "feedback_output_style.md"
        cleaned = re.sub(r"[^a-z0-9]+", "_", normalized).strip("_")
        topic = cleaned[:40] or "memory_detail"
        return f"user_{topic}.md"

    def _decision_to_turn(self, decision: LLMDecision) -> LLMTurn:
        """将旧的 mock 决策对象包装成统一 turn 结构."""

        tool_calls: list[ToolCall] = []
        if decision.action_name and decision.action_input is not None:
            tool_calls.append(ToolCall(id="mock-tool-use", name=decision.action_name, input=decision.action_input))
        return LLMTurn(
            thought=decision.thought,
            assistant_text=decision.final_answer or decision.thought,
            tool_calls=tool_calls,
            final_answer=decision.final_answer,
        )

    def _next_turn_http(
        self,
        context: BuiltContext,
        conversation: list[dict[str, Any]],
        tools: list[dict[str, object]],
    ) -> LLMTurn:
        """调用真实 HTTP 模型接口，并解析 tool_use."""

        payload = self.message_builder.build_payload(
            messages=conversation,
            model=self.config.model,
            max_tokens=self.config.max_tokens,
            tools=tools,
            system_prompt=context.system_prompt,
        )
        self._log_request(payload)
        response = self._call_model(payload)
        return self.response_parser.parse_http_turn(response)

    def build_initial_messages(self, context: BuiltContext) -> list[dict[str, Any]]:
        """为首轮请求构造用户消息."""

        return self.message_builder.build_initial_messages(context)

    def _call_model(self, payload: dict[str, Any]) -> dict[str, Any]:
        """执行真实 HTTP 请求."""

        sanitized_payload = sanitize_value(payload)
        body = json.dumps(sanitized_payload, ensure_ascii=False).encode("utf-8")
        headers = {
            "Content-Type": "application/json; charset=utf-8",
            "Accept": "application/json",
            "anthropic-version": "2023-06-01",
        }
        if self.config.api_key:
            headers["Authorization"] = f"Bearer {self.config.api_key}"
            headers["x-api-key"] = self.config.api_key
        last_error: Exception | None = None
        for request_url in self._resolve_request_urls(self.config.base_url):
            if self.logger is not None:
                self.logger.detail("LLM_HTTP", f"POST {request_url}")
            request = urllib.request.Request(request_url, data=body, headers=headers, method="POST")
            try:
                with urllib.request.urlopen(request, timeout=self.config.timeout) as response:
                    raw = response.read().decode("utf-8")
                    return json.loads(raw)
            except urllib.error.HTTPError as exc:
                error_body = exc.read().decode("utf-8", errors="replace")
                if exc.code == 404:
                    last_error = RuntimeError(f"HTTP 404 on {request_url}: {error_body}")
                    continue
                raise RuntimeError(f"HTTP {exc.code} on {request_url}: {error_body}") from exc
            except urllib.error.URLError as exc:
                raise RuntimeError(f"request failed on {request_url}: {exc}") from exc
        raise RuntimeError(str(last_error) if last_error else "request failed")

    def _resolve_request_urls(self, base_url: str) -> list[str]:
        """兼容不同服务端的 messages 路径."""

        normalized = base_url.rstrip("/")
        if normalized.endswith("/v1/messages") or normalized.endswith("/messages"):
            return [normalized]
        return [f"{normalized}/v1/messages", f"{normalized}/messages", normalized]

    def _log_request(self, payload: dict[str, Any]) -> None:
        """在 verbose 模式下打印真实出站请求体."""

        if self.logger is None or not self.logger.verbose:
            return
        payload_without_tools = {key: value for key, value in payload.items() if key != "tools"}
        preview = {
            "model": payload.get("model"),
            "max_tokens": payload.get("max_tokens"),
            "tools": [tool.get("name") for tool in payload.get("tools", []) if isinstance(tool, dict)],
            "message_count": len(payload.get("messages", [])) if isinstance(payload.get("messages"), list) else 0,
            "system_block_count": len(payload.get("system", [])) if isinstance(payload.get("system"), list) else 0,
        }
        self.logger.detail("LLM_REQUEST_PREVIEW", json.dumps(preview, ensure_ascii=False, indent=2))
        self.logger.detail("LLM_REQUEST", json.dumps(sanitize_value(payload_without_tools), ensure_ascii=False, indent=2))
