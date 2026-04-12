"""文本清洗工具."""

from __future__ import annotations

import re
from typing import Any

SURROGATE_RE = re.compile(r"[\ud800-\udfff]")


def sanitize_text(text: str) -> str:
    """替换非法代理字符，避免 JSON 或终端输出失败."""

    return SURROGATE_RE.sub("\ufffd", text)


def sanitize_value(value: Any) -> Any:
    """递归清洗列表和字典中的字符串值."""

    if isinstance(value, str):
        return sanitize_text(value)
    if isinstance(value, list):
        return [sanitize_value(item) for item in value]
    if isinstance(value, dict):
        return {sanitize_value(key): sanitize_value(item) for key, item in value.items()}
    return value

