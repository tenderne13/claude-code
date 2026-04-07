# Claude Code Memory Viewer 设计交接

## 0. 术语对照表

为了避免后续讨论时只剩英文 key，这里先统一一份术语对照。

- `viewer`：观察页面、观察台
- `session`：会话
- `sessionId`：会话 ID
- `query turn`：请求轮次
  说明：通常指从一条真实用户输入开始，到下一条真实用户输入之前的这一轮上下文
- `selected turn`：当前聚焦轮次
- `turn insights`：本轮洞察
  说明：解释这一轮为什么会这样回答
- `prompt`：用户请求
- `assistant response`：助手回复
- `injection`：注入
  说明：记忆被塞进模型上下文窗口
- `exact injection`：精确注入记录
  说明：transcript 中确实存在相关 attachment，可确认这轮真的注入了这些 memory
- `relevant memories`：相关记忆
  说明：系统为当前 query 选择并注入的 memory
- `nested memory`：嵌套记忆
  说明：由其他 memory 文件或 CLAUDE.md 链接展开后带入的记忆
- `recall candidates`：关联记忆候选
  说明：由读取轨迹推断，可能参与了回答，但不一定真正注入
- `memory activity`：记忆活动、记忆访问轨迹
  说明：读、写、编辑等行为记录
- `timeline`：时间线、流转时间线
- `session memory`：会话记忆
  说明：服务于当前 session 的结构化记忆摘要，不是长期 durable memory
- `durable memory`：持久记忆
- `agent memory`：Agent 专属记忆
- `injected / touched / stored`：已注入 / 已触达 / 已存储

## 1. 目标

这个 viewer 的目标不是简单展示 memory 文件，而是把 Claude Code 的记忆系统拆成可观察的几个层面：

- 当前项目有哪些 session
- 某个 session 当前关联了哪些 memory
- 某一轮 query 实际注入了哪些 memory
- 对话过程中 memory 如何被读取、写入、更新
- session memory、durable memory、agent memory 各自处于什么状态

当前实现已经从“文件列表页”演进成“可切项目的双视图观察台”：

- `Workbench`：三栏工作台，适合按 session / turn 排查
- `Flow`：单轮执行流程图，适合解释某一轮的注入、读写和产出

## 2. 当前实现位置

- 后端入口: [server.py](/Users/lixp/lxpConfig/pyWorkSpace/claude-code/memory_design/memory-viewer/server.py)
- 前端页面: [index.html](/Users/lixp/lxpConfig/pyWorkSpace/claude-code/memory_design/memory-viewer/static/index.html)
- 前端逻辑: [app.js](/Users/lixp/lxpConfig/pyWorkSpace/claude-code/memory_design/memory-viewer/static/app.js)
- 样式: [styles.css](/Users/lixp/lxpConfig/pyWorkSpace/claude-code/memory_design/memory-viewer/static/styles.css)
- 使用说明: [README.md](/Users/lixp/lxpConfig/pyWorkSpace/claude-code/memory_design/memory-viewer/README.md)
- 记忆系统背景说明: [memory_system.md](/Users/lixp/lxpConfig/pyWorkSpace/claude-code/memory_design/memory-viewer/memory_system.md)

## 3. 技术方案

### 3.1 后端

采用 Python 标准库实现，避免引入额外依赖：

- `http.server` 提供静态页面和 JSON API
- `ThreadingHTTPServer` 提供本地浏览器访问
- SSE 提供实时刷新
- 文件变化轮询作为实时更新机制

### 3.2 前端

纯静态页面：

- 原生 HTML/CSS/JS
- 无前端框架
- 通过 `/api/snapshot` 拉取快照
- 通过 `/api/stream` 接收实时更新

### 3.3 数据源

viewer 目前直接读取 Claude Code 本地持久化目录：

- `~/.claude/projects/<project>/` 下的 session `.jsonl`
- `~/.claude/projects/<project>/memory/`
- `~/.claude/projects/<project>/memory/logs/`
- `~/.claude/projects/<project>/<sessionId>/session-memory/summary.md`
- `~/.claude/agent-memory/`
- `<project>/.claude/agent-memory/`
- `<project>/.claude/agent-memory-local/`

不依赖远端 API，也不侵入 CLI 主链路。

当前约定：

- `Team Memory` 暂不在 viewer 中单独展示
- `KAIROS Daily Logs` 作为独立记忆分组展示

## 4. 当前页面结构

当前页面已经被重构为“侧边栏 + 双视图主区域”。

### 4.0 侧边栏

作用：先选项目，再选 session。

包含：

- 已知项目下拉框
- 手动输入项目绝对路径并切换
- 当前项目元信息
- session 下拉框
- 历史 session 列表
- SSE 连接状态

### 4.1 Workbench 左栏

作用：选 session、选 query turn、快速看近期上下文。

包含：

- session 下拉框
- 历史 session 列表
- query turn 列表
- 最近消息

### 4.2 Workbench 中栏

作用：看“这轮上下文里到底有什么”。

包含：

- Selected Turn 卡片，即“当前聚焦轮次”
- 按轮注入的 Memory，即“本轮实际进入上下文的记忆”
- Session Memory，即“当前会话记忆”
- 记忆文件总览

### 4.3 Workbench 右栏

作用：看“为什么会这样回答，以及后续发生了什么”。

包含：

- Turn Insights，即“本轮洞察”
- 关联记忆候选，即“可能参与回答的记忆候选”
- 记忆访问轨迹，即“memory activity”
- 流转时间线，即“timeline”
- 记忆索引

### 4.4 Flow 视图

作用：把单个 query turn 串成一条可解释的执行链。

当前阶段节点：

- `User Prompt`
- `Memory Prep`
- `Model Reasoning`
- `Tool Execution`
- `Assistant Response`
- `Post Process`

当前交互能力：

- 支持从左侧 turn 选择同步到 Flow 视图
- 支持显示 injected / nested / read / written / session summary 等附加节点
- 支持点击节点查看详情浮层
- 支持按类别过滤显示：
  - `Injected`
  - `Writes`
  - `Session`

补充设计原则：

- Flow 不是静态架构图，而是随 session 和 turn 动态变化的“时序解释层”
- 重点回答四件事：
  - 当前执行到了哪一步
  - 这一轮在哪个阶段用了哪些 memory
  - 这一轮在哪个阶段写入了哪些 memory
  - 输入、memory、工具执行、输出之间是什么关系
- 推荐保持“主流程骨架 + 动态事件挂点”的模式，而不是把所有事件平铺成时序图
- Flow 适合作为独立视图承载，当前 `Workbench / Flow` 顶部切换就是正确方向

当前主链路抽象可统一理解为：

`User Prompt -> Memory Prep -> Model Reasoning -> Tool Execution -> Assistant Response -> Post Process`

如果后续需要更细粒度拆分，可映射为：

- `User Prompt`
- `Load Base Memory`
- `Find Relevant Memories`
- `Inject Memories`
- `Model Reasoning`
- `Tool Execution`
- `Assistant Response`
- `Session Memory Update / Extract Memories / Memory Persisted`

当前节点和边的语义建议继续保持：

- `stage node`：主流程阶段骨架
- `memory node`：具体 memory 文件或 memory 分组
- `event badge`：挂在阶段节点上的摘要信息，如 injected / read / write / session updated
- `edge`：
  - `execution`：阶段顺序
  - `inject`：memory -> stage
  - `read`：memory 被读取
  - `write`：stage -> memory

数据可信度必须持续区分：

- `exact`：有 transcript attachment 或明确记录支撑
- `inferred`：可以从上下文或轨迹推断
- `missing`：数据缺失，不能伪装成已确认事实

当前推荐交互：

- 点击左侧 turn，Flow 切换到该轮
- hover 节点显示摘要
- 点击节点打开详情浮层
- 点击 memory 节点高亮相关边
- 筛选器优先支持 `Injected / Writes / Session / Exact`

## 5. 当前已实现能力

### 5.1 session 维度

- 默认打开当前项目最新 session
- 支持切换历史 `sessionId`
- 支持切换到其他 Claude 项目
- 支持扫描 `~/.claude/projects/` 形成已知项目列表
- 支持手动输入任意项目绝对路径并切换
- 展示 session 基本信息
- 展示最近 prompt、事件数、记忆触达数

### 5.2 memory 维度

- 展示 project memory
- 展示 KAIROS daily logs
- 展示 agent user/project/local memory
- 展示 session memory
- 展示 MEMORY.md 等索引文件
- 标记本 session 触达过的 memory 文件
- 按 memory group 展示完整内容预览
- 抽取 frontmatter 中的 `name / description / type`

当前 viewer 中“已展示的记忆类型”可分两层理解：

- 存储层类型：
  - `Project Memory`
  - `KAIROS Daily Logs`
  - `Session Memory`
  - `Agent User Memory`
  - `Agent Project Memory`
  - `Agent Local Memory`
- durable memory frontmatter 类型：
  - `user`
  - `feedback`
  - `project`
  - `reference`

当前未展示：

- `Team Memory`

### 5.3 实时性

- 页面打开后自动建立 SSE 连接
- session transcript 变化时自动刷新
- memory 文件变化时自动刷新
- session memory 变化时自动刷新
- 项目切换后自动重建 snapshot 与 SSE 订阅
- 连接断开后 3 秒自动重连
- SSE 心跳保活

### 5.4 可视化能力

- 记忆访问轨迹
- 关联记忆候选
- 流转时间线
- 按 query turn 查看 memory 注入情况
- turn 级别的响应上下文观察
- `Workbench / Flow` 双视图切换
- Flow 执行链路图
- Flow 图例与边类型区分：
  - execution
  - inject
  - read
  - write
- Flow 详情浮层
- Flow 过滤器：`Injected / Writes / Session`

### 5.5 turn 维度

- 按真实用户输入切分 query turn
- 默认优先选中最近一个存在精确注入记录的 turn
- 展示 turn 级：
  - prompt
  - assistant response
  - exact relevant memories
  - nested memories
  - memory reads
  - memory writes
  - tool count / memory read count / memory write count
  - nearby transcript

## 6. 当前后端数据模型

### 6.1 snapshot 顶层结构

当前 `/api/snapshot` 返回大致结构：

```json
{
  "generatedAt": "...",
  "projectRoot": "...",
  "projectStorageDir": "...",
  "defaultSessionId": "...",
  "selectedSessionId": "...",
  "sessions": [...],
  "session": {...},
  "memory": {...}
}
```

### 6.2 session 结构

当前 `session` 中重点字段：

- `recentMessages`
- `memoryActivity`
- `timeline`
- `queryTurns`
- `selectedQueryTurnId`
- `transcriptPath`
- `eventCount`
- `lastPrompt`
- `entrypoint`
- `slug`

### 6.3 memory 结构

当前 `memory` 中重点字段：

- `sessionSummary`
- `indexes`
- `groups`
- `recallCandidates`

其中 `groups` 当前会包含：

- `project-memory`
- `kairos-daily-log`
- `agent-user-memory`
- `agent-project-memory`
- `agent-local-memory`

### 6.4 新增项目级接口

除了 `/api/snapshot` 和 `/api/stream`，当前还新增了：

- `/api/projects`
  作用：列出 `~/.claude/projects/` 下已知且有 session 的项目
- `/api/set-project`
  作用：切换当前 viewer 指向的项目根目录

### 6.5 Flow 数据映射与后续结构建议

当前 Flow 视图已经能直接复用这些数据：

- `session.queryTurns`
- `session.selectedQueryTurnId`
- `session.memoryActivity`
- `session.timeline`
- `memory.sessionSummary`
- `memory.recallCandidates`
- `memory.groups`

当前主要映射关系：

- `User Prompt`：来自 `queryTurns[].userPrompt`
- `Inject Memories`：来自 `queryTurns[].exactRelevantMemories`
- `Nested Memory`：来自 `queryTurns[].nestedMemories`
- `Tool Execution`：来自 `memoryActivity`
- `Session Memory Update`：来自 `memory.sessionSummary.updatedAt`
- `Assistant Response`：来自当前 turn 邻近的 assistant message

如果后续想把 Flow 变成更稳定的协议层，而不是前端现场拼装，建议后端补一个独立的 `flow` 结构，例如：

```json
{
  "flow": {
    "turnId": "...",
    "nodes": [...],
    "edges": [...],
    "summary": {
      "hasExactInjectionRecord": true,
      "injectedMemoryCount": 2,
      "nestedMemoryCount": 1,
      "memoryReadCount": 3,
      "memoryWriteCount": 1,
      "sessionMemoryUpdated": true
    }
  }
}
```

其中建议：

- `nodes` 同时覆盖 `stage` 和 `memory` 两类节点
- `edges` 明确区分 `execution / inject / read / write`
- `summary` 负责聚合本轮最常用的诊断指标

## 7. “某一轮 query 实际注入了哪些 memory”的实现现状

这是当前 viewer 最关键、也最容易误解的部分。

### 7.1 代码链路确认

Claude Code 底层 relevant memory 不是普通 `Read` 工具调用，而是 attachment 机制：

- 相关选择逻辑在 `src/memdir/findRelevantMemories.ts`
- attachment 注入逻辑在 `src/utils/attachments.ts`
- 相关 attachment 类型是 `attachment.type === 'relevant_memories'`

这意味着：

- “实际注入”不能仅靠工具读写记录判断
- 最可靠的来源是 transcript 中落盘的 `attachment` 事件

### 7.2 viewer 当前策略

viewer 现在采用两层策略：

1. 精确层：
   如果 transcript 中存在 `relevant_memories` attachment，就按 query turn 精确展示这轮实际注入的 memory。

2. 推断层：
   如果 transcript 中没有该 attachment，则只能展示：
   - 关联记忆候选
   - 记忆访问轨迹
   - nested memory
   但不能声称这是“精确注入”。

### 7.3 当前限制

在目前实际扫到的本地 session 数据里，`relevant_memories` attachment 并不稳定存在，因此：

- viewer 代码已经支持精确展示
- 但历史数据不一定能提供这类记录
- 页面会明确提示“这轮没有精确 relevant memory 注入记录”

这是数据缺口，不是 viewer 解析失败。

## 8. Query Turn 的定义

这里的 `Query Turn` 可理解为“请求轮次”。

viewer 当前把一个 query turn 定义为：

- 一条真正的用户输入消息开始
- 排除 `toolUseResult` 型 user message
- 在遇到下一条真正 user message 之前，归属于当前 turn 的 attachment 都算本轮上下文

当前 turn 内关注：

- `exactRelevantMemories`
- `nestedMemories`
- `userPrompt`
- `timestamp`
- `hasExactRelevantMemoryRecord`

## 9. 三种 memory 状态的设计建议

后续设计时，建议始终区分这三类状态，不要混用：

### 9.1 Injected

真正被注入到本轮模型上下文里的 memory。

来源：

- `relevant_memories` attachment
- `nested_memory` attachment

### 9.2 Touched

本轮或本 session 中被工具读写过的 memory。

来源：

- transcript 里的 `Read / Write / Edit / MultiEdit`
- tool result 中的 filePath

### 9.3 Stored

磁盘上当前存在的 memory。

来源：

- `~/.claude/projects/.../memory/`
- `session-memory/`
- `agent-memory/`

这个区分非常重要，因为它决定了用户看到的是：

- 模型“看到了什么”
- 执行过程中“碰到了什么”
- 系统里“存着什么”

## 10. 当前最值得继续做的方向

### 10.1 viewer 继续增强

建议优先顺序：

1. 增加更细粒度筛选器
2. 增加候选 vs 精确注入对照视图
3. 增强 Flow 图
4. 增加颜色语义与跨视图联动

具体如下。

#### 10.1.1 更细粒度筛选器

当前已经有的筛选：

- Flow 视图中的 `Injected`
- Flow 视图中的 `Writes`
- Flow 视图中的 `Session`

后续建议继续增加：

- `只看 exact injected`
- `只看 touched`
- `只看 writes`
- `只看某类 memoryType`
- `只看当前 turn`

这是最直接提升可用性的改动。

#### 10.1.2 颜色语义

建议时间线和活动卡片用不同颜色区分：

- user/assistant
- memory injection
- memory read
- memory write
- session memory update

这样观察一长串时间线时更容易定位关键事件。

#### 10.1.3 对照视图

建议做一个双栏或 Tab：

- 左边：本轮“候选/触达”的 memory
- 右边：本轮“精确注入”的 memory

这能直接帮助判断 recall 质量和命中偏差。

#### 10.1.4 Flow 图继续增强

当前已经不是待做项，Flow 视图已实现一版原生 SVG 流程图。

后续建议增强为：

- 增加 tool 节点明细，不只汇总在 stage meta 中
- 支持 hover 高亮整条边
- 支持按时间或类型折叠附加节点
- 如果需要对外演示，再补 Mermaid 导出能力

当前这条主链已经是：

`user prompt -> memory prep -> model reasoning -> tool execution -> assistant response -> post process`

### 10.2 主链路埋点增强

如果目标是把 viewer 变成“精确诊断工具”，最关键的不是继续堆前端，而是补主链路埋点。

建议在 relevant memory attachment 生成后、消息入 transcript 前，追加一条稳定的 turn 级事件，至少包含：

- `turnId`
- `query text`
- `selected memory paths`
- `selection time`
- `iteration`

这样 viewer 就不需要依赖 attachment 是否恰好被持久化。

## 11. 当前验证情况

本次实现已做过的本地校验：

- `python3 -m py_compile memory_design/memory-viewer/server.py`
- `node --check memory_design/memory-viewer/static/app.js`

这两项都已经通过。

由于当前环境里的端口绑定受沙箱限制，无法在这段对话里直接把服务跑起来对外访问，但本地执行 README 中的启动命令即可。

## 12. 启动方式

```bash
cd /Users/lixp/lxpConfig/pyWorkSpace/claude-code
python3 memory_design/memory-viewer/server.py
```

默认地址：

```text
http://127.0.0.1:8765
```

## 13. 建议的下一步执行顺序

如果后续继续做，建议按这个顺序推进：

1. 补更细粒度筛选器和颜色语义
2. 做候选 vs 精确注入对照视图
3. 增强现有 Flow 图，而不是从零做 Mermaid
4. 视需要补主链路埋点
5. 如果埋点补齐，再把 viewer 升级成严格的 turn-level debug tool

## 14. 一句话总结

当前这套 viewer 已经具备了一个可工作的“记忆观察台”雏形：

- 能切项目
- 能看 session
- 能看 memory
- 能看实时变化
- 能看 turn
- 能看单轮执行 Flow
- 能在有 attachment 记录时精确展示 relevant memory 注入

下一步要么增强可视化体验，要么补主链路埋点，把它变成真正的精确诊断台。
