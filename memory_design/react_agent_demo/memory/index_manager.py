"""MEMORY.md 索引管理."""

from __future__ import annotations

import re
from pathlib import Path

from config.settings import SECTION_TITLES, VALID_MEMORY_TYPES


class IndexManager:
    """负责 MEMORY.md 的初始化、更新与删除."""

    def __init__(self, index_path: Path) -> None:
        self.index_path = index_path

    def ensure(self) -> None:
        """确保 MEMORY.md 存在，且包含所有记忆分区."""

        self.index_path.parent.mkdir(parents=True, exist_ok=True)
        if self.index_path.exists():
            return
        lines: list[str] = []
        for memory_type in VALID_MEMORY_TYPES:
            lines.append(f"# {SECTION_TITLES[memory_type]}")
            lines.append("")
        self.index_path.write_text("\n".join(lines).strip() + "\n", encoding="utf-8")

    def upsert(self, memory_type: str, name: str, description: str, filename: str) -> None:
        """插入或替换索引项."""

        lines = self.index_path.read_text(encoding="utf-8").splitlines()
        section_title = SECTION_TITLES[memory_type]
        entry_line = f"- [{name}]({filename}) — {description}"
        section_header = f"# {section_title}"
        start_index = next((index for index, line in enumerate(lines) if line.strip() == section_header), None)
        if start_index is None:
            if lines and lines[-1] != "":
                lines.append("")
            lines.extend([section_header, "", entry_line])
            self.index_path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
            return

        end_index = len(lines)
        for index in range(start_index + 1, len(lines)):
            if lines[index].strip().startswith("# "):
                end_index = index
                break

        section_lines = lines[start_index + 1 : end_index]
        pattern = re.compile(rf"- \[.+?\]\({re.escape(filename)}\)\s+—\s+.+")
        replaced = False
        new_section_lines: list[str] = []
        for line in section_lines:
            if pattern.fullmatch(line.strip()):
                if not replaced:
                    new_section_lines.append(entry_line)
                    replaced = True
                continue
            new_section_lines.append(line)
        if not replaced:
            if new_section_lines and new_section_lines[-1] != "":
                new_section_lines.append("")
            new_section_lines.append(entry_line)

        new_lines = lines[: start_index + 1] + new_section_lines + lines[end_index:]
        self.index_path.write_text("\n".join(new_lines).rstrip() + "\n", encoding="utf-8")

    def remove(self, filename: str) -> None:
        """从索引中移除指定文件."""

        pattern = re.compile(rf"- \[.+?\]\({re.escape(filename)}\)\s+—\s+.+")
        lines = self.index_path.read_text(encoding="utf-8").splitlines()
        new_lines = [line for line in lines if not pattern.fullmatch(line.strip())]
        self.index_path.write_text("\n".join(new_lines).rstrip() + "\n", encoding="utf-8")
