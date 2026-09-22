// ICODE 审批台前端。
// 约束（与上游 UI 的既有约定对齐）：
//   - 无第三方依赖、无 CDN
//   - 只用 textContent 渲染动态内容（不用 innerHTML，避免注入）
//   - 只提交 approval_id + decision；不接受也不发送任何路径/命令
(function () {
  "use strict";

  var stateUrl = "/api/state";
  var decideUrl = "/api/decision";

  function el(id) { return document.getElementById(id); }

  function clear(node) {
    while (node.firstChild) { node.removeChild(node.firstChild); }
  }

  function renderPending(items) {
    var list = el("pending");
    clear(list);
    el("pending-count").textContent = String(items.length);
    el("pending-empty").hidden = items.length !== 0;

    items.forEach(function (item) {
      var li = document.createElement("li");

      var head = document.createElement("div");
      head.className = "row";
      var tool = document.createElement("strong");
      tool.textContent = item.tool;
      var op = document.createElement("span");
      op.className = "pill dim";
      op.textContent = item.opclass;
      head.appendChild(tool);
      head.appendChild(op);

      var reason = document.createElement("div");
      reason.className = "reason";
      reason.textContent = item.reason;

      var args = document.createElement("pre");
      args.className = "args";
      args.textContent = JSON.stringify(item.arguments, null, 2);

      var actions = document.createElement("div");
      actions.className = "actions";
      var allow = document.createElement("button");
      allow.textContent = "放行";
      allow.className = "allow";
      allow.addEventListener("click", function () {
        decide(item.approval_id, "approve", allow);
      });
      var deny = document.createElement("button");
      deny.textContent = "拒绝";
      deny.className = "deny";
      deny.addEventListener("click", function () {
        decide(item.approval_id, "deny", deny);
      });
      actions.appendChild(allow);
      actions.appendChild(deny);

      li.appendChild(head);
      li.appendChild(reason);
      li.appendChild(args);
      li.appendChild(actions);
      list.appendChild(li);
    });
  }

  function renderHistory(items) {
    var list = el("history");
    clear(list);
    el("history-empty").hidden = items.length !== 0;
    items.slice().reverse().forEach(function (row) {
      var li = document.createElement("li");
      li.className = "row";
      var what = document.createElement("span");
      what.textContent = row.tool;
      var how = document.createElement("span");
      how.className = "pill " + (row.decision === "approve" ? "ok" : "no");
      how.textContent = row.decision === "approve" ? "已放行" : "已拒绝";
      var why = document.createElement("span");
      why.className = "dim";
      why.textContent = row.reason || "";
      li.appendChild(what);
      li.appendChild(how);
      li.appendChild(why);
      list.appendChild(li);
    });
  }

  function decide(approvalId, decision, button) {
    button.disabled = true;
    fetch(decideUrl, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      credentials: "same-origin",
      body: JSON.stringify({ approval_id: approvalId, decision: decision })
    }).then(function (resp) {
      return resp.json().then(function (data) {
        el("status").textContent = resp.ok
          ? (decision === "approve" ? "已放行，等待执行" : "已拒绝")
          : ("失败：" + (data.error || resp.status));
        poll();
      });
    }).catch(function (err) {
      el("status").textContent = "请求失败：" + err;
      button.disabled = false;
    });
  }

  function poll() {
    fetch(stateUrl, { credentials: "same-origin" })
      .then(function (resp) {
        if (!resp.ok) { throw new Error("HTTP " + resp.status); }
        return resp.json();
      })
      .then(function (data) {
        renderPending(data.pending || []);
        renderHistory(data.history || []);
        el("status").textContent = "已连接 · 自动刷新中";
      })
      .catch(function (err) {
        el("status").textContent = "未连接（" + err + "）";
      });
  }

  poll();
  setInterval(poll, 1500);
})();
