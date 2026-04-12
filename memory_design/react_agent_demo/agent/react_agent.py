"""ReAct Agent 对外封装."""

from __future__ import annotations

from dataclasses import dataclass, field

from agent.agent_loop import AgentLoop
from context.context_builder import ContextBuilder
from context.context_manager import ContextManager
from llm.client import LLMClient
from llm.types import LLMClientConfig
from memory.auto_memory import AutoMemoryManager
from memory.memory_store import MemoryStore
from tools.definitions.delete_memory import DeleteMemoryTool
from tools.definitions.list_memories import ListMemoriesTool
from tools.definitions.read_memory import ReadMemoryTool
from tools.definitions.search_memories import SearchMemoriesTool
from tools.definitions.upsert_memory import UpsertMemoryTool
from tools.registry import ToolRegistry
from tools.tool_executor import ToolExecutor
from utils.logger import Logger


@dataclass(slots=True)
class ReActAgent:
    """面向 CLI 的 Agent 门面类."""

    store: MemoryStore
    logger: Logger
    llm_config: LLMClientConfig
    enable_auto_memory: bool = True
    registry: ToolRegistry = field(init=False)
    loop: AgentLoop = field(init=False)

    def __post_init__(self) -> None:
        self.registry = ToolRegistry()
        self.registry.register(ReadMemoryTool(self.store))
        self.registry.register(UpsertMemoryTool(self.store))
        self.registry.register(DeleteMemoryTool(self.store))
        self.loop = AgentLoop(
            context_builder=ContextBuilder(self.store),
            context_manager=ContextManager(),
            llm_client=LLMClient(self.llm_config, logger=self.logger),
            tool_executor=ToolExecutor(self.registry),
            logger=self.logger,
            auto_memory=AutoMemoryManager(self.store, self.logger) if self.enable_auto_memory else None,
        )

    def run(self, question: str, max_steps: int) -> str:
        """运行一轮 ReAct 问答."""

        answer, _steps = self.loop.run(
            question=question,
            max_steps=max_steps,
            tool_names=[definition["name"] for definition in self.registry.list_definitions()],
        )
        return answer
