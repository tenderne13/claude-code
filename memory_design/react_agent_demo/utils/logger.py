"""统一日志输出."""

from __future__ import annotations

from dataclasses import dataclass

ANSI_RESET = "\033[0m"
ANSI_BOLD = "\033[1m"
ANSI_CYAN = "\033[36m"
ANSI_BLUE = "\033[34m"
ANSI_GREEN = "\033[32m"
ANSI_YELLOW = "\033[33m"
ANSI_MAGENTA = "\033[35m"
ANSI_RED = "\033[31m"
ANSI_GRAY = "\033[90m"


@dataclass(slots=True)
class Logger:
    """用于演示的轻量日志器."""

    verbose: bool = False

    def info(self, tag: str, message: str) -> None:
        print(f"{self._format_tag(tag)} {message}")

    def detail(self, tag: str, message: str) -> None:
        if self.verbose:
            print(f"{self._format_tag(tag)} {message}")

    def _format_tag(self, tag: str) -> str:
        """根据日志类别为标签着色，增强演示时的可读性."""

        color = self._pick_color(tag)
        return f"{ANSI_BOLD}{color}[{tag}]{ANSI_RESET}"

    def _pick_color(self, tag: str) -> str:
        """按标签前缀映射颜色."""

        if tag in {"AGENT", "DONE"}:
            return ANSI_GREEN
        if tag.startswith("THOUGHT"):
            return ANSI_CYAN
        if tag.startswith("ACTION") or tag == "EXECUTE":
            return ANSI_BLUE
        if tag.startswith("INPUT") or tag in {"LLM_REQUEST", "LLM_REQUEST_PREVIEW", "LLM_HTTP"}:
            return ANSI_MAGENTA
        if tag.startswith("RESULT") or tag.startswith("OBSERVATION"):
            return ANSI_YELLOW
        if tag in {"CONTEXT", "RAW_RESPONSE"}:
            return ANSI_GRAY
        if tag.startswith("ERROR"):
            return ANSI_RED
        return ANSI_CYAN
