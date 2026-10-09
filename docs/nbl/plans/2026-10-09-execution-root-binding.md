# Execution Root Binding Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use nbl.subagent-driven-development (recommended) or nbl.executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 给外置控制面工单增加一次性、受校验且有事务事件的隔离代码根绑定，并恢复 Linux bridge 的合法装配。

**Architecture:** 保持 project_path/out_dir/ticket_id 的索引身份不变，专用 CLI 写入 execution_binding，在线消费前重新检查目录对象。独立包以流式归约检查绑定事件与 metadata 的一致性，不访问原机器路径，不把一致性当宿主认证或 Native 证明。

**Tech Stack:** Python 3.11 stdlib、现有 v3 JSON schema、现有锁/事务/幂等机制、unittest。

---

## 基线、范围和不可跨越的边界

- 用户授权：最小 ICODE-SKILL 契约修复及测试，验收通过后推送其 main，再更新主仓库固定版本。主仓库主线基线 020acebf51b61179bf401181ac703cb3d71446b6；独立子仓库 `/home/orbbec/git/icode-skill` main 1693651c1bd7daad3272eb054f0f81d6f254d08d，本计划作者只读检查时干净。
- 子仓库源码只改 `/home/orbbec/git/icode-skill`；`/home/orbbec/git/icode/vendor/icode-skill` 在子仓库发布前保持只读。不可临时改 vendor 让测试变绿。
- 不新建 branch/worktree，不增加权限、依赖、服务，不读取模型 KEY，不顺修 G2 inspection、Windows Git、模型端点。编译并发 1，上限仍为用户规定 6。
- 本计划只覆盖绑定，不自动将全部产品入口迁移到新接口；本阶段宿主调用方是 Linux bridge 真实工程 fixture。后续产品入口必须来自可信 WorkspaceSession，而不是模型或浏览器提交路径。
- 目录检查不是内核对象锁；实际执行仍须原 WorkspaceSession/Git 身份检查、policy、原生隔离。对象替换立即拒绝，不自动重绑。
- 离线只能证明事件流可观察到的未结执行/关闭顺序及最终镜像一致性。旧 birth/migration 没记录 checkout 初始种子，不能声称重建该历史，更不能声称证明当时真实 OS 状态。无需新增伪证明布尔字段。
- G1 原源码全量已经运行，不因本计划重跑；本片源码变化后按新冻结运行本片验收。

## 文件与责任

子仓库：`tools/icode_control.py`（绑定、在线对象校验、事件归约、CLI）、`schemas/ticket-metadata.schema.json`（严格字段）、`tests/test_execution_root_binding.py`（新增测试）、`references/control_plane.md`（实际合同）。不改事件类型枚举，复用 metadata_updated。

主仓库：`src/icode/control.py`（窄 wrapper）、`src/icode/pack_verify.py`（纯离线流式镜像）、`tests/test_control.py`（参数契约）、`tests/test_execution_binding_pack.py`（新增独立包测试）、`tests/test_linux_contract_engineering.py`（原作者已写的 fixture 合法绑定）、`scripts/run_workspace_ci.py` / `tests/test_run_workspace_ci.py`（四项新绑定跨平台选择与 required-skip 守卫）、固定子模块指针。现有 Linux bridge 尚未通过的其它验收不在此片伪报完成。

## Task 1: 子仓库一次性绑定与可观察事件语义

**状态**
- [x] 任务完成：已发布 d935a5218ca2970bce8157814bfda1f03aa6c9c4；下列步骤代码保留为原计划，实际修订和验收见末尾记录。

**Dependencies:** None

**Parallelizable:** No (唯一子仓库写作者；只读研究/CI 观察可并行)

- [ ] **Step 1: 确认基线、冻结需求，先加 RED 测试**

工作目录 `/home/orbbec/git/icode-skill`。先执行 `git status --short`、`git rev-parse HEAD`、`git branch --show-current`；期望干净、上述 1693651、main。不覆盖并发用户修改。新建 `tests/test_execution_root_binding.py`，同时加入下面基础代码与 Step 6 给出的全部测试方法，然后再运行 Step 2 RED；不能先写完 Step 3–5 生产实现再补 Step 6 测试。

```python
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "tools/icode_control.py"
spec = importlib.util.spec_from_file_location("binding_control", SCRIPT)
ctl = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ctl)


class BindingTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="icode-bind-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name).resolve()
        self.control = self.root / "控制 空间"
        self.code = self.root / "代码 空间"
        self.control.mkdir()
        self.code.mkdir()
        self.ticket = self.control / ".icode_output/.icode_output_1"
        self.call("create", "--dir", self.ticket, "--ticket-id", "bind-1",
                  "--requirement", "binding test", "--birth", "plan",
                  "--request-id", "birth")

    def call(self, *args, ok=True):
        proc = subprocess.run([sys.executable, "-B", "-X", "utf8", str(SCRIPT),
                               *map(str, args)], capture_output=True,
                              text=True, encoding="utf-8", errors="strict", timeout=15)
        self.assertEqual(proc.returncode == 0, ok, (proc.stdout, proc.stderr))
        return json.loads(proc.stdout)

    def bind(self, path=None, request="binding", ticket_id="bind-1", ok=True):
        return self.call("bind-execution-root", "--dir", self.ticket,
                         "--ticket-id", ticket_id, "--execution-root", path or self.code,
                         "--request-id", request, ok=ok)

    def snapshot(self):
        return tuple((self.ticket / name).read_bytes()
                     for name in (ctl.METADATA_NAME, ctl.EVENTS_NAME))

    def test_real_cli_projection_and_subprocess_replay(self):
        before = ctl.load_metadata(self.ticket)
        first = self.bind()
        frozen = self.snapshot()
        second = self.bind()
        self.assertTrue(second["already_applied"])
        self.assertEqual(first["event_id"], second["event_id"])
        self.assertEqual(frozen, self.snapshot())
        meta = ctl.load_metadata(self.ticket)
        self.assertEqual(meta["project_path"], before["project_path"])
        self.assertEqual(ctl.execution_workspace(self.ticket, meta), self.code)
        self.assertEqual(ctl.trusted_execution_workspace(self.ticket, meta), self.code)
        policy = self.call("action-policy", "--dir", self.ticket)
        self.assertEqual(policy["execution_root"], str(self.code))
        self.assertFalse(ctl.verify_event_chain(self.ticket, meta)[1])
        (self.code / "source.txt").write_text("isolated source", encoding="utf-8")
        (self.control / "source.txt").write_text("wrong storage root", encoding="utf-8")
        self.call("metadata-update", "--dir", self.ticket,
                  "--set-json", json.dumps({"code_files": ["source.txt"]}),
                  "--request-id", "code-files")
        fact = ctl.resolve_port(self.ticket, ctl.load_metadata(self.ticket), {
            "id": "code_files", "kind": "metadata_files", "value": "/code_files",
            "base": "workspace"})
        self.assertTrue(fact["exists"])
        self.assertEqual(fact["items"][0]["sha256"], ctl.file_sha256(self.code / "source.txt"))
        self.assertNotEqual(fact["items"][0]["sha256"], ctl.file_sha256(self.control / "source.txt"))

    def test_wrong_ticket_and_overlap_and_missing_and_file_are_unchanged(self):
        file = self.root / "file"
        file.write_text("x", encoding="utf-8")
        before = self.snapshot()
        for path in (self.root, self.control, self.ticket, self.root / "missing", file):
            with self.subTest(path=path):
                self.bind(path, ok=False)
                self.assertEqual(before, self.snapshot())
        self.bind(ticket_id="wrong", ok=False)
        self.assertEqual(before, self.snapshot())

    def test_binding_is_immutable_and_request_cannot_change_root(self):
        self.bind()
        frozen = self.snapshot()
        other = self.root / "other"
        other.mkdir()
        for path, request in ((other, "binding"), (other, "new"), (self.code, "new")):
            with self.subTest(path=path, request=request):
                self.bind(path, request=request, ok=False)
                self.assertEqual(frozen, self.snapshot())

    def test_plain_metadata_and_birth_cannot_set_binding(self):
        value = {"execution_binding": {"version": 1}}
        before = self.snapshot()
        result = self.call("metadata-update", "--dir", self.ticket,
                           "--set-json", json.dumps(value), ok=False)
        self.assertEqual(result["gate_id"], "metadata_update_protected")
        self.assertEqual(before, self.snapshot())
        result = self.call("create", "--dir", self.control / ".icode_output/.icode_output_2",
                           "--ticket-id", "bind-2", "--requirement", "x", "--birth", "plan",
                           "--metadata-json", json.dumps(value), ok=False)
        self.assertEqual(result["gate_id"], "birth_protected_fields")

    def test_replaced_root_and_ancestor_rejected_but_trace_remains_readable(self):
        self.bind()
        meta = ctl.load_metadata(self.ticket)
        self.code.rename(self.root / "old-code")
        self.code.mkdir()
        for fn in (ctl.execution_workspace, ctl.trusted_execution_workspace):
            with self.assertRaises(ctl.ControlError):
                fn(self.ticket, meta)
        self.call("trace", "--dir", self.ticket)
        self.assertFalse(ctl.verify_event_chain(self.ticket, meta)[1])

    def test_old_unbound_ticket_keeps_old_root(self):
        meta = ctl.load_metadata(self.ticket)
        self.assertEqual(ctl.execution_workspace(self.ticket, meta), self.control)
        self.assertEqual(ctl.trusted_execution_workspace(self.ticket, meta), self.control)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: 验证 RED**

运行 `python3 -B -m unittest discover -s tests -p test_execution_root_binding.py -v`。预期 bind 子命令不存在导致真实失败；旧无绑定测试可通过。记录总数、失败原因与退出码，不把 argparse stderr 误报成 JSON 功能验收。call 会先断言子进程退出码，再解析 JSON；实现后必须全部无错误。

- [ ] **Step 3: schema 与在线目录对象检查**

`schemas/ticket-metadata.schema.json` properties 新增完整属性：

```json
"execution_binding": {
  "type": "object",
  "additionalProperties": false,
  "required": ["version", "path", "ancestors"],
  "properties": {
    "version": {"const": 1, "type": "integer"},
    "path": {"type": "string", "minLength": 1},
    "ancestors": {
      "type": "array", "minItems": 1, "maxItems": 256,
      "items": {
        "type": "object", "additionalProperties": false,
        "required": ["path", "device", "inode"],
        "properties": {
          "path": {"type": "string", "minLength": 1},
          "device": {"type": "integer", "minimum": 0},
          "inode": {"type": "integer", "minimum": 1}
        }
      }
    }
  }
}
```

`tools/icode_control.py` 增加 `import stat`，pathlib import 扩充 `PurePosixPath, PureWindowsPath`。以下纯检查同时用于离线镜像，不做文件系统访问。采用显式平台路径语法是为了 Windows 包在 Linux 可审，反之亦然；不把本机 Path 当离线原路径解释器。

```python
def execution_binding_shape_ok(binding):
    if not isinstance(binding, dict) or set(binding) != {"version", "path", "ancestors"}:
        return False
    if type(binding["version"]) is not int or binding["version"] != 1:
        return False
    raw = binding["path"]
    if not isinstance(raw, str) or not raw or "\x00" in raw:
        return False
    cls = PureWindowsPath if PureWindowsPath(raw).is_absolute() else PurePosixPath
    root = cls(raw)
    if not root.is_absolute() or str(root) != raw or ".." in root.parts:
        return False
    chain = list(reversed(root.parents)) + [root]
    rows = binding["ancestors"]
    if not isinstance(rows, list) or not 1 <= len(rows) <= 256 or len(rows) != len(chain):
        return False
    for row, expected in zip(rows, chain):
        if not isinstance(row, dict) or set(row) != {"path", "device", "inode"}:
            return False
        if row["path"] != str(expected):
            return False
        if type(row["device"]) is not int or row["device"] < 0:
            return False
        if type(row["inode"]) is not int or row["inode"] <= 0:
            return False
    return True


def execution_binding_topology_ok(meta):
    if "execution_binding" not in meta:
        return True
    history = meta.get("checkout_history") or []
    return (execution_binding_shape_ok(meta["execution_binding"])
            and meta.get("active_checkout") is None
            and isinstance(history, list)
            and not any(isinstance(row, dict) and row.get("state") == "active"
                        for row in history))


def capture_execution_binding(raw):
    try:
        if not isinstance(raw, str) or not raw or "\x00" in raw:
            raise ValueError("path text")
        root = Path(raw)
        if not root.is_absolute() or str(root) != raw or ".." in root.parts:
            raise ValueError("path not canonical")
        chain = list(reversed(root.parents)) + [root]
        if len(chain) > 256:
            raise ValueError("path depth")
        rows = []
        for path in chain:
            info = path.lstat()
            if (not stat.S_ISDIR(info.st_mode) or stat.S_ISLNK(info.st_mode)
                    or getattr(info, "st_file_attributes", 0)
                    & stat.FILE_ATTRIBUTE_REPARSE_POINT):
                raise ValueError("linked or non-directory component")
            if type(info.st_dev) is not int or info.st_dev < 0:
                raise ValueError("device identity unavailable")
            if type(info.st_ino) is not int or info.st_ino <= 0:
                raise ValueError("inode identity unavailable")
            rows.append({"path": str(path), "device": info.st_dev, "inode": info.st_ino})
        if root.resolve(strict=True) != root:
            raise ValueError("path resolution changed")
        value = {"version": 1, "path": str(root), "ancestors": rows}
        if not execution_binding_shape_ok(value):
            raise ValueError("binding shape")
        return value
    except (OSError, RuntimeError, ValueError) as exc:
        raise ControlError("执行根目录对象校验失败", gate_id="execution_binding_identity") from exc


def bound_execution_workspace(out_dir, meta):
    binding = meta["execution_binding"]
    if not execution_binding_topology_ok(meta):
        raise ControlError("执行根绑定与 checkout 拓扑冲突", gate_id="execution_binding_topology")
    if capture_execution_binding(binding["path"]) != binding:
        raise ControlError("执行根或祖先目录对象已替换", gate_id="execution_binding_identity")
    root = Path(binding["path"])
    control = containing_workspace(out_dir)
    if root.is_relative_to(control) or control.is_relative_to(root):
        raise ControlError("控制根与执行根不能互相包含", gate_id="execution_binding_topology")
    return root
```

在 `require_valid_metadata` 原 schema 校验完成后追加纯结构检查；无绑定工单不改变原行为，trace/离线校验不 stat 原目录：

```python
    if not execution_binding_topology_ok(meta):
        raise ControlError("执行根绑定与 checkout 拓扑冲突",
                           gate_id="execution_binding_topology")
```

在 `execution_workspace` 和 `trusted_execution_workspace` 函数体的最前面分别加入同一分支，余下旧实现逐字保留：

```python
    if "execution_binding" in meta:
        return bound_execution_workspace(out_dir, meta)
```

在 CONTROLLED_BIRTH_FIELDS 与 METADATA_UPDATE_PROTECTED 都加入 `"execution_binding"`。不要把字段加入 CLOSE_BOOKKEEPING_FIELDS。

- [ ] **Step 4: 流式事件归约的完整实现**

下面类放在 `validate_event_semantics` 之前。仅保留未结 ID 集合及一个绑定对象，诊断为固定错误类别集合，不保存第二份事件正文。已有事件 schema、执行模型归约器仍负责完整 payload、重复 attempt、终结配对等通用检查；这个归约器不取代它们。

```python
class ExecutionBindingMirror:
    def __init__(self, metadata):
        self.metadata = metadata
        self.binding = None
        self.seen = False
        self.open_steps = set()
        self.open_operations = set()
        self.open_agents = set()
        self.closed = False
        self.issues = set()

    def consume(self, event):
        kind = event.get("event_type")
        payload = event.get("payload")
        if not isinstance(payload, dict):
            return
        for start, finish, key, opened in (
            ("step_started", "step_finished", "attempt", self.open_steps),
            ("operation_started", "operation_finished", "attempt", self.open_operations),
            ("agent_spawned", "agent_result", "spawn_id", self.open_agents),
        ):
            identity = payload.get(key)
            if kind == start:
                if isinstance(identity, str) and identity:
                    opened.add(identity)
                else:
                    # Legacy starts without pairing identity cannot prove quiescence.
                    opened.add(None)
            elif kind == finish and isinstance(identity, str):
                opened.discard(identity)
        if kind == "close_phase":
            self.closed = True
        elif kind == "ticket_reopened":
            self.closed = False
            if self.seen:
                self.issues.add("binding_checkout_conflict")
        if kind != "metadata_updated":
            if "execution_root_binding" in payload:
                self.issues.add("binding_wrong_event_type")
            return
        updates = payload.get("set")
        appends = payload.get("append")
        touches = ((isinstance(updates, dict) and "execution_binding" in updates)
                   or (isinstance(appends, dict) and "execution_binding" in appends))
        marked = "execution_root_binding" in payload
        if not touches and not marked:
            if self.seen and isinstance(updates, dict):
                if updates.get("active_checkout") is not None:
                    self.issues.add("binding_checkout_conflict")
            if self.seen:
                for change in (updates, appends):
                    history = change.get("checkout_history") if isinstance(change, dict) else None
                    if isinstance(history, list) and any(
                        isinstance(row, dict) and row.get("state") == "active" for row in history
                    ):
                        self.issues.add("binding_checkout_conflict")
            return
        allowed = {"execution_root_binding", "set", "append", "metadata_hash_after"}
        if (type(payload.get("execution_root_binding")) is not int
                or payload.get("execution_root_binding") != 1
                or set(payload) - allowed
                or not isinstance(updates, dict)
                or set(updates) != {"execution_binding"}
                or appends != {}
                or not isinstance(event.get("request_id"), str)
                or not event["request_id"].strip()
                or event.get("actor") != "icode"):
            self.issues.add("binding_event_shape")
        if self.seen:
            self.issues.add("binding_event_duplicate")
        if self.open_steps or self.open_operations or self.open_agents or self.closed:
            self.issues.add("binding_not_quiescent")
        candidate = updates.get("execution_binding") if isinstance(updates, dict) else None
        if not execution_binding_shape_ok(candidate):
            self.issues.add("binding_shape")
        self.binding = candidate
        self.seen = True

    def finish(self):
        meta = self.metadata
        if isinstance(meta, dict):
            if not execution_binding_topology_ok(meta):
                self.issues.add("binding_checkout_conflict")
            if ("execution_binding" in meta) != self.seen:
                self.issues.add("binding_metadata_mismatch")
            elif self.seen and meta["execution_binding"] != self.binding:
                self.issues.add("binding_metadata_mismatch")
        return sorted(self.issues)
```

在 `validate_event_semantics` 返回 problems 前加入：

```python
    binding_mirror = ExecutionBindingMirror(meta)
    for event in events:
        binding_mirror.consume(event)
    problems.extend(binding_mirror.finish())
```

没有绑定、没有绑定标记的旧工单不得新增诊断；旧 execution-model 与 lifecycle 检查仍保持。历史 unknown ID 只会阻止新绑定，不破坏旧链可读性。

- [ ] **Step 5: 专用命令与 CLI 注册**

新增完整命令函数；事务只能复用 commit_metadata_and_event，不能自行直接写两个文件。request 同键也先确认对象仍是同一个，然后走精确 idempotency；已绑定其它请求一概拒绝，避免幂等答复变新授权。

```python
def cmd_bind_execution_root(args):
    out_dir = Path(args.dir).resolve()
    if not isinstance(args.request_id, str) or not args.request_id.strip():
        raise ControlError("绑定需要非空 request-id", exit_code=2,
                           gate_id="execution_binding_request")
    with DirLock(out_dir):
        recover_pending_transaction(out_dir)
        meta = load_metadata(out_dir)
        require_vnext(meta, out_dir)
        require_valid_metadata(meta)
        if meta.get("ticket_id") != args.ticket_id:
            raise ControlError("绑定 ticket-id 不匹配", gate_id="execution_binding_ticket")
        events, problems = verify_event_chain(out_dir, meta)
        if problems:
            raise ControlError("现有事件链不完整，拒绝绑定", gate_id="event_chain",
                               violations=problems)
        binding = capture_execution_binding(args.execution_root)
        proposed = dict(meta, execution_binding=binding)
        bound_execution_workspace(out_dir, proposed)
        payload = {"execution_root_binding": 1, "set": {"execution_binding": binding},
                   "append": {}}
        prior = find_idempotent_event(events, args.request_id, "metadata_updated", payload,
                                     actor="icode",
                                     payload_keys=("execution_root_binding", "set", "append"))
        if prior:
            if meta.get("execution_binding") != binding:
                raise ControlError("绑定重放与当前对象不一致", gate_id="execution_binding_identity")
            print(json.dumps({"ok": True, "already_applied": True,
                              "event_id": prior["event_id"], "ticket_id": args.ticket_id,
                              "request_id": args.request_id}, ensure_ascii=False, indent=2))
            return 0
        if "execution_binding" in meta:
            raise ControlError("执行根已绑定，禁止替换或使用新请求重绑",
                               gate_id="execution_binding_immutable")
        if meta.get("close_state") is not None:
            raise ControlError("关闭流程中禁止绑定", gate_id="execution_binding_quiescence")
        mirror = ExecutionBindingMirror(meta)
        for event in events:
            mirror.consume(event)
        if mirror.open_steps or mirror.open_operations or mirror.open_agents or mirror.closed:
            raise ControlError("存在未结执行或关闭状态，禁止绑定",
                               gate_id="execution_binding_quiescence")
        require_valid_metadata(proposed)
        event = commit_metadata_and_event(out_dir, meta, proposed, "metadata_updated", payload,
                                          request_id=args.request_id, actor="icode")
    print(json.dumps({"ok": True, "event_id": event["event_id"],
                      "ticket_id": args.ticket_id, "request_id": args.request_id},
                     ensure_ascii=False, indent=2))
    return 0
```

argparse 在 metadata-update 注册前新增：

```python
    p = sub.add_parser("bind-execution-root", help="一次性绑定可信宿主的隔离代码根")
    p.add_argument("--dir", required=True)
    p.add_argument("--ticket-id", required=True)
    p.add_argument("--execution-root", required=True)
    p.add_argument("--request-id", required=True)
    p.set_defaults(func=cmd_bind_execution_root)
```

- [ ] **Step 6: 预先编写的语义、路径和事务负控取得 GREEN**

以下方法在 Step 1 加入 BindingTests 并在 Step 2 记录 RED；此处保存完整代码方便对应验收。所有 monkeypatch 都只是 portable 单元故障注入，不计真实 Native；原 CLI 正控独立保留。

```python
    def test_pure_semantics_rejects_forged_markers_and_open_lifecycles(self):
        binding = ctl.capture_execution_binding(str(self.code))
        meta = dict(ctl.load_metadata(self.ticket), execution_binding=binding)
        event = {"event_type": "metadata_updated", "actor": "icode", "request_id": "b",
                 "payload": {"execution_root_binding": 1,
                             "set": {"execution_binding": binding}, "append": {}}}
        bad = []
        no_marker = json.loads(json.dumps(event))
        del no_marker["payload"]["execution_root_binding"]
        bad.append(([no_marker], meta))
        wrong_marker = json.loads(json.dumps(event))
        wrong_marker["payload"]["execution_root_binding"] = True
        bad.append(([wrong_marker], meta))
        bad.extend((([event, event], meta), ([], meta), ([event], {})))
        for kind, key in (("step_started", "attempt"), ("operation_started", "attempt"),
                          ("agent_spawned", "spawn_id")):
            bad.append(([{"event_type": kind, "payload": {key: "a"}}, event], meta))
        bad.append(([{"event_type": "close_phase", "payload": {"to": "close_planned"}}, event], meta))
        changed = json.loads(json.dumps(meta))
        changed["execution_binding"]["ancestors"][-1]["inode"] += 1
        bad.append(([event], changed))
        for sequence, value in bad:
            with self.subTest(sequence=sequence):
                mirror = ctl.ExecutionBindingMirror(value)
                for item in sequence:
                    mirror.consume(item)
                self.assertTrue(mirror.finish())
        mirror = ctl.ExecutionBindingMirror(meta)
        mirror.consume(event)
        self.assertEqual(mirror.finish(), [])

    def test_boolean_ids_extra_fields_and_windows_junction_attribute_rejected(self):
        binding = ctl.capture_execution_binding(str(self.code))
        for key, value in (("device", True), ("inode", 0), ("inode", False)):
            broken = json.loads(json.dumps(binding))
            broken["ancestors"][-1][key] = value
            self.assertFalse(ctl.execution_binding_shape_ok(broken))
        binding["extra"] = 1
        self.assertFalse(ctl.execution_binding_shape_ok(binding))
        from types import SimpleNamespace
        real = Path.lstat
        def reparse(path):
            value = real(path)
            if path == self.code:
                return SimpleNamespace(st_mode=value.st_mode, st_dev=value.st_dev,
                    st_ino=value.st_ino, st_file_attributes=ctl.stat.FILE_ATTRIBUTE_REPARSE_POINT)
            return value
        with patch.object(Path, "lstat", reparse):
            with self.assertRaises(ctl.ControlError):
                ctl.capture_execution_binding(str(self.code))

    def test_symlink_path_refused_when_platform_can_create_it(self):
        link = self.root / "link"
        try:
            link.symlink_to(self.code, target_is_directory=True)
        except OSError as exc:
            self.skipTest("host cannot create symlink: " + str(exc.errno))
        before = self.snapshot()
        self.bind(link, ok=False)
        self.assertEqual(before, self.snapshot())

    def test_ancestor_replacement_detected_when_leaf_identity_is_preserved(self):
        parent = self.root / "parent"
        parent.mkdir()
        child = parent / "child"
        child.mkdir()
        self.bind(child)
        meta = ctl.load_metadata(self.ticket)
        parent.rename(self.root / "old-parent")
        parent.mkdir()
        (self.root / "old-parent/child").rename(child)
        with self.assertRaises(ctl.ControlError):
            ctl.execution_workspace(self.ticket, meta)

    def test_all_writers_share_structural_checkout_conflict_guard(self):
        self.bind()
        meta = ctl.load_metadata(self.ticket)
        active = {"path": str(self.code), "state": "active"}
        for key, value in (("active_checkout", active), ("checkout_history", [active])):
            with self.subTest(key=key):
                self.assertFalse(ctl.execution_binding_topology_ok(dict(meta, **{key: value})))
                with self.assertRaises(ctl.ControlError):
                    ctl.require_valid_metadata(dict(meta, **{key: value}))
        self.assertTrue(ctl.execution_binding_topology_ok(
            dict(meta, checkout_history=[{"state": "released"}])))

    def test_append_failure_rolls_back_via_original_transaction(self):
        from argparse import Namespace
        args = Namespace(dir=str(self.ticket), ticket_id="bind-1",
                         execution_root=str(self.code), request_id="b")
        before = self.snapshot()
        with patch.object(ctl, "append_prepared_event", side_effect=OSError("injected")):
            with self.assertRaises(OSError):
                ctl.cmd_bind_execution_root(args)
        self.assertEqual(before, self.snapshot())
        self.assertFalse((self.ticket / ctl.TXN_NAME).exists())

    def test_real_open_agent_blocks_new_binding_without_writes(self):
        self.call("record-agent-spawn", "--dir", self.ticket,
                  "--task-scope", "binding boundary", "--expected-artifact", "note",
                  "--evidence-boundary", "portable", "--join-condition", "done",
                  "--backend", "test", "--model", "test", "--capability", "text",
                  "--request-id", "agent-open")
        before = self.snapshot()
        result = self.bind(ok=False)
        self.assertEqual(result["gate_id"], "execution_binding_quiescence")
        self.assertEqual(before, self.snapshot())

    def test_exact_replay_during_open_agent_returns_only_existing_event(self):
        first = self.bind()
        self.call("record-agent-spawn", "--dir", self.ticket,
                  "--task-scope", "binding boundary", "--expected-artifact", "note",
                  "--evidence-boundary", "portable", "--join-condition", "done",
                  "--backend", "test", "--model", "test", "--capability", "text",
                  "--request-id", "agent-open")
        before = self.snapshot()
        result = self.bind()
        self.assertTrue(result["already_applied"])
        self.assertEqual(result["event_id"], first["event_id"])
        self.assertEqual(before, self.snapshot())

    def test_unpaired_step_and_operation_block_command_before_transaction(self):
        from argparse import Namespace
        args = Namespace(dir=str(self.ticket), ticket_id="bind-1",
                         execution_root=str(self.code), request_id="b")
        # This isolates the command's quiescence guard; it is not a real step receipt.
        for kind in ("step_started", "operation_started"):
            events = [{"event_type": kind, "payload": {"attempt": "open"}}]
            with self.subTest(kind=kind):
                with patch.object(ctl, "verify_event_chain", return_value=(events, [])):
                    with patch.object(ctl, "commit_metadata_and_event") as commit:
                        with self.assertRaises(ctl.ControlError) as raised:
                            ctl.cmd_bind_execution_root(args)
                        self.assertEqual(raised.exception.extra["gate_id"],
                                         "execution_binding_quiescence")
                        commit.assert_not_called()

    def test_real_step_and_operation_cli_block_binding(self):
        # Separate tickets keep the two real open-lifecycle checks independent.
        for number, args in enumerate((
            ("step", "--step", "plan", "--phase", "start", "--attempt", "open-step",
             "--request", "open-step"),
            ("operation", "--name", "read", "--opclass", "read_only", "--phase", "start",
             "--attempt", "open-operation", "--request", "open-operation"),
        ), 2):
            ticket = self.control / ".icode_output" / (".icode_output_" + str(number))
            ticket_id = "bind-" + str(number)
            self.call("create", "--dir", ticket, "--ticket-id", ticket_id,
                      "--requirement", "open execution", "--birth", "plan")
            self.call(args[0], "--dir", ticket, *args[1:])
            before = tuple((ticket / name).read_bytes()
                           for name in (ctl.METADATA_NAME, ctl.EVENTS_NAME))
            result = self.call("bind-execution-root", "--dir", ticket,
                               "--ticket-id", ticket_id, "--execution-root", self.code,
                               "--request-id", "bind-open", ok=False)
            self.assertEqual(result["gate_id"], "execution_binding_quiescence")
            self.assertEqual(before, tuple((ticket / name).read_bytes()
                             for name in (ctl.METADATA_NAME, ctl.EVENTS_NAME)))

    def test_real_checkout_update_blocks_binding_without_new_mutation(self):
        self.call("metadata-update", "--dir", self.ticket,
                  "--set-json", json.dumps({"active_checkout": {
                      "path": str(self.code), "state": "active"}}), "--request-id", "checkout")
        before = self.snapshot()
        result = self.bind(ok=False)
        self.assertEqual(result["gate_id"], "execution_binding_topology")
        self.assertEqual(before, self.snapshot())

    def test_close_guard_invokes_actual_command_before_transaction(self):
        from argparse import Namespace
        args = Namespace(dir=str(self.ticket), ticket_id="bind-1",
                         execution_root=str(self.code), request_id="b")
        # Explicit command unit fixture, not a completed workflow/close receipt.
        meta = dict(ctl.load_metadata(self.ticket), close_state="close_planned")
        with patch.object(ctl, "load_metadata", return_value=meta):
            with patch.object(ctl, "verify_event_chain", return_value=([], [])):
                with patch.object(ctl, "commit_metadata_and_event") as commit:
                    with self.assertRaises(ctl.ControlError) as raised:
                        ctl.cmd_bind_execution_root(args)
                    self.assertEqual(raised.exception.extra["gate_id"],
                                     "execution_binding_quiescence")
                    commit.assert_not_called()
```

运行新模块、旧 metadata/transition/close/execution/regression 契约，逐条记录真实退出码：

```bash
python3 -B -m unittest discover -s tests -p test_execution_root_binding.py -v
bash tests/test_control_plane_metadata_contract.sh
bash tests/test_control_plane_transition_contract.sh
bash tests/test_control_plane_close_contract.sh
bash tests/test_execution_model_contract.sh
bash tests/test_control_plane_regression_contract.sh
```

这些是已存在的门禁，不能用 `--skip-linters` 替换测试入口。符号链接真实不可创建时允许该单项明确 skip，不把模拟 reparse 当 Windows junction 实机信用。主 Linux 上该项应实际执行。新功能还需独立审查补齐审查发现的风险；不得只因上述样例全绿就宣称全部验收通过。

- [ ] **Step 7: 文档、独立审查、子仓库发布**

`references/control_plane.md` 增加下段完整使用合同（文字编辑，不替换旧 active_checkout 合同）：

> `bind-execution-root --dir TICKET --ticket-id ID --execution-root ABS --request-id KEY` 仅供可信宿主将外置工单一次性绑定到现有隔离代码目录。它不改变索引的 project_path/out_dir/ticket_id。路径必须规范绝对路径且各段不能是链接或 reparse point；根及祖先对象身份在每次在线消费前复检。绑定前拒绝活动 checkout、关闭流程和未结执行；绑定后不能更换目录、用新 request 重绑或通过 reopen 引入另一 checkout。同键同对象重放只返回 already_applied，不表示新的执行许可。旧无绑定工单保留原逻辑。绑定事件及独立包只证明记录一致性和可观察事件顺序，不认证宿主、原机器对象或旧出生时未记录的拓扑。

作者完成 selfSPEC/selfQUALITY 后 fresh SPEC、另一 fresh QUALITY，任何未解问题不发布。检查差异仅这四条子仓库路径；`git diff --check`；按项目现有发布检查补充实际要求，不跳过现存检查。验收通过后精确暂存四文件、提交、`git push origin main`；读取 `git ls-remote origin refs/heads/main` 核实际 SHA。记录作者/审查者、命令/输出计数、SHA，而不是在本计划预填通过。主仓库消费前必须远端已可获取。

## Task 2: wrapper、独立包及真实 fixture 合法消费

**状态**
- [x] 实现与独立双审完成；主仓库全局验收和发布归 Task3，尚未完成。

**Dependencies:** Task 1

**Parallelizable:** No (需子仓库已发布 SHA；Linux fixture 唯一写作者先交接)

- [ ] **Step 1: 更新固定副本并写 wrapper RED**

确认 vendor 干净，只 fast-forward 获取 Task 1 的已核远端 main SHA；不得把独立子仓库未发布工作目录当 vendor。更新后记录 `git -C vendor/icode-skill rev-parse HEAD` 和主仓库 gitlink diff。已有 dirty Linux 测试属于其作者，先由主线程明确交接，不覆盖。

`tests/test_control.py` import 加 `make_request`，TestControlPlaneIntakeAdapter 新增完整测试：

```python
    def test_bind_execution_root_uses_explicit_trusted_path_and_stable_request(self):
        cp = RecordingControlPlane()
        trusted_path = Path("/isolated/code")
        cp.bind_execution_root("/control/ticket", ticket_id="IC-1",
                               execution_root=trusted_path)
        self.assertEqual(cp.calls[-1], (
            "bind-execution-root", "--dir", "/control/ticket",
            "--ticket-id", "IC-1", "--execution-root", str(trusted_path),
            "--request-id", make_request("IC-1", "bind-execution-root")))
        cp.bind_execution_root("/control/ticket", ticket_id="IC-1",
                               execution_root="/isolated/code", request="retry-key")
        self.assertEqual(cp.calls[-1][-1], "retry-key")
```

运行 `PYTHONPATH=src:. python3 -B -m unittest tests.test_control -v`，新增方法应因 wrapper 缺失 RED，随后 `src/icode/control.py` 新增：

```python
    def bind_execution_root(
        self, out_dir: Path | str, *, ticket_id: str,
        execution_root: Path | str, request: str | None = None,
    ) -> ControlResult:
        """Bind only a trusted host WorkspaceSession root, never model/browser text."""
        return self.run(
            "bind-execution-root", "--dir", str(out_dir),
            "--ticket-id", ticket_id, "--execution-root", str(execution_root),
            "--request-id", request or make_request(ticket_id, "bind-execution-root"),
        )
```

- [ ] **Step 2: 独立包流式镜像**

先添加下一步给出的完整 `tests/test_execution_binding_pack.py`，运行 `PYTHONPATH=src:. python3 -B -m unittest tests.test_execution_binding_pack -v`，确认真实 verify_pack 入口仍接受缺标记/重复绑定的自洽重签包而 RED。纯镜像测试以 getattr+明确断言说明缺机制，不允许仅以顶层 ImportError 代替行为 RED。记录入口负控实际失败之后，才执行下列实现，再用 Step 3 同一测试代码做 GREEN。

将 Task 1 最终已验收并发布版本的三个纯定义 `execution_binding_shape_ok`、`execution_binding_topology_ok`、`ExecutionBindingMirror` 及其实际引用的命名常量原样放入 `src/icode/pack_verify.py`，它已 import PurePosixPath/PureWindowsPath；不要复制 capture/bound 在线函数，不 import vendor 或主项目模块。保持这个文件独立可复制。特别注意作者已收到的 bounded 修复：先检查 `len(root.parents) + 1` 不超过命名上限，再物化祖先列表；不得照抄本计划冻结 Task 1 示例中先构造列表的旧顺序。超深路径负控随最终纯检查器同步验收。

Task1 独立 SPEC 后补充：最终镜像还要求恰好四字段及合法 metadata_hash_after。下面纯镜像示例的 good 必须补真实合法摘要并先断言正控通过，不能让所有负控仅因共享正控缺摘要而通过；在同一方法内同步缺失/非法摘要及后续合法摘要无法掩盖的负控。仍为三个 pack 方法，不扩大 CI ID 集合。

在 `_verify_event_chain` 已有 mirror 初始化后新增：

```python
    binding_mirror = ExecutionBindingMirror(expected_ticket_metadata)
```

在读取每条 event 的 `ticket_state_mirror.consume` 旁新增：

```python
                binding_mirror.consume(event)
```

在函数末尾 `return artifact_facts, problems.render()` 前新增：

```python
    problems.extend(binding_mirror.finish())
```

低级 `_verify_event_chain` 未传 metadata 时只检查事件本身，不凭 sentinel 误报镜像缺失；真正 `verify_pack` 已传真实 metadata，必须检查缺失/差异。

- [ ] **Step 3: 完整新增包测试**

新建 `tests/test_execution_binding_pack.py`：

```python
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import uuid

from tests._support import require_skill
from icode.control import ControlPlane
from icode.evidence import build_evidence_pack
from icode import pack_verify
from icode.pack_verify import canonical_event_hash, verify_pack


class BindingPackTests(unittest.TestCase):
    def test_real_bound_partial_pack_is_portable_after_code_disappears(self):
        settings = require_skill()
        cp = ControlPlane(settings)
        with tempfile.TemporaryDirectory(prefix="icode-binding-pack-") as raw:
            root = Path(raw).resolve()
            code = root / "code"
            code.mkdir()
            (root / "control").mkdir()
            ticket = root / "control/.icode_output/.icode_output_1"
            cp.create(ticket, ticket_id="pack-bind", requirement="binding pack")
            cp.bind_execution_root(ticket, ticket_id="pack-bind", execution_root=code)
            pack = root / "pack"
            build_evidence_pack(ticket, dest=pack, gates_json=settings.gates_json,
                                clean=False)
            self.assertFalse(verify_pack(pack))
            code.rmdir()
            env = dict(os.environ)
            env.pop("PYTHONPATH", None)
            proc = subprocess.run([sys.executable, "-I", "-B", str(pack / "verify.py"), str(pack)],
                                  cwd=root, env=env, capture_output=True,
                                  text=True, encoding="utf-8", timeout=15)
            self.assertEqual(proc.returncode, 0, (proc.stdout, proc.stderr))

    def test_self_consistent_hash_does_not_replace_binding_semantics(self):
        mirror_type = getattr(pack_verify, "ExecutionBindingMirror", None)
        self.assertIsNotNone(mirror_type, "missing execution-binding mirror")
        binding = {"version": 1, "path": "/code", "ancestors": [
            {"path": "/", "device": 1, "inode": 1},
            {"path": "/code", "device": 1, "inode": 2}]}
        good = {"event_type": "metadata_updated", "actor": "icode", "request_id": "binding",
                "payload": {"execution_root_binding": 1,
                            "set": {"execution_binding": binding}, "append": {}}}
        bad_marker = json.loads(json.dumps(good))
        del bad_marker["payload"]["execution_root_binding"]
        wrong_type = json.loads(json.dumps(good))
        wrong_type["payload"]["execution_root_binding"] = True
        missing = []
        for sequence in (missing, [bad_marker], [wrong_type], [good, good]):
            with self.subTest(sequence=sequence):
                previous = "0" * 64
                mirror = mirror_type({"execution_binding": binding})
                for event in sequence:
                    event = dict(event, previous_event_hash=previous)
                    event["event_hash"] = canonical_event_hash(event)
                    previous = event["event_hash"]
                    mirror.consume(event)
                self.assertTrue(mirror.finish())

    def test_verify_pack_and_independent_process_reject_rehashed_binding_forgery(self):
        settings = require_skill()
        cp = ControlPlane(settings)
        for mutation in ("missing-marker", "duplicate"):
            with self.subTest(mutation=mutation):
                with tempfile.TemporaryDirectory(prefix="icode-binding-forgery-") as raw:
                    root = Path(raw).resolve()
                    (root / "code").mkdir()
                    (root / "control").mkdir()
                    ticket = root / "control/.icode_output/.icode_output_1"
                    cp.create(ticket, ticket_id="binding-forgery", requirement="binding pack")
                    cp.bind_execution_root(ticket, ticket_id="binding-forgery",
                                           execution_root=root / "code")
                    pack = root / "pack"
                    report = build_evidence_pack(ticket, dest=pack,
                                                 gates_json=settings.gates_json, clean=False)
                    self.assertTrue(report.ok, report.render())
                    self.assertEqual(verify_pack(pack), [])
                    path = pack / "ticket/events.jsonl"
                    events = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
                    binding = next(event for event in events
                                   if "execution_root_binding" in event["payload"])
                    if mutation == "missing-marker":
                        del binding["payload"]["execution_root_binding"]
                    else:
                        extra = json.loads(json.dumps(binding))
                        extra["event_id"] = str(uuid.uuid4())
                        events.append(extra)
                    metadata = json.loads((pack / "ticket/metadata.json").read_text(encoding="utf-8"))
                    events[-1]["payload"]["metadata_hash_after"] = pack_verify._metadata_content_hash(metadata)
                    previous = "0" * 64
                    for event in events:
                        event["previous_event_hash"] = previous
                        event["event_hash"] = canonical_event_hash(event)
                        previous = event["event_hash"]
                    path.write_text("\n".join(json.dumps(event, ensure_ascii=False)
                                             for event in events) + "\n", encoding="utf-8")
                    manifest_path = pack / "manifest.json"
                    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
                    for item in manifest["files"]:
                        member = pack / item["path"]
                        item["sha256"] = pack_verify.sha256_file(member)
                        item["size"] = member.stat().st_size
                    manifest["pack_digest"] = pack_verify.pack_digest(manifest["files"])
                    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False) + "\n",
                                             encoding="utf-8")
                    problems = verify_pack(pack)
                    self.assertTrue(any("binding_" in item for item in problems), problems)
                    self.assertFalse(any("断链" in item or "sha256" in item for item in problems), problems)
                    environment = dict(os.environ)
                    environment.pop("PYTHONPATH", None)
                    result = subprocess.run([sys.executable, "-I", "-B", str(pack / "verify.py"), str(pack)],
                                            cwd=root, env=environment, capture_output=True, text=True,
                                            encoding="utf-8", timeout=15)
                    self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
                    self.assertIn("binding_", result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
```

这里既有纯镜像单元负控，也有实际 verify_pack 和外部独立 verify.py 的自洽重签负控；保留完整已有 tests.test_evidence 回归。新正控特意是 partial pack；不能因此宣称 full engineering 或 G2 通过。

- [ ] **Step 4: 精确修复 Linux bridge fixture**

`tests/test_linux_contract_engineering.py` 的 `_Bridge.__init__` 原 full fixture 中，将 `project_path=str(self.root)` 改成 `project_path=str(self.control)`（明确 legacy fixture 的存储根身份，不冒充真实之前阶段）。普通 create 的 metadata seed 删除 project_path，仅保留 code_files。两条分支后、写 plan 和 action-policy 前加入：

```python
        bound = self.cp.bind_execution_root(
            self.directory, ticket_id=self.ticket_id,
            execution_root=self.root,
        )
        case.assertTrue(bound.ok)
```

最终完整替换普通 create 分支：

```python
        else:
            created = self.cp.create(self.directory, ticket_id=self.ticket_id,
                requirement="change value", birth="plan", metadata_json=json.dumps({
                    "code_files": ["changed.py"]}))
            case.assertTrue(created.ok)
        bound = self.cp.bind_execution_root(
            self.directory, ticket_id=self.ticket_id, execution_root=self.root)
        case.assertTrue(bound.ok)
```

不移动 control 到 code，不删除 action-policy 根等值断言，不放宽 cleanup、receipt、reviewer 或 pack 断言。full fixture 仍只称 fixture_seed；G2 缺口保持原失败边界。

- [ ] **Step 5: 四项跨平台显式选择与 required-skip 接线，先 RED 后 GREEN**

此步只改 `scripts/run_workspace_ci.py` 与 `tests/test_run_workspace_ci.py`。现有 DEFAULT 没有选择 `tests.test_control` 或新包模块，full 仅 Linux 不能代替 Windows/macOS 验收。新增业务 ID 必须精确四项：wrapper 一项、pack 三项；不把整个旧 control 类或模块提升为 required。额外一个 selection guard 自身加入 DEFAULT 一次，不纳入四项业务 required 集合。原 POSIX、G1 的 14 项、CONTRACT_ENGINEERING 32 项与 POSIX_CONTRACT_ENGINEERING 7 项保持原集合与语义。

先在 `tests/test_run_workspace_ci.py` 的 TestWorkspaceCiCoverage 中加入以下完整方法。现有 import 已具备 importlib/io/unittest/patch/redirect_stderr，不加依赖。真实 unittest loader/suite 执行 body SkipTest 和四类 fixture lifecycle；不是手造 result.skipped。

```python
    def test_execution_binding_methods_selected_once_and_required_with_fixture_holders(self):
        expected = {
            "tests.test_control.TestControlPlaneIntakeAdapter.test_bind_execution_root_uses_explicit_trusted_path_and_stable_request",
            "tests.test_execution_binding_pack.BindingPackTests.test_real_bound_partial_pack_is_portable_after_code_disappears",
            "tests.test_execution_binding_pack.BindingPackTests.test_self_consistent_hash_does_not_replace_binding_semantics",
            "tests.test_execution_binding_pack.BindingPackTests.test_verify_pack_and_independent_process_reject_rehashed_binding_forgery",
        }
        self.assertTrue(hasattr(run_workspace_ci, "EXECUTION_BINDING_TESTS"))
        declared = run_workspace_ci.EXECUTION_BINDING_TESTS
        self.assertEqual(set(declared), expected)
        self.assertEqual(len(declared), 4)
        guard_id = (
            "tests.test_run_workspace_ci.TestWorkspaceCiCoverage."
            "test_execution_binding_methods_selected_once_and_required_with_fixture_holders"
        )
        self.assertEqual(run_workspace_ci.DEFAULT_MODULES.count(guard_id), 1)

        def cases(suite):
            for test in suite:
                if isinstance(test, unittest.TestSuite):
                    yield from cases(test)
                else:
                    yield test

        selected = [
            test.id()
            for entry in run_workspace_ci.DEFAULT_MODULES
            for test in cases(unittest.defaultTestLoader.loadTestsFromName(entry))
            if test.id() in expected
        ]
        self.assertEqual(set(selected), expected)
        self.assertEqual(len(selected), 4)
        for test_id in sorted(expected):
            self.assertEqual(run_workspace_ci.DEFAULT_MODULES.count(test_id), 1)
            loaded = list(cases(unittest.defaultTestLoader.loadTestsFromName(test_id)))
            self.assertEqual(len(loaded), 1)
            self.assertEqual(loaded[0].id(), test_id)
            self.assertFalse(getattr(type(loaded[0]), "__unittest_skip__", False))
            self.assertFalse(getattr(getattr(loaded[0], loaded[0]._testMethodName),
                                     "__unittest_skip__", False))

        actual = []

        class ObservingRunner:
            def run(self, suite):
                result = unittest.TestResult()
                suite.run(result)
                actual.append(result)
                return result

        def skip_body(_case):
            raise unittest.SkipTest("simulated required binding body unavailable")

        # These four cases prove runner classification, not business correctness.
        for test_id in sorted(expected):
            class_id, method = test_id.rsplit(".", 1)
            module_id, class_name = class_id.rsplit(".", 1)
            test_class = getattr(importlib.import_module(module_id), class_name)
            actual.clear()
            with self.subTest(body_skip=test_id):
                with patch.object(test_class, method, skip_body), patch.object(
                    run_workspace_ci.unittest, "TextTestRunner", return_value=ObservingRunner()
                ), redirect_stderr(io.StringIO()):
                    self.assertEqual(run_workspace_ci.main((test_id,)), 1)
                self.assertEqual(len(actual), 1)
                self.assertEqual(actual[0].testsRun, 1)
                self.assertEqual(actual[0].failures, [])
                self.assertEqual(actual[0].errors, [])
                self.assertEqual([test.id() for test, _ in actual[0].skipped], [test_id])
                self.assertTrue(actual[0].wasSuccessful())

        representatives = (
            "tests.test_control.TestControlPlaneIntakeAdapter.test_bind_execution_root_uses_explicit_trusted_path_and_stable_request",
            "tests.test_execution_binding_pack.BindingPackTests.test_real_bound_partial_pack_is_portable_after_code_disappears",
        )
        optional = "tests.test_control.TestControlPlaneIntakeAdapter.test_create_next_索引覆盖可省略"
        self.assertNotIn(optional, run_workspace_ci.EXECUTION_BINDING_TESTS)
        self.assertNotIn(optional, run_workspace_ci.OPERATION_ADMISSION_TESTS)
        self.assertNotIn(optional, run_workspace_ci.POSIX_R3_TESTS)

        def skip_fixture(*_args):
            raise unittest.SkipTest("simulated binding fixture unavailable")

        for test_id in (*representatives, optional):
            class_id, method = test_id.rsplit(".", 1)
            module_id, class_name = class_id.rsplit(".", 1)
            module = importlib.import_module(module_id)
            test_class = getattr(module, class_name)
            required = test_id != optional
            for fixture in ("setUpClass", "tearDownClass", "setUpModule", "tearDownModule"):
                is_class = fixture.endswith("Class")
                target = test_class if is_class else module
                replacement = classmethod(skip_fixture) if is_class else skip_fixture
                holder_id = fixture + " (" + (class_id if is_class else module_id) + ")"
                actual.clear()
                with self.subTest(test_id=test_id, fixture=fixture):
                    with patch.object(test_class, method, lambda _case: None), patch.object(
                        target, fixture, replacement, create=True
                    ), patch.object(
                        run_workspace_ci.unittest, "TextTestRunner", return_value=ObservingRunner()
                    ), redirect_stderr(io.StringIO()):
                        self.assertEqual(run_workspace_ci.main((test_id,)), 1 if required else 0)
                    self.assertEqual(len(actual), 1)
                    self.assertEqual(actual[0].testsRun, 0 if fixture.startswith("setUp") else 1)
                    self.assertEqual(actual[0].errors, [])
                    self.assertEqual(actual[0].failures, [])
                    self.assertEqual([test.id() for test, _ in actual[0].skipped], [holder_id])
                    self.assertTrue(actual[0].wasSuccessful())
```

使用已固定 venv、`PYTHONPATH=src:.` 运行这个完整 ID，记录缺少新集合/DEFAULT 选择的 RED。随后先只添加下面四项集合及 DEFAULT 项、暂不改 required 分类，再运行同一测试，确认真实 body skip 返回 0 而断言要求 1 的行为 RED。最后才完成 required/holder 分类，实现 GREEN。不得把两阶段 RED 都简写为测试加载错误。

`scripts/run_workspace_ci.py` 在 OPERATION_ADMISSION_TESTS 后新增：

```python
EXECUTION_BINDING_TESTS = (
    "tests.test_control.TestControlPlaneIntakeAdapter.test_bind_execution_root_uses_explicit_trusted_path_and_stable_request",
    "tests.test_execution_binding_pack.BindingPackTests.test_real_bound_partial_pack_is_portable_after_code_disappears",
    "tests.test_execution_binding_pack.BindingPackTests.test_self_consistent_hash_does_not_replace_binding_semantics",
    "tests.test_execution_binding_pack.BindingPackTests.test_verify_pack_and_independent_process_reject_rehashed_binding_forgery",
)
```

DEFAULT_MODULES 的 `*OPERATION_ADMISSION_TESTS,` 后精确新增：

```python
    *EXECUTION_BINDING_TESTS,
    "tests.test_run_workspace_ci.TestWorkspaceCiCoverage.test_execution_binding_methods_selected_once_and_required_with_fixture_holders",
```

main 中仅将原 required_test_ids 至 selected_fixture_ids 的局部计算替换为以下内容，之后 skipped_required_tests 和返回语义原样保留。旧 G1 14 项 holder 仍 required；只选旧可选方法时同 class/module 的 holder 不变为 required。原 POSIX required ID 集合不变，不扩大它的 fixture holder 规则。

```python
    # Only explicitly selected required contracts promote fixture-level skips.
    # Optional tests in the same class/module keep their historical semantics.
    required_test_ids = frozenset((
        *POSIX_R3_TESTS, *OPERATION_ADMISSION_TESTS, *EXECUTION_BINDING_TESTS,
    )).intersection(modules)
    selected_contract_ids = frozenset((
        *OPERATION_ADMISSION_TESTS, *EXECUTION_BINDING_TESTS,
    )).intersection(modules)
    selected_contract_classes = {test_id.rsplit(".", 1)[0] for test_id in selected_contract_ids}
    selected_contract_modules = {class_id.rsplit(".", 1)[0] for class_id in selected_contract_classes}
    selected_fixture_ids = {
        f"{fixture} ({class_id})"
        for class_id in selected_contract_classes
        for fixture in ("setUpClass", "tearDownClass")
    } | {
        f"{fixture} ({module_id})"
        for module_id in selected_contract_modules
        for fixture in ("setUpModule", "tearDownModule")
    }
```

GREEN 定点命令（实际已固定解释器执行，不安装其它环境）：

```bash
env PYTHONPATH=src:. PYTHONDONTWRITEBYTECODE=1 /tmp/icode-packaged-skill-acceptance-fqxSO0bh/venv/bin/python -B -m unittest tests.test_run_workspace_ci -v
env PYTHONPATH=src:. PYTHONDONTWRITEBYTECODE=1 /tmp/icode-packaged-skill-acceptance-fqxSO0bh/venv/bin/python -B -m unittest tests.test_control.TestControlPlaneIntakeAdapter.test_bind_execution_root_uses_explicit_trusted_path_and_stable_request tests.test_execution_binding_pack -v
```

先前 G1、POSIX 和旧 32/7 selection guard 均在第一条完整模块中回归，不修改其断言来迁就新增组。Task 3 的 DEFAULT 实际计数会增加四个业务方法加一个 guard，共五个顶层测试；guard 内部的四次 body skip、八次 required holder、四次 optional holder 是分类子场景，不计为额外真实业务/平台覆盖。Windows/macOS 要等待绑定该新 SHA 的真实 CI，不以本地 Linux 加载测试宣称跨平台成功。

- [ ] **Step 6: wrapper/pack/CI selection 回归与独立审查**

用已固定 venv 的当前解释器和 `PYTHONPATH=src:.`，运行 `-B -m unittest tests.test_control tests.test_execution_binding_pack tests.test_evidence -v`；记录三模块真实计数/skip/错误，源码新功能不得因 require_skill skip 被误报成功。核 pack 单文件静态不含新 import。本任务作者 selfSPEC/selfQUALITY 后 fresh SPEC 和不同 QUALITY；未解决不进入真实 Linux 恢复验收。

## Task 3: 真实 Linux 恢复、发布与边界交付

**状态**
- [x] 任务完成：母仓库43e7739已发布并核远端；在线新SHA各平台结果独立观察，不授总体验收。

**Dependencies:** Task 1, Task 2

**Parallelizable:** No (真实 runtime 唯一 owner；只读远端 CI 观察可并行)

- [x] **Step 1: 冻结并跑真实 bridge 两个正控**

保持原 Linux bridge 计划、 helper/manifest、原配额和清理机制，唯一 runtime owner 运行以下实际现存方法（先 `rg -n '^class |def test_bridge_' tests/test_linux_contract_engineering.py` 核类名，不猜类名）：

```bash
env PYTHONPATH=src:. PYTHONDONTWRITEBYTECODE=1 GOMAXPROCS=1 GOFLAGS=-p=1 GOTOOLCHAIN=local CMAKE_BUILD_PARALLEL_LEVEL=1 /tmp/icode-packaged-skill-acceptance-fqxSO0bh/venv/bin/python -B -m unittest tests.test_linux_contract_engineering -v
```

此命令只在该模块仍为 Task 1 的两个真实正控加三个 portable guards 时使用；若并发作者已增加后续方法，必须按已核实际 class 定位两个正控而不擅自扩测试运行。应看到 create→bind→action-policy 根一致，再进入真实 dispatch；若下一个真实失败暴露，保留证据按原 bridge 任务处理，不能改门槛掩盖。记录 source/vendor SHA、helper/manifest摘要、real dispatch 数、Reviewer数、receipt/pack结果。绑定修复成功与整条桥成功分别记账。

- [x] **Step 2: 当前片自检、一次完整新基线验证**

先 `git diff --check`，定点 wrapper/pack/control/lifecycle 与 bridge portable 回归；当前源码冻结后按原主仓库 DEFAULT → 原始 `scripts/preflight.py` 全量流程执行一次，保存真实 unittest 总数、skip、fail/error、stdout/stderr与rc。不能用缩减测试冒充 preflight，不能因 CI 还运行而重复触发。编译使用 compileall `-j1`，输出缓存到新临时目录。保留 secrets/submodule 原门禁。现存未解决平台 CI 失败必须逐项归因且保持未通过，不以本片 Linux 通过冲抵。

- [x] **Step 3: 文档记录和发布主仓库**

更新本计划状态、设计状态、Linux bridge 交接记录，写实测结果与尚未通过项；执行文档契约检查和两轮差异复核。精确暂存本片文件和已验收子模块指针，不顺带提交其他作者未验收 dirty。用户已有主线推送授权：作者及两独立审查均通过且所需门禁通过后提交 main、push、核远端 SHA，并把新 SHA 交只读 CI observer。在线 CI 未终结不要报告线上通过；持续进入 Linux bridge 后续任务而非宣称 R2/R3 完成。

### 七维自检报告模板（必须填真实结果）

| 维度 | 验收证据 |
|---|---|
| 语法/编译 | 新测试加载、schema解析、compileall -j1 实际结果 |
| 依赖/调用链 | 子仓库已发布SHA→gitlink→wrapper→两root consumer→pack |
| 逻辑/边界 | 唯一绑定、准确幂等、根与祖先、bool/reparse/路径相交 |
| 异常处理 | 事务注入回滚、对象漂移拒绝、不产生第二授权 |
| 关联模块 | 普通update/create/reopen统一互斥、旧工单回归 |
| 兼容安全 | 无新权限/依赖、离线不访问原路径、旧包与工单行为 |
| 可运行性 | 真实CLI+实际独立verify.py+Linux dispatch各自结果 |

未执行或失败必须直写未通过，不使用“异常全覆盖”或“100%可运行”填充未知。

## 计划作者实际检查记录

2026-10-09，只读检查：完整 writing-plans skill、当前设计；`rg -n` 核 control 的 create、execution_workspace、trusted_execution_workspace、metadata-update、事件语义、事务、reopen、migration、CLI；逐段阅读这些函数以及 schema、现有 tests.test_control / tests.test_evidence fixture / Linux fixture。核独立子仓库 `git status --short` 空、HEAD 1693651。最初探测 `src/icode/pack.py`、`tests/test_pack_verify.py` 不存在，后以实际 `src/icode/pack_verify.py`、`tests/test_evidence.py` 为准。未运行测试、未修改任何源码/vendor、未读取密钥、未创建分支。

设计审查反馈已交主线程并获得处理边界：旧 birth/migration 缺初始 checkout 事实不能离线证明；统一纯 metadata 拓扑检查覆盖 reopen；macOS 由可信宿主取得 resolve 后规范路径，入口自身不自动吞掉 symlink；Windows 3.11 用 reparse 属性检查。这里只说明设计决定，不代表新实现已验证。

## 作者 selfSPEC / selfQUALITY

- selfSPEC：Task 1 覆盖受保护字段、专用请求、事务、对象及祖先、旧路径兼容、当前拓扑和可观察生命周期；Task 2 覆盖主仓库适配、真实 pack 接线与离线执行、外置 fixture；Task 3 保留真实 Linux 与整体 R2/R3 的验收边界。不存在把 G2/Windows/model 混入本片的步骤。
- selfQUALITY：复核实际 API 签名、schema 路径、existing unittest/contract 入口、zero-import 独立包要求。修复了初版 control 根未 mkdir、Windows Path 字符串断言、pack 只有纯镜像负控、真实未结命令覆盖及测试编写顺序问题。补充真实源端口区分存储根与代码根的内容哈希验证。新增 close 单元测试明确是实际 cmd 的状态注入，不伪装完整关闭流程。
- 静态 placeholder 扫描未命中；`git diff --no-index --check /dev/null docs/nbl/plans/2026-10-09-execution-root-binding.md` 无诊断，新增文件差异退出码 1 是 no-index 正常语义，不是测试通过。计划未执行测试或源码；因此运行性、异常覆盖和平台验收全部待实施，作者自审通过只适用于计划完整性。
- CI 接线补审：Task 2 仅增加 runner/selection-test 两路径，精确四项新业务 required ID 加一项 DEFAULT guard；现存 G1/POSIX/32/7 集合不变。四次真实 unittest body skip、两类目标的八次实际 fixture holder skip，以及旧可选方法四类 holder 保持成功，均是分类负控而非业务验收。两阶段 RED 先验证漏选，再验证跳过误成功，之后 GREEN。Task 1 冻结段未修改；Task 2 复制最终已验收纯检查器并同步先限深再物化的命名上限修复。

---
**Execution Mode:** serial

本任务仅计划写作；按主线程显式要求 STOP，不自动调用实施技能、不执行源码或测试。三个任务必须依赖顺序执行，主线程收到计划后独立审查再分配作者。

## root执行交接

计划作者冻结版本982行、SHA256 `3f458cd56ff33846abb999ccbf1ced00d5ec850b57637cc47588d76342a0dd72`。root已全文阅读初版813行及后续完整修订，实核事务、根消费、pack API与测试辅助接口；修复缺控制目录、跨平台路径断言、真实CLI负控、完整pack负控和行为RED先行问题。设计独立SPEC无阻断。按用户持续开发及main-only要求，使用subagent-driven-development，唯一Task1作者 `/root/execution_binding_task1_writer` 仅修改独立子仓库上述四路径并独占测试；不commit/push，待root独立审查和发布。固定vendor及主仓库生产代码此刻未改。此附记不是任务完成标记。

### Task1作者交付，独立审查中

作者已STOP，子仓库HEAD仍1693651。新模块最终22/22、0skip、rc0；原RED18个方法、7 failures和16 errors（含subtest，不当成额外方法），真实create成功后缺bind子命令是预期失败。后续深度检查1方法RED、append拓扑21方法中1F，再修复为GREEN。root读diff发现的超深路径先物化问题已改为命名上限先判深再生成祖先；未知/non-dict start保留sentinel，set/append拓扑对称检查。

旧契约按顺序执行：metadata在指定Python3.11 venv下8P/1F、rc1，明确缺jsonschema；transition13P/0F、close23P/0F、regression26P/0F均rc0，execution_model整套PASS/rc0但脚本不输出逐项数。使用机器上已存在的系统Python3.10.12与jsonschema4.26.0补跑原metadata完整脚本9P/0F、rc0，命令为 `PATH=/usr/bin:/bin:/usr/local/bin PYTHONDONTWRITEBYTECODE=1 bash tests/test_control_plane_metadata_contract.sh`。无安装，不把补跑说成原venv通过。

四路径冻结SHA256：control `7ec33ccc90eb416c78a1a852e6854c65d2e2afe02c34538facbf84d63c038a45`；schema `451f8e684fcc32f13eeea9cffd5525fa6b2659b7bccd9f7347cf1cb4f2860f92`；新test `1a54657be0c87baa6182cf1f95830e33edf123aed9c7123d3cea316071437f64`；reference `fe4087684ae489a20f8370724363865cbbcb21ec65827dea71073a75ec193dc4`。作者selfSPEC/selfQUALITY通过；fresh SPEC已开始，尚无独立QUALITY或发布。Linux符号链接是真实执行，Windows路径语法/reparse仅portable或double，不授Windows原生信用。

Task2另补最小跨平台CI选择计划，root已全文核新增段：精确四个业务方法与一个selection guard，继承原required fixture拒绝，不改变G1/POSIX旧集合。实施须复制Task1最终经过审查的纯检查器及命名常量，不能复用旧危险限深顺序。此补充不改变Task1授权范围。

### Task1 独立 SPEC 首轮与窄修

独立 SPEC 冻结四路径 SHA 一致，复跑新模块 22/22、0 skip、5.336s、rc0；结论 Critical 0 / Important 1 / Minor 0。新增绑定事件仅禁止多余字段，未强制原事务必写的 metadata_hash_after：纯内存 birth→binding→后续合法 metadata_updated 中，绑定摘要缺失、True 或非法字符串均被后续最终摘要掩盖。此为离线一致性缺口，不代表在线绑定绕过或宿主认证。

已交原作者按 TDD 窄修：新绑定事件必须恰有四字段，摘要为规范 64 位小写十六进制字符串；增加后续合法事件无法掩盖缺失/非法摘要的负控，同步纯镜像正控。旧事件规则不收紧。作者独占测试，未准提交；修复后由原 SPEC 复核，再由不同 QUALITY 审查。Task2 必须复制此最终批准版本，不以首轮 22 项通过替代修复。

窄修实际 RED：1 方法、7 个子场景失败；作者完整模块 GREEN 23/23、0 skip、rc0。原独立 SPEC 再核四文件冻结值并复跑 23/23、0 skip、5.135s、rc0，Critical/Important/Minor 均为 0，首轮问题关闭。不同审查者 `/root/execution_binding_task1_quality` 已开始只读质量审查，尚未发布。

新冻结 SHA256：control `f561d4971aba2068607e2a3e74651099d4228a45de01ece65b942941187f65e4`；schema `451f8e684fcc32f13eeea9cffd5525fa6b2659b7bccd9f7347cf1cb4f2860f92`；test `ad2406836d47f002689b1173a10b306632de7703d9721f4174d73eaeb7835472`；reference `1ef443b8ea6910b23630d6ee4d53268e243737266e09d3473d018c1c779e8fcc`。本轮五项旧契约未重跑，前述旧结果不伪装成新冻结复跑。顺序决策已记录 sequential-thinking 181–183：审查及冻结检查→发布子仓库 main→更新精确 gitlink→Task2 接入，独立 Git inspection/Windows/model 边界不扩展。

### Task1 质量批准与发布前复验

不同独立 QUALITY 完整核设计、Task1、四路径实际修改及事务/两消费者/reopen调用链，冻结值一致；独立 23/23、0 skip、5.565s、rc0，Critical/Important/Minor 均 0，准许提交本片而非授予总体验收。

随后 root 对最终冻结版本顺序复跑原五契约：系统 Python 环境 metadata 9P/0F；指定 3.11 venv 的 transition 13P/0F、close 23P/0F、regression 26P/0F，execution_model 整套 PASS（未输出项数）；全部 rc0。四路径 hash 再核不变，远端 main 仍 1693651。新增模块 20 轮串行复跑已启动，结果待记录；尚无提交或推送。

### Task1 已发布，Task2 开始

root 的 20 轮串行复跑完成：每轮 23 项，共 460P、0F/0E/0skip，113.835s、rc0。两个修改 Python 文件 compileall -j1 使用新建 /tmp 缓存，rc0；diff-check 与四个已暂存 blob SHA 均匹配冻结值，暂存范围恰好四路径。子仓库提交 `d935a5218ca2970bce8157814bfda1f03aa6c9c4`（743 additions / 1 deletion）已推送 origin/main；ls-remote 独立读回相同 SHA，工作区干净。

root 确认 vendor 干净且原 HEAD 1693651 后 fetch main 并 fast-forward 至 d935a5218ca2970bce8157814bfda1f03aa6c9c4，更新后仍干净。未创建分支或以未发布源码代替固定副本。主仓库未提交；唯一 Task2 作者 `/root/execution_binding_task2_writer` 已获七路径明确交接及测试独占，按真实行为 RED 接入 wrapper、pack、Linux fixture 和跨平台 required 选择。原五项旧契约与本片 Linux 测试不授 Windows/macOS 原生或 R2/R3 总体验收信用。

### Task2 必要打包接入补充

root 全局固定 SHA 查询发现 `src/icode/skill_resources.py`、`src/icode/skill_runtime_manifest.json`、`tests/test_packaged_skill.py` 仍固定 1693651；既有 setup.py 的严格原字节 staging 将拒绝新 vendor，不能只改 gitlink。按 multi-repo-artifact-provenance 核查，属于确定的包成员来源不一致，而非增加功能或依赖。root 完整读取三个文件、setup.py 和既有闭包方案，补充三路径由 root 唯一写入，原 Task2 作者七路径不变。

补环顺序：测试 pin 更新至已发布 d935a52 并验证 RED→保持原 72 成员白名单重算原字节 size/hash/总字节及 manifest 摘要→仅同步校验器常量，不放宽验证→现有直接 wheel 与独立 sdist 重建安装测试的共享控制面消费者增加真实 create/bind/action-policy/trace 与幂等检查，在空 PATH、-I、临时 cwd 下执行。原许可排除、损坏拒绝、资源不写入检查继续。测试等待当前作者释放 runtime 后串行；独立 SPEC 与 QUALITY 同时覆盖追加三路径。新语义不外推原生隔离和全 SKILL ≥90% 一致性。决策记录 sequential-thinking 184–186。

### Task2 作者冻结及 root 打包补环实测

七路径作者已 STOP：wrapper RED 4 方法中缺入口 1F→4P；pack RED 3方法/5F/0E/0skip/1.602s，四个完整包缺 marker、重复、缺 digest、非法 digest 变异重算全链及 manifest 后旧内置 verifier 返回 []、独立 -I verify.py 返回 0；GREEN 3P/0skip/1.618s。CI RED1 缺集合 1F，RED2 四个 body skip 与八个 required fixture holder 错误返回 0（1 方法12个子场景失败），GREEN 整模块26P/0skip/.319s。最终 control+新 pack+evidence+CI 四模块 217P/0F/0E/0skip、171.410s、rc0，其中旧 evidence 184 项。未运行 native/full/DEFAULT。

root 打包补环 RED：固定成员测试 1F/.001s/rc1，明确旧 1693651 与新 d935a52 pin 不一致。仅更新既有三个 member 的 size/hash：references/control_plane.md 22817 bytes、schema 20597 bytes、control 305121 bytes；总 72 members / 1944413 bytes，许可与排除范围未变。manifest SHA256 `d51f76424fa8b2fea38064a8e3871435ab139cba3dfc49bad7aefb5327aee83a`。完整 packaged_skill 模块 GREEN 18P/0F/0E/0skip、19.252s、rc0；直接 wheel 与无 .git/vendor 的独立 sdist 重建安装均由共享控制消费者实际完成新绑定、精确幂等、存储身份不变、action-policy 代码根投影及目录消失后 trace，空 PATH / -I /临时 cwd 与资源前后字节不变保持。

root 额外三路径冻结 SHA256：skill_resources `581d199b3947c5fde2e263dfe76a9fdf7cc31c9e0bcddb5b962b303166fb3e8f`；manifest 如上；packaged test `6534148f0bb3727e0110fbcc1f589ae1e611f3ce1d4d628e3d5e7b0f5d2b1f7e`。七路径作者冻结值见后续审查/最终记录；不同只读 `/root/execution_binding_task2_spec` 已开始覆盖完整十路径与 gitlink，测试 runtime 独占交给审查者。尚无母仓库提交。

### 完整接入 SPEC 与 Linux 首次正控成功

不同独立 SPEC 核十路径/gitlink、最终vendor三个纯定义逐字一致、原72成员与CI精确选择；四模块独立复跑51P/0F/0E/0skip、20.814s、rc0，Critical/Important/Minor 均0。随后不同 QUALITY 开始只读审查，root独占执行原Linux模块，结束后再交 QUALITY 定点复跑，未并行编译。

root 实际 `tests.test_linux_contract_engineering` 全模块5P/0F/0E/0skip、5.633s、rc0：3个portable观察/清理负控（输出 retained 来自显式double，不是两个真实fixture泄漏）与code/deepcheck两个真实正控。环境Linux6.8.0-138-generic/x86_64/uid1000/systemd249/Python3.11.15，发布vendor d935a52，母仓HEAD020aceb加本片未提交源码；source_host_model_double，native_ready=false、model_quality_credit=none。

两个实际命令 exit_code0、error null、scope_cleanup_ok true、violation_observer_status complete；payload_started 保持 null，不伪造执行确认字段。原configured缓存记录payload_limit8及三对象身份；每例CP operation start/finish和verification_recorded断言通过，fresh Reviewer三次调用、step仍开放、独立partial pack通过。源before/after均 `74207282dfbff8a95b2447ebf3dab98e43a8140045f4bc9959843507fac84f21`；tested tree `b101a49c5f428e4b4fdf34170f074d5a74774420`，不外推完整步骤/G2。

本轮helper SHA256 `42dfa8ce2c024cfe9d35535ea0bad89bc97883c94a6670a09df7f8d27ff93472`，manifest `77ef0ea5fee61ad1c192f050f1cb600c4833490f3763d0951984e8a2bb10cb72`，native源 `0700aa0a9fb8f18d60d1fe2f8320d8a1a03d4c0be9e189d10922fc2ada0a1ea3`；实际resource receipt摘要两例均 `8dadc249fd843266feeb3633227f2947a8576607b954f82af1f44876f246e5b9`。code工程receipt fingerprint `a43f76eb0ef4a805205ef323e1565c9e675bb28e6c923890bbc2011aa345bb0f`、pack manifest `6591ddc6cf0c7eebea926cfd45e5e2e8986bb6a8a7eb73f0e6487f50539097b8`；deepcheck fingerprint `732f4fb39c49281bf47e33c4c0849eb4360ca5170f67fd38b5289fb4389c9d06`、pack manifest `288b5143dbc95ee2eb6862eec72af5894c59948e14bf9a997292070d2044194a`。本轮临时fixture随测试正常回收，摘要属于测试窗口证据，不称持久发布包。

### 最终质量批准与阶段稳定性

不同 QUALITY Critical/Important/Minor 均0；独立 control/newpack/CI 三模块33P/0F/0E/0skip、1.910s、rc0。AST逐字结构核三纯定义与已发布vendor一致，72成员全部原字节size/hash一致；打包18项引用root与SPEC独立实测，不冒充QUALITY本人复跑。root全文回读实际接入与CI差异、安装链；未发现新待修项。

root阶段矩阵20轮完成，每轮11项：wrapper1、独立包3、CI required guard1、Linux模块5（3portable+2真实）、固定成员清单1；累计220P/0F/0E/0skip、151.873s、rc0，每轮前后十路径及vendor控制面摘要保持一致。此矩阵不是20轮安装测试，也不把fixture子场景当额外业务测试。随后启动新冻结DEFAULT，完整preflight仅对本片新冻结运行一次；旧G1没有重复全量。

### 固定资源来源核验记录

`vendor_package_matrix`：ICODE-SKILL 从既有官方 Git remote 获取已发布 d935a52；无新外部压缩包，档案摘要/签名不适用。固定 manifest 为 d51f7642…ee83a，72成员逐项核验；根 MIT LICENSE 已读取并原字节入包。未引入 DOCX 安装器/PPT素材，核心资源与全 SKILL 能力区分。

`toolchain_compatibility`：本机 Python3.11.15、现有 setuptools>=80（测试实际断言）及既有 cc 构建 Linux 独立助手；无新工具安装，串行。新绑定为 stdlib Python；本轮 Windows/macOS 原生构建与执行尚未核验。

`build_identity`：实际调用 setuptools.build_meta.build_wheel/build_sdist，再从无.git/vendor的sdist构建wheel；输入为本主仓冻结源码与干净vendor d935a52。测试为每轮新建临时 detached source/dist/venv，不使用用户全局Skill。两安装均 pip --no-index --no-deps；记录窗口2026-10-09本轮，临时绝对路径未作为持久交付物保存。

`repo_matrix`：主仓 `/home/orbbec/git/icode` HEAD020aceb、main、本片dirty待发布；独立 `/home/orbbec/git/icode-skill` main d935a52 干净且远端匹配；vendor `/home/orbbec/git/icode/vendor/icode-skill` d935a52 干净，gitlink已精确暂存。未混用用户全局技能或未发布子仓工作树。

`artifact_matrix`：wheel内 `icode/skill_runtime/` 恰好原72成员，逐项 bytes与vendor一致；控制面member SHA f561d497…f65e4、schema451f8e68…f0f92、说明1ef443b8…e8fcc，完整值见上述冻结。原wheel与sdist重建wheel对应资源成员及manifest相同。临时wheel外包摘要未保存，不补造；原生helper的源码运行摘要另列Linux实测段，不将两个构建产物混称同一对象。

`deployment_matrix`：部署对象仅本机隔离临时venv，两种wheel安装均启动新解释器，以-I、空PATH、临时cwd读取包内默认资源并实际create/bind/replay/action-policy/trace。运行前后成员hash一致；不需要重启常驻服务，没有更改用户实际安装环境或发布PyPI。

`mismatches`：初始 repo pin / package member mismatch（vendor d935a52但manifest1693651）已由真实RED确认并同步修复。`verdict`：本轮已测试的源→72资源→临时安装绑定链 proven；正式发布包、Windows/macOS原生与R2/R3整体 unresolved。安装通过不能外推完整SKILL闭包或资源限制达标。

### 主仓库十路径最终源码冻结

以下值在独立审查、20轮矩阵及DEFAULT614P之后重新核对一致；文档进度更新不改变受测源码。

```text
acda84bf6bdec0488199c7c4620e9037203e37968e89d8c2b6a6aa80b765279e  src/icode/control.py
ef268140ff91c2ade15483a1a571ce17c6373eac60e0789d2827b0f54270332b  tests/test_control.py
f67f353b37df9f94520cb23964569d84b0a10cba231c2b62b6a79517e35326fa  src/icode/pack_verify.py
4331f5f99fe83afd96f8e2ff850db7d73d2298b1cc161b6ff925c4b13bf03cbe  tests/test_execution_binding_pack.py
fd70f8bd07e5974f952257980db90030ebd69aa8244e4709b1ca47cba51eb53a  tests/test_linux_contract_engineering.py
a2e75c8ed0de8cef5ad020c8aa853bc019761c9f5d549beaeb84370684330ff3  scripts/run_workspace_ci.py
af16ed5299ab7c8d6a1b898215d6f8b8d0e1cacb453d1a6ff0c334c492bf230c  tests/test_run_workspace_ci.py
581d199b3947c5fde2e263dfe76a9fdf7cc31c9e0bcddb5b962b303166fb3e8f  src/icode/skill_resources.py
d51f76424fa8b2fea38064a8e3871435ab139cba3dfc49bad7aefb5327aee83a  src/icode/skill_runtime_manifest.json
6534148f0bb3727e0110fbcc1f589ae1e611f3ce1d4d628e3d5e7b0f5d2b1f7e  tests/test_packaged_skill.py
```

### 子仓库官网运行详情（独立于绑定合同）

只读核对 [Public site 37908919394](https://github.com/ayukyo/icode-skill/actions/runs/37908919394)，head_sha 为 d935a5218ca2970bce8157814bfda1f03aa6c9c4，终态 failure。renderer / ubuntu-renderer job 113749054417 的 offline failure/distribution contracts 成功，随后 Public installer downloads and registers pinned owned renderer 失败；build job 113749611168 与 deploy job 113749611611 均 skipped。

实际 job 日志 09:05:13 开始 LibreOffice 下载，09:05:56 开始 `poppler-utils_22.02.0-2ubuntu0.13_amd64.deb source 1`，09:05:57 返回 `HTTP Error 404: Not Found` 并 rc1。这是本轮已观察到的既有渲染器下载失败；不将本次本地控制面通过称作线上全绿或官网部署成功。未改下载版本/摘要、未绕过验证或重跑失败 job；该独立子仓库问题不混入最小绑定授权。无 `gh` CLI 后改用官方只读 API 与 GitHub 日志工具，不安装工具、不读取令牌。

### 全量首次结果与提交前检出测试修正

冻结 DEFAULT 实测 614P/0F/0E/0skip、226.620s、rc0，含已安装 bootstrap verifier 字节绑定检查。随后原始 preflight 子进程完整运行 2479 项、2 个 subTest failures、59 skips、553.802s、rc1（子进程墙钟554.244s，预检555.738s）。密钥与子模块门禁通过；测试门禁正确阻断，未提交或推送母仓库。

两失败均在 `tests.test_packaged_skill_ci.TestPackagedSkillCi.test_real_recursive_checkout_retains_pin_bytes_under_autocrlf_override`：原测试 clone 母仓旧 HEAD，取出旧 gitlink1693651，却与运行中已更新的 SOURCE_COMMIT d935a52 比较。实际源 index 已是 d935a52，干净 vendor 同为 d935a52；这不是绑定运行失败，也不能靠先提交绕过提交前门禁。

新增本片第十一源码路径 `tests/test_packaged_skill_ci.py`，仅把真实临时检出的输入改为源 `git write-tree` 所得暂存树：两 autocrlf 场景共用一个树快照，在临时 clone 内 `read-tree --reset -u` 后仍执行真实递归 submodule update。保留原严格 SOURCE_COMMIT、原字节/manifest、CRLF 正反断言，不根据常量或 vendor HEAD 重写 gitlink，不改源 index、不建分支、不改全局配置。准确证据名称为“暂存树检出验证”，不是“新提交检出验证”。

独立只读 `/root/checkout_index_review` 复核：与 preflight 原 index 校验口径一致，无阻断问题；未运行测试。root 定点完整模块7P/0F/0E/0skip、1.341s、rc0。前述十路径生产/业务测试冻结值不变；原完整 preflight 已再次启动，待真实终态。顺序决策记录187–189。此次重跑为修正已观察失败后的必要复验，不将首次失败改写为成功。

### 母仓库全量复验通过，发布前冻结

修正后的原始 preflight 完整子进程2479项、2420P/59skip/0F/0E、593.244s、rc0；子进程墙钟593.706s、预检总595.381s，原三道守卫全部通过。没有替换子进程测试实现或删减发现范围。新增检出修正模块随后20轮串行复跑，每轮7P，共140P/0F/0E/0skip、27.381s、rc0。第十一源码路径 SHA256 `78aabcd1bd67b1e2078b53de2a31ae5a25ede16d947975fb475998e906937dae`；此前十路径不变。

`compileall -q -j1 src scripts tests` 使用新建 `/tmp/icode-binding-main-compile-XXXXXXXX` 缓存且rc0；治理、站点及严格竞品排期检查均rc0。站点检查未抓取外部导航，排期有效不等于重新研究全部20项目。发布范围明确为11源码/测试/清单路径、6文档及1 gitlink，共18路径；不包含其它平台修复、用户环境或临时安装产物。

【架构级自检报告】（本绑定分片）

- ✅ 语法/编译：完整2479项加载与运行零失败，修改源及测试j1编译通过；59环境跳过单列。
- ✅ 依赖/调用链：已发布子仓d935a52、固定gitlink、72成员资源、宿主wrapper、两个根消费者与独立验包一致；两种临时安装实际消费新绑定。
- ✅ 逻辑/边界：一次性与幂等、路径祖先/对象替换、拓扑互斥及伪造/缺失/重复绑定负控通过，不自动重绑或迁移。
- ✅ 异常处理：本片事务异常与不完整事件拒绝回归通过；未覆盖平台及完整工程负控不宣称全覆盖。
- ✅ 关联模块：旧五项CP契约、主仓全量、required-skip分类和资源来源守卫通过；暂存树检出修正保持原CRLF正反例。
- ✅ 兼容安全：无新权限、依赖、全局Git设置或模型密钥读取；离线不访问原代码目录，旧无绑定工单路径保留。
- ✅ 可运行性：实际CLI、独立verify.py、临时wheel/sdist安装、Linux两个真实命令正控分别验证；不代表完整步骤、Windows/macOS原生、模型或R2/R3整体验收。

剩余发布动作：六文档两轮检查、精确18路径暂存核验、main提交推送及远端SHA确认。发布后继续Linux bridge Task2，不因本分片通过结束总目标。

### 本片已发布，继续 Linux 失败场景验收

最终六文档连续两轮0疑似项，完整暂存diff-check通过；18路径恰为预定范围，暂存后worktree相对index无差异，十一源码SHA与上述冻结一致。提交 `43e773997e24bdb7e72a619ca005e5fd680748fb`，parent020acebf51b61179bf401181ac703cb3d71446b6，tree `a428428205a5b93e28e638095a8e6b8488e00070`，2601 additions / 30 deletions。push origin/main成功，ls-remote只返回同SHA的main，发布后工作区干净；本条提交履历随下一片记录，避免自引用。

新SHA attempt1只读观察已启动：CI37913347447初见queued，Public website37913347500已success，Windows helper provenance37913347432初见in_progress。未提前授全平台通过。公共API未认证额度耗尽后使用官方只读GitHub工具，不访问凭据或重跑工作流。

root已交唯一作者 `/root/linux_bridge_task2_writer` 接续原Linux计划Task2，限定一个测试文件16个新增负控，root仅更新文档/协调只读研究与CI；继续main-only、j1、不修改生产门、未知收束保留owned根、未决CP不自动重放。本片授权完成不表示G2/Windows/model额外子仓范围获准。

### 43e7739 在线终态

独立只读观察者已DONE/STOP，三个workflow均attempt1且绑定完整43e7739 SHA：[CI37913347447](https://github.com/ayukyo/icode/actions/runs/37913347447) failure（37success/4failure/3skip），[Pages37913347500](https://github.com/ayukyo/icode/actions/runs/37913347500) 两job success，[provenance37913347432](https://github.com/ayukyo/icode/actions/runs/37913347432) validate及四签名安装矩阵success。

双Linux full各2479total/2408P/71skip；Ubuntu DEFAULT614P及后续75P。日志中的模拟required CP缺失error annotation来自预期负控，最终unittest OK，不认作full失败。七项packaged安装矩阵均success，实际抽查Ubuntu、Win x64 Py3.12、ARM Py3.11各18项OK；不声称逐项审阅其余四份日志。六native jobs success但全部ready=false，Ubuntu22双架构8/10、Ubuntu24系7/10、mac双架构6/10，评分不代替整体准入。

四失败保留本轮区别：Windows x64 DEFAULT113763502045为594total/20skip/2E，inspection Win10093，native legacy测试错误信息自身observed[0].render触发IndexError，不能从这份日志直接认定原错为Win10038；ARM113763502200为594total/20skip/1F/1E，明确Win10093与Win10038/dispatch0。双Reviewer113763502112/113763502025均exit78、Win10035、wait_expired；x64 runner gate unavailable，ARM runner observer ready但no_matching_event，内部collector subscription均rc5，与runner层区分。

四签名安装日志报告密码学校验、offline verifier及密码学负控通过；PE capture仍parse_complete/runtime_load_verified/source_launch_verified三false。只读API/日志观察，没有独立下载或校验制品、没有重跑工作流，不授生产Windows隔离或R2/R3完成。
