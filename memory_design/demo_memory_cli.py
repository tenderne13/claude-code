#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import textwrap
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


DEFAULT_BASE_URL = "https://your-llm-service.example.com/v1/messages"
DEFAULT_MODEL = "kimi-k2.5"
DEFAULT_MEMORY_DIR = Path(__file__).resolve().parent / "demo_memory_store"
VALID_MEMORY_TYPES = ("user", "project", "feedback", "reference")
ANSI_GREEN = "\033[32m"
ANSI_RESET = "\033[0m"
SURROGATE_RE = re.compile(r"[\ud800-\udfff]")
SECTION_TITLES = {
    "user": "用户记忆",
    "project": "项目记忆",
    "feedback": "反馈",
    "reference": "参考资料",
}
FIXED_SYSTEM_PROMPT = textwrap.dedent(
    """
    You are a coding assistant demo that imitates Claude Code's memory usage pattern.
    You are operating as a ReAct-style agent with tools.

    Memory rules:
    1. Treat MEMORY.md as the long-term memory index.
    2. Use recalled topic files when they are relevant to the current request.
    3. Decide yourself whether the user's latest message is worth saving as long-term memory.
    4. Save only durable information such as user preferences, stable project facts, collaboration feedback, and reusable references.
    5. Do not save transient chatter, one-off tasks, or information already obvious from the current turn unless it has lasting value.

    Tool rules:
    1. If you need to inspect existing memory before writing, use list_memories, search_memories, or read_memory.
    2. If the user just revealed a durable preference or project fact, call upsert_memory before your final answer.
    3. When updating an existing memory, prefer rewriting the same filename instead of creating duplicates.
    4. If the user asks to forget or remove a memory, use delete_memory.
    5. After tool use is complete, respond to the user concisely and naturally.
    """
).strip()


@dataclass
class MemoryEntry:
    memory_type: str
    path: Path
    name: str
    description: str
    body: str
    score: int = 0


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def slugify(value: str) -> str:
    value = value.strip().lower()
    value = re.sub(r"[\s/]+", "_", value)
    value = re.sub(r"[^a-z0-9_\u4e00-\u9fff-]", "", value)
    return value.strip("_-") or "memory"


def parse_frontmatter(text: str) -> tuple[dict[str, str], str]:
    if not text.startswith("---\n"):
        return {}, text.strip()
    lines = text.splitlines()
    frontmatter: dict[str, str] = {}
    end_index = None
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
    body = "\n".join(lines[end_index + 1 :]).strip()
    return frontmatter, body


def tokenize(text: str) -> set[str]:
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


def sanitize_text(text: str) -> str:
    return SURROGATE_RE.sub("\ufffd", text)


def sanitize_jsonish(value: Any) -> Any:
    if isinstance(value, str):
        return sanitize_text(value)
    if isinstance(value, list):
        return [sanitize_jsonish(item) for item in value]
    if isinstance(value, dict):
        return {sanitize_jsonish(key): sanitize_jsonish(item) for key, item in value.items()}
    return value


def dumps_safe(value: Any, indent: int | None = None) -> str:
    return json.dumps(sanitize_jsonish(value), ensure_ascii=False, indent=indent)


class MemoryStore:
    def __init__(self, root: Path) -> None:
        self.root = root.expanduser().resolve()
        self.index_path = self.root / "MEMORY.md"

    def ensure(self) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        if self.index_path.exists():
            return
        lines = []
        for memory_type in VALID_MEMORY_TYPES:
            lines.append(f"# {SECTION_TITLES[memory_type]}")
            lines.append("")
        self.index_path.write_text("\n".join(lines).strip() + "\n", encoding="utf-8")

    def load_entries(self) -> list[MemoryEntry]:
        self.ensure()
        entries: list[MemoryEntry] = []
        current_type: str | None = None
        for line in self.index_path.read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            if stripped.startswith("# "):
                heading = stripped[2:].strip()
                current_type = next(
                    (key for key, title in SECTION_TITLES.items() if title == heading),
                    None,
                )
                continue
            match = re.match(r"- \[(?P<name>.+?)\]\((?P<filename>.+?)\)\s+—\s+(?P<description>.+)", stripped)
            if not match or current_type is None:
                continue
            file_path = self.root / match.group("filename")
            frontmatter, body = parse_frontmatter(file_path.read_text(encoding="utf-8")) if file_path.exists() else ({}, "")
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

    def get_entry_by_filename(self, filename: str) -> MemoryEntry | None:
        target = self.root / filename
        for entry in self.load_entries():
            if entry.path == target:
                return entry
        return None

    def delete_entry(self, filename: str) -> bool:
        target = self.root / filename
        if not target.exists() or target == self.index_path:
            return False
        target.unlink()
        self._remove_index_entry(filename)
        return True

    def search(self, query: str, limit: int) -> list[MemoryEntry]:
        query_tokens = tokenize(query)
        scored: list[MemoryEntry] = []
        for entry in self.load_entries():
            haystack = "\n".join([entry.name, entry.description, entry.body])
            memory_tokens = tokenize(haystack)
            overlap = len(query_tokens & memory_tokens)
            bonus = 0
            for token in query_tokens:
                if token and token in haystack.lower():
                    bonus += len(token)
            if overlap == 0 and bonus == 0:
                continue
            entry.score = overlap * 10 + bonus
            scored.append(entry)
        scored.sort(key=lambda item: (-item.score, item.path.name))
        return scored[:limit]

    def write_entry(
        self,
        memory_type: str,
        name: str,
        description: str,
        body: str,
        filename: str | None = None,
    ) -> Path:
        self.ensure()
        if memory_type not in VALID_MEMORY_TYPES:
            raise ValueError(f"memory type must be one of {', '.join(VALID_MEMORY_TYPES)}")
        target_name = filename or f"{slugify(name)}.md"
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
        self._upsert_index(memory_type, name, description, target_name)
        return file_path

    def seed_demo_entries(self) -> list[Path]:
        demo_entries = [
            (
                "user",
                "编程语言偏好",
                "用户更偏好 Java 示例，必要时再使用 Python",
                "用户更偏好 Java 代码示例。\n\n在讨论接口设计、工具类、服务端逻辑时，优先给 Java 版本。",
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
        ]
        written = []
        for memory_type, name, description, body, filename in demo_entries:
            written.append(self.write_entry(memory_type, name, description, body, filename))
        return written

    def _upsert_index(self, memory_type: str, name: str, description: str, filename: str) -> None:
        section_title = SECTION_TITLES[memory_type]
        lines = self.index_path.read_text(encoding="utf-8").splitlines()
        entry_line = f"- [{name}]({filename}) — {description}"
        new_lines: list[str] = []
        inserted = False
        in_target_section = False
        replaced = False

        for index, line in enumerate(lines):
            stripped = line.strip()
            if stripped == f"# {section_title}":
                in_target_section = True
                new_lines.append(line)
                continue
            if stripped.startswith("# ") and stripped != f"# {section_title}":
                if in_target_section and not inserted:
                    if new_lines and new_lines[-1] != "":
                        new_lines.append("")
                    new_lines.append(entry_line)
                    inserted = True
                in_target_section = False
            if in_target_section and re.match(rf"- \[.+?\]\({re.escape(filename)}\)\s+—\s+.+", stripped):
                if not replaced:
                    new_lines.append(entry_line)
                    replaced = True
                    inserted = True
                continue
            new_lines.append(line)
            if index == len(lines) - 1 and in_target_section and not inserted:
                if new_lines and new_lines[-1] != "":
                    new_lines.append("")
                new_lines.append(entry_line)
                inserted = True

        if not inserted:
            if new_lines and new_lines[-1] != "":
                new_lines.append("")
            new_lines.append(f"# {section_title}")
            new_lines.append("")
            new_lines.append(entry_line)

        self.index_path.write_text("\n".join(new_lines).rstrip() + "\n", encoding="utf-8")

    def _remove_index_entry(self, filename: str) -> None:
        lines = self.index_path.read_text(encoding="utf-8").splitlines()
        new_lines = []
        pattern = re.compile(rf"- \[.+?\]\({re.escape(filename)}\)\s+—\s+.+")
        for line in lines:
            if pattern.fullmatch(line.strip()):
                continue
            new_lines.append(line)
        self.index_path.write_text("\n".join(new_lines).rstrip() + "\n", encoding="utf-8")


def build_user_context(question: str, store: MemoryStore, top_k: int) -> tuple[list[dict[str, str]], list[MemoryEntry]]:
    question = sanitize_text(question)
    store.ensure()
    index_text = store.index_path.read_text(encoding="utf-8").strip()
    recalled = store.search(question, limit=top_k)
    relevant_parts = []
    for entry in recalled:
        relevant_parts.append(
            "\n".join(
                [
                    f"## {entry.name}",
                    f"path: {entry.path.name}",
                    f"type: {entry.memory_type}",
                    f"description: {entry.description}",
                    entry.body.strip(),
                ]
            ).strip()
        )
    content = [
        {
            "type": "text",
            "text": "\n".join(
                [
                    "<system-reminder>",
                    "以下是长期记忆索引 MEMORY.md，请把它当作长期记忆目录入口：",
                    index_text,
                    "</system-reminder>",
                ]
            ),
        }
    ]

    if relevant_parts :
        content.append(
            {
                "type": "text",
                "text": "\n".join(
                    [
                        "<system-reminder>",
                        "以下是按当前问题召回的相关记忆 topic 文件：",
                        "\n\n".join(relevant_parts),
                        "</system-reminder>",
                    ]
                ),
            }
        )
    content.append({"type": "text", "text": question})
    return content, recalled


def get_memory_tools() -> list[dict[str, Any]]:
    return [
        {
            "name": "list_memories",
            "description": "List current memory entries from MEMORY.md.",
            "input_schema": {
                "type": "object",
                "properties": {},
                "additionalProperties": False,
            },
        },
        {
            "name": "search_memories",
            "description": "Search existing memory topics by semantic keyword overlap and return the best matches.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "query": {"type": "string"},
                    "limit": {"type": "integer", "minimum": 1, "maximum": 10, "default": 5},
                },
                "required": ["query"],
                "additionalProperties": False,
            },
        },
        {
            "name": "read_memory",
            "description": "Read one memory topic file by filename, including frontmatter and body.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "filename": {"type": "string"},
                },
                "required": ["filename"],
                "additionalProperties": False,
            },
        },
        {
            "name": "upsert_memory",
            "description": "Create or overwrite one long-term memory topic file and update MEMORY.md.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "memory_type": {"type": "string", "enum": list(VALID_MEMORY_TYPES)},
                    "name": {"type": "string"},
                    "description": {"type": "string"},
                    "body": {"type": "string"},
                    "filename": {"type": "string"},
                },
                "required": ["memory_type", "name", "description", "body"],
                "additionalProperties": False,
            },
        },
        {
            "name": "delete_memory",
            "description": "Delete one memory topic file by filename and remove it from MEMORY.md.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "filename": {"type": "string"},
                },
                "required": ["filename"],
                "additionalProperties": False,
            },
        },
    ]


def build_payload(messages: list[dict[str, Any]], model: str, max_tokens: int) -> dict[str, Any]:
    payload = {
        "timestamp": now_iso(),
        "model": model,
        "messages": messages,
        "system": [
            {"type": "text", "text": "x-demo-billing-header: cc_version=demo; cc_entrypoint=python-cli;"},
            {"type": "text", "text": "You are a Claude-style coding agent demo."},
            {"type": "text", "text": FIXED_SYSTEM_PROMPT},
        ],
        "tools": get_memory_tools(),
        "max_tokens": max_tokens,
        "thinking": {"type": "adaptive"},
        "metadata": {"source": "memory-demo-cli"},
    }
    return payload


def build_request_preview(payload: dict[str, Any], recalled: list[MemoryEntry]) -> dict[str, Any]:
    user_question = ""
    if payload.get("messages"):
        last_message = payload["messages"][-1]
        if isinstance(last_message, dict):
            for block in reversed(last_message.get("content", [])):
                if isinstance(block, dict) and block.get("type") == "text" and isinstance(block.get("text"), str):
                    user_question = block["text"]
                    break
    return {
        "url_path_hint": "/v1/messages",
        "model": payload.get("model"),
        "max_tokens": payload.get("max_tokens"),
        "thinking": payload.get("thinking"),
        "system": [item.get("text", "") for item in payload.get("system", []) if isinstance(item, dict)],
        "tools": [tool.get("name") for tool in payload.get("tools", []) if isinstance(tool, dict)],
        "question": user_question,
        "recalled_memories": [
            {
                "name": entry.name,
                "type": entry.memory_type,
                "description": entry.description,
                "file": entry.path.name,
            }
            for entry in recalled
        ],
        "messages": payload.get("messages"),
    }


def parse_response_text(data: Any) -> str:
    if isinstance(data, dict):
        content = data.get("content")
        if isinstance(content, list):
            texts = [item.get("text", "") for item in content if isinstance(item, dict) and isinstance(item.get("text"), str)]
            if texts:
                return "\n".join(texts).strip()
        choices = data.get("choices")
        if isinstance(choices, list) and choices:
            first = choices[0]
            if isinstance(first, dict):
                message = first.get("message")
                if isinstance(message, dict):
                    message_content = message.get("content")
                    if isinstance(message_content, str):
                        return message_content.strip()
                    if isinstance(message_content, list):
                        texts = [item.get("text", "") for item in message_content if isinstance(item, dict) and isinstance(item.get("text"), str)]
                        if texts:
                            return "\n".join(texts).strip()
                text = first.get("text")
                if isinstance(text, str):
                    return text.strip()
        output_text = data.get("output_text")
        if isinstance(output_text, str):
            return output_text.strip()
        result = data.get("result")
        if isinstance(result, str):
            return result.strip()
    if isinstance(data, str):
        return data.strip()
    return dumps_safe(data, indent=2)


def extract_tool_uses(response: dict[str, Any]) -> list[dict[str, Any]]:
    content = response.get("content")
    if not isinstance(content, list):
        return []
    return [block for block in content if isinstance(block, dict) and block.get("type") == "tool_use"]


def make_tool_result_block(tool_use_id: str, content: str, is_error: bool = False) -> dict[str, Any]:
    block: dict[str, Any] = {
        "type": "tool_result",
        "tool_use_id": tool_use_id,
        "content": content,
    }
    if is_error:
        block["is_error"] = True
    return block


def print_tool_use(tool_name: str, tool_input: dict[str, Any]) -> None:
    print(f"{ANSI_GREEN}[assistant tool_use] {tool_name}{ANSI_RESET}", file=sys.stderr)
    print(f"{ANSI_GREEN}{dumps_safe(tool_input, indent=2)}{ANSI_RESET}", file=sys.stderr)


def print_tool_result(tool_name: str, content: str, is_error: bool = False) -> None:
    prefix = "[user tool_result error]" if is_error else "[user tool_result]"
    print(f"{ANSI_GREEN}{prefix} {tool_name}{ANSI_RESET}", file=sys.stderr)
    print(f"{ANSI_GREEN}{content}{ANSI_RESET}", file=sys.stderr)


def execute_tool(store: MemoryStore, tool_name: str, tool_input: dict[str, Any]) -> tuple[str, Path | None]:
    if tool_name == "list_memories":
        entries = store.load_entries()
        result = {
            "entries": [
                {
                    "memory_type": entry.memory_type,
                    "name": entry.name,
                    "description": entry.description,
                    "filename": entry.path.name,
                }
                for entry in entries
            ]
        }
        return dumps_safe(result, indent=2), None
    if tool_name == "search_memories":
        query = str(tool_input.get("query", "")).strip()
        limit = int(tool_input.get("limit", 5))
        matches = store.search(query, limit=limit)
        result = {
            "matches": [
                {
                    "memory_type": entry.memory_type,
                    "name": entry.name,
                    "description": entry.description,
                    "filename": entry.path.name,
                    "score": entry.score,
                }
                for entry in matches
            ]
        }
        return dumps_safe(result, indent=2), None
    if tool_name == "read_memory":
        filename = str(tool_input.get("filename", "")).strip()
        entry = store.get_entry_by_filename(filename)
        if entry is None:
            raise ValueError(f"memory file not found: {filename}")
        result = {
            "memory_type": entry.memory_type,
            "name": entry.name,
            "description": entry.description,
            "filename": entry.path.name,
            "body": entry.body,
        }
        return dumps_safe(result, indent=2), None
    if tool_name == "upsert_memory":
        path = store.write_entry(
            memory_type=str(tool_input["memory_type"]),
            name=str(tool_input["name"]),
            description=str(tool_input["description"]),
            body=str(tool_input["body"]),
            filename=str(tool_input["filename"]).strip() if tool_input.get("filename") else None,
        )
        result = {
            "status": "ok",
            "saved_path": str(path),
            "filename": path.name,
        }
        return dumps_safe(result, indent=2), path
    if tool_name == "delete_memory":
        filename = str(tool_input["filename"]).strip()
        deleted = store.delete_entry(filename)
        result = {
            "status": "ok" if deleted else "not_found",
            "filename": filename,
        }
        return dumps_safe(result, indent=2), None
    raise ValueError(f"unknown tool: {tool_name}")


def build_turn_messages(history: list[dict[str, Any]], turn_content: list[dict[str, str]]) -> list[dict[str, Any]]:
    messages: list[dict[str, Any]] = []
    messages.extend(history)
    messages.append({"role": "user", "content": turn_content})
    return messages


def extract_assistant_text(response: dict[str, Any]) -> str:
    content = response.get("content", [])
    if not isinstance(content, list):
        return ""
    texts = []
    for block in content:
        if isinstance(block, dict) and block.get("type") == "text" and isinstance(block.get("text"), str):
            text = sanitize_text(block["text"]).strip()
            if text:
                texts.append(text)
    return "\n".join(texts).strip()


def run_agent_loop(
    question: str,
    history: list[dict[str, Any]],
    store: MemoryStore,
    model: str,
    max_tokens: int,
    base_url: str,
    api_key: str | None,
    timeout: int,
    top_k: int,
    max_steps: int,
    print_request_preview: bool,
) -> tuple[dict[str, Any], list[MemoryEntry], list[Path]]:
    initial_content, recalled = build_user_context(question, store, top_k)
    messages = build_turn_messages(history, initial_content)
    saved_paths: list[Path] = []

    for step in range(1, max_steps + 1):
        payload = build_payload(messages=messages, model=model, max_tokens=max_tokens)
        if print_request_preview:
            print(f"[request-preview step={step}]")
            print(dumps_safe(build_request_preview(payload, recalled), indent=2))
        response = call_model(
            base_url=base_url,
            payload=payload,
            api_key=api_key,
            timeout=timeout,
        )
        assistant_message = {
            "role": response.get("role", "assistant"),
            "content": response.get("content", []),
        }
        messages.append(assistant_message)
        tool_uses = extract_tool_uses(response)
        if not tool_uses:
            return response, recalled, saved_paths

        tool_result_blocks: list[dict[str, Any]] = []
        for tool_use in tool_uses:
            tool_name = str(tool_use.get("name", ""))
            tool_input = tool_use.get("input", {})
            tool_use_id = str(tool_use.get("id", ""))
            if isinstance(tool_input, dict):
                print_tool_use(tool_name, tool_input)
            try:
                result_text, saved_path = execute_tool(store, tool_name, tool_input if isinstance(tool_input, dict) else {})
                if saved_path is not None:
                    saved_paths.append(saved_path)
                print_tool_result(tool_name, result_text, is_error=False)
                tool_result_blocks.append(make_tool_result_block(tool_use_id, result_text))
            except Exception as exc:
                error_text = str(exc)
                print_tool_result(tool_name, error_text, is_error=True)
                tool_result_blocks.append(make_tool_result_block(tool_use_id, error_text, is_error=True))
        messages.append({"role": "user", "content": tool_result_blocks})
        recalled = store.search(question, limit=top_k)

    raise RuntimeError(f"agent loop exceeded max steps: {max_steps}")


def resolve_request_urls(base_url: str) -> list[str]:
    normalized = base_url.rstrip("/")
    if normalized.endswith("/v1/messages") or normalized.endswith("/messages"):
        return [normalized]
    return [f"{normalized}/v1/messages", f"{normalized}/messages", normalized]


def call_model(base_url: str, payload: dict[str, Any], api_key: str | None, timeout: int) -> dict[str, Any]:
    body = dumps_safe(payload).encode("utf-8")
    headers = {
        "Content-Type": "application/json; charset=utf-8",
        "Accept": "application/json",
        "anthropic-version": "2023-06-01",
    }
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
        headers["x-api-key"] = api_key
    last_error: Exception | None = None
    for request_url in resolve_request_urls(base_url):
        request = urllib.request.Request(request_url, data=body, headers=headers, method="POST")
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                raw = response.read().decode("utf-8")
                return json.loads(raw)
        except urllib.error.HTTPError as exc:
            error_body = exc.read().decode("utf-8", errors="replace")
            if exc.code == 404:
                last_error = RuntimeError(f"HTTP 404 on {request_url}: {error_body}")
                continue
            raise RuntimeError(f"HTTP {exc.code} on {request_url}: {error_body}") from exc
        except urllib.error.URLError as exc:
            raise RuntimeError(f"request failed on {request_url}: {exc}") from exc
    raise RuntimeError(str(last_error) if last_error else "request failed")


def print_recalled_memories(recalled: list[MemoryEntry]) -> None:
    if not recalled:
        print("[memory] no relevant memories recalled", file=sys.stderr)
        return
    print("[memory] recalled topics:", file=sys.stderr)
    for entry in recalled:
        print(
            f"  - {entry.name} ({entry.memory_type}, score={entry.score}, file={entry.path.name})",
            file=sys.stderr,
        )


def print_memory_saved(path: Path) -> None:
    print(f"[memory] saved: {path}", file=sys.stderr)


def resolve_api_key(args: argparse.Namespace) -> str | None:
    return (
        args.api_key
        or os.getenv("FUYAO_API_KEY")
        or os.getenv("XIAOPENG_API_KEY")
        or os.getenv("OPENAI_API_KEY")
        or os.getenv("ANTHROPIC_API_KEY")
    )


def command_init_demo(args: argparse.Namespace) -> int:
    store = MemoryStore(args.memory_dir)
    written = store.seed_demo_entries()
    print(f"initialized demo memory store: {store.root}")
    for path in written:
        print(path)
    return 0


def command_list(args: argparse.Namespace) -> int:
    store = MemoryStore(args.memory_dir)
    entries = store.load_entries()
    print(f"memory dir: {store.root}")
    print(f"index: {store.index_path}")
    for entry in entries:
        print(f"- [{entry.memory_type}] {entry.name} | {entry.description} | {entry.path.name}")
    return 0


def command_remember(args: argparse.Namespace) -> int:
    store = MemoryStore(args.memory_dir)
    path = store.write_entry(
        memory_type=args.memory_type,
        name=args.name,
        description=args.description,
        body=args.body,
        filename=args.filename,
    )
    print(path)
    return 0


def command_chat(args: argparse.Namespace) -> int:
    store = MemoryStore(args.memory_dir)
    initial_content, recalled = build_user_context(
        question=args.question,
        store=store,
        top_k=args.top_k,
    )
    payload = build_payload(
        messages=[{"role": "user", "content": initial_content}],
        model=args.model,
        max_tokens=args.max_tokens,
    )
    if args.print_payload:
        print(dumps_safe(payload, indent=2))
        return 0
    print_recalled_memories(recalled)
    api_key = resolve_api_key(args)
    response, recalled, saved_paths = run_agent_loop(
        question=args.question,
        history=[],
        store=store,
        model=args.model,
        max_tokens=args.max_tokens,
        base_url=args.base_url,
        api_key=api_key,
        timeout=args.timeout,
        top_k=args.top_k,
        max_steps=args.max_steps,
        print_request_preview=args.print_request_preview,
    )
    for saved_path in saved_paths:
        print_memory_saved(saved_path)
    if args.print_response_json:
        print(dumps_safe(response, indent=2))
        return 0
    print(parse_response_text(response))
    return 0


def command_repl(args: argparse.Namespace) -> int:
    store = MemoryStore(args.memory_dir)
    api_key = resolve_api_key(args)
    history: list[dict[str, Any]] = []

    print("Interactive memory agent. Type /exit to quit.")
    while True:
        try:
            question = input("\nYou> ").strip()
        except EOFError:
            print()
            break
        except KeyboardInterrupt:
            print("\nInterrupted.")
            break

        if not question:
            continue
        if question in {"/exit", "/quit", "exit", "quit"}:
            break

        recalled = store.search(question, limit=args.top_k)
        print_recalled_memories(recalled)
        response, _, saved_paths = run_agent_loop(
            question=question,
            history=history,
            store=store,
            model=args.model,
            max_tokens=args.max_tokens,
            base_url=args.base_url,
            api_key=api_key,
            timeout=args.timeout,
            top_k=args.top_k,
            max_steps=args.max_steps,
            print_request_preview=args.print_request_preview,
        )
        for saved_path in saved_paths:
            print_memory_saved(saved_path)

        assistant_text = extract_assistant_text(response)
        history.append({"role": "user", "content": [{"type": "text", "text": question}]})
        history.append({"role": "assistant", "content": [{"type": "text", "text": assistant_text}]})
        print(f"Assistant> {assistant_text}")

    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Claude Code memory demo implemented in Python")
    parser.add_argument("--memory-dir", type=Path, default=DEFAULT_MEMORY_DIR, help="memory store directory")
    subparsers = parser.add_subparsers(dest="command", required=True)

    init_demo = subparsers.add_parser("init-demo", help="create a demo memory store")
    init_demo.set_defaults(func=command_init_demo)

    list_parser = subparsers.add_parser("list", help="list all memory entries")
    list_parser.set_defaults(func=command_list)

    remember = subparsers.add_parser("remember", help="write one memory topic and update MEMORY.md")
    remember.add_argument("--type", dest="memory_type", choices=VALID_MEMORY_TYPES, required=True)
    remember.add_argument("--name", required=True)
    remember.add_argument("--description", required=True)
    remember.add_argument("--body", required=True)
    remember.add_argument("--filename")
    remember.set_defaults(func=command_remember)

    chat = subparsers.add_parser("chat", help="recall related memories and call the model")
    chat.add_argument("question")
    chat.add_argument("--base-url", default=DEFAULT_BASE_URL)
    chat.add_argument("--model", default=DEFAULT_MODEL)
    chat.add_argument("--api-key")
    chat.add_argument("--top-k", type=int, default=3)
    chat.add_argument("--max-tokens", type=int, default=2048)
    chat.add_argument("--max-steps", type=int, default=6)
    chat.add_argument("--timeout", type=int, default=60)
    chat.add_argument("--print-payload", action="store_true")
    chat.add_argument("--print-request-preview", action=argparse.BooleanOptionalAction, default=True)
    chat.add_argument("--print-response-json", action="store_true")
    chat.set_defaults(func=command_chat)

    repl = subparsers.add_parser("repl", help="interactive multi-turn chat in the terminal")
    repl.add_argument("--base-url", default=DEFAULT_BASE_URL)
    repl.add_argument("--model", default=DEFAULT_MODEL)
    repl.add_argument("--api-key")
    repl.add_argument("--top-k", type=int, default=3)
    repl.add_argument("--max-tokens", type=int, default=2048)
    repl.add_argument("--max-steps", type=int, default=6)
    repl.add_argument("--timeout", type=int, default=60)
    repl.add_argument("--print-request-preview", action=argparse.BooleanOptionalAction, default=True)
    repl.set_defaults(func=command_repl)

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    try:
        return int(args.func(args))
    except Exception as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
