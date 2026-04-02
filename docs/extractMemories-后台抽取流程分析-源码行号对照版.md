# extractMemories 后台抽取流程分析（源码行号对照版）

## 1. 文档目的

这份文档是 [extractMemories-后台抽取流程分析](/Users/lixp/lxpConfig/pyWorkSpace/claude-code/docs/extractMemories-后台抽取流程分析.md) 的源码对照版。

写法遵循一条原则：

- 每个结论都尽量落到具体文件和行号
- 优先给“入口、状态、分支、权限、写入、退出保障”这些真正影响行为的代码点

## 2. 总入口与初始化

### 2.1 系统启动时会初始化 extractMemories

结论：

- `extractMemories` 不是懒初始化
- 它在后台 housekeeping 启动时就会调用 `initExtractMemories()`

源码位置：

- `startBackgroundHousekeeping()` 调用 `initExtractMemories()`
- 文件：`src/utils/backgroundHousekeeping.ts:31-36`

对应代码点：

- `feature('EXTRACT_MEMORIES')` 判断：`src/utils/backgroundHousekeeping.ts:34`
- 真正初始化调用：`src/utils/backgroundHousekeeping.ts:35`

### 2.2 `initExtractMemories()` 创建闭包态状态机

结论：

- 运行状态不是分散的模块变量
- 是由 `initExtractMemories()` 一次性创建 closure-scoped 状态

源码位置：

- `initExtractMemories()` 定义：`src/services/extractMemories/extractMemories.ts:296`
- 注释说明“fresh closure captures all mutable state”：`src/services/extractMemories/extractMemories.ts:290-295`

## 3. stopHooks 触发链路

### 3.1 主触发点在 `handleStopHooks()`

结论：

- `extractMemories` 在每轮 query loop 结束后，由 stop hooks fire-and-forget 触发

源码位置：

- `handleStopHooks()` 中的触发逻辑：`src/query/stopHooks.ts:136-153`

关键行号：

- 不是 `--bare` 才会进入背景处理：`src/query/stopHooks.ts:136`
- `EXTRACT_MEMORIES` gate：`src/query/stopHooks.ts:142`
- 必须不是 subagent：`src/query/stopHooks.ts:143`
- 必须 `isExtractModeActive()`：`src/query/stopHooks.ts:144`
- 真正调用 `executeExtractMemories(...)`：`src/query/stopHooks.ts:149-152`

### 3.2 stopHooks 传入的是完整回合上下文

结论：

- 抽取看到的不是零散文本
- 而是 `REPLHookContext`，包含 messages、systemPrompt、userContext、systemContext、toolUseContext、querySource

源码位置：

- `stopHookContext` 构造：`src/query/stopHooks.ts:77-84`

## 4. 触发门控条件

### 4.1 `isExtractModeActive()` 是第一层总开关

结论：

- 抽取功能受 GrowthBook flag 控制
- 非交互模式下是否启用也受额外 flag 影响

源码位置：

- 函数定义：`src/memdir/paths.ts:69-77`

关键行号：

- `tengu_passport_quail` 总 gate：`src/memdir/paths.ts:70-72`
- 非交互补充 gate `tengu_slate_thimble`：`src/memdir/paths.ts:73-76`

### 4.2 auto memory 关闭时，extractMemories 也会直接失效

结论：

- 即使 stopHooks 触发到了 `executeExtractMemories`
- 只要 auto memory 关闭，内部也会直接返回

源码位置：

- `isAutoMemoryEnabled()` 定义：`src/memdir/paths.ts:30-55`
- `executeExtractMemoriesImpl()` 内部检查：`src/services/extractMemories/extractMemories.ts:544-547`

辅助说明：

- `CLAUDE_CODE_SIMPLE` 会让 auto memory 关闭：`src/memdir/paths.ts:38-43`
- `autoMemoryEnabled` setting 也能关闭：`src/memdir/paths.ts:50-53`

### 4.3 remote mode 下不会运行

结论：

- 当前是 remote mode 时，extractMemories 直接跳过

源码位置：

- remote mode 判断：`src/services/extractMemories/extractMemories.ts:549-552`

### 4.4 subagent 不参与 extractMemories

结论：

- 只有主线程参与后台抽取
- 子代理回合不会触发自己的 extractMemories

源码位置：

- stopHooks 入口处先排除：`src/query/stopHooks.ts:143`
- `executeExtractMemoriesImpl()` 再次排除：`src/services/extractMemories/extractMemories.ts:531-534`

## 5. 内部状态机

### 5.1 `inFlightExtractions` 记录所有未完成抽取

结论：

- 系统会保存所有尚未结束的抽取 Promise
- 供退出前 drain 使用

源码位置：

- 定义：`src/services/extractMemories/extractMemories.ts:299-303`
- 加入集合：`src/services/extractMemories/extractMemories.ts:569-572`
- 完成后移除：`src/services/extractMemories/extractMemories.ts:573-576`

### 5.2 `lastMemoryMessageUuid` 是增量游标

结论：

- 每次抽取只处理上次成功抽取之后新增的消息

源码位置：

- 定义：`src/services/extractMemories/extractMemories.ts:305-307`
- 计算消息数量时使用：`src/services/extractMemories/extractMemories.ts:338-343`
- 主线程已写 memory 时推进游标：`src/services/extractMemories/extractMemories.ts:352-355`
- fork 成功后推进游标：`src/services/extractMemories/extractMemories.ts:429-435`

### 5.3 `inProgress` 做并发互斥

结论：

- 同一时刻只允许一个 `runExtraction()`

源码位置：

- 定义：`src/services/extractMemories/extractMemories.ts:312-313`
- 开始执行时置 `true`：`src/services/extractMemories/extractMemories.ts:388`
- finally 中置 `false`：`src/services/extractMemories/extractMemories.ts:503-504`
- 入口处根据 `inProgress` 合并请求：`src/services/extractMemories/extractMemories.ts:554-563`

### 5.4 `turnsSinceLastExtraction` 做节流

结论：

- 不是每个触发回合都会真的 fork 抽取
- 是否抽取受阈值控制

源码位置：

- 定义：`src/services/extractMemories/extractMemories.ts:315-316`
- 节流逻辑：`src/services/extractMemories/extractMemories.ts:374-386`
- 阈值来源 `tengu_bramble_lintel`：`src/services/extractMemories/extractMemories.ts:381`

### 5.5 `pendingContext` 做尾随补跑

结论：

- 抽取执行过程中如果又来了新 stopHooks，不会并发排队
- 只保留最新一份 context，等当前执行完后补跑一次

源码位置：

- 定义：`src/services/extractMemories/extractMemories.ts:318-325`
- inProgress 时覆盖写入：`src/services/extractMemories/extractMemories.ts:554-563`
- finally 中取出并触发 trailing run：`src/services/extractMemories/extractMemories.ts:506-520`

## 6. 增量消息范围与主线程直写互斥

### 6.1 只统计模型可见消息

结论：

- `extractMemories` 的输入原料不是全部消息类型
- 只统计 `user` 与 `assistant`

源码位置：

- `isModelVisibleMessage()`：`src/services/extractMemories/extractMemories.ts:74-80`
- `countModelVisibleMessagesSince()`：`src/services/extractMemories/extractMemories.ts:82-109`

### 6.2 如果主模型已经写了 memory，后台抽取直接跳过

结论：

- 主线程直写优先级高于后台抽取
- 两者在同一批消息上是互斥的

源码位置：

- `hasMemoryWritesSince()` 定义：`src/services/extractMemories/extractMemories.ts:121-148`
- `runExtraction()` 中的跳过分支：`src/services/extractMemories/extractMemories.ts:345-360`
- 打点 `tengu_extract_memories_skipped_direct_write`：`src/services/extractMemories/extractMemories.ts:356-358`

### 6.3 判定“主线程已写 memory”的标准

结论：

- 它不是看普通文本
- 而是扫描 assistant tool_use block，检查是否有 Edit/Write 指向 auto memory 路径

源码位置：

- 写路径提取函数 `getWrittenFilePath()`：`src/services/extractMemories/extractMemories.ts:232-248`
- `hasMemoryWritesSince()` 遍历 assistant content：`src/services/extractMemories/extractMemories.ts:133-145`
- `isAutoMemPath(filePath)` 条件：`src/services/extractMemories/extractMemories.ts:141-143`

## 7. manifest 预扫描与 prompt 构建

### 7.1 抽取前会扫描已有 memory 清单

结论：

- 主线程会提前读取当前 memory 目录已有 topic 文件头部信息
- 注入给子代理，避免子代理自己浪费一轮去列目录

源码位置：

- 调用 `scanMemoryFiles()` + `formatMemoryManifest()`：`src/services/extractMemories/extractMemories.ts:395-400`

相关扫描逻辑：

- `scanMemoryFiles()`：`src/memdir/memoryScan.ts:32-69`
- 只扫描 `.md` 且排除 `MEMORY.md`：`src/memdir/memoryScan.ts:39-41`
- 读取 frontmatter 头部：`src/memdir/memoryScan.ts:43-57`
- 格式化 manifest：`src/memdir/memoryScan.ts:77-89`

### 7.2 根据是否启用 team memory 选择不同 prompt

结论：

- auto-only 和 combined prompt 是两套模板

源码位置：

- 分支选择：`src/services/extractMemories/extractMemories.ts:402-413`
- auto-only prompt 定义：`src/services/extractMemories/prompts.ts:50-94`
- combined prompt 定义：`src/services/extractMemories/prompts.ts:101-154`

### 7.3 prompt 明确限制“只分析最近消息，不要外扩验证”

结论：

- extract prompt 不允许把抽取扩展成代码调查任务

源码位置：

- prompt opener 定义：`src/services/extractMemories/prompts.ts:29-43`
- “只用最近消息”要求：`src/services/extractMemories/prompts.ts:35`
- “不要 grepping source / 不要读代码 / 不要 git 命令”：`src/services/extractMemories/prompts.ts:41-42`

### 7.4 prompt 明确要求先读后写

结论：

- prompt 显式要求：
  - 第 1 轮并行 Read
  - 第 2 轮并行 Write/Edit

源码位置：

- 工具策略说明：`src/services/extractMemories/prompts.ts:37-40`

## 8. fork 子代理执行

### 8.1 通过 `runForkedAgent()` 启动独立 query loop

结论：

- `extractMemories` 不是普通函数内直接写文件
- 而是 fork 一个真正的子代理 query loop 来完成

源码位置：

- `runForkedAgent(...)` 调用：`src/services/extractMemories/extractMemories.ts:415-427`

关键参数：

- `querySource: 'extract_memories'`：`src/services/extractMemories/extractMemories.ts:419`
- `forkLabel: 'extract_memories'`：`src/services/extractMemories/extractMemories.ts:420`
- `skipTranscript: true`：`src/services/extractMemories/extractMemories.ts:421-423`
- `maxTurns: 5`：`src/services/extractMemories/extractMemories.ts:424-426`

### 8.2 它会共享主线程 prompt cache 关键参数

结论：

- 抽取子代理复用主线程 cache-safe 参数，以便提高 prompt cache 命中

源码位置：

- `createCacheSafeParams(context)`：`src/services/extractMemories/extractMemories.ts:372`
- `CacheSafeParams` 解释：`src/utils/forkedAgent.ts:46-68`
- `createCacheSafeParams()` 定义：`src/utils/forkedAgent.ts:122-140`

### 8.3 为什么要 `skipTranscript: true`

结论：

- 子代理不记录 transcript，避免与主线程 transcript 写入发生竞争

源码位置：

- 注释与配置：`src/services/extractMemories/extractMemories.ts:421-423`

## 9. 权限边界

### 9.1 抽取代理的权限由 `createAutoMemCanUseTool()` 控制

结论：

- 所有工具使用都要先过这个权限函数

源码位置：

- 函数定义：`src/services/extractMemories/extractMemories.ts:171-220`
- 创建并注入：`src/services/extractMemories/extractMemories.ts:371`

### 9.2 允许的工具

结论：

- 无条件允许：`FileRead`、`Grep`、`Glob`
- 条件允许：只读 Bash
- 有范围限制地允许：`FileEdit` / `FileWrite`，但只能写 memoryDir 内文件

源码位置：

- 允许 `REPL`：`src/services/extractMemories/extractMemories.ts:173-181`
- 允许 `FileRead/Grep/Glob`：`src/services/extractMemories/extractMemories.ts:184-191`
- 只读 Bash 判断：`src/services/extractMemories/extractMemories.ts:193-204`
- 写文件路径限制：`src/services/extractMemories/extractMemories.ts:206-215`

### 9.3 明确拒绝的工具

结论：

- MCP、Agent、可写 Bash、超出 memoryDir 的写操作都会被拒绝

源码位置：

- 拒绝逻辑 `denyAutoMemTool(...)`：`src/services/extractMemories/extractMemories.ts:154-163`
- 默认拒绝返回：`src/services/extractMemories/extractMemories.ts:217-220`

## 10. 写入结果与统计

### 10.1 写入路径来自 fork 子代理实际产生的 tool_use block

结论：

- 系统不会猜测写了什么
- 而是从 fork 子代理返回消息里提取真实 `file_path`

源码位置：

- `extractWrittenPaths()` 定义：`src/services/extractMemories/extractMemories.ts:251-269`
- fork 结果提取写路径：`src/services/extractMemories/extractMemories.ts:437`

### 10.2 `MEMORY.md` 被视为机械索引更新，不算真正记忆文件

结论：

- 用户可感知的“记忆沉淀”统计按 topic 文件算
- `MEMORY.md` 更新会被过滤掉

源码位置：

- 过滤 `basename(p) !== ENTRYPOINT_NAME`：`src/services/extractMemories/extractMemories.ts:463-467`

### 10.3 成功后会记录 usage、写入数、team 写入数等指标

结论：

- 抽取结果带完整 usage 和产出统计

源码位置：

- usage 汇总和 hitPct：`src/services/extractMemories/extractMemories.ts:440-453`
- 成功事件 `tengu_extract_memories_extraction`：`src/services/extractMemories/extractMemories.ts:472-485`

### 10.4 如果真的写入了记忆，会给主线程追加 system message

结论：

- 用户在主会话里能看到“memory saved”类提示
- 但这属于附加系统消息，不影响主回答

源码位置：

- 判断 `memoryPaths.length > 0`：`src/services/extractMemories/extractMemories.ts:490`
- `createMemorySavedMessage(...)`：`src/services/extractMemories/extractMemories.ts:491`
- `appendSystemMessage?.(msg)`：`src/services/extractMemories/extractMemories.ts:495`

## 11. 错误处理与恢复

### 11.1 抽取失败不会打断主流程

结论：

- `extractMemories` 是 best-effort
- 失败只记日志和埋点，不抛到用户层

源码位置：

- catch 注释：`src/services/extractMemories/extractMemories.ts:497-500`
- 错误埋点：`src/services/extractMemories/extractMemories.ts:500-502`

### 11.2 失败时不会推进游标

结论：

- 下一次仍然可以重新考虑这批消息

源码位置：

- 成功后才推进游标：`src/services/extractMemories/extractMemories.ts:429-435`
- 注释明确写明“如果 agent errors，cursor stays put”：`src/services/extractMemories/extractMemories.ts:429-431`

## 12. 并发合并与尾随补跑

### 12.1 抽取中再次触发，不会并发启动第二个 fork

结论：

- 入口看到 `inProgress` 时，直接合并请求

源码位置：

- `if (inProgress)`：`src/services/extractMemories/extractMemories.ts:557`
- 写日志：`src/services/extractMemories/extractMemories.ts:558-560`
- 记录 `tengu_extract_memories_coalesced`：`src/services/extractMemories/extractMemories.ts:561`
- 覆盖写入 `pendingContext`：`src/services/extractMemories/extractMemories.ts:562`

### 12.2 当前执行结束后会检查并触发 trailing run

结论：

- `pendingContext` 不会丢
- 会在 finally 里补跑

源码位置：

- 取出 trailing context：`src/services/extractMemories/extractMemories.ts:510-511`
- 日志 `running trailing extraction`：`src/services/extractMemories/extractMemories.ts:513-515`
- 真正补跑调用：`src/services/extractMemories/extractMemories.ts:516-519`

### 12.3 trailing run 不受普通节流阈值约束

结论：

- 已经积压的待处理上下文不能被再次节流跳过

源码位置：

- 节流判断包在 `if (!isTrailingRun)` 中：`src/services/extractMemories/extractMemories.ts:377-385`

## 13. 非交互退出前的 drain 保障

### 13.1 headless/print 模式下，退出前会等待 in-flight extraction

结论：

- 进程退出前会调用 `drainPendingExtraction()`
- 尽量避免 fork 子代理被过早杀死

源码位置：

- `print.ts` 中 drain 调用：`src/cli/print.ts:962-969`
- 实际 `await drainPendingExtraction()`：`src/cli/print.ts:967-968`

### 13.2 `drainPendingExtraction()` 会等待所有 in-flight Promise 或超时

结论：

- 这不是无限等待
- 而是带软超时的 drain

源码位置：

- `drainer` 定义：`src/services/extractMemories/extractMemories.ts:579-586`
- `drainPendingExtraction()` 导出：`src/services/extractMemories/extractMemories.ts:611-614`

关键行号：

- 空集合直接返回：`src/services/extractMemories/extractMemories.ts:580`
- `Promise.all(inFlightExtractions)`：`src/services/extractMemories/extractMemories.ts:581-582`
- 超时 race：`src/services/extractMemories/extractMemories.ts:581-585`

## 14. 调试时最值得盯的行号

如果你后面要排查“为什么没抽取 / 为什么重复 / 为什么抽取延迟”，最值得先看的是下面这组行号：

- 触发入口：`src/query/stopHooks.ts:141-152`
- gate：`src/memdir/paths.ts:69-77`
- 初始化：`src/utils/backgroundHousekeeping.ts:31-36`
- 主线程直写跳过：`src/services/extractMemories/extractMemories.ts:345-360`
- 节流：`src/services/extractMemories/extractMemories.ts:374-386`
- fork 调用：`src/services/extractMemories/extractMemories.ts:415-427`
- 写入结果提取：`src/services/extractMemories/extractMemories.ts:437-467`
- 并发合并：`src/services/extractMemories/extractMemories.ts:554-563`
- trailing run：`src/services/extractMemories/extractMemories.ts:506-520`
- headless drain：`src/cli/print.ts:962-969`

## 15. 总结

如果把源码行号对照起来看，`extractMemories` 的实现可以压缩成下面这条主线：

1. 启动时初始化闭包状态机：`src/utils/backgroundHousekeeping.ts:31-36`，`src/services/extractMemories/extractMemories.ts:296-325`
2. 每轮结束由 stopHooks 触发：`src/query/stopHooks.ts:141-152`
3. 先过 gate、auto memory、remote、subagent 判断：`src/memdir/paths.ts:69-77`，`src/services/extractMemories/extractMemories.ts:531-552`
4. 再做互斥、节流、主线程直写跳过：`src/services/extractMemories/extractMemories.ts:345-386`，`src/services/extractMemories/extractMemories.ts:554-563`
5. 然后 fork 受限权限子代理去读写 memory：`src/services/extractMemories/extractMemories.ts:371-427`
6. 成功后推进游标、统计写入、回注 system message：`src/services/extractMemories/extractMemories.ts:429-496`
7. 若中途来了新请求，则 finally 里做 trailing run：`src/services/extractMemories/extractMemories.ts:503-520`
8. 非交互退出前再 drain 一次：`src/cli/print.ts:962-969`，`src/services/extractMemories/extractMemories.ts:579-614`
