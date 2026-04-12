"""预设演示数据."""

from __future__ import annotations

from pathlib import Path

from memory.memory_store import MemoryStore

SEED_ITEMS = [
    (
        "user",
        "编程语言偏好",
        "用户更偏好 Java 示例，必要时再使用 Python",
        "用户更偏好 Java 代码示例。在讨论接口设计、工具类、服务端逻辑时，优先给 Java 版本。",
        "user_programming_preference.md",
    ),
    (
        "user",
        "饮食偏好",
        "用户不喜欢茴香和大蒜",
        "用户的饮食偏好：\n- 不喜欢茴香\n- 不喜欢大蒜\n\n推荐餐厅、菜谱、食材方案时应主动规避。",
        "user_dietary_preference.md",
    ),
    (
        "feedback",
        "不使用 emoji",
        "代码、文档和回答中避免使用 emoji",
        "规则：输出中不要使用 emoji 或表情符号，保持纯文本风格。",
        "feedback_no_emoji.md",
    ),
    (
        "project",
        "记忆子系统分享项目",
        "当前项目聚焦 Claude Code 风格记忆系统与 ReAct Agent 演示",
        "项目目标：为部门内部技术分享准备一个可运行、可讲解、结构清晰的 ReAct Agent 演示框架。",
        "project_memory_sharing.md",
    ),
    (
        "reference",
        "长期记忆设计原则",
        "适合保存稳定偏好、项目事实和可复用参考资料",
        "长期记忆应避免一次性任务和短期聊天内容，重点保存稳定且可复用的信息。",
        "reference_memory_principles.md",
    ),
]


def seed_demo_memories(root: Path) -> list[Path]:
    """写入预置演示数据."""

    store = MemoryStore(root)
    written: list[Path] = []
    for memory_type, name, description, body, filename in SEED_ITEMS:
        written.append(store.upsert_memory(memory_type, name, description, body, filename))
    return written
