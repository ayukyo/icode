(function () {
  "use strict";
  var translations = {
    "zh-CN": {
      productSubtitle: "研发工单工作台", language: "语言", newTicket: "新建工单", workspace: "工作台", allTickets: "全部工单", needsAttention: "需要我处理", inProgress: "处理中", completed: "已完成",
      scopeTitle: "当前范围", scopeBody: "单工程研发任务；不会执行通用办公自动化。", currentProject: "当前工程", search: "搜索工单", searchPlaceholder: "搜索编号、标题或内容", ticketList: "工单列表",
      emptyTitle: "还没有工单", emptyBody: "创建第一张研发工单，ICODE 会记录状态和处理证据。", welcomeTitle: "选择一张工单", welcomeBody: "在这里查看当前状态、执行方式、目标和下一步。",
      executionMode: "执行方式", priority: "紧急程度", updatedAt: "最近更新", problemDescription: "问题或需求", expectedResult: "希望得到的结果", technicalDetails: "技术详情", rawStatus: "控制面状态", completedSteps: "已完成步骤", communicationLanguage: "工单沟通语言",
      connecting: "正在连接…", connected: "已连接", unavailable: "工作台暂不可用", softwareRequest: "软件研发需求", project: "业务系统", title: "问题或需求标题",
      priorityLow: "低", priorityNormal: "普通", priorityHigh: "高", priorityUrgent: "紧急", interactiveMode: "会话模式", autonomousMode: "自动模式", autonomousPending: "自动模式（等待激活）",
      interactiveHelp: "适合需要逐步沟通和确认的需求。", autonomousHelp: "建单只记录自动处理意图，不会自动启动；建单后请在工单详情中确认启动。", cancel: "取消", submitTicket: "提交工单", submitting: "正在提交…", created: "工单已创建", noSteps: "暂无", unknown: "未知",
      autonomyEyebrow: "自动处理", autonomyTitle: "自主运行", pauseSemantics: "仅在当前契约步骤完成后暂停；正在进行的模型调用不会被中途截断。", runtimeCapability: "运行能力", configuredLimits: "配置限制", lastStep: "最近步骤", capabilityEnabled: "已启用（仅服务端配置）", capabilityDisabled: "未启用；需由管理员启动工作台能力", limitsFormat: "最多 {turns} 回合 · token 预算 {tokens} · 隔离 {isolation}", isolationEnforced: "后端已配置，待自检", isolationApplicationOnly: "仅应用层限制", isolationNotConfigured: "未配置", isolationPolicyUnavailable: "策略级隔离尚未就绪，自动处理会阻断", startAutonomy: "启动自动处理", pauseAutonomy: "在步骤边界暂停", resumeAutonomy: "继续自动处理", cancelAutonomy: "取消自动处理", takeoverAutonomy: "接管为会话模式", intentAccepted: "操作已接受", pending: "等待启动", starting: "正在启动", running: "正在自动处理", pause_requested: "已请求暂停", paused: "已暂停", cancel_requested: "已请求取消", cancelled: "已取消", succeeded: "自动处理已完成", failed: "自动处理失败", blocked: "已被门禁阻断", interrupted: "已中断",
      protectionTitle: "运行保护", protectionScope: "可访问范围", protectionNetwork: "网络", protectionLastBlock: "最近阻止的动作", protectionCheckPending: "尚未完成保护检查", protectionUnavailable: "保护不可用", protectionNotEnabled: "自动处理尚未启用", protectionUnverified: "尚未验证", protectionNoBlock: "暂无", protectionIsolationBlock: "保护未就绪，已阻止自动运行",
      submitted: "已提交", understanding: "正在理解需求", reviewing_plan: "正在检查方案", finalizing_plan: "正在整理方案", ready_to_implement: "方案准备完成", working: "正在处理", checking: "正在全面检查", preparing_delivery: "正在整理交付结果"
    },
    "en-US": {
      productSubtitle: "Software Delivery Workbench", language: "Language", newTicket: "New ticket", workspace: "Workspace", allTickets: "All tickets", needsAttention: "Needs my attention", inProgress: "In progress", completed: "Completed",
      scopeTitle: "Current scope", scopeBody: "Single-project software work; this is not a general office automation tool.", currentProject: "Current project", search: "Search tickets", searchPlaceholder: "Search ID, title, or content", ticketList: "Ticket list",
      emptyTitle: "No tickets yet", emptyBody: "Create the first software ticket; ICODE will track state and evidence.", welcomeTitle: "Select a ticket", welcomeBody: "Review its status, execution mode, goal, and next action here.",
      executionMode: "Execution mode", priority: "Priority", updatedAt: "Last updated", problemDescription: "Problem or request", expectedResult: "Expected result", technicalDetails: "Technical details", rawStatus: "Control-plane status", completedSteps: "Completed steps", communicationLanguage: "Ticket language",
      connecting: "Connecting…", connected: "Connected", unavailable: "Workbench unavailable", softwareRequest: "Software request", project: "Business system", title: "Request title",
      priorityLow: "Low", priorityNormal: "Normal", priorityHigh: "High", priorityUrgent: "Urgent", interactiveMode: "Interactive", autonomousMode: "Autonomous", autonomousPending: "Autonomous (pending activation)",
      interactiveHelp: "Best when the request needs ongoing clarification and confirmation.", autonomousHelp: "Creating the ticket records autonomous intent but does not start it. Confirm Start in the ticket detail afterward.", cancel: "Cancel", submitTicket: "Submit ticket", submitting: "Submitting…", created: "Ticket created", noSteps: "None", unknown: "Unknown",
      autonomyEyebrow: "Automatic work", autonomyTitle: "Autonomous run", pauseSemantics: "Pauses only after the current contract step finishes; an in-flight model call is not interrupted.", runtimeCapability: "Runtime capability", configuredLimits: "Configured limits", lastStep: "Last step", capabilityEnabled: "Enabled (server-side configuration only)", capabilityDisabled: "Disabled; an administrator must enable it when starting the workbench", limitsFormat: "Up to {turns} turns · token budget {tokens} · isolation {isolation}", isolationEnforced: "backend configured, check pending", isolationApplicationOnly: "application-layer only", isolationNotConfigured: "not configured", isolationPolicyUnavailable: "policy-level isolation unavailable; autonomous work will be blocked", startAutonomy: "Start autonomous work", pauseAutonomy: "Pause at step boundary", resumeAutonomy: "Resume autonomous work", cancelAutonomy: "Cancel autonomous work", takeoverAutonomy: "Take over interactively", intentAccepted: "Action accepted", pending: "Waiting to start", starting: "Starting", running: "Running autonomously", pause_requested: "Pause requested", paused: "Paused", cancel_requested: "Cancellation requested", cancelled: "Cancelled", succeeded: "Autonomous work completed", failed: "Autonomous work failed", blocked: "Blocked by a gate", interrupted: "Interrupted",
      protectionTitle: "Run protection", protectionScope: "Access scope", protectionNetwork: "Network", protectionLastBlock: "Last blocked action", protectionCheckPending: "Protection check not complete", protectionUnavailable: "Protection unavailable", protectionNotEnabled: "Automatic work is not enabled", protectionUnverified: "Not verified", protectionNoBlock: "None", protectionIsolationBlock: "Automatic work blocked because protection is not ready",
      submitted: "Submitted", understanding: "Understanding request", reviewing_plan: "Reviewing plan", finalizing_plan: "Finalizing plan", ready_to_implement: "Ready to implement", working: "Working", checking: "Running checks", preparing_delivery: "Preparing delivery"
    }
  };
  var ACTIVE_AUTONOMY_STATES = ["starting", "running", "pause_requested", "cancel_requested"];
  var RESUMABLE_AUTONOMY_STATES = ["paused", "failed", "blocked", "interrupted"];
  var state = { locale: "zh-CN", projects: [], tickets: [], selectedTicketId: null, selectedTicket: null, capabilities: {}, pollTimer: null, statusKey: "connecting", statusDetail: "" };
  var localeKey = "icode.workbench.locale";
  function byId(id) { return document.getElementById(id); }
  function text(key) { return translations[state.locale][key] || translations["en-US"][key] || key; }
  function formatText(key, values) { var result = text(key); Object.keys(values).forEach(function (name) { result = result.replace("{" + name + "}", String(values[name])); }); return result; }
  function clear(node) { while (node.firstChild) { node.removeChild(node.firstChild); } }
  function setStatus(key, detail) { state.statusKey = key; state.statusDetail = detail || ""; byId("status").textContent = text(key) + (state.statusDetail ? " · " + state.statusDetail : ""); }
  function normalizeLocale(value) { var lower = String(value || "").toLowerCase(); if (lower.indexOf("zh") === 0) { return "zh-CN"; } if (lower.indexOf("en") === 0) { return "en-US"; } return null; }
  function detectLocale() {
    var saved = normalizeLocale(localStorage.getItem(localeKey));
    if (saved) { return saved; }
    var candidates = (navigator.languages || []).slice(); candidates.push(navigator.language);
    for (var index = 0; index < candidates.length; index += 1) { var supported = normalizeLocale(candidates[index]); if (supported) { return supported; } }
    return "zh-CN";
  }
  function applyLocale(locale) {
    state.locale = normalizeLocale(locale) || "zh-CN"; localStorage.setItem(localeKey, state.locale); document.documentElement.lang = state.locale; byId("language-select").value = state.locale;
    document.querySelectorAll("[data-i18n]").forEach(function (node) { node.textContent = text(node.getAttribute("data-i18n")); });
    document.querySelectorAll("[data-i18n-placeholder]").forEach(function (node) { node.setAttribute("placeholder", text(node.getAttribute("data-i18n-placeholder"))); });
    if (state.selectedTicket) { renderDetail(state.selectedTicket); } else { renderTickets(state.tickets); }
    setStatus(state.statusKey, state.statusDetail); updateModeHelp();
  }
  function stageLabel(ticket) { return text(ticket.stage_key || "unknown"); }
  function modeLabel(ticket) { if (ticket.requested_execution_mode === "autonomous" && ticket.mode_status === "pending_activation") { return text("autonomousPending"); } return ticket.effective_execution_mode === "autonomous" ? text("autonomousMode") : text("interactiveMode"); }
  function renderTickets(items) {
    var list = byId("ticket-list"); clear(list); byId("ticket-count").textContent = String(items.length); byId("ticket-empty").hidden = items.length !== 0;
    items.forEach(function (ticket) {
      var button = document.createElement("button"); button.type = "button"; button.className = "ticket-card" + (state.selectedTicketId === ticket.ticket_id ? " selected" : "");
      var top = document.createElement("span"); top.className = "ticket-card-top"; var id = document.createElement("span"); id.className = "ticket-id"; id.textContent = ticket.ticket_id;
      var status = document.createElement("span"); status.className = "badge"; status.textContent = stageLabel(ticket); top.appendChild(id); top.appendChild(status);
      var title = document.createElement("strong"); title.textContent = ticket.title; var meta = document.createElement("span"); meta.className = "ticket-meta"; meta.textContent = modeLabel(ticket) + " · " + (ticket.updated_at || "—");
      button.appendChild(top); button.appendChild(title); button.appendChild(meta); button.addEventListener("click", function () { selectTicket(ticket.ticket_id); }); list.appendChild(button);
    });
  }
  function priorityLabel(priority) { var key = "priority" + priority.charAt(0).toUpperCase() + priority.slice(1); return text(key); }
  function runtimeState(ticket) { return (ticket.autonomous_run || {}).state || "pending"; }
  function renderProtection(ticket) {
    var limits = (state.capabilities.autonomous || {}).limits || {};
    var statusKey = ticket.requested_execution_mode !== "autonomous" ? "protectionNotEnabled" : ({
      enforced: "protectionCheckPending",
      policy_unavailable: "protectionUnavailable",
      application_only: "protectionUnavailable",
      not_configured: "protectionNotEnabled"
    }[limits.isolation_level] || "protectionNotEnabled");
    byId("protection-status").textContent = text(statusKey);
    byId("protection-scope").textContent = text("protectionUnverified");
    byId("protection-network").textContent = text("protectionUnverified");
    byId("protection-last-block").textContent = text((ticket.autonomous_run || {}).error_code === "isolation_unavailable" ? "protectionIsolationBlock" : "protectionNoBlock");
  }
  function renderAutonomy(ticket) {
    var panel = byId("autonomy-panel");
    var requested = ticket.requested_execution_mode === "autonomous";
    panel.hidden = !requested;
    if (!requested) { return; }
    var capability = state.capabilities.autonomous || { enabled: false, limits: {} };
    var limits = capability.limits || {};
    var isolationKey = {
      enforced: "isolationEnforced",
      application_only: "isolationApplicationOnly",
      policy_unavailable: "isolationPolicyUnavailable",
      not_configured: "isolationNotConfigured"
    }[limits.isolation_level] || "isolationNotConfigured";
    var current = runtimeState(ticket);
    byId("autonomy-state").textContent = text(current);
    byId("autonomy-capability").textContent = text(capability.enabled ? "capabilityEnabled" : "capabilityDisabled");
    byId("autonomy-limits").textContent = formatText("limitsFormat", {
      turns: limits.max_turns || "—",
      tokens: limits.budget_tokens || "—",
      isolation: text(isolationKey)
    });
    byId("autonomy-last-step").textContent = (ticket.autonomous_run || {}).last_step || text("noSteps");
    var allowed = {
      start: ["pending", "cancelled", "succeeded"].indexOf(current) !== -1,
      pause: ["starting", "running"].indexOf(current) !== -1,
      resume: RESUMABLE_AUTONOMY_STATES.indexOf(current) !== -1,
      cancel: ["starting", "running", "pause_requested"].indexOf(current) !== -1,
      takeover: ["starting", "running", "pause_requested"].indexOf(current) !== -1
    };
    ["start", "pause", "resume", "cancel", "takeover"].forEach(function (intent) {
      byId("intent-" + intent).disabled = !capability.enabled || !allowed[intent];
    });
  }
  function renderDetail(ticket) {
    state.selectedTicketId = ticket.ticket_id; state.selectedTicket = ticket; byId("welcome-panel").hidden = true; byId("ticket-detail").hidden = false;
    byId("detail-id").textContent = ticket.ticket_id; byId("detail-title").textContent = ticket.title; byId("detail-status").textContent = stageLabel(ticket); byId("detail-mode").textContent = modeLabel(ticket);
    byId("detail-priority").textContent = priorityLabel(ticket.priority); byId("detail-updated").textContent = ticket.updated_at || "—"; byId("detail-description").textContent = ticket.description || ticket.requirement || "—"; byId("detail-expected").textContent = ticket.expected_result || "—";
    byId("detail-raw-status").textContent = ticket.status; byId("detail-steps").textContent = (ticket.completed_steps || []).join(", ") || text("noSteps"); byId("detail-locale").textContent = ticket.locale; renderAutonomy(ticket); renderProtection(ticket); renderTickets(state.tickets); scheduleActivePoll(ticket);
  }
  function selectTicket(ticketId) {
    return fetch("/api/v1/tickets/" + encodeURIComponent(ticketId), { credentials: "same-origin" }).then(function (response) { if (!response.ok) { throw new Error("HTTP " + response.status); } return response.json(); }).then(function (payload) { renderDetail(payload.ticket); return payload.ticket; }).catch(function () { setStatus("unavailable"); });
  }
  function scheduleActivePoll(ticket) {
    if (state.pollTimer) { globalThis.clearTimeout(state.pollTimer); state.pollTimer = null; }
    if (!ticket || ACTIVE_AUTONOMY_STATES.indexOf(runtimeState(ticket)) === -1) { return; }
    state.pollTimer = globalThis.setTimeout(function () {
      if (state.selectedTicketId === ticket.ticket_id) { selectTicket(ticket.ticket_id); }
    }, 1000);
  }
  function loadTickets(query) {
    var url = "/api/v1/tickets" + (query ? "?query=" + encodeURIComponent(query) : "");
    return fetch(url, { credentials: "same-origin" }).then(function (response) { if (!response.ok) { throw new Error("HTTP " + response.status); } return response.json(); }).then(function (payload) { state.projects = payload.projects || []; state.tickets = payload.tickets || []; if (state.projects[0]) { byId("project-name").textContent = state.projects[0].name; } renderTickets(state.tickets); return payload; });
  }
  function openNewTicket() {
    var select = byId("new-ticket-project"); clear(select); state.projects.forEach(function (project) { var option = document.createElement("option"); option.value = project.project_id; option.textContent = project.name; select.appendChild(option); }); byId("new-ticket-dialog").showModal();
  }
  function updateModeHelp() { byId("mode-help").textContent = byId("execution-mode").value === "autonomous" ? text("autonomousHelp") : text("interactiveHelp"); }
  function requestId() { if (globalThis.crypto && typeof globalThis.crypto.randomUUID === "function") { return "ui-" + globalThis.crypto.randomUUID(); } return "ui-" + Date.now() + "-" + Math.random().toString(16).slice(2); }
  function submitTicket(event) {
    event.preventDefault(); var button = byId("submit-ticket"); button.disabled = true; button.textContent = text("submitting");
    var payload = { project_id: byId("new-ticket-project").value, title: byId("ticket-title").value, description: byId("ticket-description").value, expected_result: byId("expected-result").value, priority: byId("ticket-priority").value, locale: state.locale, execution_mode: byId("execution-mode").value, request_id: requestId() };
    fetch("/api/v1/tickets", { method: "POST", credentials: "same-origin", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload) })
      .then(function (response) { return response.json().then(function (data) { if (!response.ok) { throw new Error(data.message || "HTTP " + response.status); } return data; }); })
      .then(function (data) { byId("new-ticket-dialog").close(); byId("new-ticket-form").reset(); setStatus("created"); return loadTickets("").then(function () { renderDetail(data.ticket); }); })
      .catch(function (error) { setStatus("unavailable", error.message); })
      .finally(function () { button.disabled = false; button.textContent = text("submitTicket"); updateModeHelp(); });
  }
  function submitIntent(intent) {
    if (!state.selectedTicketId) { return; }
    var payload = { intent: intent, request_id: requestId() };
    var button = byId("intent-" + intent); button.disabled = true;
    fetch("/api/v1/tickets/" + encodeURIComponent(state.selectedTicketId) + "/intents", { method: "POST", credentials: "same-origin", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload) })
      .then(function (response) { return response.json().then(function (data) { if (!response.ok) { throw new Error(data.message || data.code || "HTTP " + response.status); } return data; }); })
      .then(function (data) { setStatus("intentAccepted"); renderDetail(data.ticket); return loadTickets(""); })
      .catch(function (error) { setStatus("unavailable", error.message); if (state.selectedTicket) { renderAutonomy(state.selectedTicket); } });
  }
  function bootstrap() {
    state.locale = detectLocale(); applyLocale(state.locale);
    fetch("/api/v1/bootstrap", { credentials: "same-origin" }).then(function (response) { if (!response.ok) { throw new Error("HTTP " + response.status); } return response.json(); }).then(function (payload) { state.projects = payload.projects || []; state.tickets = payload.tickets || []; state.capabilities = payload.capabilities || {}; if (state.projects[0]) { byId("project-name").textContent = state.projects[0].name; } renderTickets(state.tickets); setStatus("connected"); }).catch(function () { setStatus("unavailable"); });
  }
  byId("language-select").addEventListener("change", function (event) { applyLocale(event.target.value); });
  byId("ticket-search").addEventListener("input", function (event) { loadTickets(event.target.value).catch(function () { setStatus("unavailable"); }); });
  byId("new-ticket-button").addEventListener("click", openNewTicket); byId("close-dialog").addEventListener("click", function () { byId("new-ticket-dialog").close(); }); byId("cancel-ticket").addEventListener("click", function () { byId("new-ticket-dialog").close(); });
  ["start", "pause", "resume", "cancel", "takeover"].forEach(function (intent) { byId("intent-" + intent).addEventListener("click", function () { submitIntent(intent); }); });
  byId("execution-mode").addEventListener("change", updateModeHelp); byId("new-ticket-form").addEventListener("submit", submitTicket); bootstrap();
})();
