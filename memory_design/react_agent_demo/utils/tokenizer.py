"""简易分词与打分工具."""

from __future__ import annotations

import re


def tokenize(text: str) -> set[str]:
    """同时支持英文 token 和中文连续片段的粗粒度切分."""

    normalized = text.lower()
    tokens = set(re.findall(r"[a-z0-9_]+", normalized))
    chinese_segments = re.findall(r"[\u4e00-\u9fff]+", normalized)
    for segment in chinese_segments:
        if len(segment) == 1:
            tokens.add(segment)
            continue
        tokens.add(segment)
        for size in (2, 3):
            if len(segment) < size:
                continue
            for index in range(len(segment) - size + 1):
                tokens.add(segment[index : index + size])
    return {token for token in tokens if token.strip()}
