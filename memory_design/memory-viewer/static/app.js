const state = {
  selectedSessionId: null,
  eventSource: null,
  selectedQueryTurnId: null,
  currentSnapshot: null,
};

// Maps flow node element -> detail payload, populated during renderFlowView
const flowNodeData = new WeakMap();

// Temporary registry for flow node payloads (cleared on each renderFlowView)
let _flowNodeRegistry = [];

function registerFlowNode(payload) {
  const idx = _flowNodeRegistry.length;
  _flowNodeRegistry.push(payload);
  return idx;
}

function term(text, tooltip) {
  return `<span class="term-hint" title="${escapeHtml(tooltip)}">${escapeHtml(text)}</span>`;
}

function formatDate(value) {
  if (!value) return "-";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString("zh-CN", { hour12: false });
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;");
}

function shorten(text, limit = 280) {
  if (!text) return "";
  const s = String(text).replace(/\s+/g, " ").trim();
  return s.length <= limit ? s : s.slice(0, limit - 3) + "...";
}

function setConnection(status, text) {
  const indicator = document.getElementById("connection-indicator");
  const label = document.getElementById("connection-text");
  indicator.className = `indicator indicator-${status}`;
  label.textContent = text;
}

function renderSessionOptions(snapshot) {
  const select = document.getElementById("session-select");
  const sessions = snapshot.sessions ?? [];
  select.innerHTML = "";
  sessions.forEach((session) => {
    const option = document.createElement("option");
    option.value = session.sessionId;
    option.textContent = `${session.sessionId} · ${formatDate(session.updatedAt)}`;
    option.selected = session.sessionId === snapshot.selectedSessionId;
    select.appendChild(option);
  });
}

function renderSessionList(snapshot) {
  const container = document.getElementById("session-list");
  const sessions = snapshot.sessions ?? [];
  if (!sessions.length) {
    container.innerHTML = '<div class="empty-state">当前项目还没有 session 记录。</div>';
    return;
  }
  container.innerHTML = sessions
    .map((session) => {
      const active = session.sessionId === snapshot.selectedSessionId ? "active" : "";
      return `
        <button class="session-item ${active}" data-session-id="${escapeHtml(session.sessionId)}">
          <span class="session-item-id">${escapeHtml(session.sessionId)}</span>
          <span class="session-item-time">${escapeHtml(formatDate(session.updatedAt))}</span>
          <span class="session-item-text">${escapeHtml(session.lastUserMessage || session.firstUserMessage || "无用户消息")}</span>
        </button>
      `;
    })
    .join("");
  container.querySelectorAll("[data-session-id]").forEach((button) => {
    button.addEventListener("click", () => {
      const sessionId = button.getAttribute("data-session-id");
      if (!sessionId || sessionId === state.selectedSessionId) return;
      loadSnapshot(sessionId, true);
    });
  });
}

function renderRecentMessages(messages) {
  const container = document.getElementById("recent-messages");
  if (!messages?.length) {
    container.innerHTML = '<div class="empty-state">当前 session 还没有可展示的消息。</div>';
    return;
  }
  container.innerHTML = messages
    .map(
      (message) => `
        <article class="message-card ${message.role}">
          <div class="message-meta">
            <span>${escapeHtml(message.role)}</span>
            <span>${escapeHtml(formatDate(message.timestamp))}</span>
          </div>
          <div class="message-content">${escapeHtml(message.content)}</div>
        </article>
      `,
    )
    .join("");
}

function renderRecallCandidates(candidates) {
  const container = document.getElementById("recall-candidates");
  if (!candidates?.length) {
    container.innerHTML = '<div class="empty-state">当前 session 还没有识别出明显的关联记忆读取。</div>';
    return;
  }
  container.innerHTML = candidates
    .map(
      (item) => `
        <article class="memory-item touched">
          <div class="memory-item-top">
            <div>
              <div class="memory-item-name">${escapeHtml(item.name)}</div>
              <div class="memory-item-path">${escapeHtml(item.relativePath || item.path)}</div>
            </div>
            <div class="memory-item-side">
              <span class="pill">${escapeHtml(item.memoryLabel || "Memory")}</span>
              ${item.memoryType ? `<span class="pill">${escapeHtml(item.memoryType)}</span>` : ""}
            </div>
          </div>
          <div class="memory-item-desc">${escapeHtml(item.description || "无描述")}</div>
          <div class="recall-meta">最近读取: ${escapeHtml(formatDate(item.lastAccessAt))} · 读取次数: ${escapeHtml(String(item.readCount || 0))}</div>
          <details>
            <summary>查看内容预览</summary>
            <pre class="code-block">${escapeHtml(item.contentPreview || "")}</pre>
          </details>
        </article>
      `,
    )
    .join("");
}

function findTurnMessages(turn, recentMessages) {
  if (!turn || !recentMessages?.length) return [];
  const prompt = turn.userPrompt || "";
  const matchedIndex = recentMessages.findIndex(
    (message) => message.role === "user" && message.content.includes(prompt.slice(0, 24)),
  );
  if (matchedIndex === -1) return recentMessages.slice(-2);
  return recentMessages.slice(matchedIndex, Math.min(recentMessages.length, matchedIndex + 3));
}

function renderTurnInsights(turn, recentMessages) {
  const container = document.getElementById("turn-insights");
  if (!turn) {
    container.innerHTML = '<div class="empty-state">选中一个 turn 后，这里会显示它的回答、命中线索和上下文。</div>';
    return;
  }
  const messages = findTurnMessages(turn, recentMessages);
  const assistantMessage = [...messages].reverse().find((message) => message.role === "assistant");
  container.innerHTML = `
    <article class="insight-card">
      <div class="subsection-title">${term("Prompt", "Prompt：用户当前这一轮输入给模型的请求")}</div>
      <div class="query-turn-prompt">${escapeHtml(turn.userPrompt || "无 prompt")}</div>
    </article>
    <article class="insight-card">
      <div class="subsection-title">${term("Assistant Response", "Assistant Response：本轮与该请求相邻的助手回复")}</div>
      <div class="message-content">${escapeHtml(assistantMessage?.content || "当前窗口内没有匹配到相邻 assistant 回复。")}</div>
    </article>
    <article class="insight-card">
      <div class="subsection-title">${term("Injection Status", "Injection Status：当前轮次是否存在精确的记忆注入记录")}</div>
      <div class="message-content">${escapeHtml(
        turn.hasExactRelevantMemoryRecord
          ? `这轮有 ${turn.exactRelevantMemories?.length || 0} 个精确 relevant memories 注入记录。这里的 relevant memories 指本轮被系统选中并塞进上下文窗口的相关记忆。`
          : "这轮没有精确注入记录，当前只能展示 transcript 里实际落盘的 attachment。",
      )}</div>
    </article>
    <article class="insight-card">
      <div class="subsection-title">${term("Nearby Transcript", "Nearby Transcript：当前 turn 附近的会话记录片段，用于辅助理解回答上下文")}</div>
      <div class="message-list compact">
        ${
          messages.length
            ? messages
                .map(
                  (message) => `
                    <article class="message-card ${message.role}">
                      <div class="message-meta">
                        <span>${escapeHtml(message.role)}</span>
                        <span>${escapeHtml(formatDate(message.timestamp))}</span>
                      </div>
                      <div class="message-content">${escapeHtml(message.content)}</div>
                    </article>
                  `,
                )
                .join("")
            : '<div class="empty-state">没有找到相邻 transcript 片段。</div>'
        }
      </div>
    </article>
  `;
}

function renderSelectedTurnFocus(turn) {
  const container = document.getElementById("query-turn-focus");
  if (!turn) {
    container.innerHTML = '<div class="empty-state">当前没有可聚焦的 turn。</div>';
    return;
  }
  container.innerHTML = `
    <div class="focus-top">
      <span class="pill">${turn.hasExactRelevantMemoryRecord ? term("exact injection", "存在精确注入记录：这一轮有实际落盘的 relevant_memories attachment") : term("turn only", "仅有轮次信息，没有扫描到精确注入记录")}</span>
      <span class="recall-meta">${escapeHtml(formatDate(turn.timestamp))}</span>
    </div>
    <div class="query-turn-prompt large">${escapeHtml(turn.userPrompt || "无 prompt")}</div>
    <div class="focus-stats">
      <div class="focus-stat">
        <span class="stat-label">${term("Relevant", "Relevant：本轮被判定与请求相关、并精确记录为已注入的记忆数量")}</span>
        <span class="stat-value">${escapeHtml(String(turn.exactRelevantMemories?.length || 0))}</span>
      </div>
      <div class="focus-stat">
        <span class="stat-label">${term("Nested", "Nested：本轮注入的嵌套记忆数量，通常来自记忆链展开或附带加载")}</span>
        <span class="stat-value">${escapeHtml(String(turn.nestedMemories?.length || 0))}</span>
      </div>
    </div>
  `;
}

function syncSelectedTurnPanels(session) {
  const selectedTurn = renderQueryTurns(session?.queryTurns ?? [], session?.selectedQueryTurnId ?? null);
  renderSelectedTurnFocus(selectedTurn);
  renderTurnInsights(selectedTurn, session?.recentMessages ?? []);
  const flowVisible = document.getElementById("view-flow")?.classList.contains("active");
  if (flowVisible) {
    renderFlowView(state.currentSnapshot, selectedTurn);
  }
}

function renderQueryTurns(turns, preferredTurnId) {
  const list = document.getElementById("query-turn-list");
  if (!turns?.length) {
    list.innerHTML = '<div class="empty-state">当前 session 还没有可识别的用户 query turn。</div>';
    state.selectedQueryTurnId = null;
    return null;
  }

  const selectedTurnId =
    turns.some((turn) => turn.turnId === state.selectedQueryTurnId)
      ? state.selectedQueryTurnId
      : preferredTurnId || turns[turns.length - 1]?.turnId;
  state.selectedQueryTurnId = selectedTurnId;

  list.innerHTML = turns
    .slice()
    .reverse()
    .map((turn, index) => {
      const active = turn.turnId === selectedTurnId ? "active" : "";
      const exact = turn.hasExactRelevantMemoryRecord ? "exact" : "missing";
      const count = turn.exactRelevantMemories?.length ?? 0;
      return `
        <button class="query-turn-item ${active}" data-turn-id="${escapeHtml(turn.turnId)}">
          <div class="query-turn-top">
            <span class="query-turn-index">${term(`Turn ${turns.length - index}`, `Turn：第 ${turns.length - index} 轮请求`)}</span>
            <span class="pill ${exact === "exact" ? "" : "accent"}">${exact === "exact" ? term(`${count} injected`, "injected：这一轮存在精确记录的记忆注入") : term("no exact record", "没有扫描到精确 relevant memory 注入记录")}</span>
          </div>
          <div class="query-turn-time">${escapeHtml(formatDate(turn.timestamp))}</div>
          <div class="query-turn-prompt">${escapeHtml(turn.userPrompt || "无 prompt")}</div>
        </button>
      `;
    })
    .join("");

  list.querySelectorAll("[data-turn-id]").forEach((button) => {
    button.addEventListener("click", () => {
      state.selectedQueryTurnId = button.getAttribute("data-turn-id");
      syncSelectedTurnPanels(state.currentSnapshot?.session ?? null);
    });
  });

  const selectedTurn = turns.find((turn) => turn.turnId === selectedTurnId) || turns[turns.length - 1];
  const exactMemories = selectedTurn?.exactRelevantMemories ?? [];
  const nestedMemories = selectedTurn?.nestedMemories ?? [];
  if (!selectedTurn) return null;

  const exactHtml = exactMemories.length
    ? exactMemories
        .map(
          (memory) => `
            <article class="memory-item touched">
              <div class="memory-item-top">
                <div>
                  <div class="memory-item-name">${escapeHtml(memory.name)}</div>
                  <div class="memory-item-path">${escapeHtml(memory.relativePath || memory.path)}</div>
                </div>
                <div class="memory-item-side">
                  <span class="pill">${term("exact injected", "精确注入：这条记忆明确出现在 transcript 记录的 relevant_memories attachment 中")}</span>
                  ${memory.memoryType ? `<span class="pill">${escapeHtml(memory.memoryType)}</span>` : ""}
                </div>
              </div>
              <div class="memory-item-desc">${escapeHtml(memory.description || "无描述")}</div>
              ${memory.header ? `<div class="recall-meta">${escapeHtml(memory.header)}</div>` : ""}
              <details>
                <summary>查看注入内容</summary>
                <pre class="code-block">${escapeHtml(memory.contentPreview || "")}</pre>
              </details>
            </article>
          `,
        )
        .join("")
    : '<div class="empty-state">这轮 query 没有扫描到精确的 `relevant_memories` attachment。可能是该能力没触发，也可能当前 transcript 没有保留这类 attachment。</div>';

  const nestedHtml = nestedMemories.length
    ? `
      <div class="subsection">
        <div class="subsection-title">${term("Nested Memory", "Nested Memory：由嵌套引用、联动展开或附带加载进入上下文的记忆")}</div>
        <div class="memory-item-list">
          ${nestedMemories
            .map(
              (memory) => `
                <article class="memory-item">
                  <div class="memory-item-name">${escapeHtml(memory.name)}</div>
                  <div class="memory-item-path">${escapeHtml(memory.relativePath || memory.path)}</div>
                  <details>
                    <summary>查看内容预览</summary>
                    <pre class="code-block">${escapeHtml(memory.contentPreview || "")}</pre>
                  </details>
                </article>
              `,
            )
            .join("")}
        </div>
      </div>
    `
    : "";

  document.getElementById("query-turn-detail").innerHTML = `
    <div class="query-turn-summary">
      <div class="subsection-title">${term("Selected Turn", "Selected Turn：当前选中并展开分析的请求轮次")}</div>
      <div class="query-turn-prompt large">${escapeHtml(selectedTurn.userPrompt || "无 prompt")}</div>
      <div class="recall-meta">时间: ${escapeHtml(formatDate(selectedTurn.timestamp))}</div>
    </div>
    <div class="subsection">
      <div class="subsection-title">${term("Exact Relevant Memories", "Exact Relevant Memories：本轮精确记录为进入上下文窗口的相关记忆")}</div>
      <div class="memory-item-list">${exactHtml}</div>
    </div>
    ${nestedHtml}
  `;
  return selectedTurn;
}

function renderActivity(activity) {
  const container = document.getElementById("memory-activity");
  if (!activity?.length) {
    container.innerHTML = '<div class="empty-state">这个 session 里暂时没有识别到记忆读写轨迹。</div>';
    return;
  }
  container.innerHTML = activity
    .map(
      (item) => `
        <article class="activity-card">
          <div class="activity-top">
            <span class="pill">${escapeHtml(item.memoryLabel)}</span>
            <span class="activity-action">${escapeHtml(item.action)}</span>
            <span class="activity-time">${escapeHtml(formatDate(item.timestamp))}</span>
          </div>
          <div class="activity-path">${escapeHtml(item.relativePath)}</div>
          <div class="activity-sub">${escapeHtml(item.toolName || item.source || "-")}</div>
        </article>
      `,
    )
    .join("");
}

function renderIndexes(indexes) {
  const container = document.getElementById("memory-indexes");
  if (!indexes?.length) {
    container.innerHTML = '<div class="empty-state">当前没有发现 MEMORY.md 或类似索引文件。</div>';
    return;
  }
  container.innerHTML = indexes
    .map(
      (item) => `
        <article class="index-card">
          <div class="panel-header compact">
            <h4>${escapeHtml(item.groupLabel)}</h4>
            <span class="panel-meta">${escapeHtml(formatDate(item.updatedAt))}</span>
          </div>
          <div class="index-path">${escapeHtml(item.path)}</div>
          <pre class="code-block">${escapeHtml(item.content || "")}</pre>
        </article>
      `,
    )
    .join("");
}

function renderMemoryGroups(groups) {
  const container = document.getElementById("memory-groups");
  container.innerHTML = "";
  const visibleGroups = (groups ?? []).filter((group) => group.items?.length);
  if (!visibleGroups.length) {
    container.innerHTML = '<div class="empty-state">当前没有扫描到记忆文件。</div>';
    return;
  }
  visibleGroups.forEach((group) => {
    const section = document.createElement("section");
    section.className = "memory-group";
    section.innerHTML = `
      <div class="panel-header compact">
        <h4>${escapeHtml(group.groupLabel)}</h4>
        <span class="panel-meta">${escapeHtml(group.root)}</span>
      </div>
      <div class="memory-item-list">
        ${group.items
          .map(
            (item) => `
              <article class="memory-item ${item.touchedInSession ? "touched" : ""}">
                <div class="memory-item-top">
                  <div>
                    <div class="memory-item-name">${escapeHtml(item.name)}</div>
                    <div class="memory-item-path">${escapeHtml(item.relativePath)}</div>
                  </div>
                  <div class="memory-item-side">
                    ${item.memoryType ? `<span class="pill">${escapeHtml(item.memoryType)}</span>` : ""}
                    ${item.touchedInSession ? '<span class="pill accent">session touched</span>' : ""}
                  </div>
                </div>
                <div class="memory-item-desc">${escapeHtml(item.description || "无描述")}</div>
                <details>
                  <summary>查看内容</summary>
                  <pre class="code-block">${escapeHtml(item.content || "")}</pre>
                </details>
              </article>
            `,
          )
          .join("")}
      </div>
    `;
    container.appendChild(section);
  });
}

function renderTimeline(items) {
  const container = document.getElementById("timeline");
  if (!items?.length) {
    container.innerHTML = '<div class="empty-state">当前还没有足够的数据拼出流转时间线。</div>';
    return;
  }
  container.innerHTML = items
    .map(
      (item) => `
        <article class="timeline-item timeline-${escapeHtml(item.kind || "event")}">
          <div class="timeline-dot"></div>
          <div class="timeline-body">
            <div class="timeline-top">
              <span class="timeline-title">${escapeHtml(item.title || "-")}</span>
              <span class="timeline-time">${escapeHtml(formatDate(item.timestamp))}</span>
            </div>
            <div class="timeline-subtitle">${escapeHtml(item.subtitle || "-")}</div>
            <div class="timeline-detail">${escapeHtml(item.detail || "")}</div>
          </div>
        </article>
      `,
    )
    .join("");
}

function renderSnapshot(snapshot) {
  state.currentSnapshot = snapshot;
  state.selectedSessionId = snapshot.selectedSessionId;
  renderSessionOptions(snapshot);
  renderSessionList(snapshot);

  document.getElementById("project-root").textContent = snapshot.projectRoot ?? "-";
  document.getElementById("project-storage").textContent = snapshot.projectStorageDir ?? "-";
  document.getElementById("generated-at").textContent = formatDate(snapshot.generatedAt);

  // Keep project input in sync with current root
  const inputEl = document.getElementById("project-root-input");
  if (inputEl && snapshot.projectRoot) inputEl.value = snapshot.projectRoot;

  const session = snapshot.session;
  document.getElementById("hero-session").textContent = session?.sessionId ?? "暂无 Session";
  document.getElementById("hero-summary").textContent = session
    ? `入口: ${session.entrypoint || "-"} · 开始于 ${formatDate(session.startedAt)} · 更新于 ${formatDate(session.updatedAt)}`
    : "当前项目还没有可展示的 session。";
  document.getElementById("last-prompt").textContent = session?.lastPrompt || "-";
  document.getElementById("event-count").textContent = String(session?.eventCount ?? 0);
  document.getElementById("activity-count").textContent = String(session?.memoryActivity?.length ?? 0);

  const sessionSummary = snapshot.memory?.sessionSummary;
  document.getElementById("session-memory-updated").textContent = sessionSummary
    ? formatDate(sessionSummary.updatedAt)
    : "未生成";
  document.getElementById("session-memory-content").textContent = sessionSummary?.content || "当前 session 没有 session-memory/summary.md";

  renderRecallCandidates(snapshot.memory?.recallCandidates ?? []);
  syncSelectedTurnPanels(session ?? null);
  renderTimeline(session?.timeline ?? []);
  renderRecentMessages(session?.recentMessages ?? []);
  renderActivity(session?.memoryActivity ?? []);
  renderIndexes(snapshot.memory?.indexes ?? []);
  renderMemoryGroups(snapshot.memory?.groups ?? []);
}

function getSelectedTurn(session) {
  const turns = session?.queryTurns ?? [];
  return turns.find((turn) => turn.turnId === state.selectedQueryTurnId) || turns[turns.length - 1] || null;
}

function buildFlowMemoryNode(item, variant, stageKey, detailType) {
  const idx = registerFlowNode({ item, detailType });
  return `
    <button
      class="flow-memory-node ${escapeHtml(variant)}"
      data-stage="${escapeHtml(stageKey)}"
      data-flow-idx="${idx}"
    >
      <div class="flow-memory-name">${escapeHtml(item.name || item.relativePath || item.path || "Unknown")}</div>
      <div class="flow-memory-type">${escapeHtml(item.memoryLabel || item.memoryType || item.toolName || variant)}</div>
    </button>
  `;
}

function renderFlowView(snapshot, preferredTurn = null) {
  const flowDiagram = document.getElementById("flow-diagram");
  const flowIndicator = document.getElementById("flow-turn-indicator");
  if (!flowDiagram || !snapshot?.session) return;

  const turn = preferredTurn || getSelectedTurn(snapshot.session);
  if (!turn) {
    flowIndicator.textContent = "当前 session 没有可用 turn";
    flowDiagram.innerHTML = `
      <div class="flow-empty">
        <p>当前 session 还没有可识别的 Query Turn</p>
        <p class="muted">流程图需要至少一轮真实用户输入</p>
      </div>
    `;
    hideFlowMemoryDetail();
    return;
  }

  flowIndicator.textContent = `${formatDate(turn.timestamp)} · ${shorten(turn.userPrompt || "无 prompt", 64)}`;

  // Reset node registry for this render pass
  _flowNodeRegistry = [];

  const showInjected = document.getElementById("filter-injected")?.checked ?? true;
  const showWrites = document.getElementById("filter-writes")?.checked ?? true;
  const showSession = document.getElementById("filter-session")?.checked ?? true;

  const sessionSummary = snapshot.memory?.sessionSummary;
  const stages = [
    {
      key: "prompt",
      title: "User Prompt",
      icon: "01",
      meta: turn.userPrompt ? shorten(turn.userPrompt, 72) : "无 prompt",
      status: "done",
      accessories: [],
    },
    {
      key: "memory-prep",
      title: "Memory Prep",
      icon: "02",
      meta: `${turn.exactRelevantMemories?.length || 0} injected · ${turn.nestedMemories?.length || 0} nested`,
      status: turn.hasExactRelevantMemoryRecord ? "done" : "inferred",
      accessories: [
        ...(showInjected ? (turn.exactRelevantMemories || []).map((item) => buildFlowMemoryNode(item, "injected", "memory-prep", "memory")) : []),
        ...(showInjected ? (turn.nestedMemories || []).map((item) => buildFlowMemoryNode(item, "nested", "memory-prep", "memory")) : []),
      ],
    },
    {
      key: "reasoning",
      title: "Model Reasoning",
      icon: "03",
      meta: turn.toolCount
        ? `触发 ${turn.toolCount} 个工具调用`
        : "直接生成回复，未调用工具",
      status: "done",
      accessories: [],
    },
    {
      key: "tools",
      title: "Tool Execution",
      icon: "04",
      meta: turn.toolCount
        ? `${turn.toolCount} calls · ${turn.memoryReadCount || 0} mem reads · ${turn.memoryWriteCount || 0} mem writes`
        : "本轮无工具调用",
      status: turn.toolCount ? "active" : "missing",
      // Only show memory-related nodes here; plain tool calls are summarised in meta
      accessories: [
        ...(turn.memoryReads || []).map((item) => buildFlowMemoryNode(item, "read", "tools", "memory")),
        ...(showWrites ? (turn.memoryWrites || []).map((item) => buildFlowMemoryNode(item, "written", "tools", "memory")) : []),
      ],
    },
    {
      key: "response",
      title: "Assistant Response",
      icon: "05",
      meta: turn.assistantResponse ? shorten(turn.assistantResponse, 72) : "未捕获到文本输出",
      status: turn.assistantResponse ? "done" : "missing",
      accessories: turn.assistantResponse
        ? [
            (() => {
              const idx = registerFlowNode({
                item: { title: "Assistant Response", content: turn.assistantResponse },
                detailType: "response",
              });
              return `
                <button class="flow-memory-node reasoning" data-stage="response" data-flow-idx="${idx}">
                  <div class="flow-memory-name">回复内容</div>
                  <div class="flow-memory-type">${escapeHtml(shorten(turn.assistantResponse, 60))}</div>
                </button>
              `;
            })(),
          ]
        : [],
    },
    {
      key: "post",
      title: "Post Process",
      icon: "06",
      meta: sessionSummary
        ? `session-memory updated ${formatDate(sessionSummary.updatedAt)}`
        : "未检测到 session-memory 更新",
      status: showSession && sessionSummary ? "inferred" : "missing",
      accessories:
        showSession && sessionSummary
          ? [
              (() => {
                const idx = registerFlowNode({ item: sessionSummary, detailType: "session-summary" });
                return `
                  <button class="flow-memory-node session" data-stage="post" data-flow-idx="${idx}">
                    <div class="flow-memory-name">session-memory/summary.md</div>
                    <div class="flow-memory-type">${escapeHtml(shorten(sessionSummary.content || "", 60))}</div>
                  </button>
                `;
              })(),
            ]
          : [],
    },
  ];

  flowDiagram.innerHTML = `
    <svg class="flow-connectors" id="flow-svg" aria-hidden="true"></svg>
    <div class="flow-stage-row">
      ${stages
        .map(
          (stage) => `
            <section class="flow-stage">
              <div class="flow-stage-node ${escapeHtml(stage.status)}" data-stage="${escapeHtml(stage.key)}">
                <div class="flow-stage-icon">${escapeHtml(stage.icon)}</div>
                <div class="flow-stage-title">${escapeHtml(stage.title)}</div>
                <div class="flow-stage-meta">${escapeHtml(stage.meta)}</div>
              </div>
              <div class="flow-stage-memories">
                ${
                  stage.accessories.length
                    ? stage.accessories.join("")
                    : '<div class="flow-stage-placeholder">无附加事件</div>'
                }
              </div>
            </section>
          `,
        )
        .join("")}
    </div>
  `;

  initFlowView();
  // Draw SVG connectors after DOM is painted
  requestAnimationFrame(() => drawFlowConnectors(flowDiagram, stages));
}

function drawFlowConnectors(container, stages) {
  const svg = container.querySelector("#flow-svg");
  if (!svg) return;

  const containerRect = container.getBoundingClientRect();
  const scrollLeft = container.scrollLeft;
  const scrollTop = container.scrollTop;

  // Collect stage node rects relative to the flow-diagram container
  const nodeRects = [];
  stages.forEach((stage) => {
    const el = container.querySelector(`.flow-stage-node[data-stage="${stage.key}"]`);
    if (!el) return;
    const r = el.getBoundingClientRect();
    nodeRects.push({
      key: stage.key,
      status: stage.status,
      left: r.left - containerRect.left + scrollLeft,
      top: r.top - containerRect.top + scrollTop,
      right: r.right - containerRect.left + scrollLeft,
      bottom: r.bottom - containerRect.top + scrollTop,
      cx: r.left - containerRect.left + scrollLeft + r.width / 2,
      cy: r.top - containerRect.top + scrollTop + r.height / 2,
      width: r.width,
      height: r.height,
    });
  });

  if (nodeRects.length < 2) return;

  // Resize SVG to cover the full scrollable area of the container
  const row = container.querySelector(".flow-stage-row");
  const rowRect = row ? row.getBoundingClientRect() : containerRect;
  const svgW = rowRect.width + 80;
  const svgH = rowRect.height + 40;
  svg.setAttribute("width", svgW);
  svg.setAttribute("height", svgH);
  svg.setAttribute("viewBox", `0 0 ${svgW} ${svgH}`);

  const paths = [];

  // Main execution chain: horizontal arrows between consecutive stage nodes
  for (let i = 0; i < nodeRects.length - 1; i++) {
    const from = nodeRects[i];
    const to = nodeRects[i + 1];
    const x1 = from.right;
    const y1 = from.cy;
    const x2 = to.left;
    const y2 = to.cy;
    const mx = (x1 + x2) / 2;
    const isDashed = from.status === "inferred" || from.status === "missing";
    paths.push(`
      <path
        d="M ${x1} ${y1} C ${mx} ${y1}, ${mx} ${y2}, ${x2} ${y2}"
        class="flow-edge execution${isDashed ? " inferred" : ""}"
        marker-end="url(#arrow-exec)"
      />
    `);
  }

  // Memory accessory connectors: vertical line from stage node bottom to each memory node
  stages.forEach((stage) => {
    const stageRect = nodeRects.find((r) => r.key === stage.key);
    if (!stageRect || !stage.accessories.length) return;

    const memNodes = container.querySelectorAll(`.flow-memory-node[data-stage="${stage.key}"]`);
    memNodes.forEach((memEl) => {
      const mr = memEl.getBoundingClientRect();
      const mx = mr.left - containerRect.left + scrollLeft + mr.width / 2;
      const myTop = mr.top - containerRect.top + scrollTop;

      // Determine edge class from node variant
      let edgeClass = "inject";
      if (memEl.classList.contains("written")) edgeClass = "write";
      else if (memEl.classList.contains("read")) edgeClass = "read";
      else if (memEl.classList.contains("session")) edgeClass = "write";
      else if (memEl.classList.contains("nested")) edgeClass = "inject";
      else if (memEl.classList.contains("reasoning")) edgeClass = "execution";

      const x1 = stageRect.cx;
      const y1 = stageRect.bottom;
      const x2 = mx;
      const y2 = myTop;
      const cy1 = y1 + (y2 - y1) * 0.4;
      const cy2 = y1 + (y2 - y1) * 0.6;

      paths.push(`
        <path
          d="M ${x1} ${y1} C ${x1} ${cy1}, ${x2} ${cy2}, ${x2} ${y2}"
          class="flow-edge ${edgeClass}"
          marker-end="url(#arrow-${edgeClass})"
        />
      `);
    });
  });

  svg.innerHTML = `
    <defs>
      <marker id="arrow-exec" markerWidth="8" markerHeight="8" refX="6" refY="3" orient="auto">
        <path d="M0,0 L0,6 L8,3 z" fill="var(--accent)" />
      </marker>
      <marker id="arrow-inject" markerWidth="8" markerHeight="8" refX="6" refY="3" orient="auto">
        <path d="M0,0 L0,6 L8,3 z" fill="#22a06b" />
      </marker>
      <marker id="arrow-read" markerWidth="8" markerHeight="8" refX="6" refY="3" orient="auto">
        <path d="M0,0 L0,6 L8,3 z" fill="#339af0" />
      </marker>
      <marker id="arrow-write" markerWidth="8" markerHeight="8" refX="6" refY="3" orient="auto">
        <path d="M0,0 L0,6 L8,3 z" fill="#e8590c" />
      </marker>
    </defs>
    ${paths.join("")}
  `;
}

async function loadSnapshot(sessionId, reconnectStream = false) {
  const params = sessionId ? `?session_id=${encodeURIComponent(sessionId)}` : "";
  const response = await fetch(`/api/snapshot${params}`, { cache: "no-store" });
  if (!response.ok) {
    throw new Error(`加载快照失败: ${response.status}`);
  }
  const snapshot = await response.json();
  renderSnapshot(snapshot);
  if (reconnectStream) {
    connectStream(snapshot.selectedSessionId);
  }
}

function connectStream(sessionId) {
  if (state.eventSource) {
    state.eventSource.close();
  }
  const params = sessionId ? `?session_id=${encodeURIComponent(sessionId)}` : "";
  const source = new EventSource(`/api/stream${params}`);
  state.eventSource = source;
  setConnection("pending", "正在建立实时连接");

  source.addEventListener("open", () => {
    setConnection("live", "实时同步中");
  });

  source.addEventListener("snapshot", (event) => {
    const snapshot = JSON.parse(event.data);
    renderSnapshot(snapshot);
    setConnection("live", "实时同步中");
  });

  source.addEventListener("error", () => {
    setConnection("error", "连接中断，3 秒后重连");
    source.close();
    setTimeout(() => connectStream(state.selectedSessionId), 3000);
  });
}

document.getElementById("session-select").addEventListener("change", (event) => {
  const sessionId = event.target.value;
  loadSnapshot(sessionId, true).catch((error) => {
    console.error(error);
    setConnection("error", error.message);
  });
});

// ===== Flow View =====
function initFlowView() {
  document.querySelectorAll(".flow-memory-node").forEach((node) => {
    node.addEventListener("click", () => {
      const idxStr = node.dataset.flowIdx;
      if (idxStr == null) return;
      const entry = _flowNodeRegistry[Number(idxStr)];
      if (!entry) return;
      showFlowMemoryDetail(entry.item, entry.detailType);
    });
  });
}

function showFlowMemoryDetail(detail, detailType) {
  const panel = document.getElementById("flow-memory-detail");
  if (!panel) return;

  let title = "Flow Detail";
  let meta = "";
  let description = "";
  let preview = "";

  if (detailType === "tool") {
    title = detail.toolName || "Tool";
    meta = detail.timestamp ? formatDate(detail.timestamp) : "";
    description = detail.summary || "无参数摘要";
  } else if (detailType === "session-summary") {
    title = "session-memory/summary.md";
    meta = detail.updatedAt ? formatDate(detail.updatedAt) : "";
    description = detail.path || "";
    preview = detail.content || "";
  } else if (detailType === "response") {
    title = detail.title || "Assistant Response";
    preview = detail.content || "";
  } else {
    title = detail.name || detail.relativePath || "Memory";
    meta = detail.memoryLabel || detail.memoryType || "";
    description = detail.description || detail.path || "";
    preview = detail.contentPreview || "";
  }

  panel.innerHTML = `
    <div class="flow-memory-panel-header">
      <h4>${escapeHtml(title)}</h4>
      <button id="flow-detail-close" class="flow-memory-panel-close">×</button>
    </div>
    <div class="flow-memory-panel-content">
      ${meta ? `<div class="pill">${escapeHtml(meta)}</div>` : ""}
      ${description ? `<div class="memory-item-desc">${escapeHtml(description)}</div>` : ""}
      ${preview ? `<pre class="code-block">${escapeHtml(preview)}</pre>` : ""}
    </div>
  `;
  panel.classList.add("active");
  document.getElementById("flow-detail-close")?.addEventListener("click", () => hideFlowMemoryDetail());
}

function hideFlowMemoryDetail() {
  const panel = document.getElementById("flow-memory-detail");
  if (!panel) return;
  panel.classList.remove("active");
  panel.innerHTML = "";
}

// ===== View Tabs =====
function initViewTabs() {
  const tabs = document.querySelectorAll(".view-tab");
  const contents = document.querySelectorAll(".view-content");

  tabs.forEach((tab) => {
    tab.addEventListener("click", () => {
      const view = tab.dataset.view;
      tabs.forEach((item) => item.classList.remove("active"));
      tab.classList.add("active");
      contents.forEach((item) => item.classList.remove("active"));
      document.getElementById(`view-${view}`)?.classList.add("active");
      if (view === "flow") {
        renderFlowView(state.currentSnapshot, getSelectedTurn(state.currentSnapshot?.session));
      }
    });
  });
}

["filter-injected", "filter-writes", "filter-session"].forEach((id) => {
  document.getElementById(id)?.addEventListener("change", () => {
    renderFlowView(state.currentSnapshot, getSelectedTurn(state.currentSnapshot?.session));
  });
});

loadSnapshot(null, false)
  .then(() => {
    connectStream(state.selectedSessionId);
    initViewTabs();
    initProjectSwitcher();
  })
  .catch((error) => {
    console.error(error);
    setConnection("error", error.message);
  });

// ===== Project Switcher =====
async function initProjectSwitcher() {
  const select = document.getElementById("project-select");
  const input = document.getElementById("project-root-input");
  const btn = document.getElementById("project-apply-btn");
  const msg = document.getElementById("project-switch-msg");

  // Pre-fill input with current project root
  if (state.currentSnapshot?.projectRoot) {
    input.value = state.currentSnapshot.projectRoot;
  }

  // Load known projects list
  try {
    const res = await fetch("/api/projects", { cache: "no-store" });
    const data = await res.json();
    const projects = data.projects ?? [];
    select.innerHTML = '<option value="">— 从已知项目选择 —</option>';
    projects.forEach((p) => {
      const opt = document.createElement("option");
      opt.value = p.projectRoot || p.sanitizedName;
      const label = p.projectRoot || p.sanitizedName;
      opt.textContent = `${label}  (${p.sessionCount} sessions · ${formatDate(p.updatedAt)})`;
      if (!p.projectRoot) opt.disabled = true;
      select.appendChild(opt);
    });
  } catch {
    select.innerHTML = '<option value="">无法加载项目列表</option>';
  }

  // Selecting from dropdown fills the input
  select.addEventListener("change", () => {
    if (!select.value) return;
    input.value = select.value;
    msg.textContent = "";
    msg.className = "project-switch-msg";
  });

  async function applySwitch() {
    const raw = input.value.trim();
    if (!raw) return;
    btn.disabled = true;
    msg.textContent = "切换中…";
    msg.className = "project-switch-msg info";
    try {
      const res = await fetch("/api/set-project", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ projectRoot: raw }),
      });
      if (!res.ok) {
        const text = await res.text();
        throw new Error(text || `HTTP ${res.status}`);
      }
      const data = await res.json();
      msg.textContent = `已切换到 ${data.projectRoot}`;
      msg.className = "project-switch-msg success";
      // Reset session selection and reload
      state.selectedQueryTurnId = null;
      await loadSnapshot(null, true);
    } catch (err) {
      msg.textContent = `切换失败: ${err.message}`;
      msg.className = "project-switch-msg error";
    } finally {
      btn.disabled = false;
    }
  }

  btn.addEventListener("click", applySwitch);
  input.addEventListener("keydown", (e) => {
    if (e.key === "Enter") applySwitch();
  });
}
