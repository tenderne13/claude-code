# Claude Code 记忆子系统拆解

基于 [memory-system.md](/Users/lixp/lxpConfig/pyWorkSpace/claude-code/memory_design/memory-system.md) 的总览，这里将各类记忆机制拆成独立文档，便于分别分析设计意图、执行链路和车机语音系统映射。

## 文档索引

1. [01-auto-memory-analysis.md](/Users/lixp/lxpConfig/pyWorkSpace/claude-code/memory_design/01-auto-memory-analysis.md)
2. [02-team-memory-analysis.md](/Users/lixp/lxpConfig/pyWorkSpace/claude-code/memory_design/02-team-memory-analysis.md)
3. [03-kairos-daily-log-analysis.md](/Users/lixp/lxpConfig/pyWorkSpace/claude-code/memory_design/03-kairos-daily-log-analysis.md)
4. [04-dream-consolidation-analysis.md](/Users/lixp/lxpConfig/pyWorkSpace/claude-code/memory_design/04-dream-consolidation-analysis.md)
5. [05-session-memory-analysis.md](/Users/lixp/lxpConfig/pyWorkSpace/claude-code/memory_design/05-session-memory-analysis.md)
6. [06-extract-memories-analysis.md](/Users/lixp/lxpConfig/pyWorkSpace/claude-code/memory_design/06-extract-memories-analysis.md)
7. [07-agent-memory-analysis.md](/Users/lixp/lxpConfig/pyWorkSpace/claude-code/memory_design/07-agent-memory-analysis.md)
8. [08-remember-skill-analysis.md](/Users/lixp/lxpConfig/pyWorkSpace/claude-code/memory_design/08-remember-skill-analysis.md)

## 建议阅读顺序

1. 先看 `auto-memory`，理解 Claude Code 的主长期记忆形态。
2. 再看 `team memory`、`agent memory`，理解 scope 拆分。
3. 然后看 `KAIROS` 与 `dream/consolidation`，理解日志化与离线蒸馏。
4. 最后看 `SessionMemory`、`extractMemories`、`remember`，理解续写、补写和人工治理。
