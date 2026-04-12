"""ReAct 主循环."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from agent.types import AgentStep
from context.context_builder import ContextBuilder
from context.context_manager import ContextManager
from llm.client import LLMClient
from llm.message_builder import MessageBuilder
from memory.auto_memory import AutoMemoryManager
from tools.tool_executor import ToolExecutor
from utils.logger import Logger


@dataclass(slots=True)
class AgentLoop:
    """协调上下文构建、LLM 决策和工具执行的总控流程."""

    context_builder: ContextBuilder
    context_manager: ContextManager
    llm_client: LLMClient
    tool_executor: ToolExecutor
    logger: Logger
    auto_memory: AutoMemoryManager | None = None
    message_builder: MessageBuilder = field(default_factory=MessageBuilder)

    def run(self, question: str, max_steps: int, tool_names: list[str]) -> tuple[str, list[AgentStep]]:
        """执行完整的 ReAct 循环，直到拿到最终答案或步数耗尽."""

        self.logger.info("AGENT", f"开始 ReAct 循环，最大步数: {max_steps}")
        steps: list[AgentStep] = []
        self.context_manager.add_user_message(question)
        conversation: list[dict[str, Any]] | None = None
        for index in range(1, max_steps + 1):
            built_context = self.context_builder.build(question)
            preview = self.message_builder.build_preview(built_context, tool_names)
            self.logger.detail("CONTEXT", json.dumps(preview, ensure_ascii=False, indent=2))
            if conversation is None:
                conversation = self.llm_client.build_initial_messages(built_context)
            turn = self.llm_client.next_turn(
                question=question,
                context=built_context,
                conversation=conversation,
                observations=self.context_manager.observations,
                tools=self._tool_definitions(tool_names),
            )
            if turn.raw_response is not None:
                self.logger.detail("RAW_RESPONSE", json.dumps(turn.raw_response, ensure_ascii=False, indent=2))
            self.logger.info(f"THOUGHT-{index}", turn.thought)
            steps.append(AgentStep(step_type="thought", content=turn.thought))
            if turn.final_answer:
                self.logger.info("DONE", "循环结束，返回最终答案")
                self.context_manager.add_assistant_message(turn.final_answer)
                if self.auto_memory is not None:
                    used_tools = [step.tool_name for step in steps if step.tool_name]
                    self.auto_memory.run_post_turn_extraction(
                        question=question,
                        final_answer=turn.final_answer,
                        used_tools=used_tools,
                    )
                steps.append(AgentStep(step_type="final", content=turn.final_answer))
                return turn.final_answer, steps
            if not turn.tool_calls:
                break
            raw_content = None
            if isinstance(turn.raw_response, dict):
                candidate = turn.raw_response.get("content")
                if isinstance(candidate, list):
                    raw_content = candidate
            assistant_blocks: list[dict[str, Any]] = []
            if raw_content is not None:
                assistant_blocks = raw_content
            else:
                if turn.assistant_text:
                    assistant_blocks.append({"type": "text", "text": turn.assistant_text})
            tool_result_blocks: list[dict[str, Any]] = []
            for tool_call in turn.tool_calls:
                self.logger.info(f"ACTION-{index}", f"调用工具: {tool_call.name}")
                self.logger.info(f"INPUT-{index}", json.dumps(tool_call.input, ensure_ascii=False))
                result = self.tool_executor.execute(tool_call.name, tool_call.input)
                self.logger.info("EXECUTE", f"执行工具: {tool_call.name}")
                self.logger.info(f"RESULT-{index}", json.dumps(result, ensure_ascii=False))
                observation = {"tool_name": tool_call.name, "result": result}
                self.context_manager.add_observation(observation)
                tool_result_blocks.append(
                    {
                        "type": "tool_result",
                        "tool_use_id": tool_call.id,
                        "content": json.dumps(result, ensure_ascii=False),
                        "is_error": not bool(result.get("ok", False)) if isinstance(result, dict) else False,
                    }
                )
                self.logger.info(f"OBSERVATION-{index}", "已记录工具返回结果，进入下一轮推理。")
                steps.append(
                    AgentStep(
                        step_type="action",
                        content=f"调用工具 {tool_call.name}",
                        tool_name=tool_call.name,
                        tool_input=tool_call.input,
                        tool_result=result,
                    )
                )
            conversation.append({"role": "assistant", "content": assistant_blocks})
            conversation.append({"role": "user", "content": tool_result_blocks})
        fallback = "已达到最大步数限制，演示停止。"
        self.context_manager.add_assistant_message(fallback)
        if self.auto_memory is not None:
            used_tools = [step.tool_name for step in steps if step.tool_name]
            self.auto_memory.run_post_turn_extraction(
                question=question,
                final_answer=fallback,
                used_tools=used_tools,
            )
        return fallback, steps

    def _tool_definitions(self, tool_names: list[str]) -> list[dict[str, object]]:
        """根据注册表导出工具定义."""

        definitions = self.tool_executor.registry.list_definitions()
        return [definition for definition in definitions if str(definition.get("name")) in set(tool_names)]
