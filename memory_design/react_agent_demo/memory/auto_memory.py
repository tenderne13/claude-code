"""演示版 Auto Memory / extractMemories 实现."""

from __future__ import annotations

import re
from dataclasses import dataclass

from memory.memory_store import MemoryStore, build_memory_filename
from utils.logger import Logger


@dataclass(slots=True)
class ExtractedMemory:
    """一次自动抽取得到的记忆候选."""

    memory_type: str
    name: str
    description: str
    body: str
    filename: str


class AutoMemoryManager:
    """模拟 Claude Code 的回合后记忆抽取流程."""

    def __init__(self, store: MemoryStore, logger: Logger) -> None:
        self.store = store
        self.logger = logger

    def run_post_turn_extraction(
        self,
        question: str,
        final_answer: str,
        used_tools: list[str],
    ) -> list[str]:
        """在回合结束后抽取长期记忆，并写回 memory store."""

        if "upsert_memory" in used_tools:
            self.logger.info("AUTO_MEMORY", "本轮已显式写入记忆，跳过自动抽取。")
            return []

        extracted = self.extract_memories(question=question, final_answer=final_answer)
        if not extracted:
            self.logger.info("AUTO_MEMORY", "未发现适合持久化的稳定信息。")
            return []

        written_files: list[str] = []
        for item in extracted:
            existing = self.store.read_memory(item.filename)
            if existing is not None and existing.body.strip() == item.body.strip():
                self.logger.info("AUTO_MEMORY", f"记忆已存在，跳过重复写入: {item.filename}")
                continue
            path = self.store.upsert_memory(
                memory_type=item.memory_type,
                name=item.name,
                description=item.description,
                body=item.body,
                filename=item.filename,
            )
            written_files.append(path.name)
            self.logger.info("AUTO_MEMORY", f"已自动写入记忆: {path.name}")
        return written_files

    def extract_memories(self, question: str, final_answer: str) -> list[ExtractedMemory]:
        """根据用户输入和最终回复抽取 durable memory."""

        text = question.strip()
        normalized = text.lower()
        candidates: list[ExtractedMemory] = []

        preference_match = re.search(r"(以后请|请|希望|偏好|更偏好|习惯|喜欢用)(.+)", text)
        dislike_match = re.search(r"(不喜欢|不要|避免)(.+)", text)

        if any(keyword in text for keyword in ("记住", "记下来", "以后请", "偏好", "喜欢用", "习惯")):
            body = self._build_body("用户偏好", text, final_answer)
            description = self._short_description(text, fallback="用户新增了一条稳定偏好")
            candidates.append(
                ExtractedMemory(
                    memory_type="user",
                    name=self._pick_name(preference_match.group(2) if preference_match else text, "用户偏好"),
                    description=description,
                    body=body,
                    filename=build_memory_filename("user", self._pick_name(preference_match.group(2) if preference_match else text, "用户偏好"), description, body),
                )
            )

        if any(keyword in text for keyword in ("不喜欢", "不要", "避免", "别用", "禁用")):
            body = self._build_body("用户反馈/约束", text, final_answer)
            description = self._short_description(text, fallback="新增一条反馈约束")
            candidates.append(
                ExtractedMemory(
                    memory_type="feedback",
                    name=self._pick_name(dislike_match.group(2) if dislike_match else text, "反馈约束"),
                    description=description,
                    body=body,
                    filename=build_memory_filename("feedback", self._pick_name(dislike_match.group(2) if dislike_match else text, "反馈约束"), description, body),
                )
            )

        if any(keyword in normalized for keyword in ("项目", "仓库", "demo", "演示", "react_agent_demo")) and any(
            keyword in text for keyword in ("是", "用于", "目标", "背景", "当前项目", "这个项目")
        ):
            body = self._build_body("项目事实", text, final_answer)
            description = self._short_description(text, fallback="新增一条项目背景事实")
            candidates.append(
                ExtractedMemory(
                    memory_type="project",
                    name=self._pick_name(text, "项目事实"),
                    description=description,
                    body=body,
                    filename=build_memory_filename("project", self._pick_name(text, "项目事实"), description, body),
                )
            )

        unique: dict[str, ExtractedMemory] = {}
        for item in candidates:
            unique[item.filename] = item
        return list(unique.values())

    def _pick_name(self, text: str, fallback: str) -> str:
        cleaned = re.sub(r"\s+", " ", text).strip(" ，。:：,.;；")
        return cleaned[:24] or fallback

    def _short_description(self, text: str, fallback: str) -> str:
        cleaned = re.sub(r"\s+", " ", text).strip()
        return cleaned[:40] or fallback

    def _build_body(self, category: str, question: str, final_answer: str) -> str:
        return "\n".join(
            [
                f"来源类别：{category}",
                f"用户原话：{question.strip()}",
                f"当轮回复摘要：{final_answer.strip()}",
                "",
                "说明：这条记忆由演示版 extractMemories 在回合结束后自动抽取得到，用于模拟 Claude Code 的 Auto Memory 回流。",
            ]
        ).strip()
