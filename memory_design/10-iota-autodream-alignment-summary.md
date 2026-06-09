# iota 对齐 autoDream 能力方案摘要

## 1. 要解决什么问题

当前 `iota-core` 和 `iota-memory` 已经分别解决了两件事：

- session transcript 不再依赖本地存储，具备集群能力
- 长期记忆不再依赖本地 markdown，具备服务化能力

但还缺一条关键链路：

> 缺少类似 `autoDream` 的后台记忆整理能力，无法持续把近期 session 中的新信息整理进长期记忆，也无法把“记忆被改写”作为正式事件暴露出来。

这也是本次对齐的核心目标。

## 2. 结论

`autoDream` 的本质不是“再存一条 memory”，而是后台长期记忆治理：

- 从近期 session 中收集增量信号
- 与已有长期记忆做对比
- 对记忆执行合并、修正、替换、删除
- 输出本次整理结果

`iota` 对齐时，不需要复刻 `Claude Code` 的 `MEMORY.md + topic files` 文件形态，但必须补齐同等能力：

1. 后台 consolidation 调度
2. 基于近期 session 的记忆整理编排
3. 记忆改写事件
4. 多用户隔离下的安全治理

## 3. 职责边界

建议明确分层，避免能力混杂。

`iota-core` 负责：

- 从 `RedisClaudeSessionStore` / `RedisConversationStore` 收集近期 session 信号
- 做时间门控、session 数门控、并发锁控制
- 组织 consolidation 输入
- 调用模型或独立 agent 产出整理决策

`iota-memory` 负责：

- 提供统一的 memory query / write / search / classify 能力
- 提供 `create / supersede / delete / history` 等 mutation 能力
- 对外发布 `MemoryChangedEvent`

不建议让 `iota-memory` 内嵌智能体或 dream agent。否则 memory service 会和 agent orchestration 耦合，边界会变差。

## 4. 多用户约束

`Claude Code` / `Hermes` 的 `autoDream` 基本建立在单用户前提上；`iota` 不是。

因此 `iota` 的 consolidation 不能按“全局统一做梦”设计，而必须按隔离域执行。最小治理单元建议是：

- `tenant_id + user_scope_id`
- `tenant_id + project_scope_id`
- `tenant_id + agent_namespace`

所有 consolidation job、memory query、memory write、change event 都必须带：

- `tenant_id`
- `isolation_key`
- `scope_type`
- `scope_id`

否则会有跨用户串扰和误改写风险。

## 5. 记忆怎么整理

建议把整理过程定义为一条后台链路，而不是单次写入动作：

1. `iota-core` 收集最近一段时间的 session summary、recent transcript hint、已有长期记忆摘要
2. consolidation agent 基于这些输入产出决策：
   - `create`
   - `merge`
   - `supersede`
   - `delete`
   - `keep`
3. `iota-memory` 执行正式写回
4. 每次改写都生成 `MemoryChangedEvent`

整理原则建议保持和 `autoDream` 一致：

- 优先更新已有主题，不堆重复记忆
- 允许旧记忆被新证据覆盖
- 相对时间改写成绝对时间
- 过滤临时任务状态、debug 噪声、一次性路径信息

## 6. 为什么“记忆被改写”一定要事件化

只保留最终 memory 状态不够，因为系统还需要知道：

- 哪条记忆被谁改了
- 为什么改
- 改写前后是什么关系
- 是否影响了其他 scope 或其他消费方

因此建议把 `MemoryChangedEvent` 作为正式领域事件输出，至少覆盖：

- `created`
- `updated`
- `superseded`
- `deleted`

事件中建议带上：

- `tenant_id`
- `isolation_key`
- `memory_id`
- `previous_memory_id` / `superseded_ids`
- `scope_type` / `scope_id`
- `source`
- `job_id`
- `changed_at`
- `reason`

## 7. 建议落地路径

建议分三步推进：

### P1：补齐后台调度骨架

- 在 `iota-core` 增加 consolidation coordinator
- 补时间门控、session 门控、并发锁
- 打通 session summary / hint 输入

### P2：补齐整理编排与 mutation API

- 在 `iota-core` 增加 consolidation agent 编排
- 在 `iota-memory` 明确 `create / supersede / delete / history` API
- 建立整理决策到正式写回的链路

### P3：补齐改写事件与审计

- 发布 `MemoryChangedEvent`
- 提供按 tenant / user / project 查询的审计视图
- 支持回看某次 consolidation 改了哪些记忆

## 8. 一句话建议

建议把 `autoDream` 对齐成一条“多用户隔离下的后台记忆治理链路”：

- 智能整理在 `iota-core`
- memory domain 在 `iota-memory`
- 改写事件正式化
- 所有能力按 `tenant + scope` 隔离运行

这样既能对齐 `autoDream` 的核心价值，也不会破坏 `iota` 现有服务边界。
