"""项目配置常量."""

from __future__ import annotations

from pathlib import Path
import os

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MEMORY_DIR = PROJECT_ROOT / "demo_memory_store"
DEFAULT_MAX_STEPS = 4
DEFAULT_TOP_K = 3
DEFAULT_MAX_TOKENS = 2048
DEFAULT_TIMEOUT = 60
DEFAULT_LLM_MODE = "http"
DEFAULT_BASE_URL = "https://your-llm-service.example.com/v1/messages"
DEFAULT_MODEL = "kimi-k2.5"
VALID_MEMORY_TYPES = ("user", "project", "feedback", "reference")
SECTION_TITLES = {
    "user": "用户记忆",
    "project": "项目记忆",
    "feedback": "反馈",
    "reference": "参考资料",
}
SYSTEM_PROMPT_TEMPLATE = """
你是一个用于技术分享演示的 ReAct Agent。

你的目标不是隐藏实现，而是主动展示以下机制：
1. Thought：先解释你准备做什么。
2. Action：如有必要，调用记忆工具。
3. Observation：根据工具返回结果继续推理。
4. Final Answer：最后用中文给出结论。

记忆使用规则：
1. MEMORY.md 是长期记忆索引入口。
2. 先检索，再读取，再回答。
3. 只把稳定偏好、项目事实、反馈约束、可复用参考资料写入长期记忆。
4. 对临时聊天内容不要落库。
5. 创建详细记忆文件时，文件名必须使用英文 snake_case，并显式传入 filename。
6. 文件名格式固定为 `<memory_type>_<topic>.md`，例如：
   - `user_programming_preference.md`
   - `user_dietary_preference.md`
   - `feedback_no_emoji.md`
   - `project_memory_sharing.md`
7. 不要使用 `会话新增偏好.md`、`新的记忆.md`、`偏好1.md` 这类模糊文件名。
8. topic 应该表达“这条详细记忆到底在讲什么”，优先使用稳定主题词，例如 `programming_preference`、`dietary_preference`、`output_style`、`coding_convention`。
""".strip()


def resolve_api_key(cli_value: str | None = None) -> str | None:
    """按既定优先级解析 API Key."""

    return (
        cli_value
        or os.getenv("FUYAO_API_KEY")
        or os.getenv("XIAOPENG_API_KEY")
        or os.getenv("OPENAI_API_KEY")
        or os.getenv("ANTHROPIC_API_KEY")
    )
