# Progress

更新时间：2026-04-12

## 当前状态

项目已完成第一阶段骨架搭建，可以直接运行并演示：

- 记忆索引 `MEMORY.md` 的初始化与维护
- 基于关键词召回的记忆搜索
- ReAct 核心循环日志输出
- `chat` 与 `repl` 两种交互方式
- `remember` / `delete` 的手动记忆治理
- 回合结束后的 Auto Memory / `extractMemories` 演示链路

## 当前默认实现策略

- LLM 层使用规则驱动 Mock，实现稳定、可预测的技术分享演示
- 当前默认使用真实 HTTP 模型模式，也可通过 `--llm-mode mock` 切回规则驱动模式
- 重点优先展示模块拆分、上下文构建和工具调用链路
- 默认开启 Auto Memory，可通过 `--disable-auto-memory` 关闭后做 AB 对比
- 如需避免现场网络波动，可显式传入 `--llm-mode mock`

## 建议下次续做入口

建议从 `ResponseParser` 和真实模型返回兼容性继续完善，尤其是：

`增加更细的 ResponseParser，支持解析真实模型返回的工具调用结构`
