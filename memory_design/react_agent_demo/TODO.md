# TODO

最后更新：2026-04-12

## 已完成

- [x] 建立 `agent / context / memory / tools / llm / utils / demo_data / config` 模块边界
- [x] 实现 `MemoryStore`、`IndexManager`、`MemorySearch`
- [x] 实现 `list/search/read/upsert/delete` 五个记忆工具
- [x] 实现 `chat / repl / list / remember / delete / init-demo` CLI 命令
- [x] 提供规则驱动 `Mock LLM`，可稳定展示 ReAct 主循环
- [x] 提供 `--verbose` 上下文日志输出
- [x] 增加演示版 Auto Memory / `extractMemories`，支持回合结束后自动写回长期记忆

## 待完成

- [x] 为 `llm/client.py` 增加真实 HTTP LLM 调用模式，并和 Mock 模式可切换
- [ ] 增加更细的 `ResponseParser`，支持解析真实模型返回的工具调用结构
- [ ] 为 `ContextBuilder` 增加策略模式，支持不同上下文注入策略对比演示
- [ ] 为 `remember` 与 `chat` 增加更可靠的 durable memory 判定逻辑，减少自动抽取误判
- [ ] 增加单元测试与 `python -m unittest` 覆盖核心链路
- [ ] 增加架构图图片版，便于 PPT 直接引用
- [ ] 为 REPL 增加会话内历史摘要展示，强化“记忆积累”演示效果
- [ ] 支持更友好的读取指令解析，例如“打开编程语言偏好那条记忆”

## 下次建议优先级

1. 先补真实 LLM 接口和响应解析，这样项目就能从“稳定演示版”升级到“真实调用版”。
2. 然后补测试，锁定当前模块边界，避免继续迭代时回归。
3. 最后补策略模式和分享素材，提升技术分享的讲解效果。
