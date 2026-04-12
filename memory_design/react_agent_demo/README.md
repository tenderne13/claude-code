# ReAct Agent Demo

基于 `tasks/prd-react-agent-framework.md` 实现的 Python 命令行演示项目。目标是把单文件版记忆 Demo 拆成模块化 ReAct Agent 框架，便于技术分享时讲解以下内容：

- ReAct 循环：Thought / Action / Observation / Final Answer
- 上下文工程：系统提示词、MEMORY.md 索引、相关记忆注入
- 记忆系统：list / search / read / upsert / delete 五类操作
- Auto Memory：回合结束后自动抽取 durable memory 并写回 `demo_memory_store`
- 演示数据：预置用户偏好、项目事实、反馈约束、参考原则

## 目录结构

```text
react_agent_demo/
├── agent/
├── config/
├── context/
├── demo_data/
├── demo_memory_store/
├── llm/
├── memory/
├── tools/
├── utils/
├── main.py
├── README.md
├── TODO.md
└── PROGRESS.md
```

## 快速开始

```bash
cd /Users/lixp/lxpConfig/pyWorkSpace/claude-code/memory_design/react_agent_demo
python3 main.py init-demo
python3 main.py list
python3 main.py chat "用户更偏好什么编程语言？" --verbose
python3 main.py chat "我不喜欢韭菜，以后推荐菜时避开" --llm-mode mock --verbose
python3 main.py repl --verbose
python3 main.py chat "用户更偏好什么编程语言？" --llm-mode mock --verbose
python3 main.py chat "我不喜欢韭菜，以后推荐菜时避开" --llm-mode mock --verbose --disable-auto-memory
```

## CLI 命令

- `init-demo`：初始化预置记忆
- `chat "<问题>"`：执行单轮 ReAct 演示
- `repl`：多轮演示模式
- `list`：查看所有记忆
- `remember`：手动添加记忆
- `delete`：删除指定记忆
- `--disable-auto-memory`：关闭回合结束后的自动记忆抽取，便于对比演示

## LLM 模式

- `http`：默认模式，真实调用 `demo_memory_cli.py` 已验证可通的模型服务
- `mock`：规则驱动回退模式，适合离线或稳定演示

真实调用示例：

```bash
python3 main.py chat "用户更偏好什么编程语言？" \
  --llm-mode http \
  --base-url "https://your-llm-service.example.com/v1/messages" \
  --model "kimi-k2.5"
```

可选从环境变量读取 API Key：

- `FUYAO_API_KEY`
- `XIAOPENG_API_KEY`
- `OPENAI_API_KEY`
- `ANTHROPIC_API_KEY`

## 架构关系

```text
main.py
  -> ReActAgent
     -> AgentLoop
        -> ContextBuilder + ContextManager
        -> AutoMemoryManager
        -> LLMClient(Mock)
        -> ToolExecutor
           -> ToolRegistry
              -> list/search/read/upsert/delete
                 -> MemoryStore
                    -> IndexManager + MemorySearch + MEMORY.md
```

## 说明

- 当前默认使用规则驱动的 `Mock LLM`，保证分享现场稳定复现 ReAct 流程。
- `--verbose` 会打印上下文构建摘要，方便讲解模型“看到了什么”。
- `memory/auto_memory.py` 是演示版 `extractMemories`，在每轮结束后根据用户输入抽取稳定偏好、反馈约束或项目事实并写回。
- 项目仅依赖 Python 标准库，便于在任意终端环境快速运行。
