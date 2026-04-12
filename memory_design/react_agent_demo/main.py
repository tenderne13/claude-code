"""CLI 入口."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from agent.react_agent import ReActAgent
from config.settings import (
    DEFAULT_BASE_URL,
    DEFAULT_LLM_MODE,
    DEFAULT_MAX_STEPS,
    DEFAULT_MAX_TOKENS,
    DEFAULT_MEMORY_DIR,
    DEFAULT_MODEL,
    DEFAULT_TIMEOUT,
    resolve_api_key,
)
from demo_data.seed_memories import seed_demo_memories
from llm.types import LLMClientConfig
from memory.memory_store import MemoryStore
from utils.logger import Logger
from utils.sanitizer import sanitize_text


def build_parser() -> argparse.ArgumentParser:
    """构建命令行参数."""

    def add_verbose_flag(target: argparse.ArgumentParser) -> None:
        target.add_argument("--verbose", action="store_true", help="打印详细上下文构建日志")

    def add_auto_memory_flag(target: argparse.ArgumentParser) -> None:
        target.add_argument(
            "--disable-auto-memory",
            action="store_true",
            help="关闭回合结束后的自动记忆抽取，便于对比演示",
        )

    parser = argparse.ArgumentParser(
        prog="react-agent-demo",
        description="ReAct Agent 技术分享演示项目",
    )
    parser.add_argument("--memory-dir", type=Path, default=DEFAULT_MEMORY_DIR, help="记忆目录路径")
    add_verbose_flag(parser)

    subparsers = parser.add_subparsers(dest="command", required=True)

    init_demo = subparsers.add_parser("init-demo", help="初始化预设演示记忆")
    add_verbose_flag(init_demo)
    init_demo.add_argument("--force", action="store_true", help="预留参数，当前实现为幂等覆盖")

    chat = subparsers.add_parser("chat", help="单轮对话模式")
    add_verbose_flag(chat)
    chat.add_argument("question", help="用户问题")
    chat.add_argument("--max-steps", type=int, default=DEFAULT_MAX_STEPS, help="最大推理步数")
    chat.add_argument("--llm-mode", choices=["mock", "http"], default=DEFAULT_LLM_MODE, help="LLM 运行模式")
    chat.add_argument("--base-url", default=DEFAULT_BASE_URL, help="真实模型服务地址")
    chat.add_argument("--model", default=DEFAULT_MODEL, help="模型名称")
    chat.add_argument("--api-key", help="模型 API Key，可省略并从环境变量读取")
    chat.add_argument("--max-tokens", type=int, default=DEFAULT_MAX_TOKENS, help="模型输出 token 上限")
    chat.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT, help="HTTP 请求超时秒数")
    add_auto_memory_flag(chat)

    repl = subparsers.add_parser("repl", help="多轮交互模式")
    add_verbose_flag(repl)
    repl.add_argument("--llm-mode", choices=["mock", "http"], default=DEFAULT_LLM_MODE, help="LLM 运行模式")
    repl.add_argument("--base-url", default=DEFAULT_BASE_URL, help="真实模型服务地址")
    repl.add_argument("--model", default=DEFAULT_MODEL, help="模型名称")
    repl.add_argument("--api-key", help="模型 API Key，可省略并从环境变量读取")
    repl.add_argument("--max-tokens", type=int, default=DEFAULT_MAX_TOKENS, help="模型输出 token 上限")
    repl.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT, help="HTTP 请求超时秒数")
    add_auto_memory_flag(repl)
    listing = subparsers.add_parser("list", help="列出全部记忆")
    add_verbose_flag(listing)

    remember = subparsers.add_parser("remember", help="手动添加长期记忆")
    add_verbose_flag(remember)
    remember.add_argument("--type", required=True, help="记忆类型")
    remember.add_argument("--name", required=True, help="记忆名称")
    remember.add_argument("--description", required=True, help="记忆摘要")
    remember.add_argument("--body", required=True, help="记忆正文")
    remember.add_argument("--filename", help="可选文件名")

    delete = subparsers.add_parser("delete", help="删除指定记忆")
    add_verbose_flag(delete)
    delete.add_argument("filename", help="待删除的记忆文件名")
    return parser


def command_init_demo(store: MemoryStore) -> int:
    """初始化演示数据."""

    written = seed_demo_memories(store.root)
    print(f"已初始化 {len(written)} 条演示记忆到: {store.root}")
    return 0


def command_list(store: MemoryStore) -> int:
    """打印全部记忆."""

    entries = store.list_memories()
    if not entries:
        print("当前没有记忆。")
        return 0
    for index, entry in enumerate(entries, start=1):
        print(f"{index}. [{entry.memory_type}] {entry.name} ({entry.path.name})")
        print(f"   {entry.description}")
    return 0


def command_remember(args: argparse.Namespace, store: MemoryStore) -> int:
    """手动写入记忆."""

    file_path = store.upsert_memory(args.type, args.name, args.description, args.body, args.filename)
    print(f"记忆已写入: {file_path.name}")
    return 0


def command_delete(args: argparse.Namespace, store: MemoryStore) -> int:
    """删除记忆."""

    if store.delete_memory(args.filename):
        print(f"记忆已删除: {args.filename}")
        return 0
    print(f"未找到记忆: {args.filename}")
    return 1


def command_chat(args: argparse.Namespace, store: MemoryStore, logger: Logger) -> int:
    """执行单轮 ReAct 对话."""

    question = sanitize_text(args.question)
    llm_config = LLMClientConfig(
        mode=args.llm_mode,
        model=args.model,
        base_url=args.base_url,
        api_key=resolve_api_key(args.api_key),
        max_tokens=args.max_tokens,
        timeout=args.timeout,
    )
    agent = ReActAgent(
        store=store,
        logger=logger,
        llm_config=llm_config,
        enable_auto_memory=not getattr(args, "disable_auto_memory", False),
    )
    answer = agent.run(question=question, max_steps=args.max_steps)
    print(f"\nAssistant: {answer}")
    return 0


def command_repl(args: argparse.Namespace, store: MemoryStore, logger: Logger) -> int:
    """进入 REPL 模式，便于现场多轮演示."""

    print("进入 REPL 模式，输入 exit 或 quit 退出。")
    while True:
        try:
            question = input("\nYou> ").strip()
        except EOFError:
            print()
            return 0
        if question in {"exit", "quit"}:
            return 0
        if not question:
            continue
        chat_args = argparse.Namespace(
            question=sanitize_text(question),
            max_steps=DEFAULT_MAX_STEPS,
            llm_mode=args.llm_mode,
            model=args.model,
            base_url=args.base_url,
            api_key=args.api_key,
            max_tokens=args.max_tokens,
            timeout=args.timeout,
        )
        command_chat(chat_args, store, logger)


def main() -> int:
    """程序主入口."""

    parser = build_parser()
    args = parser.parse_args()
    logger = Logger(verbose=args.verbose)
    store = MemoryStore(args.memory_dir)
    store.ensure()

    if args.command == "init-demo":
        return command_init_demo(store)
    if args.command == "list":
        return command_list(store)
    if args.command == "remember":
        return command_remember(args, store)
    if args.command == "delete":
        return command_delete(args, store)
    if args.command == "chat":
        return command_chat(args, store, logger)
    if args.command == "repl":
        return command_repl(args, store, logger)
    parser.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
