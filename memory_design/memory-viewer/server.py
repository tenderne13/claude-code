#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import threading
import time
from datetime import datetime, timezone
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse


STATIC_DIR = Path(__file__).resolve().parent / "static"
DEFAULT_PORT = 8765
MAX_RECENT_MESSAGES = 8
MAX_MEMORY_ACTIVITY = 40
MAX_TIMELINE_ITEMS = 80
MAX_RECALL_CANDIDATES = 12
MAX_QUERY_TURNS = 24
MAX_FILE_PREVIEW = 12000
MAX_TEXT_SNIPPET = 280


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def sanitize_path(name: str) -> str:
    return re.sub(r"[^a-zA-Z0-9]", "-", name)


def safe_read_text(path: Path, limit: int | None = None) -> str:
    try:
        text = path.read_text(encoding="utf-8")
    except (FileNotFoundError, IsADirectoryError, PermissionError, UnicodeDecodeError):
        return ""
    if limit is not None and len(text) > limit:
        return text[:limit] + "\n\n...<truncated>..."
    return text


def safe_stat(path: Path) -> os.stat_result | None:
    try:
        return path.stat()
    except FileNotFoundError:
        return None


def iso_from_timestamp(ts: float | None) -> str | None:
    if ts is None:
        return None
    return datetime.fromtimestamp(ts, timezone.utc).isoformat()


def rel_path(path: Path, start: Path) -> str:
    try:
        return str(path.relative_to(start))
    except ValueError:
        return str(path)


def is_under_root(file_path: Path, root: Path) -> bool:
    resolved = file_path.expanduser().resolve(strict=False)
    root_resolved = root.expanduser().resolve(strict=False)
    resolved_str = str(resolved)
    root_str = str(root_resolved)
    return resolved_str == root_str or resolved_str.startswith(root_str + os.sep)


def classify_memory_path(
    file_path: Path,
    project_memory_dir: Path,
    project_storage_dir: Path,
    session_id: str,
    agent_user_dir: Path,
    agent_project_dir: Path,
    agent_local_dir: Path,
) -> dict[str, str] | None:
    if is_under_root(file_path, project_memory_dir / "team"):
        return None
    resolved = file_path.expanduser().resolve(strict=False)
    kairos_logs_dir = project_memory_dir / "logs"
    buckets = [
        ("session-memory", "Session Memory", project_storage_dir / session_id / "session-memory"),
        ("kairos-daily-log", "KAIROS Daily Log", kairos_logs_dir),
        ("project-memory", "Project Memory", project_memory_dir),
        ("agent-user-memory", "Agent User Memory", agent_user_dir),
        ("agent-project-memory", "Agent Project Memory", agent_project_dir),
        ("agent-local-memory", "Agent Local Memory", agent_local_dir),
    ]
    for key, label, root in buckets:
        root_resolved = root.expanduser().resolve(strict=False)
        root_prefix = str(root_resolved)
        resolved_str = str(resolved)
        if resolved_str == root_prefix or resolved_str.startswith(root_prefix + os.sep):
            return {
                "kind": key,
                "label": label,
                "relative_path": rel_path(file_path, root),
            }
    return None


def parse_frontmatter(text: str) -> tuple[dict[str, str], str]:
    if not text.startswith("---\n"):
        return {}, text
    lines = text.splitlines()
    frontmatter: dict[str, str] = {}
    end_index = None
    for index in range(1, min(len(lines), 40)):
        line = lines[index]
        if line.strip() == "---":
            end_index = index
            break
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        frontmatter[key.strip()] = value.strip()
    if end_index is None:
        return {}, text
    body = "\n".join(lines[end_index + 1 :]).strip()
    return frontmatter, body


def normalize_content_blocks(content: Any) -> str:
    if isinstance(content, str):
        return content.strip()
    if not isinstance(content, list):
        return ""
    parts: list[str] = []
    for block in content:
        if not isinstance(block, dict):
            continue
        block_type = block.get("type")
        if block_type == "text":
            text = block.get("text")
            if isinstance(text, str):
                parts.append(text.strip())
        elif block_type == "tool_result":
            inner = block.get("content")
            if isinstance(inner, str):
                parts.append(inner.strip())
            elif isinstance(inner, list):
                for item in inner:
                    if isinstance(item, dict) and isinstance(item.get("text"), str):
                        parts.append(item["text"].strip())
    return "\n".join(part for part in parts if part).strip()


def shorten(text: str, limit: int = MAX_TEXT_SNIPPET) -> str:
    text = " ".join(text.split())
    if len(text) <= limit:
        return text
    return text[: limit - 3] + "..."


def is_real_user_turn(event: dict[str, Any]) -> bool:
    if event.get("type") != "user":
        return False
    if event.get("toolUseResult") is not None:
        return False
    message = event.get("message", {})
    if not isinstance(message, dict) or message.get("role") != "user":
        return False
    return bool(normalize_content_blocks(message.get("content")))


def summarize_tool_input(tool_input: dict[str, Any]) -> str:
    summary_parts: list[str] = []
    if isinstance(tool_input.get("file_path"), str):
        summary_parts.append(Path(tool_input["file_path"]).name)
    if isinstance(tool_input.get("command"), str):
        summary_parts.append(shorten(tool_input["command"], 80))
    if isinstance(tool_input.get("prompt"), str):
        summary_parts.append(shorten(tool_input["prompt"], 80))
    if isinstance(tool_input.get("query"), str):
        summary_parts.append(shorten(tool_input["query"], 80))
    return " · ".join(summary_parts[:2])


class ViewerService:
    def __init__(self, project_root: Path, claude_home: Path) -> None:
        self.claude_home = claude_home.expanduser().resolve()
        self.agent_user_dir = self.claude_home / "agent-memory"
        self._lock = threading.Lock()
        self._set_project_root(project_root)

    def _set_project_root(self, project_root: Path) -> None:
        self.project_root = project_root.expanduser().resolve()
        self.project_storage_dir = (
            self.claude_home / "projects" / sanitize_path(str(self.project_root))
        )
        self.project_memory_dir = self.project_storage_dir / "memory"
        self.agent_project_dir = self.project_root / ".claude" / "agent-memory"
        self.agent_local_dir = self.project_root / ".claude" / "agent-memory-local"

    def switch_project_root(self, project_root: Path) -> None:
        with self._lock:
            self._set_project_root(project_root)

    def list_known_projects(self) -> list[dict[str, Any]]:
        """Scan ~/.claude/projects/ and return dirs that have at least one .jsonl session."""
        projects_dir = self.claude_home / "projects"
        if not projects_dir.exists():
            return []

        # Build a lookup: sanitized_name -> real_path by scanning likely parent dirs
        # We walk up to depth=4 under home to find matching project roots
        home = Path.home()
        sanitized_to_real: dict[str, str] = {}
        search_roots = [home]
        try:
            for depth1 in home.iterdir():
                if depth1.is_dir() and not depth1.name.startswith("."):
                    search_roots.append(depth1)
                    for depth2 in depth1.iterdir():
                        if depth2.is_dir() and not depth2.name.startswith("."):
                            search_roots.append(depth2)
                            for depth3 in depth2.iterdir():
                                if depth3.is_dir() and not depth3.name.startswith("."):
                                    search_roots.append(depth3)
        except PermissionError:
            pass
        for candidate in search_roots:
            key = sanitize_path(str(candidate))
            sanitized_to_real[key] = str(candidate)

        results: list[dict[str, Any]] = []
        for entry in sorted(projects_dir.iterdir()):
            if not entry.is_dir():
                continue
            jsonl_files = list(entry.glob("*.jsonl"))
            if not jsonl_files:
                continue
            latest_mtime = max(f.stat().st_mtime for f in jsonl_files)
            real_path = sanitized_to_real.get(entry.name)
            results.append({
                "sanitizedName": entry.name,
                "projectRoot": real_path,
                "sessionCount": len(jsonl_files),
                "updatedAt": iso_from_timestamp(latest_mtime),
            })
        results.sort(key=lambda x: x["updatedAt"] or "", reverse=True)
        return results

    def list_session_files(self) -> list[Path]:
        if not self.project_storage_dir.exists():
            return []
        return sorted(
            self.project_storage_dir.glob("*.jsonl"),
            key=lambda path: path.stat().st_mtime,
            reverse=True,
        )

    def get_default_session_id(self) -> str | None:
        files = self.list_session_files()
        if not files:
            return None
        return files[0].stem

    def read_jsonl(self, path: Path) -> list[dict[str, Any]]:
        events: list[dict[str, Any]] = []
        try:
            with path.open("r", encoding="utf-8") as handle:
                for raw_line in handle:
                    line = raw_line.strip()
                    if not line:
                        continue
                    try:
                        parsed = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    if isinstance(parsed, dict):
                        events.append(parsed)
        except FileNotFoundError:
            return []
        return events

    def build_sessions_index(self) -> list[dict[str, Any]]:
        sessions: list[dict[str, Any]] = []
        for session_file in self.list_session_files():
            events = self.read_jsonl(session_file)
            first_user = None
            last_user = None
            last_assistant = None
            slug = None
            entrypoint = None
            started_at = None
            user_count = 0
            assistant_count = 0
            for event in events:
                event_type = event.get("type")
                if event_type == "last-prompt" and isinstance(event.get("lastPrompt"), str):
                    last_user = event["lastPrompt"].strip()
                if event_type == "user":
                    user_count += 1
                    if started_at is None:
                        started_at = event.get("timestamp")
                    message = event.get("message", {})
                    text = normalize_content_blocks(message.get("content"))
                    if text:
                        first_user = first_user or text
                        last_user = text
                    slug = slug or event.get("slug")
                    entrypoint = entrypoint or event.get("entrypoint")
                elif event_type == "assistant":
                    assistant_count += 1
                    message = event.get("message", {})
                    text = normalize_content_blocks(message.get("content"))
                    if text:
                        last_assistant = text
                    slug = slug or event.get("slug")
                    entrypoint = entrypoint or event.get("entrypoint")
            stat = safe_stat(session_file)
            sessions.append(
                {
                    "sessionId": session_file.stem,
                    "startedAt": started_at,
                    "updatedAt": iso_from_timestamp(stat.st_mtime if stat else None),
                    "sizeBytes": stat.st_size if stat else 0,
                    "slug": slug,
                    "entrypoint": entrypoint,
                    "userCount": user_count,
                    "assistantCount": assistant_count,
                    "firstUserMessage": shorten(first_user or ""),
                    "lastUserMessage": shorten(last_user or ""),
                    "lastAssistantMessage": shorten(last_assistant or ""),
                }
            )
        return sessions

    def scan_markdown_inventory(
        self,
        root: Path,
        group_key: str,
        group_label: str,
        touched_paths: set[str],
        recursive: bool = True,
        include_index: bool = True,
        exclude_roots: list[Path] | None = None,
    ) -> tuple[dict[str, Any] | None, list[dict[str, Any]]]:
        if not root.exists():
            return None, []
        excluded = [
            path.expanduser().resolve(strict=False)
            for path in (exclude_roots or [])
        ]
        walker = root.rglob("*.md") if recursive else root.glob("*.md")
        items: list[dict[str, Any]] = []
        index_info = None
        for path in sorted(walker):
            resolved_path = path.expanduser().resolve(strict=False)
            if any(
                str(resolved_path) == str(excluded_root)
                or str(resolved_path).startswith(str(excluded_root) + os.sep)
                for excluded_root in excluded
            ):
                continue
            if path.name == "MEMORY.md":
                if include_index:
                    stat = safe_stat(path)
                    index_info = {
                        "groupKey": group_key,
                        "groupLabel": group_label,
                        "path": str(path),
                        "relativePath": rel_path(path, root),
                        "updatedAt": iso_from_timestamp(stat.st_mtime if stat else None),
                        "content": safe_read_text(path, MAX_FILE_PREVIEW),
                    }
                continue
            text = safe_read_text(path, MAX_FILE_PREVIEW)
            frontmatter, body = parse_frontmatter(text)
            stat = safe_stat(path)
            items.append(
                {
                    "groupKey": group_key,
                    "groupLabel": group_label,
                    "name": frontmatter.get("name") or path.stem,
                    "description": frontmatter.get("description") or shorten(body, 140),
                    "memoryType": frontmatter.get("type"),
                    "path": str(path),
                    "relativePath": rel_path(path, root),
                    "updatedAt": iso_from_timestamp(stat.st_mtime if stat else None),
                    "sizeBytes": stat.st_size if stat else 0,
                    "content": text,
                    "touchedInSession": str(path) in touched_paths,
                }
            )
        items.sort(key=lambda item: item["updatedAt"] or "", reverse=True)
        return index_info, items

    def build_memory_activity(self, session_id: str, events: list[dict[str, Any]]) -> list[dict[str, Any]]:
        activities: list[dict[str, Any]] = []
        for event in events:
            event_type = event.get("type")
            timestamp = event.get("timestamp")
            if event_type == "assistant":
                message = event.get("message", {})
                content = message.get("content")
                if not isinstance(content, list):
                    continue
                for block in content:
                    if not isinstance(block, dict) or block.get("type") != "tool_use":
                        continue
                    tool_name = block.get("name")
                    tool_input = block.get("input", {})
                    if not isinstance(tool_input, dict):
                        continue
                    file_path_value = tool_input.get("file_path")
                    if not isinstance(file_path_value, str):
                        continue
                    classification = classify_memory_path(
                        Path(file_path_value),
                        self.project_memory_dir,
                        self.project_storage_dir,
                        session_id,
                        self.agent_user_dir,
                        self.agent_project_dir,
                        self.agent_local_dir,
                    )
                    if not classification:
                        continue
                    action = "access"
                    if tool_name == "Read":
                        action = "read"
                    elif tool_name in {"Write", "Edit", "MultiEdit"}:
                        action = "write"
                    activities.append(
                        {
                            "timestamp": timestamp,
                            "source": "assistant-tool",
                            "toolName": tool_name,
                            "action": action,
                            "path": file_path_value,
                            "memoryKind": classification["kind"],
                            "memoryLabel": classification["label"],
                            "relativePath": classification["relative_path"],
                        }
                    )
            elif event_type == "user":
                tool_result = event.get("toolUseResult")
                if not isinstance(tool_result, dict):
                    continue
                file_info = tool_result.get("file")
                if not isinstance(file_info, dict):
                    continue
                file_path_value = file_info.get("filePath")
                if not isinstance(file_path_value, str):
                    continue
                classification = classify_memory_path(
                    Path(file_path_value),
                    self.project_memory_dir,
                    self.project_storage_dir,
                    session_id,
                    self.agent_user_dir,
                    self.agent_project_dir,
                    self.agent_local_dir,
                )
                if not classification:
                    continue
                activities.append(
                    {
                        "timestamp": timestamp,
                        "source": "tool-result",
                        "toolName": tool_result.get("type"),
                        "action": "result",
                        "path": file_path_value,
                        "memoryKind": classification["kind"],
                        "memoryLabel": classification["label"],
                        "relativePath": classification["relative_path"],
                    }
                )
        activities.sort(key=lambda item: item.get("timestamp") or "", reverse=True)
        return activities[:MAX_MEMORY_ACTIVITY]

    def build_recent_messages(self, events: list[dict[str, Any]]) -> list[dict[str, Any]]:
        messages: list[dict[str, Any]] = []
        for event in events:
            event_type = event.get("type")
            if event_type not in {"user", "assistant"}:
                continue
            text = normalize_content_blocks(event.get("message", {}).get("content"))
            if not text:
                continue
            messages.append(
                {
                    "role": event_type,
                    "timestamp": event.get("timestamp"),
                    "content": shorten(text, 1200),
                }
            )
        return messages[-MAX_RECENT_MESSAGES:]

    def build_timeline(
        self,
        events: list[dict[str, Any]],
        activity: list[dict[str, Any]],
        session_summary: dict[str, Any] | None,
    ) -> list[dict[str, Any]]:
        timeline: list[dict[str, Any]] = []
        for event in events:
            event_type = event.get("type")
            if event_type not in {"user", "assistant"}:
                continue
            text = normalize_content_blocks(event.get("message", {}).get("content"))
            if not text:
                continue
            role_label = "User" if event_type == "user" else "Assistant"
            timeline.append(
                {
                    "timestamp": event.get("timestamp"),
                    "kind": f"{event_type}-message",
                    "title": f"{role_label} Message",
                    "subtitle": shorten(text, 220),
                    "detail": shorten(text, 1200),
                }
            )
        for event in events:
            if event.get("type") != "attachment":
                continue
            attachment = event.get("attachment", {})
            if not isinstance(attachment, dict):
                continue
            attachment_type = attachment.get("type")
            if attachment_type == "relevant_memories":
                memories = attachment.get("memories", [])
                count = len(memories) if isinstance(memories, list) else 0
                subtitle = ", ".join(
                    Path(item.get("path", "")).name
                    for item in memories[:3]
                    if isinstance(item, dict)
                )
                timeline.append(
                    {
                        "timestamp": event.get("timestamp"),
                        "kind": "relevant-memory-injection",
                        "title": f"Injected {count} Relevant Memories",
                        "subtitle": subtitle or "relevant_memories attachment",
                        "detail": "\n".join(
                            item.get("path", "")
                            for item in memories
                            if isinstance(item, dict)
                        ),
                    }
                )
            elif attachment_type == "nested_memory":
                path = attachment.get("path")
                if isinstance(path, str):
                    timeline.append(
                        {
                            "timestamp": event.get("timestamp"),
                            "kind": "nested-memory-injection",
                            "title": "Injected Nested Memory",
                            "subtitle": Path(path).name,
                            "detail": path,
                        }
                    )
        for item in activity:
            timeline.append(
                {
                    "timestamp": item.get("timestamp"),
                    "kind": "memory-activity",
                    "title": f"{item.get('memoryLabel', 'Memory')} {item.get('action', 'access')}",
                    "subtitle": item.get("relativePath") or item.get("path"),
                    "detail": f"{item.get('toolName') or item.get('source') or '-'} · {item.get('path')}",
                }
            )
        if session_summary:
            timeline.append(
                {
                    "timestamp": session_summary.get("updatedAt"),
                    "kind": "session-summary",
                    "title": "Session Memory Updated",
                    "subtitle": "session-memory/summary.md",
                    "detail": shorten(session_summary.get("content") or "", 600),
                }
            )
        timeline.sort(key=lambda item: item.get("timestamp") or "", reverse=True)
        return timeline[:MAX_TIMELINE_ITEMS]

    def build_recall_candidates(
        self,
        activity: list[dict[str, Any]],
        inventory_by_path: dict[str, dict[str, Any]],
    ) -> list[dict[str, Any]]:
        candidates: dict[str, dict[str, Any]] = {}
        for item in activity:
            if item.get("memoryKind") == "session-memory":
                continue
            if item.get("action") not in {"read", "result"}:
                continue
            path = item.get("path")
            if not isinstance(path, str):
                continue
            existing = candidates.get(path)
            if existing is None:
                inventory = inventory_by_path.get(path, {})
                candidates[path] = {
                    "path": path,
                    "relativePath": item.get("relativePath"),
                    "memoryLabel": item.get("memoryLabel"),
                    "memoryKind": item.get("memoryKind"),
                    "name": inventory.get("name") or Path(path).stem,
                    "description": inventory.get("description") or "",
                    "memoryType": inventory.get("memoryType"),
                    "contentPreview": shorten(inventory.get("content") or "", 900),
                    "lastAccessAt": item.get("timestamp"),
                    "readCount": 1,
                }
            else:
                existing["readCount"] += 1
                if (item.get("timestamp") or "") > (existing.get("lastAccessAt") or ""):
                    existing["lastAccessAt"] = item.get("timestamp")
        ordered = sorted(
            candidates.values(),
            key=lambda item: ((item.get("lastAccessAt") or ""), item.get("readCount", 0)),
            reverse=True,
        )
        return ordered[:MAX_RECALL_CANDIDATES]

    def build_query_turns(
        self,
        session_id: str,
        events: list[dict[str, Any]],
        inventory_by_path: dict[str, dict[str, Any]],
    ) -> tuple[list[dict[str, Any]], str | None]:
        turns: list[dict[str, Any]] = []
        current_turn: dict[str, Any] | None = None

        def flush_current_turn() -> None:
            nonlocal current_turn
            if current_turn is None:
                return
            assistant_responses = current_turn.pop("assistantResponses", [])
            tool_calls = current_turn.pop("toolCalls", [])
            current_turn["assistantResponse"] = shorten(
                "\n\n".join(response for response in assistant_responses if response),
                1200,
            )
            current_turn["toolCalls"] = tool_calls
            current_turn["toolCount"] = len(tool_calls)
            current_turn["memoryReadCount"] = len(current_turn["memoryReads"])
            current_turn["memoryWriteCount"] = len(current_turn["memoryWrites"])
            turns.append(current_turn)
            current_turn = None

        for event in events:
            if is_real_user_turn(event):
                flush_current_turn()
                prompt = normalize_content_blocks(event.get("message", {}).get("content"))
                current_turn = {
                    "turnId": event.get("uuid") or f"turn-{len(turns) + 1}",
                    "timestamp": event.get("timestamp"),
                    "userPrompt": prompt,
                    "exactRelevantMemories": [],
                    "nestedMemories": [],
                    "memoryReads": [],
                    "memoryWrites": [],
                    "assistantResponses": [],
                    "toolCalls": [],
                    "hasExactRelevantMemoryRecord": False,
                }
                continue

            if current_turn is None:
                continue

            event_type = event.get("type")
            if event_type == "assistant":
                message = event.get("message", {})
                content = message.get("content")
                text = normalize_content_blocks(content)
                if text:
                    current_turn["assistantResponses"].append(text)
                if isinstance(content, list):
                    for block in content:
                        if not isinstance(block, dict) or block.get("type") != "tool_use":
                            continue
                        tool_name = block.get("name")
                        tool_input = block.get("input", {})
                        if not isinstance(tool_name, str) or not isinstance(tool_input, dict):
                            continue
                        tool_record = {
                            "toolName": tool_name,
                            "summary": summarize_tool_input(tool_input),
                            "timestamp": event.get("timestamp"),
                        }
                        current_turn["toolCalls"].append(tool_record)
                        file_path_value = tool_input.get("file_path")
                        if not isinstance(file_path_value, str):
                            continue
                        classification = classify_memory_path(
                            Path(file_path_value),
                            self.project_memory_dir,
                            self.project_storage_dir,
                            session_id,
                            self.agent_user_dir,
                            self.agent_project_dir,
                            self.agent_local_dir,
                        )
                        if not classification:
                            continue
                        inventory = inventory_by_path.get(file_path_value, {})
                        target_list = (
                            current_turn["memoryReads"]
                            if tool_name == "Read"
                            else current_turn["memoryWrites"]
                            if tool_name in {"Write", "Edit", "MultiEdit"}
                            else None
                        )
                        if target_list is None:
                            continue
                        target_list.append(
                            {
                                "path": file_path_value,
                                "relativePath": inventory.get("relativePath")
                                or classification["relative_path"],
                                "name": inventory.get("name") or Path(file_path_value).stem,
                                "description": inventory.get("description") or "",
                                "memoryType": inventory.get("memoryType"),
                                "memoryKind": classification["kind"],
                                "memoryLabel": classification["label"],
                                "timestamp": event.get("timestamp"),
                                "toolName": tool_name,
                            }
                        )
                continue

            if event_type != "attachment":
                continue
            attachment = event.get("attachment", {})
            if not isinstance(attachment, dict):
                continue
            attachment_type = attachment.get("type")

            if attachment_type == "relevant_memories":
                memories = attachment.get("memories", [])
                if isinstance(memories, list):
                    for mem in memories:
                        if not isinstance(mem, dict):
                            continue
                        path = mem.get("path")
                        if not isinstance(path, str):
                            continue
                        if is_under_root(Path(path), self.project_memory_dir / "team"):
                            continue
                        inventory = inventory_by_path.get(path, {})
                        classification = classify_memory_path(
                            Path(path),
                            self.project_memory_dir,
                            self.project_storage_dir,
                            session_id,
                            self.agent_user_dir,
                            self.agent_project_dir,
                            self.agent_local_dir,
                        )
                        current_turn["exactRelevantMemories"].append(
                            {
                                "path": path,
                                "relativePath": inventory.get("relativePath") or Path(path).name,
                                "name": inventory.get("name") or Path(path).stem,
                                "description": inventory.get("description") or "",
                                "memoryType": inventory.get("memoryType"),
                                "memoryKind": classification["kind"] if classification else None,
                                "memoryLabel": classification["label"] if classification else None,
                                "contentPreview": shorten(mem.get("content") or "", 900),
                                "mtimeMs": mem.get("mtimeMs"),
                                "header": mem.get("header"),
                            }
                        )
                current_turn["hasExactRelevantMemoryRecord"] = True
            elif attachment_type == "nested_memory":
                path = attachment.get("path")
                if not isinstance(path, str):
                    continue
                if is_under_root(Path(path), self.project_memory_dir / "team"):
                    continue
                content = attachment.get("content", {})
                inventory = inventory_by_path.get(path, {})
                classification = classify_memory_path(
                    Path(path),
                    self.project_memory_dir,
                    self.project_storage_dir,
                    session_id,
                    self.agent_user_dir,
                    self.agent_project_dir,
                    self.agent_local_dir,
                )
                preview = ""
                if isinstance(content, dict):
                    preview = shorten(content.get("content") or "", 700)
                current_turn["nestedMemories"].append(
                    {
                        "path": path,
                        "relativePath": inventory.get("relativePath") or Path(path).name,
                        "name": inventory.get("name") or Path(path).stem,
                        "memoryKind": classification["kind"] if classification else None,
                        "memoryLabel": classification["label"] if classification else None,
                        "contentPreview": preview,
                    }
                )

        flush_current_turn()

        turns = turns[-MAX_QUERY_TURNS:]
        selected_turn_id = None
        for turn in reversed(turns):
            if turn.get("hasExactRelevantMemoryRecord"):
                selected_turn_id = turn["turnId"]
                break
        if selected_turn_id is None and turns:
            selected_turn_id = turns[-1]["turnId"]
        return turns, selected_turn_id

    def build_session_snapshot(self, session_id: str | None) -> dict[str, Any]:
        sessions = self.build_sessions_index()
        default_session_id = sessions[0]["sessionId"] if sessions else None
        selected_session_id = session_id or default_session_id
        snapshot: dict[str, Any] = {
            "generatedAt": now_iso(),
            "projectRoot": str(self.project_root),
            "claudeHome": str(self.claude_home),
            "projectStorageDir": str(self.project_storage_dir),
            "defaultSessionId": default_session_id,
            "selectedSessionId": selected_session_id,
            "sessions": sessions,
            "session": None,
            "memory": {
                "indexes": [],
                "groups": [],
                "sessionSummary": None,
                "recallCandidates": [],
            },
        }
        if not selected_session_id:
            return snapshot

        session_file = self.project_storage_dir / f"{selected_session_id}.jsonl"
        events = self.read_jsonl(session_file)
        activity = self.build_memory_activity(selected_session_id, events)
        touched_paths = {item["path"] for item in activity}
        recent_messages = self.build_recent_messages(events)
        started_at = None
        entrypoint = None
        slug = None
        last_prompt = None
        for event in events:
            if event.get("type") == "user":
                started_at = started_at or event.get("timestamp")
                entrypoint = entrypoint or event.get("entrypoint")
                slug = slug or event.get("slug")
            if event.get("type") == "last-prompt" and isinstance(event.get("lastPrompt"), str):
                last_prompt = event["lastPrompt"].strip()
        session_stat = safe_stat(session_file)
        snapshot["session"] = {
            "sessionId": selected_session_id,
            "transcriptPath": str(session_file),
            "startedAt": started_at,
            "updatedAt": iso_from_timestamp(session_stat.st_mtime if session_stat else None),
            "entrypoint": entrypoint,
            "slug": slug,
            "lastPrompt": last_prompt,
            "eventCount": len(events),
            "recentMessages": recent_messages,
            "memoryActivity": activity,
            "queryTurns": [],
            "selectedQueryTurnId": None,
        }

        session_summary_path = (
            self.project_storage_dir / selected_session_id / "session-memory" / "summary.md"
        )
        session_summary_info = None
        if session_summary_path.exists():
            session_summary_stat = safe_stat(session_summary_path)
            session_summary_info = {
                "path": str(session_summary_path),
                "updatedAt": iso_from_timestamp(
                    session_summary_stat.st_mtime if session_summary_stat else None
                ),
                "content": safe_read_text(session_summary_path, MAX_FILE_PREVIEW),
            }
            snapshot["memory"]["sessionSummary"] = session_summary_info

        inventories = [
            (
                "project-memory",
                "Project Memory",
                self.project_memory_dir,
                True,
                True,
                [self.project_memory_dir / "team", self.project_memory_dir / "logs"],
            ),
            (
                "kairos-daily-log",
                "KAIROS Daily Logs",
                self.project_memory_dir / "logs",
                True,
                False,
                [],
            ),
            (
                "agent-user-memory",
                "Agent User Memory",
                self.agent_user_dir,
                True,
                False,
                [],
            ),
            (
                "agent-project-memory",
                "Agent Project Memory",
                self.agent_project_dir,
                True,
                False,
                [],
            ),
            (
                "agent-local-memory",
                "Agent Local Memory",
                self.agent_local_dir,
                True,
                False,
                [],
            ),
        ]
        inventory_by_path: dict[str, dict[str, Any]] = {}
        for group_key, group_label, root, recursive, include_index, exclude_roots in inventories:
            index_info, items = self.scan_markdown_inventory(
                root,
                group_key,
                group_label,
                touched_paths,
                recursive=recursive,
                include_index=include_index,
                exclude_roots=exclude_roots,
            )
            if index_info:
                snapshot["memory"]["indexes"].append(index_info)
            snapshot["memory"]["groups"].append(
                {
                    "groupKey": group_key,
                    "groupLabel": group_label,
                    "root": str(root),
                    "items": items,
                }
            )
            for item in items:
                inventory_by_path[item["path"]] = item
        snapshot["memory"]["recallCandidates"] = self.build_recall_candidates(
            activity, inventory_by_path
        )
        query_turns, selected_turn_id = self.build_query_turns(
            selected_session_id, events, inventory_by_path
        )
        snapshot["session"]["queryTurns"] = query_turns
        snapshot["session"]["selectedQueryTurnId"] = selected_turn_id
        snapshot["session"]["timeline"] = self.build_timeline(
            events, activity, session_summary_info
        )
        return snapshot

    def compute_fingerprint(self, session_id: str | None) -> str:
        payload = {
            "selectedSessionId": session_id or self.get_default_session_id(),
            "projectStorageDirMtime": iso_from_timestamp(
                safe_stat(self.project_storage_dir).st_mtime if safe_stat(self.project_storage_dir) else None
            ),
            "sessionFiles": [],
            "memoryFiles": [],
        }
        for session_file in self.list_session_files():
            stat = safe_stat(session_file)
            payload["sessionFiles"].append(
                {
                    "path": str(session_file),
                    "mtime": stat.st_mtime if stat else None,
                    "size": stat.st_size if stat else None,
                }
            )
        watch_roots = [
            self.project_memory_dir,
            self.agent_user_dir,
            self.agent_project_dir,
            self.agent_local_dir,
        ]
        if session_id:
            watch_roots.append(self.project_storage_dir / session_id / "session-memory")
        for root in watch_roots:
            if not root.exists():
                continue
            for path in sorted(root.rglob("*")):
                if not path.is_file():
                    continue
                stat = safe_stat(path)
                payload["memoryFiles"].append(
                    {
                        "path": str(path),
                        "mtime": stat.st_mtime if stat else None,
                        "size": stat.st_size if stat else None,
                    }
                )
        return json.dumps(payload, ensure_ascii=False, sort_keys=True)


class ViewerHandler(BaseHTTPRequestHandler):
    server_version = "ClaudeMemoryViewer/0.1"

    @property
    def viewer(self) -> ViewerService:
        return self.server.viewer_service  # type: ignore[attr-defined]

    def log_message(self, fmt: str, *args: Any) -> None:
        sys.stderr.write("%s - - [%s] %s\n" % (self.client_address[0], self.log_date_time_string(), fmt % args))

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path == "/":
            self.serve_static("index.html", "text/html; charset=utf-8")
            return
        if parsed.path == "/static/app.js":
            self.serve_static("app.js", "application/javascript; charset=utf-8")
            return
        if parsed.path == "/static/styles.css":
            self.serve_static("styles.css", "text/css; charset=utf-8")
            return
        if parsed.path == "/api/snapshot":
            params = parse_qs(parsed.query)
            session_id = params.get("session_id", [None])[0]
            self.send_json(self.viewer.build_session_snapshot(session_id))
            return
        if parsed.path == "/api/stream":
            params = parse_qs(parsed.query)
            session_id = params.get("session_id", [None])[0]
            self.serve_sse(session_id)
            return
        if parsed.path == "/api/projects":
            self.send_json({"projects": self.viewer.list_known_projects()})
            return
        self.send_error(HTTPStatus.NOT_FOUND, "Not found")

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path == "/api/set-project":
            length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(length)
            try:
                data = json.loads(body)
                project_root = data.get("projectRoot", "").strip()
                if not project_root:
                    self.send_error(HTTPStatus.BAD_REQUEST, "projectRoot is required")
                    return
                path = Path(project_root).expanduser().resolve()
                if not path.exists():
                    self.send_error(HTTPStatus.BAD_REQUEST, f"Path does not exist: {path}")
                    return
                self.viewer.switch_project_root(path)
                self.send_json({"ok": True, "projectRoot": str(self.viewer.project_root)})
            except (json.JSONDecodeError, ValueError) as exc:
                self.send_error(HTTPStatus.BAD_REQUEST, str(exc))
            return
        self.send_error(HTTPStatus.NOT_FOUND, "Not found")

    def serve_static(self, filename: str, content_type: str) -> None:
        path = STATIC_DIR / filename
        if not path.exists():
            self.send_error(HTTPStatus.NOT_FOUND, "Static file not found")
            return
        body = path.read_bytes()
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def send_json(self, payload: dict[str, Any]) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def serve_sse(self, session_id: str | None) -> None:
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "text/event-stream; charset=utf-8")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "keep-alive")
        self.end_headers()

        last_fingerprint = ""
        try:
            while True:
                effective_session = session_id or self.viewer.get_default_session_id()
                fingerprint = self.viewer.compute_fingerprint(effective_session)
                if fingerprint != last_fingerprint:
                    snapshot = self.viewer.build_session_snapshot(effective_session)
                    payload = json.dumps(snapshot, ensure_ascii=False)
                    self.wfile.write(f"event: snapshot\ndata: {payload}\n\n".encode("utf-8"))
                    self.wfile.flush()
                    last_fingerprint = fingerprint
                else:
                    self.wfile.write(b": heartbeat\n\n")
                    self.wfile.flush()
                time.sleep(1.0)
        except (BrokenPipeError, ConnectionResetError):
            return


def parse_args() -> argparse.Namespace:
    repo_root = Path(__file__).resolve().parents[2]
    parser = argparse.ArgumentParser(description="Claude Code memory viewer")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--project-root", default=str(repo_root))
    parser.add_argument("--claude-home", default=str(Path.home() / ".claude"))
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    viewer_service = ViewerService(
        project_root=Path(args.project_root),
        claude_home=Path(args.claude_home),
    )
    server = ThreadingHTTPServer((args.host, args.port), ViewerHandler)
    server.viewer_service = viewer_service  # type: ignore[attr-defined]
    print(
        f"Memory viewer listening on http://{args.host}:{args.port}\n"
        f"project_root={viewer_service.project_root}\n"
        f"project_storage_dir={viewer_service.project_storage_dir}",
        flush=True,
    )
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
