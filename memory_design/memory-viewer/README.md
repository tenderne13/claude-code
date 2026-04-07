# Memory Viewer MVP

一个独立的浏览器可视化工具，用来展示当前项目下 Claude Code session 和记忆文件的关系。

## 这版覆盖的能力

- 默认打开当前项目最近更新的 session
- 可切换历史 `sessionId`
- 实时刷新 session transcript / session memory / project memory / agent memory 的变化
- 展示 `KAIROS Daily Logs`
- 从 session `.jsonl` 中提取记忆访问轨迹，展示哪些 memory 文件被读写过
- 输出“关联记忆候选”，把 session 实际读过的 memory 文件聚合出来
- 输出“流转时间线”，把消息、memory 读写、session memory 更新放到同一视图
- 按 query turn 展示 transcript 中精确记录的 `relevant_memories` 注入结果

当前不展示：

- `Team Memory`

## 启动方式

```bash
cd /Users/lixp/lxpConfig/pyWorkSpace/claude-code
python3 memory_design/memory-viewer/server.py
```

默认地址：

```text
http://127.0.0.1:8765
```

## 可选参数

```bash
python3 memory_design/memory-viewer/server.py \
  --host 127.0.0.1 \
  --port 8765 \
  --project-root /Users/lixp/lxpConfig/pyWorkSpace/claude-code \
  --claude-home /Users/lixp/.claude
```

## 当前实现思路

- 后端：Python 标准库 `http.server`，无额外依赖
- 实时：SSE + 文件变化轮询
- 数据源：
- `~/.claude/projects/<project>/` 下的 session `.jsonl`
- `~/.claude/projects/<project>/memory/`
- `~/.claude/projects/<project>/memory/logs/`
- `~/.claude/projects/<project>/<sessionId>/session-memory/summary.md`
- `~/.claude/agent-memory/`
- `<project>/.claude/agent-memory/`
- `<project>/.claude/agent-memory-local/`
- transcript 里的 `attachment.type === 'relevant_memories'` 与 `nested_memory`

## 适合下一步补强的点

- 如果某些运行模式没有把 `relevant_memories` attachment 落盘，需要在 query 链路补埋点或补持久化
- 增加 Mermaid 流转图，把 transcript 事件和 memory 文件变更串起来
- 对接 watcher 而不是轮询，降低空闲刷新成本
- 增加 filter，只看某类 memory 或只看本 session 改过的 memory
