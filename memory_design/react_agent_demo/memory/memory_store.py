"""记忆系统主入口."""

from __future__ import annotations

import re
from pathlib import Path

from config.settings import VALID_MEMORY_TYPES
from memory.index_manager import IndexManager
from memory.memory_entry import MemoryEntry
from memory.memory_search import MemorySearch
from utils.validators import validate_memory_type


def parse_frontmatter(text: str) -> tuple[dict[str, str], str]:
    """解析 Markdown 文件中的 YAML 风格 frontmatter."""

    if not text.startswith("---\n"):
        return {}, text.strip()
    lines = text.splitlines()
    frontmatter: dict[str, str] = {}
    end_index: int | None = None
    for index in range(1, len(lines)):
        line = lines[index]
        if line.strip() == "---":
            end_index = index
            break
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        frontmatter[key.strip()] = value.strip()
    if end_index is None:
        return {}, text.strip()
    return frontmatter, "\n".join(lines[end_index + 1 :]).strip()


def slugify(value: str) -> str:
    """将记忆标题转成适合文件名的 slug."""

    value = value.strip().lower()
    value = re.sub(r"[\s/]+", "_", value)
    value = re.sub(r"[^a-z0-9_\u4e00-\u9fff-]", "", value)
    return value.strip("_-") or "memory"


def infer_memory_topic(memory_type: str, name: str, description: str, body: str) -> str:
    """根据内容推断更稳定的 topic 名称，减少文件命名混乱."""

    text = " ".join([name, description, body]).lower()
    if any(keyword in text for keyword in ("java", "python", "编程语言", "语言偏好", "programming")):
        return "programming_preference"
    if any(keyword in text for keyword in ("饮食", "菜", "忌口", "茴香", "大蒜", "韭菜", "香菜", "diet")):
        return "dietary_preference"
    if any(keyword in text for keyword in ("emoji", "表情", "输出风格", "语气", "格式")):
        return "output_style"
    if any(keyword in text for keyword in ("规范", "约束", "不要", "避免", "禁用")) and memory_type == "feedback":
        return "interaction_constraint"
    if any(keyword in text for keyword in ("项目", "仓库", "demo", "演示", "分享")) and memory_type == "project":
        return "project_context"
    candidate = slugify(description or name)
    return candidate[:48] or "memory_detail"


def build_memory_filename(memory_type: str, name: str, description: str, body: str) -> str:
    """生成 `<memory_type>_<topic>.md` 风格的文件名."""

    topic = infer_memory_topic(memory_type, name, description, body)
    return f"{memory_type}_{topic}.md"


class MemoryStore:
    """封装长期记忆的 CRUD 与搜索操作."""

    def __init__(self, root: Path) -> None:
        self.root = root.expanduser().resolve()
        self.index_manager = IndexManager(self.root / "MEMORY.md")
        self.searcher = MemorySearch()

    @property
    def index_path(self) -> Path:
        """返回 MEMORY.md 路径."""

        return self.index_manager.index_path

    def ensure(self) -> None:
        """确保记忆目录与索引文件存在."""

        self.root.mkdir(parents=True, exist_ok=True)
        self.index_manager.ensure()

    def load_entries(self) -> list[MemoryEntry]:
        """从 MEMORY.md 加载所有已注册的记忆条目."""

        self.ensure()
        entries: list[MemoryEntry] = []
        current_type: str | None = None
        for line in self.index_path.read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            if stripped.startswith("# "):
                heading = stripped[2:].strip()
                current_type = next(
                    (
                        key
                        for key, title in {
                            "user": "用户记忆",
                            "project": "项目记忆",
                            "feedback": "反馈",
                            "reference": "参考资料",
                        }.items()
                        if title == heading
                    ),
                    None,
                )
                continue
            match = re.match(r"- \[(?P<name>.+?)\]\((?P<filename>.+?)\)\s+—\s+(?P<description>.+)", stripped)
            if not match or current_type is None:
                continue
            file_path = self.root / match.group("filename")
            if file_path.exists():
                frontmatter, body = parse_frontmatter(file_path.read_text(encoding="utf-8"))
            else:
                frontmatter, body = {}, ""
            entries.append(
                MemoryEntry(
                    memory_type=frontmatter.get("type", current_type),
                    path=file_path,
                    name=frontmatter.get("name", match.group("name")),
                    description=frontmatter.get("description", match.group("description")),
                    body=body,
                )
            )
        return entries

    def list_memories(self) -> list[MemoryEntry]:
        """返回全部记忆条目."""

        return self.load_entries()

    def search_memories(self, query: str, limit: int = 5) -> list[MemoryEntry]:
        """搜索相关记忆."""

        return self.searcher.search(query=query, entries=self.load_entries(), limit=limit)

    def search(self, query: str, limit: int = 5) -> list[MemoryEntry]:
        """兼容 demo_memory_cli.py 的命名方式."""

        return self.search_memories(query=query, limit=limit)

    def read_memory(self, filename: str) -> MemoryEntry | None:
        """按文件名读取单条记忆."""

        target = self.root / filename
        for entry in self.load_entries():
            if entry.path == target:
                return entry
        return None

    def upsert_memory(
        self,
        memory_type: str,
        name: str,
        description: str,
        body: str,
        filename: str | None = None,
    ) -> Path:
        """创建或覆盖一条长期记忆，并同步更新 MEMORY.md."""

        self.ensure()
        validate_memory_type(memory_type)
        target_name = filename or build_memory_filename(memory_type, name, description, body)
        if not target_name.endswith(".md"):
            target_name = f"{target_name}.md"
        file_path = self.root / target_name
        content = "\n".join(
            [
                "---",
                f"name: {name}",
                f"description: {description}",
                f"type: {memory_type}",
                "---",
                "",
                body.strip(),
                "",
            ]
        )
        file_path.write_text(content, encoding="utf-8")
        self.index_manager.upsert(memory_type, name, description, target_name)
        return file_path

    def delete_memory(self, filename: str) -> bool:
        """删除记忆文件，并从索引中清理对应条目."""

        self.ensure()
        target = self.root / filename
        if not target.exists() or target == self.index_path:
            return False
        target.unlink()
        self.index_manager.remove(filename)
        return True
