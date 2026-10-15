# Windows CI positive loopback admin boundary Implementation Plan

> **For agentic workers:** 本轮只编写 PLAN；root 全文及 fresh SPEC/不同 QUALITY 双审之前禁止落 TEST/SOURCE/CI/Git。正式实施使用 nbl.subagent-driven-development 或 nbl.executing-plans，独立 TEST/SOURCE 作者。main-only/online-first 覆盖 worktree/分支/每步提交默认。

**Goal:** 为唯一 admin 预分配 positive SID 提供完整 Get 原件、受保护持久账本、单 SID 固定系统 CLI 和独立清理能力；Reviewer 与 foreign 永不被修改。

**Architecture:** 原件读取、句柄/ACL/Job 原语与协调状态分开；只有受信 admin workflow parent 创建的受保护实例可以执行固定操作。core 的 State/JSON 只作模型，不作为 authority。实际标准用户私有 session、双 nonce 与 workflow 启用属于下一片完整 PLAN 的硬依赖。

**Tech Stack:** Python >=3.12、Windows SDK ctypes、受保护 NTFS 句柄、Job、固定 System32 工具；无安装、服务、socket broker 或第三方依赖。本机 3.11 仅软件诊断。

---

## 当前冻结前架构核对

根授权/结构化思考 receipt `2fd95d`，双 binding 补充 receipt `79f5e7`。当前权威候选 `619ed7771d9741eab11cb8a333965521d0c8d228`；原 `e94f72004071188b1c69e838f6faa98bc58e9723`（父 `ca41c78d6f57938f8dd9aa1fb912dad7e44efe9c`）保留历史。当前 CI `38682951338`、provenance `38682951358`、Pages `38682951556` 全部终态前不得推新候选。这里保留交接状态，不冒称持续线上观察。本 admin PLAN、独立 admin TEST DOC、addendum 不在该 core 候选内；不修改已提交 core 资产。

已完整读取 109 行同名 DESIGN、147 行 Get include、Reviewer job 的实际标准用户启动/观察/finally（844–2140）、wrapper 1283–1810 与现有 Job 原语相关定义。当前 Get include 只给目标采样，不能当完整列表；当前 probeRoot 授标准用户 Modify，不能放 admin 代码/账本；当前 finally 会删除临时账号和 probeRoot，admin 证据必须位于独立受保护目录。现有 run_windows_job 没有 Resume 前持久化 PID/creationtime 的接点；不能把返回后的 PID 或可构造结果对象伪装成该证明，不能扩大现有产品固定 argv guard。

root 已锁定端口合同：admin 预分配并冻结两个端口；下一片标准用户 listener 必须 exact bind，冲突 fail-closed，不重选、不修改 manifest、不增加请求枚举。探测释放至实际 bind 不是端口保留或原子操作；只有真实 listener/host canary/双 nonce/token/Job 事实才授连通信用。端口仅关联证据，不成为 CLI 参数或权限来源。

root 已锁定命令链：CreateProcessW(CREATE_SUSPENDED) → 独立 KILL_ON_JOB_CLOSE Job → 持久化 intent、PID/creationtime 并 Flush → Resume；创建或写账本失败不得 Resume，必须尝试实际回收。正常/超时清理必须等到本次命令进程与 Job active count 均归零；不能 Popen 后才写 PID，再把崩溃窗口当已回收。Create suspended 与 AssignJob 之间父进程死亡时，只能说未 Resume 因而没有该进程的 late add，不能说资源已回收；残留未知必须失败。PROC_THREAD_ATTRIBUTE_JOB_LIST 若被采用，先核 SDK/系统合同及实际 ABI，不凭名称授原子保证，也不扩大产品 argv 入口。

2026-10-15 官方合同核对：[UpdateProcThreadAttribute](https://learn.microsoft.com/en-us/windows/win32/api/processthreadsapi/nf-processthreadsapi-updateprocthreadattribute) 将 JOB_LIST 定义为按序分配给新进程的 Job handle 列表，属性值缓冲区必须活到 attribute list 销毁；支持 Windows 10 / Server 2016 及之后。该合同支持准备 STARTUPINFOEX 后在创建时指定 Job，不意味着之后账本写入/Flush 自动原子，也不保证所有进程创建失败路径无残留。[Job Objects](https://learn.microsoft.com/en-us/windows/win32/procthread/job-objects) 说明普通 CreateProcess 后代默认入 Job、breakaway flags 可改变此行为；WMI Win32_Process.Create 例外不在此默认承诺内，故不得称任意恶意账号的所有进程都受树约束。[JOBOBJECT_BASIC_PROCESS_ID_LIST](https://learn.microsoft.com/en-us/windows/win32/api/winnt/ns-winnt-jobobject_basic_process_id_list) 包括嵌套 child Jobs 的进程；必须完整返回 Assigned/Returned 一致，不能仅按 ActiveProcesses==1 猜剩下的是绑定父 PID。采纳创建时 JOB_LIST 与完整 PID 列表/持有父句柄复核；暂缓把它泛化为通用 runner；不适配仅 caller bool/计数授回收信用。没有执行本机 API 或声称原生通过。

## 完整候选的责任边界与实施停点

下方是待 root 全文及 fresh SPEC／不同 QUALITY 双审的完整 SOURCE 候选；完整 TEST 资产由相邻 `2026-10-15-windows-ci-positive-loopback-admin-tests.md` 单独冻结并以精确 hash 绑定。评审通过前只允许阅读及明确批准的 RAM 诊断，禁止落实际 TEST/SOURCE/CI 或启用豁免。

| 责任 | 必需的真实边界 |
| --- | --- |
| 完整 Get reader | 受保护候选代码；二进制 SID/uint32 Attributes；count≤4096；逐 SID 与数组 HeapFree 原件；崩溃/无效 ownership graph 为 unknown；不加载 Set export |
| Native storage | 创建时 protected owner/DACL；admin-only ledger；标准用户只读 manifest/receipt；独立固定写入槽；root/file 句柄和实际 volume/file ID；拒 reparse/hardlink/替换；读期间拒写；durable Flush |
| Native command | GetSystemDirectoryW；锁定工具文件身份/hash/PE 架构/版本；唯一 LoopbackExempt -a/-d -p=预绑定 SID；无 shell/PATH；suspended/Job/persist/Resume；真实回收 |
| Coordinator | 从 native 事实和受保护 ledger 恢复，不接受 State/JSON 授权；一次性 slot 消费；baseline/add/predelete/post 原件；保首错；foreign 差异不回滚；冲突 unknown 不猜 SID |
| Independent recovery | 同候选/run/job/session 的受保护原账本；不能扫描 user 目录；先排除晚命令；normal finally 与独立 always 都可调用同一窄清理；坏账本保持 unknown |

root 已锁定标准用户 payload 回收的独立 OS 接点：admin-only outer Job。下一片受信 workflow parent 在 created gate 之前将标准用户测试父进程加入并通过 OS 确认；不允许 breakaway。正常 finished 要求完整 Job PID 列表只有绑定父 PID，持有句柄确认相同 creationtime 且父仍活；异常先 TerminateJobObject 并确认完整列表为空，再窄清理。probe_finished JSON 不提供回收 authority，不新增句柄交接请求或通用 callback。outer Job/nested Job 的实际兼容性必须同 SHA 双 Windows 验证，失败 fail-closed。

已锁定的双 binding：实际 core `Manifest` 的 started_ms/deadline_ms 与 digest 不改；bootstrap 独立 domain、独立 digest、唯一 180s 时钟，只接受一次 profile_created。两次 fresh 完整 Get 稳定后才冻结新的 operation Manifest，其 60s 从唯一 add-intent 边界开始，probe_finished 只能绑定该 operation。prepared_ms 在 freeze 完成且账号仍不存在时记录，prepare／attach 不重置；operation 与 recovery 时钟各只有一个起点。没有第三客户端请求、伪造过去时间或延长既有窗口。

已核实际固定链：`windows_job.py:1231` 的 flags 为 SUSPENDED|UNICODE_ENVIRONMENT|EXTENDED_STARTUPINFO_PRESENT，无 CREATE_BREAKAWAY_FROM_JOB；当前 Job limits 无 breakaway flags。`_observe_positive_loopback_config` 在 `run_windows_appcontainer` 前/后产生只读 helper 子进程，但函数在返回前有界 wait/reap，并把未回收显式传播；下一片必须在 finished gate 前完成这些 helper 的停止/回收。Reviewer 的异步 WFP 观察启动在正控段之后，不能提前跨入此 gate。监听器是同标准用户父进程中的线程，不增加 Job PID。若实际新增或遗留任何自有 helper，必须先有界回收且保留原观测；不得排除这些 PID 或把 count>1 降格通过。

---
**Execution Mode:** serial（待双审）。STOP：本文不是实施授权；完整 TEST/SOURCE、原生只读门、下一片实际 consumer 接线分别验收，不得互相替代。

## Asset: `scripts/windows_positive_loopback_admin.py`

完整协调资产与下方 Native／Store／Job 一起实施，不可单独启用。

```python
"""One CI-owned positive SID coordinator; never a product permission broker."""
from __future__ import annotations

import hashlib
import json
import re
import time
import sys

from icode import windows_positive_loopback_policy as policy
from scripts.windows_positive_loopback_admin_native import Native
from scripts.windows_positive_loopback_admin_win32 import _release_owned


class AdminError(RuntimeError):
    pass


def _wire(value):
    return json.dumps(value, ensure_ascii=True, sort_keys=True,
                      separators=(",", ":"), allow_nan=False).encode("ascii")


BOOTSTRAP_DOMAIN = "icode_positive_bootstrap_v1"
OPERATION_DOMAIN = "icode_positive_operation_v1"


def _unique(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise AdminError("duplicate_key")
        result[key] = value
    return result


def _decode(wire):
    if type(wire) is not bytes or not 0 < len(wire) <= 4096:
        raise AdminError("request_size")
    try:
        return json.loads(wire.decode("utf-8"), object_pairs_hook=_unique,
                          parse_constant=lambda value: (_ for _ in ()).throw(AdminError("json_constant")))
    except (UnicodeError, ValueError, RecursionError) as exc:
        raise AdminError("request_json") from exc


def _bootstrap_expected(bootstrap):
    fields = {"schema", "domain", "repository", "source_sha", "run_id", "run_attempt",
              "job", "matrix", "session", "account_sid", "pid", "process_created",
              "positive_profile", "reviewer_profile", "positive_sid", "reviewer_sid",
              "nonce", "ipv4_port", "ipv6_port", "prepared_ms", "preparation_deadline_ms"}
    if type(bootstrap) is not dict or set(bootstrap) != fields:
        raise AdminError("bootstrap_schema")
    if (type(bootstrap["schema"]) is not int or bootstrap["schema"] != 1
            or bootstrap["domain"] != BOOTSTRAP_DOMAIN
            or bootstrap["repository"] != "ayukyo/icode"
            or bootstrap["job"] != "windows-reviewer-snapshot-probe"
            or bootstrap["matrix"] not in ("x64", "ARM64")):
        raise AdminError("bootstrap_schema")
    for key, pattern in (("source_sha", r"[0-9a-f]{40}"), ("run_id", r"[1-9][0-9]{0,19}"),
                         ("session", r"[0-9a-f]{32}"), ("nonce", r"[0-9a-f]{32}"),
                         ("positive_profile", r"icode-[0-9a-f]{32}"),
                         ("reviewer_profile", r"icode-[0-9a-f]{32}")):
        if type(bootstrap[key]) is not str or re.fullmatch(pattern, bootstrap[key]) is None:
            raise AdminError("bootstrap_text")
    for key, maximum in (("run_attempt", 0xFFFFFFFF), ("pid", 0xFFFFFFFF),
                         ("process_created", (1 << 64) - 1),
                         ("ipv4_port", 65535), ("ipv6_port", 65535)):
        if type(bootstrap[key]) is not int or not 1 <= bootstrap[key] <= maximum:
            raise AdminError("bootstrap_number")
    for key in ("prepared_ms", "preparation_deadline_ms"):
        if type(bootstrap[key]) is not int or not 0 <= bootstrap[key] < (1 << 63):
            raise AdminError("bootstrap_clock")
    if bootstrap["preparation_deadline_ms"] - bootstrap["prepared_ms"] != 180000:
        raise AdminError("bootstrap_clock")
    for key in ("account_sid", "positive_sid", "reviewer_sid"):
        policy.sid_bytes(bootstrap[key])
    if (not bootstrap["account_sid"].startswith("S-1-5-21-")
            or not bootstrap["positive_sid"].startswith("S-1-15-2-")
            or not bootstrap["reviewer_sid"].startswith("S-1-15-2-")
            or bootstrap["positive_sid"] == bootstrap["reviewer_sid"]
            or bootstrap["positive_profile"] == bootstrap["reviewer_profile"]):
        raise AdminError("bootstrap_identity")
    keys = ("session", "pid", "process_created", "positive_profile", "positive_sid",
            "reviewer_sid", "nonce", "ipv4_port", "ipv6_port")
    return dict(schema=1, domain=BOOTSTRAP_DOMAIN, kind="profile_created",
                binding=hashlib.sha256(_wire(bootstrap)).hexdigest(),
                **{key: bootstrap[key] for key in keys})


def encode_bootstrap_request(bootstrap):
    result = _wire(_bootstrap_expected(bootstrap))
    if len(result) > 4096:
        raise AdminError("request_size")
    return result


def validate_bootstrap_request(wire, bootstrap, now_ms):
    expected = _bootstrap_expected(bootstrap)
    if (type(now_ms) is not int
            or not bootstrap["prepared_ms"] <= now_ms < bootstrap["preparation_deadline_ms"]):
        raise AdminError("bootstrap_window")
    actual = _decode(wire)
    if (type(actual) is not dict or set(actual) != set(expected)
            or any(type(actual[key]) is not type(value) or actual[key] != value
                   for key, value in expected.items())):
        raise AdminError("bootstrap_binding")
    return "profile_created"


def encode_operation_request(manifest, session):
    request = json.loads(policy.encode_request(manifest, "probe_finished"))
    wire = _wire(dict(schema=1, domain=OPERATION_DOMAIN, session=session, request=request))
    if len(wire) > 4096:
        raise AdminError("request_size")
    return wire


def validate_operation_request(wire, manifest, session, now_ms):
    value = _decode(wire)
    if (type(value) is not dict or set(value) != {"schema", "domain", "session", "request"}
            or type(value["schema"]) is not int or value["schema"] != 1
            or type(value["domain"]) is not str or value["domain"] != OPERATION_DOMAIN
            or type(value["session"]) is not str or value["session"] != session
            or type(value["request"]) is not dict):
        raise AdminError("operation_binding")
    return policy.validate_request(_wire(value["request"]), manifest,
                                   "probe_finished", now_ms)


def _mapping(raw):
    expected = {"schema", "entries", "api_code", "complete", "sid_attempted",
                "sid_freed", "array_freed", "library_freed", "process_reaped"}
    if type(raw) is not dict or set(raw) != expected or type(raw["schema"]) is not int or raw["schema"] != 1:
        raise AdminError("get_schema")
    if (type(raw["api_code"]) is not int or raw["api_code"] != 0
            or any(raw[key] is not True for key in (
                "complete", "array_freed", "library_freed", "process_reaped"))
            or type(raw["entries"]) is not list or len(raw["entries"]) > 4096
            or type(raw["sid_attempted"]) is not int or type(raw["sid_freed"]) is not int):
        raise AdminError("get_unverified")
    if raw["sid_attempted"] != len(raw["entries"]) or raw["sid_freed"] != len(raw["entries"]):
        raise AdminError("get_release")
    result = {}
    for item in raw["entries"]:
        if type(item) is not list or len(item) != 2:
            raise AdminError("get_entry")
        sid, attributes = item
        binary = policy.sid_bytes(sid)
        if binary in result or type(attributes) is not int or not 0 <= attributes <= 0xFFFFFFFF:
            raise AdminError("get_identity")
        result[binary] = attributes
    return result


class Admin:
    """Native owns all authority. A core State is never accepted by this API."""
    def __init__(self, store):
        self.native = Native()
        self.store = self.native.reopen(store)
        self.data = self.store.data

    @classmethod
    def freeze_before_user(cls, trusted_context, account_name):
        return Native().freeze(trusted_context, account_name)

    @classmethod
    def prepare(cls, frozen_root, account_sid):
        # Only the trusted workflow parent calls this, before user launch.
        # Native validates the administrator token, candidate context, paths,
        # descriptors, derived identities and fixed tool before returning.
        native = Native()
        store = native.prepare(frozen_root, account_sid)
        result = cls.__new__(cls)
        result.native, result.store, result.data = native, store, store.data
        return result

    def attach_parent(self, pid):
        if self.data["phase"] != "prepared":
            raise AdminError("parent_phase")
        try:
            self.native.attach_parent(self.store, pid)
        except Exception:
            self._failure("parent_failed")
            raise AdminError("parent_failed") from None
        # PID, creation time, token user and Job membership came from handles.
        self.data["phase"] = "bound"
        self.store.flush()
        self.native.publish_manifest(self.store)

    def _failure(self, code):
        allowed = {"created_request", "get_failed", "preexisting", "baseline_delta",
                   "add_failed", "add_delta", "deadline", "parent_failed",
                   "finished_request", "foreign_delta", "owner_conflict",
                   "cleanup_failed", "ledger_failed"}
        if code not in allowed:
            code = "ledger_failed"
        if self.data["first_error"] is None:
            self.data["first_error"] = code
        self.data["exact_restoration"] = False
        self.store.flush()

    def _read(self, name):
        raw = self.native.full_get(self.store)
        value = _mapping(raw)
        self.data["observations"][name] = raw
        self.store.flush()
        return value

    def _request(self, kind):
        self.native.verify_parent(self.store)
        wire = self.native.consume_request(self.store, kind)
        if kind == "profile_created":
            bootstrap = self.native.bootstrap(self.store)
            validate_bootstrap_request(wire, bootstrap, self.native.now_ms())
            return bootstrap
        if kind != "probe_finished":
            raise AdminError("request_kind")
        manifest = self.native.manifest(self.store)
        validate_operation_request(wire, manifest, self.data["session"], self.native.now_ms())
        # The native layer has durably consumed this one fixed slot before
        # returning its bytes; repeating a valid JSON cannot replay an operation.
        return manifest

    def created(self):
        if self.data["phase"] != "bound":
            raise AdminError("created_phase")
        try:
            bootstrap = self._request("profile_created")
        except Exception:
            self._failure("created_request")
            raise AdminError("created_request") from None
        try:
            first, second = self._read("baseline_first"), self._read("baseline")
        except Exception:
            self._failure("get_failed")
            raise AdminError("get_failed") from None
        positive = policy.sid_bytes(bootstrap["positive_sid"])
        reviewer = policy.sid_bytes(bootstrap["reviewer_sid"])
        if first != second:
            self._failure("baseline_delta")
            raise AdminError("baseline_delta")
        if positive in second or reviewer in second:
            self._failure("preexisting")
            raise AdminError("preexisting")
        try:
            manifest = self.native.freeze_operation(self.store)
        except Exception:
            self._failure("ledger_failed")
            raise AdminError("ledger_failed") from None
        self.data.update(phase="add_intent", owned_intent=True,
                         intent_ms=manifest.started_ms, target_attributes=None)
        # This durable write, including baseline and preallocated SID, is the
        # prerequisite for Native.command to create any add process.
        self.store.flush()
        try:
            command = self.native.command(self.store, "add")
        except Exception:
            self._failure("add_failed")
            raise AdminError("add_failed") from None
        try:
            after = self._read("after_add")
        except Exception:
            self._failure("get_failed")
            raise AdminError("get_failed") from None
        attributes = after.pop(positive, None)
        self.data["target_attributes"] = attributes
        self.store.flush()
        if not command["reaped"] or command["timed_out"] or command["exit_code"] != 0:
            self._failure("add_failed")
            raise AdminError("add_failed")
        if attributes is None or after != second or reviewer in after:
            self._failure("add_delta")
            raise AdminError("add_delta")
        if self.native.now_ms() >= manifest.deadline_ms:
            self._failure("deadline")
            raise AdminError("deadline")
        self.data.update(phase="added", add_verified=True)
        self.store.flush()
        self.native.publish(self.store, "add", {
            "schema": 1, "binding": manifest.digest, "domain": OPERATION_DOMAIN,
            "stage": "added", "add_verified": True,
            "pre_absent": True, "reviewer_unexempt": True,
            "first_error": self.data["first_error"],
            "evidence_sha256": hashlib.sha256(_wire(self.data["observations"]["after_add"])).hexdigest(),
            "native_restoration_verified": None,
        })

    def finished(self):
        try:
            self._request("probe_finished")
        except Exception:
            self._failure("finished_request")
            raise AdminError("finished_request") from None
        # JSON never supplies Job/nonce/token authority. Native checks the exact
        # live parent PID list in the admin-held outer Job before normal cleanup.
        if not self.native.parent_only(self.store):
            self._failure("parent_failed")
            self.cleanup(abnormal=True)
            raise AdminError("parent_failed")
        return self.cleanup(abnormal=False)

    def cleanup(self, *, abnormal):
        already_completed = self.data["phase"] == "cleaned"
        try:
            self.native.verify_store(self.store)
            if self.data["owned_intent"]:
                # Fresh recovery observations are a new validation pass, not a
                # continuation of a previously published success. Preserve its
                # original completion clock but durably withdraw success now.
                self.data.update(phase="cleanup_intent", exact_restoration=False,
                                 delete_verified=False, others_preserved=False)
                self.store.flush()
            self.native.reap_commands(self.store)
            if abnormal:
                self.native.stop_parent_job(self.store)
            elif not self.native.parent_only(self.store):
                raise AdminError("parent_failed")
            if not self.data["owned_intent"]:
                bootstrap = self.native.bootstrap(self.store)
                return self.native.publish(self.store, "cleanup", {
                    "schema": 1,
                    "binding": hashlib.sha256(_wire(bootstrap)).hexdigest(),
                    "domain": BOOTSTRAP_DOMAIN,
                    "stage": "not_owned", "delete_verified": None,
                    "native_restoration_verified": None,
                })
            before = self._read("pre_delete")
            manifest = self.native.manifest(self.store)
            if not already_completed and self.native.now_ms() >= manifest.deadline_ms:
                self._failure("deadline")
            positive = policy.sid_bytes(manifest.positive_sid)
            reviewer = policy.sid_bytes(manifest.reviewer_sid)
            baseline = _mapping(self.data["observations"]["baseline"])
            expected = dict(before)
            target = expected.pop(positive, None)
            if expected != baseline or reviewer in before:
                self._failure("foreign_delta")
            known = self.data["target_attributes"]
            if target is not None and not self.native.has_add_attempt(self.store):
                self._failure("owner_conflict")
                raise AdminError("owner_conflict")
            if target is not None and known is not None and target != known:
                self._failure("owner_conflict")
                raise AdminError("owner_conflict")
            self.data["phase"] = "cleanup_intent"
            self.store.flush()
            if target is not None:
                command = self.native.command(self.store, "delete")
                if not command["reaped"] or command["timed_out"] or command["exit_code"] != 0:
                    self._failure("cleanup_failed")
                    raise AdminError("cleanup_failed")
            after = self._read("post_delete")
            if after != expected or positive in after or reviewer in after:
                self._failure("cleanup_failed")
                raise AdminError("cleanup_failed")
            completed = self.native.now_ms()
            if not already_completed and completed >= manifest.deadline_ms:
                self._failure("deadline")
            exact = after == baseline and self.data["first_error"] is None
            self.data.update(phase="cleaned", delete_verified=True,
                             others_preserved=True, exact_restoration=exact)
            if not already_completed:
                self.data["operation_completed_ms"] = completed
            self.store.flush()
            return self.native.publish(self.store, "cleanup", {
                "schema": 1, "binding": manifest.digest, "domain": OPERATION_DOMAIN,
                "stage": "cleaned" if exact else "unknown",
                "delete_verified": True, "others_preserved": True,
                "reviewer_unexempt": True, "first_error": self.data["first_error"],
                "cleanup_error": self.data["cleanup_error"],
                "evidence_sha256": hashlib.sha256(_wire(self.data["observations"]["post_delete"])).hexdigest(),
                "native_restoration_verified": exact,
            })
        except Exception:
            self.data["cleanup_error"] = "cleanup_failed"
            self._failure("cleanup_failed")
            raise AdminError("cleanup_failed") from None

    def serve(self):
        stage = "created_request"
        try:
            self.native.wait_request(self.store, "profile_created", 180000)
            stage = "ledger_failed"
            self.created()
            stage = "finished_request"
            manifest = self.native.manifest(self.store)
            self.native.wait_request(self.store, "probe_finished",
                                     max(0, manifest.deadline_ms - self.native.now_ms()))
            return self.finished()
        except Exception:
            # Includes wait/read/size errors and freeze/publish exceptions
            # outside the narrower helpers. A nonzero process exit cannot
            # substitute for truthful durable first-error/cleanup receipts.
            _release_owned(sys.exception(), lambda: self._failure(stage))
            raise
        finally:
            _release_owned(sys.exception(),
                lambda: self.cleanup(abnormal=True) if self.data['phase'] != 'cleaned' else None,
            )

    @classmethod
    def recover(cls, trusted_root):
        # Invoked by a separate workflow always step from its trusted exact root
        # record. Reopen verifies ACL/identity/context; never scan for a ledger.
        result = cls.__new__(cls)
        result.native = Native()
        # Includes reopen/validation, not a fresh 30s for every phase.
        result.native.recovery_deadline = result.native.now_ms() + 30000
        result.store = result.native.reopen(trusted_root)
        result.data = result.store.data
        try:
            return result.cleanup(abnormal=True)
        finally:
            _release_owned(sys.exception(),
                lambda: result.store.close(),
            )
```

## Asset: `scripts/windows_positive_loopback_full_get.py`

仅允许由 admin adapter 的固定 worker 分支启动，stdout 必须指向 admin-only 原件句柄，不得在 workflow 直接运行并公开输出。父进程真实确认 worker 回收后才补 process_reaped；worker 自己不提供该信用。

```python
"""Bounded complete Get worker. Its output is private evidence, never a notice."""
from __future__ import annotations

import ctypes
from ctypes import wintypes
import json
from pathlib import Path
import sys


class SID_AND_ATTRIBUTES(ctypes.Structure):
    _fields_ = [("Sid", ctypes.c_void_p), ("Attributes", ctypes.c_uint32)]


def _bind(library, name, result, arguments):
    function = getattr(library, name)
    function.restype = result
    function.argtypes = arguments
    return function


def _load():
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    _bind(kernel, "FreeLibrary", wintypes.BOOL, [wintypes.HMODULE])
    system_directory = _bind(kernel, "GetSystemDirectoryW", wintypes.UINT,
                             [wintypes.LPWSTR, wintypes.UINT])
    buffer = ctypes.create_unicode_buffer(32768)
    length = system_directory(buffer, len(buffer))
    if not 0 < length < len(buffer):
        raise OSError("system_directory")
    system = Path(buffer.value)
    if not system.is_absolute() or system.name.casefold() != "system32":
        raise OSError("system_directory")
    advapi = ctypes.WinDLL(str(system / "advapi32.dll"), use_last_error=True, winmode=0x800)
    library = ctypes.WinDLL(str(system / "FirewallAPI.dll"), use_last_error=True, winmode=0x800)
    try:
        _bind(kernel, "GetProcessHeap", ctypes.c_void_p, [])
        _bind(kernel, "HeapFree", wintypes.BOOL,
              [ctypes.c_void_p, wintypes.DWORD, ctypes.c_void_p])
        _bind(advapi, "IsValidSid", wintypes.BOOL, [ctypes.c_void_p])
        _bind(advapi, "GetLengthSid", wintypes.DWORD, [ctypes.c_void_p])
        query = _bind(library, "NetworkIsolationGetAppContainerConfig", wintypes.DWORD,
                      [ctypes.POINTER(wintypes.DWORD), ctypes.POINTER(ctypes.c_void_p)])
    except BaseException as primary:
        try:
            if not kernel.FreeLibrary(library._handle):
                raise OSError("free_library")
        except BaseException as error:
            primary.add_note(f"cleanup_unknown: {error!r}")
        raise
    return kernel, advapi, library, query


def _text_sid(value):
    if (type(value) is not bytes or len(value) < 12 or value[0] != 1
            or not 1 <= value[1] <= 15 or len(value) != 8 + 4 * value[1]):
        raise ValueError("invalid_sid")
    authority = int.from_bytes(value[2:8], "big")
    parts = [int.from_bytes(value[index:index + 4], "little")
             for index in range(8, len(value), 4)]
    return "S-1-" + str(authority) + "-" + "-".join(map(str, parts))


def collect():
    result = dict(schema=1, entries=[], api_code=None, complete=False,
                  sid_attempted=0, sid_freed=0, array_freed=False,
                  library_freed=False, process_reaped=None)
    kernel = advapi = library = query = None
    count = wintypes.DWORD()
    array = ctypes.c_void_p()
    pointers = []
    graph_safe = False
    valid = False
    try:
        kernel, advapi, library, query = _load()
        result["api_code"] = int(query(ctypes.byref(count), ctypes.byref(array)))
        if result["api_code"] != 0 or count.value > 4096 or (count.value and not array.value):
            raise ValueError("query_incomplete")
        if count.value:
            entries = ctypes.cast(array, ctypes.POINTER(SID_AND_ATTRIBUTES))
            for index in range(count.value):
                pointer = entries[index].Sid
                if not pointer or pointer == array.value or pointer in pointers:
                    raise ValueError("unsafe_ownership_graph")
                pointers.append(pointer)
                if not advapi.IsValidSid(pointer):
                    raise ValueError("invalid_sid")
            # Only a complete, nonaliased ownership graph may be individually
            # freed. Invalid pointers may crash this worker; parent treats that
            # as incomplete and never consumes a partial snapshot.
        graph_safe = True
        identities = set()
        for index, pointer in enumerate(pointers):
            length = int(advapi.GetLengthSid(pointer))
            if not 12 <= length <= 68:
                raise ValueError("invalid_sid_length")
            binary = ctypes.string_at(pointer, length)
            text = _text_sid(binary)
            if binary in identities:
                raise ValueError("duplicate_sid")
            identities.add(binary)
            attributes = int(entries[index].Attributes)
            result["entries"].append([text, attributes])
        valid = True
    except Exception:
        valid = False
    finally:
        # One failed HeapFree must not skip any other proven owned pointer.
        if graph_safe:
            try:
                heap = kernel.GetProcessHeap()
            except BaseException:
                heap = None
            if heap:
                for pointer in pointers:
                    result["sid_attempted"] += 1
                    try:
                        if kernel.HeapFree(heap, 0, pointer):
                            result["sid_freed"] += 1
                    except BaseException:
                        valid = False
                try:
                    result["array_freed"] = not array.value or bool(kernel.HeapFree(heap, 0, array))
                except BaseException:
                    valid = False
        if library is not None:
            try:
                result["library_freed"] = bool(kernel.FreeLibrary(library._handle))
            except BaseException:
                valid = False
        result["complete"] = bool(valid and graph_safe and result["array_freed"]
            and result["library_freed"] and result["sid_attempted"] == count.value
            and result["sid_freed"] == count.value and len(result["entries"]) == count.value)
    return result


def main():
    if sys.platform != "win32" or sys.argv[1:] != ["--full-get"]:
        return 2
    result = collect()
    wire = json.dumps(result, ensure_ascii=True, sort_keys=True,
                      separators=(",", ":"), allow_nan=False).encode("ascii")
    if len(wire) > 1048576:
        return 3
    sys.stdout.buffer.write(wire + b"\n")
    sys.stdout.buffer.flush()
    return 0 if result["complete"] else 4


if __name__ == "__main__":
    raise SystemExit(main())
```

## Asset: `scripts/windows_positive_loopback_admin_win32.py`

专用 adapter 的 Win32 ABI；不提供命令行入口或可由请求指定的 API 名称。

```python
from __future__ import annotations

import ctypes as c
from ctypes import wintypes as t
from pathlib import Path
import os
import struct
import sys


class Failure(RuntimeError):
    pass


class SA(c.Structure):
    _fields_ = [("length", t.DWORD), ("descriptor", c.c_void_p), ("inherit", t.BOOL)]


class FILE_INFO(c.Structure):
    _fields_ = [("attributes", t.DWORD), ("created", t.FILETIME),
                ("accessed", t.FILETIME), ("written", t.FILETIME),
                ("volume", t.DWORD), ("size_high", t.DWORD), ("size_low", t.DWORD),
                ("links", t.DWORD), ("index_high", t.DWORD), ("index_low", t.DWORD)]


class STARTUP(c.Structure):
    _fields_ = [("cb", t.DWORD), ("reserved", t.LPWSTR), ("desktop", t.LPWSTR),
                ("title", t.LPWSTR), ("x", t.DWORD), ("y", t.DWORD),
                ("x_size", t.DWORD), ("y_size", t.DWORD), ("x_count", t.DWORD),
                ("y_count", t.DWORD), ("fill", t.DWORD), ("flags", t.DWORD),
                ("show", t.WORD), ("reserved_bytes", t.WORD),
                ("reserved_pointer", c.c_void_p), ("stdin", t.HANDLE),
                ("stdout", t.HANDLE), ("stderr", t.HANDLE)]


class STARTUP_EX(c.Structure):
    _fields_ = [("startup", STARTUP), ("attributes", c.c_void_p)]


class PROCESS(c.Structure):
    _fields_ = [("process", t.HANDLE), ("thread", t.HANDLE),
                ("pid", t.DWORD), ("tid", t.DWORD)]


class IO(c.Structure):
    _fields_ = [(name, c.c_ulonglong) for name in (
        "read_ops", "write_ops", "other_ops", "read_bytes", "write_bytes", "other_bytes")]


class LIMITS(c.Structure):
    _fields_ = [("process_time", c.c_longlong), ("job_time", c.c_longlong),
                ("flags", t.DWORD), ("minimum", c.c_size_t), ("maximum", c.c_size_t),
                ("active_limit", t.DWORD), ("affinity", c.c_size_t),
                ("priority", t.DWORD), ("scheduling", t.DWORD)]


class EXTENDED_LIMITS(c.Structure):
    _fields_ = [("basic", LIMITS), ("io", IO), ("process_memory", c.c_size_t),
                ("job_memory", c.c_size_t), ("peak_process", c.c_size_t),
                ("peak_job", c.c_size_t)]


class TOKEN_USER(c.Structure):
    _fields_ = [("sid", c.c_void_p), ("attributes", t.DWORD)]


class GENERIC_MAPPING(c.Structure):
    _fields_ = [("read", t.DWORD), ("write", t.DWORD),
                ("execute", t.DWORD), ("all", t.DWORD)]


def checked(value, stage):
    if not value:
        raise Failure(stage)
    return value


def _release_owned(primary, *actions):
    """Attempt each owned release; never replace an active body exception."""
    errors = []
    for action in actions:
        try:
            action()
        except BaseException as error:
            errors.append(error)
    if errors:
        failure = primary if primary is not None else errors[0]
        for error in errors:
            failure.add_note(f"cleanup_unknown: {error!r}")
        if primary is None:
            raise failure


class Win32:
    def __init__(self):
        if sys.platform != "win32" or sys.version_info < (3, 12):
            raise Failure("unsupported_host")
        self.k = c.WinDLL("kernel32", use_last_error=True)
        self.k.GetSystemDirectoryW.restype = t.UINT
        self.k.GetSystemDirectoryW.argtypes = [t.LPWSTR, t.UINT]
        system = c.create_unicode_buffer(32768)
        length = self.k.GetSystemDirectoryW(system, len(system))
        if not 0 < length < len(system) or Path(system.value).name.casefold() != "system32":
            raise Failure("system_directory")
        self.system_directory = Path(system.value)
        self.a = c.WinDLL(str(self.system_directory / "advapi32.dll"), use_last_error=True, winmode=0x800)
        self.u = c.WinDLL(str(self.system_directory / "userenv.dll"), use_last_error=True, winmode=0x800)
        specs = {
            "k": {
                "CloseHandle": (t.BOOL, [t.HANDLE]),
                "LocalFree": (c.c_void_p, [c.c_void_p]),
                "GetCurrentProcess": (t.HANDLE, []),
                "GetCurrentProcessId": (t.DWORD, []),
                "GetModuleHandleW": (t.HANDLE, [t.LPCWSTR]),
                "GetModuleFileNameW": (t.DWORD, [t.HANDLE, t.LPWSTR, t.DWORD]),
                "K32EnumProcessModules": (t.BOOL, [t.HANDLE, c.POINTER(t.HANDLE), t.DWORD, c.POINTER(t.DWORD)]),
                "GetFileAttributesW": (t.DWORD, [t.LPCWSTR]),
                "SetFileAttributesW": (t.BOOL, [t.LPCWSTR, t.DWORD]),
                "MoveFileExW": (t.BOOL, [t.LPCWSTR, t.LPCWSTR, t.DWORD]),
                "GetSystemDirectoryW": (t.UINT, [t.LPWSTR, t.UINT]),
                "GetTempPathW": (t.DWORD, [t.DWORD, t.LPWSTR]),
                "CreateDirectoryW": (t.BOOL, [t.LPCWSTR, c.POINTER(SA)]),
                "CreateFileW": (t.HANDLE, [t.LPCWSTR, t.DWORD, t.DWORD, c.POINTER(SA), t.DWORD, t.DWORD, t.HANDLE]),
                "GetFileInformationByHandle": (t.BOOL, [t.HANDLE, c.POINTER(FILE_INFO)]),
                "GetFinalPathNameByHandleW": (t.DWORD, [t.HANDLE, t.LPWSTR, t.DWORD, t.DWORD]),
                "ReadFile": (t.BOOL, [t.HANDLE, c.c_void_p, t.DWORD, c.POINTER(t.DWORD), c.c_void_p]),
                "WriteFile": (t.BOOL, [t.HANDLE, c.c_void_p, t.DWORD, c.POINTER(t.DWORD), c.c_void_p]),
                "SetFilePointerEx": (t.BOOL, [t.HANDLE, c.c_longlong, c.POINTER(c.c_longlong), t.DWORD]),
                "SetEndOfFile": (t.BOOL, [t.HANDLE]),
                "FlushFileBuffers": (t.BOOL, [t.HANDLE]),
                "CreateJobObjectW": (t.HANDLE, [c.POINTER(SA), t.LPCWSTR]),
                "OpenJobObjectW": (t.HANDLE, [t.DWORD, t.BOOL, t.LPCWSTR]),
                "SetInformationJobObject": (t.BOOL, [t.HANDLE, c.c_int, c.c_void_p, t.DWORD]),
                "QueryInformationJobObject": (t.BOOL, [t.HANDLE, c.c_int, c.c_void_p, t.DWORD, c.POINTER(t.DWORD)]),
                "AssignProcessToJobObject": (t.BOOL, [t.HANDLE, t.HANDLE]),
                "IsProcessInJob": (t.BOOL, [t.HANDLE, t.HANDLE, c.POINTER(t.BOOL)]),
                "TerminateJobObject": (t.BOOL, [t.HANDLE, t.UINT]),
                "TerminateProcess": (t.BOOL, [t.HANDLE, t.UINT]),
                "OpenProcess": (t.HANDLE, [t.DWORD, t.BOOL, t.DWORD]),
                "GetProcessTimes": (t.BOOL, [t.HANDLE, c.POINTER(t.FILETIME), c.POINTER(t.FILETIME), c.POINTER(t.FILETIME), c.POINTER(t.FILETIME)]),
                "GetExitCodeProcess": (t.BOOL, [t.HANDLE, c.POINTER(t.DWORD)]),
                "WaitForSingleObject": (t.DWORD, [t.HANDLE, t.DWORD]),
                "ResumeThread": (t.DWORD, [t.HANDLE]),
                "CreateProcessW": (t.BOOL, [t.LPCWSTR, t.LPWSTR, c.c_void_p, c.c_void_p, t.BOOL, t.DWORD, c.c_void_p, t.LPCWSTR, c.POINTER(STARTUP_EX), c.POINTER(PROCESS)]),
                "InitializeProcThreadAttributeList": (t.BOOL, [c.c_void_p, t.DWORD, t.DWORD, c.POINTER(c.c_size_t)]),
                "UpdateProcThreadAttribute": (t.BOOL, [c.c_void_p, t.DWORD, c.c_size_t, c.c_void_p, c.c_size_t, c.c_void_p, c.POINTER(c.c_size_t)]),
                "DeleteProcThreadAttributeList": (None, [c.c_void_p]),
            },
            "a": {
                "ConvertStringSidToSidW": (t.BOOL, [t.LPCWSTR, c.POINTER(c.c_void_p)]),
                "CheckTokenMembership": (t.BOOL, [t.HANDLE, c.c_void_p, c.POINTER(t.BOOL)]),
                "ConvertStringSecurityDescriptorToSecurityDescriptorW": (t.BOOL, [t.LPCWSTR, t.DWORD, c.POINTER(c.c_void_p), c.POINTER(t.DWORD)]),
                "GetSecurityInfo": (t.DWORD, [t.HANDLE, c.c_int, t.DWORD, c.POINTER(c.c_void_p), c.POINTER(c.c_void_p), c.POINTER(c.c_void_p), c.POINTER(c.c_void_p), c.POINTER(c.c_void_p)]),
                "SetSecurityInfo": (t.DWORD, [t.HANDLE, c.c_int, t.DWORD, c.c_void_p, c.c_void_p, c.c_void_p, c.c_void_p]),
                "GetSecurityDescriptorDacl": (t.BOOL, [c.c_void_p, c.POINTER(t.BOOL), c.POINTER(c.c_void_p), c.POINTER(t.BOOL)]),
                "GetSecurityDescriptorOwner": (t.BOOL, [c.c_void_p, c.POINTER(c.c_void_p), c.POINTER(t.BOOL)]),
                "GetSecurityDescriptorControl": (t.BOOL, [c.c_void_p, c.POINTER(t.WORD), c.POINTER(t.DWORD)]),
                "IsValidSid": (t.BOOL, [c.c_void_p]),
                "GetLengthSid": (t.DWORD, [c.c_void_p]),
                "ConvertSidToStringSidW": (t.BOOL, [c.c_void_p, c.POINTER(t.LPWSTR)]),
                "FreeSid": (c.c_void_p, [c.c_void_p]),
                "OpenProcessToken": (t.BOOL, [t.HANDLE, t.DWORD, c.POINTER(t.HANDLE)]),
                "GetTokenInformation": (t.BOOL, [t.HANDLE, c.c_int, c.c_void_p, t.DWORD, c.POINTER(t.DWORD)]),
                "DuplicateToken": (t.BOOL, [t.HANDLE, c.c_int, c.POINTER(t.HANDLE)]),
                "ImpersonateLoggedOnUser": (t.BOOL, [t.HANDLE]),
                "RevertToSelf": (t.BOOL, []),
                "LookupAccountNameW": (t.BOOL, [t.LPCWSTR, t.LPCWSTR, c.c_void_p, c.POINTER(t.DWORD), t.LPWSTR, c.POINTER(t.DWORD), c.POINTER(t.DWORD)]),
                "LookupAccountSidW": (t.BOOL, [t.LPCWSTR, c.c_void_p, t.LPWSTR, c.POINTER(t.DWORD), t.LPWSTR, c.POINTER(t.DWORD), c.POINTER(t.DWORD)]),
                "AccessCheck": (t.BOOL, [c.c_void_p, t.HANDLE, t.DWORD, c.POINTER(GENERIC_MAPPING), c.c_void_p, c.POINTER(t.DWORD), c.POINTER(t.DWORD), c.POINTER(t.BOOL)]),
            },
            "u": {"DeriveAppContainerSidFromAppContainerName": (c.c_long, [t.LPCWSTR, c.POINTER(c.c_void_p)])},
        }
        for module, names in specs.items():
            for name, (result, arguments) in names.items():
                function = getattr(getattr(self, module), name)
                function.restype, function.argtypes = result, arguments

    def close(self, handle):
        if handle:
            checked(self.k.CloseHandle(handle), "close_handle")

    def descriptor(self, text):
        pointer = c.c_void_p()
        checked(self.a.ConvertStringSecurityDescriptorToSecurityDescriptorW(
            text, 1, c.byref(pointer), None), "descriptor")
        return pointer

    def security(self, descriptor):
        present, defaulted, owner_defaulted = t.BOOL(), t.BOOL(), t.BOOL()
        dacl, owner = c.c_void_p(), c.c_void_p()
        control, revision = t.WORD(), t.DWORD()
        checked(self.a.GetSecurityDescriptorDacl(descriptor, c.byref(present), c.byref(dacl), c.byref(defaulted)), "descriptor_dacl")
        checked(self.a.GetSecurityDescriptorOwner(descriptor, c.byref(owner), c.byref(owner_defaulted)), "descriptor_owner")
        checked(self.a.GetSecurityDescriptorControl(descriptor, c.byref(control), c.byref(revision)), "descriptor_control")
        if not present.value or defaulted.value or not dacl.value or not owner.value:
            raise Failure("descriptor_shape")
        size = struct.unpack("<BBHHH", c.string_at(dacl, 8))[2]
        if size < 8 or not self.a.IsValidSid(owner):
            raise Failure("descriptor_shape")
        return c.string_at(owner, self.a.GetLengthSid(owner)), c.string_at(dacl, size), bool(control.value & 0x1000)

    def verify_security(self, handle, expected_sddl, *, object_type=1):
        descriptor, expected = c.c_void_p(), self.descriptor(expected_sddl)
        try:
            if self.a.GetSecurityInfo(handle, object_type, 5, None, None, None, None, c.byref(descriptor)) != 0:
                raise Failure("get_security")
            actual, wanted = self.security(descriptor), self.security(expected)
            if actual != wanted or not actual[2]:
                raise Failure("security_changed")
        finally:
            _release_owned(sys.exception(),
                *(lambda pointer=pointer: checked(not self.k.LocalFree(pointer), "free_descriptor") for pointer in (descriptor, expected) if pointer.value),
            )

    def info(self, handle, *, directory=False):
        info = FILE_INFO()
        checked(self.k.GetFileInformationByHandle(handle, c.byref(info)), "file_information")
        if bool(info.attributes & 0x10) != directory or info.attributes & 0x400 or (not directory and info.links != 1):
            raise Failure("file_shape")
        return (int(info.volume), (int(info.index_high) << 32) | int(info.index_low))

    def open_file(self, path, sddl, *, create=False, write=False, directory=False, inherit=False):
        descriptor = self.descriptor(sddl)
        handle = None
        transferred = False
        try:
            attributes = SA(c.sizeof(SA), descriptor, inherit)
            access = 0x00020080 | (0 if directory else 0x80000000) | (0x40000000 if write else 0)
            if directory and write:
                access |= 0x00040000
            handle = self.k.CreateFileW(str(path), access, 3 if directory else 1,
                c.byref(attributes), 1 if create else 3,
                0x00200000 | (0x02000000 if directory else 0), None)
            if handle in (None, c.c_void_p(-1).value):
                handle = None
                raise Failure("open_file", c.get_last_error())
            identity = self.info(handle, directory=directory)
            if not identity[1]:
                raise Failure("file_identity")
            self.verify_security(handle, sddl)
            final = c.create_unicode_buffer(32768)
            length = self.k.GetFinalPathNameByHandleW(handle, final, len(final), 0)
            checked(0 < length < len(final), "final_path")
            observed = final.value[4:] if final.value.startswith("\\\\?\\") else final.value
            if os.path.normcase(observed) != os.path.normcase(str(path)):
                raise Failure("file_namespace")
            # Transfer only after descriptor cleanup succeeds. A failure in a
            # return's finally must not strand a handle the caller never got.
            allocation, descriptor = descriptor, None
            _release_owned(None, lambda: checked(not self.k.LocalFree(allocation), "free_descriptor"))
            result = (handle, identity)
            transferred = True
            return result
        finally:
            _release_owned(sys.exception(),
                lambda: checked(not self.k.LocalFree(descriptor), "free_descriptor") if descriptor is not None else None,
                lambda: self.close(handle) if handle and not transferred else None,
            )

    def create_directory(self, path, sddl):
        descriptor = self.descriptor(sddl)
        try:
            attributes = SA(c.sizeof(SA), descriptor, False)
            checked(self.k.CreateDirectoryW(str(path), c.byref(attributes)), "create_directory")
        finally:
            _release_owned(sys.exception(),
                lambda: checked(not self.k.LocalFree(descriptor), 'free_descriptor'),
            )

    def set_root_dacl(self, handle, old_sddl, new_sddl):
        self.verify_security(handle, old_sddl)
        descriptor = self.descriptor(new_sddl)
        try:
            dacl, present, defaulted = c.c_void_p(), t.BOOL(), t.BOOL()
            checked(self.a.GetSecurityDescriptorDacl(descriptor, c.byref(present), c.byref(dacl), c.byref(defaulted)), "root_dacl")
            if not present.value or defaulted.value or not dacl.value:
                raise Failure("root_dacl")
            if self.a.SetSecurityInfo(handle, 1, 0x80000004, None, None, dacl, None) != 0:
                raise Failure("root_dacl")
            self.verify_security(handle, new_sddl)
        finally:
            _release_owned(sys.exception(),
                lambda: checked(not self.k.LocalFree(descriptor), 'free_descriptor'),
            )

    def pin_ancestor(self, path, *, observe_only=False):
        handle = self.k.CreateFileW(str(path), 0x00020080, 3, None, 3,
                                    0x02200000, None)
        if handle in (None, c.c_void_p(-1).value):
            raise Failure("pin_ancestor")
        try:
            self.info(handle, directory=True)
            if not observe_only:
                self.verify_ancestor(handle)
            return handle
        except BaseException:
            _release_owned(sys.exception(), lambda: self.close(handle))
            raise

    def read(self, handle, limit):
        checked(self.k.SetFilePointerEx(handle, 0, None, 0), "seek")
        data, count = c.create_string_buffer(limit + 1), t.DWORD()
        checked(self.k.ReadFile(handle, data, limit + 1, c.byref(count), None), "read")
        if count.value > limit:
            raise Failure("file_limit")
        return data.raw[:count.value]

    def write(self, handle, data):
        checked(self.k.SetFilePointerEx(handle, 0, None, 0), "seek")
        buffer, count = c.create_string_buffer(data), t.DWORD()
        checked(self.k.WriteFile(handle, buffer, len(data), c.byref(count), None), "write")
        if count.value != len(data):
            raise Failure("short_write")
        checked(self.k.SetEndOfFile(handle), "truncate")
        checked(self.k.FlushFileBuffers(handle), "flush")

    def process_created(self, handle):
        values = [t.FILETIME() for _ in range(4)]
        checked(self.k.GetProcessTimes(handle, *[c.byref(value) for value in values]), "process_times")
        return (int(values[0].dwHighDateTime) << 32) | int(values[0].dwLowDateTime)

    def sid_binary(self, text):
        pointer = c.c_void_p()
        checked(self.a.ConvertStringSidToSidW(text, c.byref(pointer)), "sid_parse")
        try:
            checked(self.a.IsValidSid(pointer), "sid_parse")
            return c.string_at(pointer, self.a.GetLengthSid(pointer))
        finally:
            _release_owned(sys.exception(),
                lambda: checked(not self.k.LocalFree(pointer), 'sid_free'),
            )

    def assert_admin(self):
        pointer, member = c.c_void_p(), t.BOOL()
        checked(self.a.ConvertStringSidToSidW("S-1-5-32-544", c.byref(pointer)), "admin_sid")
        try:
            checked(self.a.CheckTokenMembership(None, pointer, c.byref(member)), "admin_token")
            if not member.value:
                raise Failure("admin_token")
        finally:
            _release_owned(sys.exception(),
                lambda: checked(not self.k.LocalFree(pointer), 'sid_free'),
            )

    def verify_ancestor(self, handle):
        descriptor = c.c_void_p()
        if self.a.GetSecurityInfo(handle, 1, 5, None, None, None, None, c.byref(descriptor)) != 0:
            raise Failure("ancestor_security")
        try:
            owner, acl, _protected = self.security(descriptor)
            trusted = {self.sid_binary("S-1-5-32-544"), self.sid_binary("S-1-5-18"),
                       self.sid_binary(self.process_user(self.k.GetCurrentProcess()))}
            if owner not in trusted:
                raise Failure("ancestor_owner")
            count, offset = struct.unpack("<BBHHH", acl[:8])[3], 8
            for _ in range(count):
                if offset + 4 > len(acl):
                    raise Failure("ancestor_acl")
                kind, flags, size = struct.unpack("<BBH", acl[offset:offset + 4])
                if size < 4 or offset + size > len(acl):
                    raise Failure("ancestor_acl")
                if not flags & 8 and kind != 1:
                    if kind != 0 or size < 20:
                        raise Failure("ancestor_acl")
                    mask = struct.unpack("<I", acl[offset + 4:offset + 8])[0]
                    identity = acl[offset + 8:offset + size]
                    if mask & 0x500D0156 and identity not in trusted:
                        raise Failure("ancestor_writable")
                offset += size
            if offset > len(acl):
                raise Failure("ancestor_acl")
        finally:
            _release_owned(sys.exception(),
                lambda: checked(not self.k.LocalFree(descriptor), 'free_descriptor') if descriptor.value else None,
            )

    def observe_security(self, handle):
        descriptor = c.c_void_p()
        if self.a.GetSecurityInfo(handle, 1, 5, None, None, None, None, c.byref(descriptor)) != 0:
            raise Failure("observe_security")
        try:
            owner, acl, protected = self.security(descriptor)
            return dict(owner_binary=owner.hex(), dacl_binary=acl.hex(), protected=protected)
        finally:
            _release_owned(sys.exception(),
                lambda: checked(not self.k.LocalFree(descriptor), 'free_descriptor') if descriptor.value else None,
            )

    def effective_access(self, handle, parent_process):
        descriptor, token, impersonation = c.c_void_p(), t.HANDLE(), t.HANDLE()
        try:
            if self.a.GetSecurityInfo(handle, 1, 7, None, None, None, None, c.byref(descriptor)) != 0:
                raise Failure("access_descriptor")
            checked(self.a.OpenProcessToken(parent_process, 10, c.byref(token)), "access_token")
            checked(self.a.DuplicateToken(token, 2, c.byref(impersonation)), "access_impersonation")
            mapping = GENERIC_MAPPING(0x120089, 0x120116, 0x1200A0, 0x1F01FF)
            privileges = c.create_string_buffer(16384)
            size, granted, allowed = t.DWORD(len(privileges)), t.DWORD(), t.BOOL()
            checked(self.a.AccessCheck(descriptor, impersonation, 0x02000000,
                c.byref(mapping), privileges, c.byref(size), c.byref(granted),
                c.byref(allowed)), "effective_access")
            if size.value > len(privileges) or not 0 <= granted.value <= 0xFFFFFFFF:
                raise Failure("effective_access_incomplete")
            return dict(api_completed=True, access_status=bool(allowed.value),
                        granted=int(granted.value), privilege_bytes=int(size.value))
        finally:
            _release_owned(sys.exception(),
                *(lambda owned=owned: self.close(owned) for owned in (impersonation, token) if owned),
                lambda: checked(not self.k.LocalFree(descriptor), "free_descriptor") if descriptor.value else None,
            )

    def process_user(self, process):
        token, needed = t.HANDLE(), t.DWORD()
        checked(self.a.OpenProcessToken(process, 8, c.byref(token)), "process_token")
        try:
            self.a.GetTokenInformation(token, 1, None, 0, c.byref(needed))
            if not 0 < needed.value <= 4096:
                raise Failure("token_size")
            buffer = c.create_string_buffer(needed.value)
            checked(self.a.GetTokenInformation(token, 1, buffer, len(buffer), c.byref(needed)), "token_user")
            if not c.sizeof(TOKEN_USER) <= needed.value <= len(buffer):
                raise Failure("token_size")
            sid = c.cast(buffer, c.POINTER(TOKEN_USER)).contents.sid
            base = c.addressof(buffer)
            if not sid or not base + c.sizeof(TOKEN_USER) <= sid < base + needed.value:
                raise Failure("token_sid")
            checked(self.a.IsValidSid(sid), "token_sid")
            length = int(self.a.GetLengthSid(sid))
            if not 12 <= length <= 68 or sid + length > base + needed.value:
                raise Failure("token_sid")
            text = t.LPWSTR()
            checked(self.a.ConvertSidToStringSidW(sid, c.byref(text)), "sid_text")
            try:
                return text.value
            finally:
                _release_owned(sys.exception(),
                    lambda: checked(not self.k.LocalFree(text), 'free_sid_text'),
                )
        finally:
            _release_owned(sys.exception(),
                lambda: self.close(token),
            )

    def job_pids(self, job):
        # At most 32 fixed-chain members; do not truncate a larger live tree.
        size = 8 + 32 * c.sizeof(c.c_size_t)
        buffer, returned = c.create_string_buffer(size), t.DWORD()
        checked(self.k.QueryInformationJobObject(job, 3, buffer, size, c.byref(returned)), "job_query")
        assigned, listed = struct.unpack("<II", buffer.raw[:8])
        if (assigned != listed or listed > 32 or returned.value > size
                or returned.value < 8 + listed * c.sizeof(c.c_size_t)):
            raise Failure("job_query_incomplete")
        pointer = c.cast(c.byref(buffer, 8), c.POINTER(c.c_size_t))
        result = tuple(int(pointer[index]) for index in range(listed))
        if len(set(result)) != len(result) or any(pid < 1 for pid in result):
            raise Failure("job_query_identity")
        return result
```

## Asset: `scripts/windows_positive_loopback_admin_store.py`

```python
from __future__ import annotations

import ctypes as c
import hashlib
import json
import os
from pathlib import Path
import re
import time
import sys

from scripts.windows_positive_loopback_admin_win32 import Win32, Failure, _release_owned


PRIVATE = "O:BAD:P(A;OICI;FA;;;BA)(A;OICI;FA;;;SY)"
LEDGER_LIMIT = 8388608


def wire(value):
    return json.dumps(value, ensure_ascii=True, sort_keys=True,
                      separators=(",", ":"), allow_nan=False).encode("ascii")


def unique(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise Failure("duplicate_key")
        result[key] = value
    return result


def decode(value, limit):
    if type(value) is not bytes or not value or len(value) > limit:
        raise Failure("file_size")
    try:
        return json.loads(value.decode("utf-8"), object_pairs_hook=unique,
                          parse_constant=lambda x: (_ for _ in ()).throw(Failure("json_constant")))
    except (ValueError, UnicodeError, RecursionError) as exc:
        raise Failure("file_json") from exc


class Store:
    def __init__(self, root):
        if type(root) is not Path and not isinstance(root, Path):
            raise Failure("root_type")
        if not root.is_absolute() or root.resolve(strict=True) != root or re.fullmatch(r"icode-positive-admin-[0-9a-f]{32}", root.name) is None:
            raise Failure("root_namespace")
        self.w = Win32()
        self.w.assert_admin()
        self.root, self.handles, self.pins = root, [], []
        try:
            self.route_records = []
            for parent in reversed(root.parents):
                handle = self.w.pin_ancestor(parent, observe_only=True)
                self.pins.append(handle)
                self.route_records.append(dict(path=str(parent),
                    identity=list(self.w.info(handle, directory=True)),
                    security=self.w.observe_security(handle)))
            self.root_handle = self.w.pin_ancestor(root)
            self.pins.append(self.root_handle)
            self.root_identity = self.w.info(self.root_handle, directory=True)
            self.lock, _identity = self.w.open_file(root / "lock", PRIVATE, write=True)
            self.handles.append(self.lock)
            self.data = decode(self.read("ledger.json", PRIVATE, LEDGER_LIMIT), LEDGER_LIMIT)
            if type(self.data) is not dict or self.data.get("schema") != 1:
                raise Failure("ledger_schema")
            if self.data.get("root_identity") != list(self.root_identity):
                raise Failure("root_identity")
        except BaseException:
            _release_owned(sys.exception(), self.close)
            raise

    @classmethod
    def create(cls, root, data):
        w = Win32()
        w.assert_admin()
        pins = []
        try:
            for parent in reversed(root.parents):
                pins.append(w.pin_ancestor(parent, observe_only=True))
            w.create_directory(root, PRIVATE)
            root_handle, identity = w.open_file(root, PRIVATE, directory=True)
            pins.append(root_handle)
            data["root_identity"] = list(identity)
            for name in ("lock", "ledger.json"):
                handle, identity = w.open_file(root / name, PRIVATE, create=True, write=True)
                try:
                    data["file_identities"][name] = list(identity)
                    w.write(handle, wire(data) if name == "ledger.json" else b"")
                finally:
                    _release_owned(sys.exception(),
                        lambda: w.close(handle),
                    )
        finally:
            _release_owned(sys.exception(),
                *(lambda handle=handle: w.close(handle) for handle in reversed(pins)),
            )
        return cls(root)

    def flush(self):
        # A torn/truncated write is never replayed as an earlier successful
        # transaction: reopening malformed JSON fails closed and does not guess.
        encoded = wire(self.data)
        if len(encoded) > LEDGER_LIMIT:
            raise Failure("ledger_limit")
        handle, identity = self.w.open_file(self.root / "ledger.json", PRIVATE, write=True)
        try:
            if self.data["file_identities"].get("ledger.json") != list(identity):
                raise Failure("ledger_replaced")
            self.w.write(handle, encoded)
            if self.w.info(handle) != identity:
                raise Failure("ledger_replaced")
        finally:
            _release_owned(sys.exception(),
                lambda: self.w.close(handle),
            )

    def file_descriptor(self, role):
        if role == "private":
            return PRIVATE
        sid = self.data["account_sid"]
        if type(sid) is not str or re.fullmatch(r"S-1-5-21-(?:[0-9]+-){3}[0-9]+", sid) is None:
            raise Failure("account_sid")
        if role == "public":
            return PRIVATE + "(A;;FR;;;" + sid + ")"
        if role == "request":
            # Write data/read data only, no delete/owner/DACL/parent mutation.
            return PRIVATE + "(A;;0x120003;;;" + sid + ")"
        raise Failure("file_role")

    def read(self, name, descriptor, limit):
        self._leaf(name)
        handle, identity = self.w.open_file(self.root / name, descriptor)
        try:
            expected = self.data.get("file_identities", {}).get(name) if hasattr(self, "data") else None
            if expected is not None and list(identity) != expected:
                raise Failure("file_replaced")
            result = self.w.read(handle, limit)
            if self.w.info(handle) != identity:
                raise Failure("file_replaced")
            return result
        finally:
            _release_owned(sys.exception(),
                lambda: self.w.close(handle),
            )

    def write(self, name, data, role="private", *, create=False):
        self._leaf(name)
        descriptor = self.file_descriptor(role)
        handle, identity = self.w.open_file(self.root / name, descriptor, create=create, write=True)
        try:
            identities = self.data["file_identities"]
            if not create and identities.get(name) != list(identity):
                raise Failure("file_replaced")
            self.w.write(handle, data)
            if create:
                identities[name] = list(identity)
        finally:
            _release_owned(sys.exception(),
                lambda: self.w.close(handle),
            )

    def create_directory(self, relative):
        parts = Path(relative).parts
        if not parts or Path(relative).is_absolute() or any(part in (".", "..") for part in parts):
            raise Failure("directory_name")
        path = self.root
        held = []
        try:
            for number, part in enumerate(parts):
                path /= part
                leaf = number == len(parts) - 1
                exists = path.exists()
                if leaf and exists:
                    raise Failure("directory_exists")
                if not exists:
                    # CreateDirectory is CREATE_NEW; a race cannot silently
                    # replace a component or admit a pre-existing leaf.
                    self.w.create_directory(path, PRIVATE)
                handle, identity = self.w.open_file(path, PRIVATE, directory=True)
                held.append((handle, identity))
            for handle, identity in held:
                if self.w.info(handle, directory=True) != identity:
                    raise Failure("directory_changed")
            # Existing prefixes are admitted only after exact protected SD,
            # canonical namespace and no-reparse identity checks, then pinned
            # for the Store lifetime; exists() by itself is never authority.
            self.pins.extend(handle for handle, _identity in held)
            held.clear()
        finally:
            _release_owned(sys.exception(),
                *(lambda handle=handle: self.w.close(handle) for handle, _identity in reversed(held)),
            )

    @staticmethod
    def _leaf(name):
        if type(name) is not str or re.fullmatch(r"[A-Za-z0-9_.-]{1,100}", name) is None or name in (".", ".."):
            raise Failure("file_name")

    def close(self):
        # Pop only means this instance attempted release, not OS confirmation.
        actions = []
        for collection in (getattr(self, "handles", []), getattr(self, "pins", [])):
            while collection:
                handle = collection.pop()
                actions.append(lambda handle=handle: self.w.close(handle))
        _release_owned(sys.exception(), *actions)


def copy_private_tree(store, source, destination, *, deadline):
    # Called only after Native proved the intended temporary account absent.
    # Source handles deny write/delete; every destination gets an explicit
    # protected descriptor, not a copied user ACL or a symlink/reparse object.
    # Inspect the supplied namespace before resolve: resolving first would
    # erase evidence that the input root itself was a link/reparse object.
    source = Path(source).absolute()
    for entry in reversed((source, *source.parents)):
        if entry.is_symlink() or getattr(entry.lstat(), "st_file_attributes", 0) & 0x400:
            raise Failure("freeze_reparse")
    if source.resolve(strict=True) != source:
        raise Failure("freeze_source_namespace")
    destination = store.root / destination
    store.w.create_directory(destination, PRIVATE)
    records, total = [], 0
    def enumeration_failed(error):
        raise Failure("freeze_enumeration") from error

    for current, directories, files in os.walk(
            source, topdown=True, followlinks=False, onerror=enumeration_failed):
        if time.monotonic() > deadline:
            raise Failure("freeze_deadline")
        relative = Path(current).relative_to(source)
        directories[:] = [name for name in directories if name.casefold() not in
                          {"site-packages", "__pycache__", "test", "tests", "idlelib", "tkinter", "ensurepip"}]
        for name in directories + files:
            path = Path(current) / name
            if name.casefold() == "pyvenv.cfg" or name.casefold().endswith("._pth"):
                raise Failure("unsupported_runtime_layout")
            if path.is_symlink() or getattr(path.lstat(), "st_file_attributes", 0) & 0x400:
                raise Failure("freeze_reparse")
            target = destination / path.relative_to(source)
            if name in directories:
                store.w.create_directory(target, PRIVATE)
                continue
            if len(records) >= 100000:
                raise Failure("freeze_count")
            raw_handle = store.w.k.CreateFileW(str(path), 0x80020080, 1, None, 3, 0x00200000, None)
            if raw_handle in (None, c.c_void_p(-1).value):
                raise Failure("freeze_source_open")
            out = None
            try:
                source_identity = store.w.info(raw_handle)
                store.w.verify_ancestor(raw_handle)
                info = path.lstat()
                size = int(info.st_size)
                if size < 0 or size > 268435456:
                    raise Failure("freeze_file_limit")
                total += size
                if total > 2147483648:
                    raise Failure("freeze_total_limit")
                data = store.w.read(raw_handle, size)
                if len(data) != size or store.w.info(raw_handle) != source_identity:
                    raise Failure("freeze_source_changed")
                out, target_identity = store.w.open_file(target, PRIVATE, create=True, write=True)
                store.w.write(out, data)
                records.append(dict(path=target.relative_to(store.root).as_posix(),
                                    identity=list(target_identity), size=size,
                                    sha256=hashlib.sha256(data).hexdigest()))
            finally:
                _release_owned(sys.exception(),
                    lambda: store.w.close(out) if out else None,
                    lambda: store.w.close(raw_handle),
                )
            if time.monotonic() > deadline:
                raise Failure("freeze_deadline")
    return records
```

此复制原语不是完整加载准入。实际 Native._source_tree 在调用前打开并持有原入口全路径及每个源目录无重解析句柄，记录身份／成员，复制后第二次完整枚举核对，再逐源文件复读比对受保护副本 digest。不能以文件 ACL 检查代替目录完整性，也不能把局部 RAM 通过授予加载信用。任何枚举 OSError 均失败，不接受部分 records。

加载边界的固定依据：CPython v3.12.10（commit `0cc81280367df838c4b199f8f0378837165071c2`）的 [getpath.py](https://github.com/python/cpython/blob/v3.12.10/Modules/getpath.py) 294–351 行在 site 前处理 exe 同级／父级 pyvenv.cfg；388–419、672–689 行证明 DLL._pth 优先且可通过 import site 启用 site；585–658 行即使 zip 不存在也把 DLL 目录 python312.zip 纳入搜索。`-I -S` 不能作为这些布局已关闭的证据。[dynload_win.c](https://github.com/python/cpython/blob/v3.12.10/Python/dynload_win.c) 148–231 行另涉及 pyd、python3.dll 加载。未来完整 freeze 必须明确枚举并拒绝未声明的 cfg／各命名 ._pth／zip（含被搜索但原先不存在的槽），冻结解释器 DLL 与真实扩展依赖并核验实际已加载路径；runtime 同级／父级槽的 ACL 和身份同样纳入保护。当前 copy 资产仅覆盖树内命名拒绝，不冒充上述完整消费者已实现。

恢复故障分账：当前可变 ledger 原地写入发生撕裂、缺失或严格解析失败时，always 的结果只能是 unknown／候选失败；禁止从文件名、stdout、部分 JSON 或扫描结果猜 SID，禁止报告恢复成功或零残留。完整且已 Flush 的正常／可恢复记录仍必须由 Native 重新打开并核验实际命名 command Job、原 PID/creation time、实际退出与完整 Job 成员事实，不能以 reaped/resume_attempted 字段自证。intent 仅表示准备；durable ready-to-resume 仅表示可能执行，均不是 add 已执行证明。该故障语义沿用冻结 SPEC，不引入额外恢复 authority。

## Asset: `native/windows/icode_positive_loopback_admin_abi.c`

```c
#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <stddef.h>
#include <stdint.h>
#include <stdio.h>

_Static_assert(sizeof(DWORD) == 4, "DWORD");
_Static_assert(sizeof(BOOL) == 4, "BOOL");
_Static_assert(sizeof(FILETIME) == 8, "FILETIME");
_Static_assert(sizeof(ULONG_PTR) == sizeof(void *), "ULONG_PTR");

typedef BOOL (WINAPI *ProcessTimesFn)(HANDLE, LPFILETIME, LPFILETIME,
                                    LPFILETIME, LPFILETIME);

int main(int argc, char **argv) {
    ProcessTimesFn process_times = GetProcessTimes;
    FILETIME created, exited, kernel, user;
    BOOL call_ok;
    HANDLE heap;
    void *owned;
    BOOL freed;
    const char *machine;
    (void)argv;
    if (argc != 1) return 2;
#if defined(_M_ARM64)
    machine = "ARM64";
#elif defined(_M_X64)
    machine = "x64";
#else
#error Unsupported CI probe architecture
#endif
    call_ok = process_times(GetCurrentProcess(), &created, &exited, &kernel, &user);
    heap = GetProcessHeap();
    owned = heap ? HeapAlloc(heap, 0, 64) : NULL;
    freed = owned ? HeapFree(heap, 0, owned) : FALSE;
    if (!call_ok || !freed) return 3;
    printf("{\"schema\":1,\"machine\":\"%s\",\"DWORD\":%zu,\"BOOL\":%zu,"
           "\"FILETIME\":%zu,\"HANDLE\":%zu,\"SA\":%zu,\"FILE_INFO\":%zu,"
           "\"STARTUP\":%zu,\"STARTUP_EX\":%zu,\"PROCESS\":%zu,"
           "\"TOKEN_USER\":%zu,\"GENERIC_MAPPING\":%zu,\"EXTENDED_LIMITS\":%zu,"
           "\"sa_descriptor\":%zu,\"file_volume\":%zu,\"file_links\":%zu,"
           "\"startup_stdin\":%zu,\"startup_attributes\":%zu,\"process_pid\":%zu,"
           "\"token_sid\":%zu,\"job_pid_list\":%zu,\"job_list_attribute\":%llu,"
           "\"calling_convention_verified\":true,\"owned_buffer_freed\":true,\"layout\":{",
           machine, sizeof(DWORD), sizeof(BOOL), sizeof(FILETIME), sizeof(HANDLE),
           sizeof(SECURITY_ATTRIBUTES), sizeof(BY_HANDLE_FILE_INFORMATION),
           sizeof(STARTUPINFOW), sizeof(STARTUPINFOEXW), sizeof(PROCESS_INFORMATION),
           sizeof(TOKEN_USER), sizeof(GENERIC_MAPPING), sizeof(JOBOBJECT_EXTENDED_LIMIT_INFORMATION),
           offsetof(SECURITY_ATTRIBUTES, lpSecurityDescriptor),
           offsetof(BY_HANDLE_FILE_INFORMATION, dwVolumeSerialNumber),
           offsetof(BY_HANDLE_FILE_INFORMATION, nNumberOfLinks),
           offsetof(STARTUPINFOW, hStdInput),
           offsetof(STARTUPINFOEXW, lpAttributeList),
           offsetof(PROCESS_INFORMATION, dwProcessId),
           offsetof(TOKEN_USER, User),
           offsetof(JOBOBJECT_BASIC_PROCESS_ID_LIST, ProcessIdList),
           (unsigned long long)PROC_THREAD_ATTRIBUTE_JOB_LIST);
    /* Independent SDK oracle. Keys match every consumed Python field. */
#define S(key, type) printf("\"" key "\":%zu,", sizeof(type))
#define O(key, type, field) printf("\"" key "\":%zu,", offsetof(type, field))
    S("WORD", WORD); S("LONG", LONG); S("ULONG_PTR", ULONG_PTR);
    S("IO", IO_COUNTERS); S("LIMITS", JOBOBJECT_BASIC_LIMIT_INFORMATION);
    S("SID_AND_ATTRIBUTES", SID_AND_ATTRIBUTES);
    O("FILETIME.dwLowDateTime", FILETIME, dwLowDateTime);
    O("FILETIME.dwHighDateTime", FILETIME, dwHighDateTime);
    O("SA.length", SECURITY_ATTRIBUTES, nLength);
    O("SA.descriptor", SECURITY_ATTRIBUTES, lpSecurityDescriptor);
    O("SA.inherit", SECURITY_ATTRIBUTES, bInheritHandle);
    O("FILE_INFO.attributes", BY_HANDLE_FILE_INFORMATION, dwFileAttributes);
    O("FILE_INFO.created", BY_HANDLE_FILE_INFORMATION, ftCreationTime);
    O("FILE_INFO.accessed", BY_HANDLE_FILE_INFORMATION, ftLastAccessTime);
    O("FILE_INFO.written", BY_HANDLE_FILE_INFORMATION, ftLastWriteTime);
    O("FILE_INFO.volume", BY_HANDLE_FILE_INFORMATION, dwVolumeSerialNumber);
    O("FILE_INFO.size_high", BY_HANDLE_FILE_INFORMATION, nFileSizeHigh);
    O("FILE_INFO.size_low", BY_HANDLE_FILE_INFORMATION, nFileSizeLow);
    O("FILE_INFO.links", BY_HANDLE_FILE_INFORMATION, nNumberOfLinks);
    O("FILE_INFO.index_high", BY_HANDLE_FILE_INFORMATION, nFileIndexHigh);
    O("FILE_INFO.index_low", BY_HANDLE_FILE_INFORMATION, nFileIndexLow);
    O("STARTUP.cb", STARTUPINFOW, cb);
    O("STARTUP.reserved", STARTUPINFOW, lpReserved);
    O("STARTUP.desktop", STARTUPINFOW, lpDesktop);
    O("STARTUP.title", STARTUPINFOW, lpTitle);
    O("STARTUP.x", STARTUPINFOW, dwX); O("STARTUP.y", STARTUPINFOW, dwY);
    O("STARTUP.x_size", STARTUPINFOW, dwXSize);
    O("STARTUP.y_size", STARTUPINFOW, dwYSize);
    O("STARTUP.x_count", STARTUPINFOW, dwXCountChars);
    O("STARTUP.y_count", STARTUPINFOW, dwYCountChars);
    O("STARTUP.fill", STARTUPINFOW, dwFillAttribute);
    O("STARTUP.flags", STARTUPINFOW, dwFlags);
    O("STARTUP.show", STARTUPINFOW, wShowWindow);
    O("STARTUP.reserved_bytes", STARTUPINFOW, cbReserved2);
    O("STARTUP.reserved_pointer", STARTUPINFOW, lpReserved2);
    O("STARTUP.stdin", STARTUPINFOW, hStdInput);
    O("STARTUP.stdout", STARTUPINFOW, hStdOutput);
    O("STARTUP.stderr", STARTUPINFOW, hStdError);
    O("STARTUP_EX.startup", STARTUPINFOEXW, StartupInfo);
    O("STARTUP_EX.attributes", STARTUPINFOEXW, lpAttributeList);
    O("PROCESS.process", PROCESS_INFORMATION, hProcess);
    O("PROCESS.thread", PROCESS_INFORMATION, hThread);
    O("PROCESS.pid", PROCESS_INFORMATION, dwProcessId);
    O("PROCESS.tid", PROCESS_INFORMATION, dwThreadId);
    O("IO.read_ops", IO_COUNTERS, ReadOperationCount);
    O("IO.write_ops", IO_COUNTERS, WriteOperationCount);
    O("IO.other_ops", IO_COUNTERS, OtherOperationCount);
    O("IO.read_bytes", IO_COUNTERS, ReadTransferCount);
    O("IO.write_bytes", IO_COUNTERS, WriteTransferCount);
    O("IO.other_bytes", IO_COUNTERS, OtherTransferCount);
    O("LIMITS.process_time", JOBOBJECT_BASIC_LIMIT_INFORMATION, PerProcessUserTimeLimit);
    O("LIMITS.job_time", JOBOBJECT_BASIC_LIMIT_INFORMATION, PerJobUserTimeLimit);
    O("LIMITS.flags", JOBOBJECT_BASIC_LIMIT_INFORMATION, LimitFlags);
    O("LIMITS.minimum", JOBOBJECT_BASIC_LIMIT_INFORMATION, MinimumWorkingSetSize);
    O("LIMITS.maximum", JOBOBJECT_BASIC_LIMIT_INFORMATION, MaximumWorkingSetSize);
    O("LIMITS.active_limit", JOBOBJECT_BASIC_LIMIT_INFORMATION, ActiveProcessLimit);
    O("LIMITS.affinity", JOBOBJECT_BASIC_LIMIT_INFORMATION, Affinity);
    O("LIMITS.priority", JOBOBJECT_BASIC_LIMIT_INFORMATION, PriorityClass);
    O("LIMITS.scheduling", JOBOBJECT_BASIC_LIMIT_INFORMATION, SchedulingClass);
    O("EXTENDED_LIMITS.basic", JOBOBJECT_EXTENDED_LIMIT_INFORMATION, BasicLimitInformation);
    O("EXTENDED_LIMITS.io", JOBOBJECT_EXTENDED_LIMIT_INFORMATION, IoInfo);
    O("EXTENDED_LIMITS.process_memory", JOBOBJECT_EXTENDED_LIMIT_INFORMATION, ProcessMemoryLimit);
    O("EXTENDED_LIMITS.job_memory", JOBOBJECT_EXTENDED_LIMIT_INFORMATION, JobMemoryLimit);
    O("EXTENDED_LIMITS.peak_process", JOBOBJECT_EXTENDED_LIMIT_INFORMATION, PeakProcessMemoryUsed);
    O("EXTENDED_LIMITS.peak_job", JOBOBJECT_EXTENDED_LIMIT_INFORMATION, PeakJobMemoryUsed);
    O("SID_AND_ATTRIBUTES.Sid", SID_AND_ATTRIBUTES, Sid);
    O("SID_AND_ATTRIBUTES.Attributes", SID_AND_ATTRIBUTES, Attributes);
    O("TOKEN_USER.sid", TOKEN_USER, User.Sid);
    O("TOKEN_USER.attributes", TOKEN_USER, User.Attributes);
    O("GENERIC_MAPPING.read", GENERIC_MAPPING, GenericRead);
    O("GENERIC_MAPPING.write", GENERIC_MAPPING, GenericWrite);
    O("GENERIC_MAPPING.execute", GENERIC_MAPPING, GenericExecute);
    O("GENERIC_MAPPING.all", GENERIC_MAPPING, GenericAll);
    O("JOB_PID.assigned", JOBOBJECT_BASIC_PROCESS_ID_LIST, NumberOfAssignedProcesses);
    O("JOB_PID.count", JOBOBJECT_BASIC_PROCESS_ID_LIST, NumberOfProcessIdsInList);
    printf("\"JOB_PID.pids\":%zu}}\n",
           offsetof(JOBOBJECT_BASIC_PROCESS_ID_LIST, ProcessIdList));
#undef O
#undef S
    return 0;
}
```

## Asset: exact `native/windows/CMakeLists.txt` addition

只在该文件最终末尾新增以下内容，不改任何已有 target/flags/安装入口。此目标不在默认 ALL 中；下一片真实 workflow 必须显式 build 并在 CLI 写前运行/比对，其原件来自同 candidate 受保护构建位置。

```cmake
add_executable(icode_positive_loopback_admin_abi EXCLUDE_FROM_ALL
  icode_positive_loopback_admin_abi.c
)
set_target_properties(icode_positive_loopback_admin_abi PROPERTIES
  OUTPUT_NAME "icode-positive-loopback-admin-abi"
  C_STANDARD 11
  C_STANDARD_REQUIRED YES
  C_EXTENSIONS NO
)
target_compile_definitions(icode_positive_loopback_admin_abi PRIVATE
  UNICODE _UNICODE _WIN32_WINNT=0x0A00
)
if(MSVC)
  set_property(TARGET icode_positive_loopback_admin_abi PROPERTY
    MSVC_RUNTIME_LIBRARY "MultiThreaded$<$<CONFIG:Debug>:Debug>"
  )
  target_compile_options(icode_positive_loopback_admin_abi PRIVATE /W4 /WX)
endif()
```

## Asset: `scripts/windows_positive_loopback_admin_jobs.py`

```python
from __future__ import annotations

import ctypes as c
from ctypes import wintypes as t
from pathlib import Path
import subprocess
import time
import sys

from scripts.windows_positive_loopback_admin_store import PRIVATE
from scripts.windows_positive_loopback_admin_win32 import (
    SA, STARTUP_EX, PROCESS, EXTENDED_LIMITS, Failure, checked, _release_owned,
)


def create_job(store, name):
    w = store.w
    descriptor = w.descriptor(PRIVATE)
    job = None
    transferred = False
    try:
        security = SA(c.sizeof(SA), descriptor, False)
        c.set_last_error(0)
        job = w.k.CreateJobObjectW(c.byref(security), name)
        checked(job, "job_create")
        if c.get_last_error() == 183:
            raise Failure("job_collision")
        limits = EXTENDED_LIMITS()
        limits.basic.flags = 0x2000  # KILL_ON_JOB_CLOSE; no breakaway flags.
        checked(w.k.SetInformationJobObject(job, 9, c.byref(limits), c.sizeof(limits)), "job_limits")
        w.verify_security(job, PRIVATE, object_type=6)
        allocation, descriptor = descriptor, None
        _release_owned(None, lambda: checked(not w.k.LocalFree(allocation), "free_descriptor"))
        transferred = True
        return job
    finally:
        _release_owned(sys.exception(),
            lambda: checked(not w.k.LocalFree(descriptor), "free_descriptor") if descriptor is not None else None,
            lambda: w.close(job) if job and not transferred else None,
        )


def wait_empty(store, job, milliseconds):
    deadline = time.monotonic() + milliseconds / 1000
    while True:
        if store.w.job_pids(job) == ():
            return
        if time.monotonic() >= deadline:
            raise Failure("job_not_empty")
        time.sleep(0.01)


def _argv(store, kind):
    root, data = store.root, store.data
    python = root / "runtime" / "python.exe"
    if kind == "get":
        return [str(python), "-I", "-S", "-B",
                str(root / "trusted" / "scripts" / "windows_positive_loopback_full_get.py"),
                "--full-get"]
    if kind == "abi":
        return [str(root / "icode-positive-loopback-admin-abi.exe")]
    if kind not in ("add", "delete"):
        raise Failure("command_kind")
    sid = data["bootstrap"]["positive_sid"]
    if sid == data["bootstrap"]["reviewer_sid"] or not sid.startswith("S-1-15-2-"):
        raise Failure("command_sid")
    if not data["owned_intent"] or data["operation_manifest"] is None:
        raise Failure("command_intent")
    if kind == "add":
        if data["phase"] != "add_intent" or any(item["kind"] == "add" for item in data["commands"]):
            raise Failure("command_replay")
        if int(time.monotonic() * 1000) >= data["operation_manifest"]["deadline_ms"]:
            raise Failure("command_deadline")
    elif data["phase"] != "cleanup_intent":
        raise Failure("command_phase")
    return [data["system_tool"]["path"], "LoopbackExempt",
            "-a" if kind == "add" else "-d", "-p=" + sid]


def run_fixed(store, kind, *, budget_ms=5000):
    if type(budget_ms) is not int or not 0 < budget_ms <= 5000:
        raise Failure("command_budget")
    work_deadline = time.monotonic() + budget_ms / 1000
    argv = _argv(store, kind)
    if len(store.data["commands"]) >= 32:
        raise Failure("command_count")
    number = len(store.data["commands"])
    output = "command-" + str(number) + ".out"
    name = "Local\\ICODE.Positive." + store.data["session"] + ".command." + str(number)
    record = dict(kind=kind, job=name, output=output, state="allocated", pid=None,
                  process_created=None, resume_permitted=False, resume_attempted=False,
                  resume_returned=None, exit_code=None, timed_out=False, reaped=False)
    store.write(output, b"", create=True)
    store.data["commands"].append(record)
    store.flush()
    w = store.w
    job = thread = process_handle = out = null = None
    attribute_list = None
    attributes_initialized = False
    successful_return = False
    try:
        job = create_job(store, name)
        out, _ = w.open_file(store.root / output, PRIVATE, write=True, inherit=True)
        security = SA(c.sizeof(SA), None, True)
        null = w.k.CreateFileW("\\\\.\\NUL", 0x80000000, 3, c.byref(security), 3, 0, None)
        if null in (None, c.c_void_p(-1).value):
            raise Failure("null_handle")
        size = c.c_size_t()
        w.k.InitializeProcThreadAttributeList(None, 2, 0, c.byref(size))
        if not 1 <= size.value <= 1048576:
            raise Failure("attribute_size")
        # c_size_t array supplies pointer alignment on x64 and ARM64.
        storage = (c.c_size_t * ((size.value + c.sizeof(c.c_size_t) - 1) // c.sizeof(c.c_size_t)))()
        attribute_list = c.cast(storage, c.c_void_p)
        checked(w.k.InitializeProcThreadAttributeList(attribute_list, 2, 0, c.byref(size)), "attribute_init")
        attributes_initialized = True
        jobs, handles = (t.HANDLE * 1)(job), (t.HANDLE * 2)(out, null)
        checked(w.k.UpdateProcThreadAttribute(attribute_list, 0, 0x0002000D,
            c.cast(jobs, c.c_void_p), c.sizeof(jobs), None, None), "job_attribute")
        checked(w.k.UpdateProcThreadAttribute(attribute_list, 0, 0x00020002,
            c.cast(handles, c.c_void_p), c.sizeof(handles), None, None), "handle_attribute")
        startup, process = STARTUP_EX(), PROCESS()
        startup.startup.cb = c.sizeof(startup)
        startup.startup.flags = 0x100
        startup.startup.stdin = null
        startup.startup.stdout = out
        startup.startup.stderr = out
        startup.attributes = attribute_list
        command = c.create_unicode_buffer(subprocess.list2cmdline(argv))
        # Environment contains only trusted Windows/frozen runtime locations;
        # no PATH, Python, GITHUB_ENV/OUTPUT or user-controlled loading hints.
        windows = str(w.system_directory.parent)
        environment = c.create_unicode_buffer(
            "SystemRoot=" + windows + "\0TEMP=" + str(store.root)
            + "\0TMP=" + str(store.root) + "\0\0")
        checked(w.k.CreateProcessW(argv[0], command, None, None, True,
            0x00000004 | 0x00000400 | 0x00080000 | 0x08000000,
            environment, str(store.root / "runtime"), c.byref(startup), c.byref(process)), "command_create")
        process_handle, thread = process.process, process.thread
        if not process.pid or set(w.job_pids(job)) != {int(process.pid)}:
            raise Failure("command_job_admission")
        creation = w.process_created(process_handle)
        if not creation:
            raise Failure("command_identity")
        record.update(state="ready", pid=int(process.pid), process_created=creation,
                      resume_permitted=True, resume_attempted=None)
        # The only path to Resume comes after this actual FlushFileBuffers.
        store.flush()
        if time.monotonic() >= work_deadline:
            raise Failure("command_work_deadline")
        if kind == "add" and int(time.monotonic() * 1000) >= store.data["operation_manifest"]["deadline_ms"]:
            raise Failure("command_deadline")
        record["resume_attempted"] = True
        previous = int(w.k.ResumeThread(thread))
        record["resume_returned"] = previous
        if previous != 1:
            raise Failure("command_resume")
        remaining = max(0, min(budget_ms, int((work_deadline - time.monotonic()) * 1000)))
        waited = int(w.k.WaitForSingleObject(process_handle, remaining))
        record["timed_out"] = waited == 258
        if waited not in (0, 258):
            raise Failure("command_wait")
        if waited == 258 or w.job_pids(job):
            _release_owned(None,
                lambda: checked(w.k.TerminateJobObject(job, 1), "command_terminate"),
                lambda: checked(w.k.WaitForSingleObject(process_handle, 2000) == 0, "command_reap"),
                lambda: wait_empty(store, job, 2000),
            )
        else:
            wait_empty(store, job, 2000)
        code = t.DWORD()
        checked(w.k.GetExitCodeProcess(process_handle, c.byref(code)), "command_exit")
        record.update(exit_code=int(code.value), reaped=True, state="reaped")
        store.flush()
        successful_return = True
        return dict(record)
    finally:
        primary = sys.exception()
        errors = []
        if process_handle and not record["reaped"]:
            try:
                _release_owned(None,
                    lambda: checked(w.k.TerminateJobObject(job, 1), "command_terminate") if job
                            else checked(w.k.TerminateProcess(process_handle, 1), "command_terminate"),
                    lambda: checked(w.k.WaitForSingleObject(process_handle, 2000) == 0, "command_reap"),
                    lambda: wait_empty(store, job, 2000) if job else None,
                )
                record.update(reaped=True, state="reaped_after_failure")
            except BaseException as error:
                errors.append(error)
        if attributes_initialized:
            try:
                w.k.DeleteProcThreadAttributeList(attribute_list)
            except BaseException as error:
                errors.append(error)
        for handle in (thread, process_handle, null, out, job):
            if handle:
                try:
                    w.close(handle)
                except BaseException as error:
                    errors.append(error)
        if not successful_return:
            if record["resume_attempted"] is None:
                # This live instance knows it never reached Resume. A crash
                # leaves durable ready/attempted=None, not this in-memory fact.
                record["resume_attempted"] = False
            try:
                store.flush()
            except BaseException as error:
                errors.append(error)
        if errors:
            record["reaped"] = False
            record["state"] = "cleanup_unknown"
            try:
                store.flush()
            except BaseException as error:
                errors.append(error)
            failure = primary if primary is not None else errors[0]
            for error in errors:
                failure.add_note(f"cleanup_unknown: {error!r}")
            if primary is None:
                raise failure
```

## Asset: `scripts/windows_positive_loopback_admin_native.py`

此模块只由受保护的固定 admin 入口加载。所有输入 JSON 仅是关联资料；admin token、文件句柄、有效权限、进程身份和 Job 都由本模块重取。`prepare` 不允许任何 CLI 写；`attach_parent` 完成真实标准用户 token 的只读准入后才允许 created gate。readonly admission 失败保留原始 owner/security/rights 证据，不推定未知 owner 是 TrustedInstaller，不将拒绝本身记为 ready。

```python
"""CI-only authority adapter for the fixed positive-loopback lifecycle."""
from __future__ import annotations
import ctypes as c
from ctypes import wintypes as t
from dataclasses import asdict
import hashlib
import importlib
import json
import os
from pathlib import Path
import re
import socket
import sys
import time
import uuid

from icode import windows_positive_loopback_policy as policy
from scripts import windows_positive_loopback_admin_win32 as abi
from scripts.windows_positive_loopback_admin_win32 import Win32, Failure, checked, _release_owned
from scripts.windows_positive_loopback_admin_store import Store, PRIVATE, wire, decode, copy_private_tree
from scripts.windows_positive_loopback_admin_jobs import create_job, run_fixed, wait_empty
from scripts.windows_positive_loopback_full_get import SID_AND_ATTRIBUTES, _text_sid

CONTEXT = {"repository", "source_sha", "run_id", "run_attempt", "job", "matrix"}
FIELDS = {"schema", "context", "account_name", "account_sid", "session", "root_identity",
          "phase", "bootstrap", "operation_manifest", "owned_intent", "intent_ms",
          "target_attributes", "commands", "observations", "file_identities", "frozen_files",
          "frozen_directories", "system_tool", "consumed", "parent", "outer_job", "first_error",
          "cleanup_error", "add_verified", "delete_verified", "others_preserved", "exact_restoration",
          "readonly_prepare", "operation_completed_ms", "prepared_ms", "profile_names", "nonce", "ports", "reads"}
PHASES = {"frozen", "prepared", "bound", "add_intent", "added", "cleanup_intent", "cleaned"}
ERRORS = {"created_request", "get_failed", "preexisting", "baseline_delta", "add_failed",
          "add_delta", "deadline", "parent_failed", "finished_request", "foreign_delta",
          "owner_conflict", "cleanup_failed", "ledger_failed"}
COMMAND = {"kind", "job", "output", "state", "pid", "process_created", "resume_permitted",
           "resume_attempted", "resume_returned", "exit_code", "timed_out", "reaped"}
COMMAND_STATES = {"allocated", "ready", "reaped", "reaped_after_failure", "cleanup_unknown"}
SLOTS = {"profile_created": "profile-created.request", "probe_finished": "probe-finished.request"}
PUBLIC = {"bootstrap": "bootstrap.json", "operation": "operation.json", "add": "add.json", "cleanup": "cleanup.json"}
ROUTE_MUTATION = 0x000D0152
LEAF_MUTATION = 0x000D0156


def require(value, name):
    if not value:
        raise Failure(name)


def integer(value, minimum=0, maximum=(1 << 63) - 1):
    return type(value) is int and minimum <= value <= maximum


def context(value):
    require(type(value) is dict and set(value) == CONTEXT, "context_schema")
    require(value["repository"] == "ayukyo/icode" and value["job"] == "windows-reviewer-snapshot-probe"
            and value["matrix"] in ("x64", "ARM64"), "context_fixed")
    require(type(value["source_sha"]) is str and re.fullmatch(r"[0-9a-f]{40}", value["source_sha"]), "context_sha")
    require(type(value["run_id"]) is str and re.fullmatch(r"[1-9][0-9]{0,19}", value["run_id"]), "context_run")
    require(integer(value["run_attempt"], 1, 0xFFFFFFFF), "context_attempt")
    expected = {"GITHUB_REPOSITORY": value["repository"], "GITHUB_SHA": value["source_sha"],
                "GITHUB_RUN_ID": value["run_id"], "GITHUB_RUN_ATTEMPT": str(value["run_attempt"]),
                "GITHUB_JOB": value["job"], "RUNNER_ARCH": {"x64": "X64", "ARM64": "ARM64"}[value["matrix"]]}
    require(os.environ.get("GITHUB_ACTIONS") == "true" and os.environ.get("RUNNER_ENVIRONMENT") == "github-hosted"
            and os.environ.get("RUNNER_OS") == "Windows", "context_runner")
    require(os.environ.get("GITHUB_REF") == "refs/heads/main"
            and os.environ.get("GITHUB_WORKFLOW_REF") == "ayukyo/icode/.github/workflows/ci.yml@refs/heads/main"
            and os.environ.get("GITHUB_WORKFLOW_SHA") == value["source_sha"], "context_workflow")
    require(os.environ.get("ICODE_CI_POSITIVE_LOOPBACK_ADMIN") == "1"
            and os.environ.get("ICODE_CI_POSITIVE_LOOPBACK_DEDICATED_WRITER") == "1", "context_authorization")
    require(all(os.environ.get(key) == item for key, item in expected.items()), "context_environment")
    # These environment values are not a remote attestation. The caller must be
    # the fixed trusted workflow parent and must possess a real admin token.
    return dict(value)


def manifest_from(value):
    fields = set(policy.Manifest.__dataclass_fields__)
    require(type(value) is dict and set(value) == fields and type(value["admission"]) is dict
            and set(value["admission"]) == set(policy.AdmissionFacts.__dataclass_fields__), "operation_schema")
    body = dict(value)
    body["admission"] = policy.AdmissionFacts(**body["admission"])
    return policy.Manifest(**body)


def file_identity(value):
    require(type(value) is list and len(value) == 2 and integer(value[0], 0, 0xFFFFFFFF)
            and integer(value[1], 1, (1 << 64) - 1), "identity_schema")


def security(value):
    require(type(value) is dict and set(value) == {"owner_binary", "dacl_binary", "protected"}
            and type(value["protected"]) is bool, "security_schema")
    for name in ("owner_binary", "dacl_binary"):
        require(type(value[name]) is str and 0 < len(value[name]) <= 131070
                and len(value[name]) % 2 == 0 and re.fullmatch(r"[0-9a-f]+", value[name]), "security_hex")


def effective(value):
    require(type(value) is dict and set(value) == {"api_completed", "access_status", "granted", "privilege_bytes"}
            and value["api_completed"] is True and type(value["access_status"]) is bool
            and integer(value["granted"], 0, 0xFFFFFFFF) and integer(value["privilege_bytes"], 0, 16384)
            and (value["access_status"] or value["granted"] == 0), "effective_schema")


def image_info(value):
    require(type(value) is dict and set(value) == {"identity", "links", "attributes", "size"}, "image_schema")
    file_identity(value["identity"])
    require(integer(value["links"], 1, 0xFFFFFFFF) and integer(value["attributes"], 0, 0xFFFFFFFF)
            and not value["attributes"] & (0x10 | 0x400) and integer(value["size"], 0, (1 << 64) - 1), "image_shape")


def version(value):
    require(type(value) is list and len(value) == 4 and all(integer(item, 0, 65535) for item in value), "version_schema")


def image_proof(value, matrix):
    require(type(value) is dict and set(value) == {"file_info", "sha256", "machine", "file_version", "product_version"}, "image_proof_schema")
    image_info(value["file_info"])
    require(type(value["sha256"]) is str and re.fullmatch(r"[0-9a-f]{64}", value["sha256"])
            and type(value["machine"]) is int and value["machine"] == {"x64": 0x8664, "ARM64": 0xAA64}[matrix], "image_proof_binding")
    version(value["file_version"])
    version(value["product_version"])


def admission(value, matrix, *, private_images=(), system_directory=None):
    # Parsing is not OS authority. Native supplies the exact protected root's
    # frozen image set and real GetSystemDirectory result during verification.
    approved_private = {Path(path) for path in private_images}
    require(type(value) is dict and set(value) == {"schema", "routes", "root_security", "root_effective",
            "sdk_layout_verified", "python_binding_verified", "loader_verified", "canaries_verified",
            "loader_images", "tool", "runner_arch_raw"} and type(value["schema"]) is int and value["schema"] == 1, "admission_schema")
    require(all(value[name] is True for name in ("sdk_layout_verified", "python_binding_verified", "loader_verified", "canaries_verified"))
            and value["runner_arch_raw"] == {"x64": "X64", "ARM64": "ARM64"}[matrix], "admission_facts")
    security(value["root_security"])
    require(value["root_security"]["protected"] is True, "admission_root")
    effective(value["root_effective"])
    require((value["root_effective"]["granted"] & LEAF_MUTATION) == 0, "admission_root_rights")
    for name in ("routes", "loader_images", "tool"):
        require(type(value[name]) is list and 0 < len(value[name]) <= 100000, "admission_records")
        for item in value[name]:
            base = {"path", "identity", "security", "effective"}
            require(type(item) is dict and set(item) in (base, base | {"file_info", "provenance"},
                    base | {"file_info", "file_version", "product_version", "provenance"}), "admission_record_schema")
            require(type(item["path"]) is str and Path(item["path"]).is_absolute(), "admission_record_path")
            file_identity(item["identity"])
            security(item["security"])
            effective(item["effective"])
            mask = LEAF_MUTATION if "file_info" in item else ROUTE_MUTATION
            require((item["effective"]["granted"] & mask) == 0, "admission_record_rights")
            if "file_info" in item:
                path = Path(item["path"])
                if path in approved_private:
                    require(item["file_info"] is None and item["provenance"] is None, "admission_private_image")
                else:
                    require((path.parent == Path(system_directory) if system_directory is not None
                             else path.parent.name.casefold() == "system32"), "admission_system_image_path")
                    require(item["file_info"] is not None and item["provenance"] is not None, "admission_system_image_proof")
                    image_info(item["file_info"])
                    require(item["identity"] == item["file_info"]["identity"], "admission_record_identity")
                    image_proof(item["provenance"], matrix)
                    require(item["provenance"]["file_info"] == item["file_info"], "admission_image_proof")
            if "file_version" in item:
                version(item["file_version"])
                version(item["product_version"])
                require(item["file_version"] == item["provenance"]["file_version"]
                        and item["product_version"] == item["provenance"]["product_version"], "admission_tool_version")


def ledger(data, *, private_root=None, system_directory=None):
    require(type(data) is dict and set(data) == FIELDS and type(data["schema"]) is int and data["schema"] == 1, "ledger_schema")
    context(data["context"])
    require(type(data["session"]) is str and re.fullmatch(r"[0-9a-f]{32}", data["session"]), "ledger_session")
    file_identity(data["root_identity"])
    require(type(data["account_name"]) is str and re.fullmatch(r"icodeprobe_[A-Za-z0-9]{1,9}", data["account_name"]), "ledger_account")
    require(data["phase"] in PHASES, "ledger_phase")
    for name in ("owned_intent", "add_verified", "delete_verified", "others_preserved", "exact_restoration"):
        require(type(data[name]) is bool, "ledger_bool")
    for name in ("first_error", "cleanup_error"):
        require(data[name] is None or type(data[name]) is str and data[name] in ERRORS, "ledger_error")
    for name in ("intent_ms", "operation_completed_ms", "prepared_ms"):
        require(data[name] is None or integer(data[name]), "ledger_clock")
    require(data["target_attributes"] is None or integer(data["target_attributes"], 0, 0xFFFFFFFF), "ledger_attributes")
    require(type(data["consumed"]) is dict and set(data["consumed"]) == set(SLOTS)
            and all(type(item) is bool for item in data["consumed"].values()), "ledger_consumed")
    require(type(data["file_identities"]) is dict and len(data["file_identities"]) <= 64, "ledger_files")
    for name, identity in data["file_identities"].items():
        Store._leaf(name)
        require(type(identity) is list and len(identity) == 2 and integer(identity[0], 0, 0xFFFFFFFF)
                and integer(identity[1], 1, (1 << 64) - 1), "ledger_file_identity")
    require(type(data["commands"]) is list and len(data["commands"]) <= 32, "ledger_commands")
    for number, record in enumerate(data["commands"]):
        require(type(record) is dict and set(record) == COMMAND, "ledger_command_schema")
        require(record["kind"] in ("get", "abi", "add", "delete") and record["state"] in COMMAND_STATES
                and record["job"] == "Local\\ICODE.Positive." + data["session"] + ".command." + str(number)
                and record["output"] == "command-" + str(number) + ".out", "ledger_command_binding")
        for field in ("pid", "process_created", "exit_code", "resume_returned"):
            maximum = (1 << 64) - 1 if field == "process_created" else 0xFFFFFFFF
            require(record[field] is None or integer(record[field], 1 if field in ("pid", "process_created") else 0, maximum), "ledger_command_number")
        require(type(record["resume_permitted"]) is bool and type(record["timed_out"]) is bool
                and type(record["reaped"]) is bool and (record["resume_attempted"] is None
                or type(record["resume_attempted"]) is bool), "ledger_command_bool")
        require((record["pid"] is None) == (record["process_created"] is None), "ledger_command_identity")
        if record["resume_permitted"]:
            require(record["pid"] is not None, "ledger_command_ready")
        if record["state"] == "allocated":
            require(record["pid"] is None and record["resume_permitted"] is False
                    and record["resume_attempted"] is False, "ledger_command_allocated")
        if record["state"] == "ready":
            require(record["resume_permitted"] is True and record["reaped"] is False, "ledger_command_ready")
        if record["state"] in ("reaped", "reaped_after_failure"):
            require(record["reaped"] is True, "ledger_command_reaped")
        if record["state"] == "cleanup_unknown":
            require(record["reaped"] is False, "ledger_command_unknown")
        if record["kind"] in ("add", "delete"):
            require(data["owned_intent"] and data["operation_manifest"] is not None, "ledger_command_intent")
    require(sum(item["kind"] == "add" for item in data["commands"]) <= 1, "ledger_add_replay")
    require(type(data["observations"]) is dict and set(data["observations"]) <= {
        "baseline_first", "baseline", "after_add", "pre_delete", "post_delete"}, "ledger_observations")
    require(type(data["reads"]) is list and len(data["reads"]) <= 32, "ledger_reads")
    for item in data["reads"]:
        require(type(item) is dict and set(item) == {"started_ms", "finished_ms", "command_index", "raw_sha256", "reader_sha256"}, "ledger_read_schema")
        require(integer(item["started_ms"]) and integer(item["finished_ms"], item["started_ms"])
                and integer(item["command_index"], 0, len(data["commands"]) - 1)
                and data["commands"][item["command_index"]]["kind"] == "get", "ledger_read_command")
        require(all(type(item[key]) is str and re.fullmatch(r"[0-9a-f]{64}", item[key])
                    for key in ("raw_sha256", "reader_sha256")), "ledger_read_hash")
    # Import only after this module is fully initialized; no circular authority.
    from scripts.windows_positive_loopback_admin import _mapping, _bootstrap_expected
    for raw in data["observations"].values():
        _mapping(raw)
    if data["phase"] == "frozen":
        require(data["bootstrap"] is None and data["account_sid"] is None and data["parent"] is None, "ledger_frozen")
    else:
        require(type(data["account_sid"]) is str and data["account_sid"].startswith("S-1-5-21-"), "ledger_account_sid")
        policy.sid_bytes(data["account_sid"])
    if data["bootstrap"] is not None:
        _bootstrap_expected(data["bootstrap"])
        require(data["bootstrap"]["session"] == data["session"]
                and data["bootstrap"]["account_sid"] == data["account_sid"], "ledger_bootstrap")
        for key in CONTEXT:
            require(data["bootstrap"][key] == data["context"][key], "ledger_bootstrap_context")
        require(data["parent"] is not None and all(data["bootstrap"][key] == data["parent"][key]
                for key in ("pid", "process_created")), "ledger_bootstrap_parent")
        require(data["bootstrap"]["nonce"] == data["nonce"]
                and data["bootstrap"]["positive_profile"] == data["profile_names"][0]
                and data["bootstrap"]["reviewer_profile"] == data["profile_names"][1]
                and data["ports"] == [data["bootstrap"]["ipv4_port"], data["bootstrap"]["ipv6_port"]]
                and data["bootstrap"]["prepared_ms"] == data["prepared_ms"], "ledger_bootstrap_identity")
    if data["operation_manifest"] is not None:
        operation = manifest_from(data["operation_manifest"])
        require(data["bootstrap"] is not None and data["consumed"]["profile_created"], "ledger_operation_admission")
        for key in CONTEXT | {"account_sid", "pid", "process_created", "positive_profile", "reviewer_profile", "positive_sid", "reviewer_sid", "nonce", "ipv4_port", "ipv6_port"}:
            require(getattr(operation, key) == data["bootstrap"][key], "ledger_operation_binding")
        require(data["phase"] in {"bound", "add_intent", "added", "cleanup_intent", "cleaned"}
                and data["readonly_prepare"] is not None and data["parent"] is not None
                and data["outer_job"] is not None, "ledger_operation_phase")
        require({"baseline_first", "baseline"} <= set(data["observations"]), "ledger_baseline_missing")
        first = _mapping(data["observations"]["baseline_first"])
        baseline = _mapping(data["observations"]["baseline"])
        positive, reviewer = policy.sid_bytes(operation.positive_sid), policy.sid_bytes(operation.reviewer_sid)
        require(first == baseline and positive not in baseline and reviewer not in baseline,
                "ledger_baseline_not_owned")
    if data["owned_intent"]:
        require(data["operation_manifest"] is not None and data["intent_ms"] is not None
                and "baseline" in data["observations"], "ledger_intent")
        require(data["intent_ms"] == data["operation_manifest"]["started_ms"], "ledger_intent_clock")
        require(data["phase"] in {"add_intent", "added", "cleanup_intent", "cleaned"}, "ledger_owned_phase")
    else:
        require(data["phase"] in {"frozen", "prepared", "bound"} and data["intent_ms"] is None
                and data["target_attributes"] is None and not any(data[name] for name in
                ("add_verified", "delete_verified", "others_preserved", "exact_restoration")), "ledger_unowned_phase")
    if data["phase"] in {"bound", "add_intent", "added", "cleanup_intent", "cleaned"}:
        require(data["bootstrap"] is not None and data["readonly_prepare"] is not None
                and data["parent"] is not None and data["outer_job"] is not None, "ledger_admitted_phase")
    if "baseline" in data["observations"]:
        require("baseline_first" in data["observations"], "ledger_baseline_order")
    if any(name in data["observations"] for name in ("after_add", "pre_delete", "post_delete")):
        require(data["owned_intent"], "ledger_observation_ownership")
    if "after_add" in data["observations"]:
        require(any(item["kind"] == "add" for item in data["commands"]), "ledger_after_add_command")
    if "post_delete" in data["observations"]:
        require("pre_delete" in data["observations"], "ledger_delete_observation_order")
    if any(item["kind"] == "delete" for item in data["commands"]):
        require(data["phase"] in {"cleanup_intent", "cleaned"} and "pre_delete" in data["observations"], "ledger_delete_phase")
    if data["consumed"]["probe_finished"]:
        require(data["owned_intent"] and data["operation_manifest"] is not None and data["add_verified"], "ledger_finished_admission")
    if data["add_verified"]:
        require(data["owned_intent"] and data["phase"] in {"added", "cleanup_intent", "cleaned"}
                and "after_add" in data["observations"] and data["target_attributes"] is not None, "ledger_add_verified")
        expected_add = dict(baseline)
        expected_add[positive] = data["target_attributes"]
        require(_mapping(data["observations"]["after_add"]) == expected_add, "ledger_add_observation")
        require(any(item["kind"] == "add" and item["resume_permitted"] is True
                and item["resume_attempted"] is True and item["resume_returned"] == 1
                and item["reaped"] is True and item["timed_out"] is False and item["exit_code"] == 0
                for item in data["commands"]), "ledger_add_command_result")
    if data["phase"] == "added":
        require(data["add_verified"], "ledger_added_phase")
    require(data["delete_verified"] == data["others_preserved"], "ledger_delete_flags")
    if data["delete_verified"]:
        require(data["owned_intent"] and data["phase"] == "cleaned"
                and {"pre_delete", "post_delete"} <= set(data["observations"]), "ledger_delete_verified")
        expected_delete = _mapping(data["observations"]["pre_delete"])
        expected_delete.pop(positive, None)
        deleted = _mapping(data["observations"]["post_delete"])
        require(deleted == expected_delete and positive not in deleted and reviewer not in deleted, "ledger_delete_observation")
    if data["exact_restoration"]:
        require(data["phase"] == "cleaned" and data["first_error"] is None
                and integer(data["operation_completed_ms"])
                and data["operation_manifest"] is not None
                and data["operation_manifest"]["started_ms"] <= data["operation_completed_ms"] < data["operation_manifest"]["deadline_ms"], "ledger_restoration_clock")
        require(data["delete_verified"] and data["cleanup_error"] is None
                and _mapping(data["observations"]["post_delete"]) == baseline, "ledger_restoration_observation")
    require(type(data["frozen_files"]) is list and len(data["frozen_files"]) <= 100000
            and type(data["frozen_directories"]) is list and len(data["frozen_directories"]) <= 10000, "ledger_freeze_count")
    seen = set()
    for item in data["frozen_files"]:
        require(type(item) is dict and set(item) == {"path", "identity", "size", "sha256"}, "ledger_frozen_file")
        relative = Path(item["path"])
        require(type(item["path"]) is str and not relative.is_absolute() and relative.parts
                and not any(part in (".", "..") for part in relative.parts) and item["path"] not in seen, "ledger_frozen_path")
        seen.add(item["path"])
        require(type(item["identity"]) is list and len(item["identity"]) == 2
                and integer(item["identity"][0], 0, 0xFFFFFFFF) and integer(item["identity"][1], 1, (1 << 64) - 1)
                and integer(item["size"], 0, 268435456) and type(item["sha256"]) is str
                and re.fullmatch(r"[0-9a-f]{64}", item["sha256"]), "ledger_frozen_identity")
    for item in data["frozen_directories"]:
        require(type(item) is dict and set(item) == {"path", "identity"}
                and type(item["path"]) is str and type(item["identity"]) is list
                and len(item["identity"]) == 2 and all(integer(part, 0, (1 << 64) - 1) for part in item["identity"]), "ledger_frozen_directory")
    require(type(data["profile_names"]) is list and len(data["profile_names"]) == 2
            and len(set(data["profile_names"])) == 2
            and all(type(item) is str and re.fullmatch(r"icode-[0-9a-f]{32}", item) for item in data["profile_names"]), "ledger_profiles")
    require(type(data["nonce"]) is str and re.fullmatch(r"[0-9a-f]{32}", data["nonce"]), "ledger_nonce")
    require(type(data["ports"]) is list and len(data["ports"]) in (0, 2)
            and all(integer(item, 1, 65535) for item in data["ports"]), "ledger_ports")
    if data["parent"] is not None:
        require(type(data["parent"]) is dict and set(data["parent"]) == {"pid", "process_created"}
                and integer(data["parent"]["pid"], 1, 0xFFFFFFFF)
                and integer(data["parent"]["process_created"], 1, (1 << 64) - 1), "ledger_parent")
    require(data["outer_job"] is None or data["outer_job"] == "Local\\ICODE.Positive." + data["session"] + ".parent", "ledger_outer_job")
    if data["system_tool"] is not None:
        tool = data["system_tool"]
        require(type(tool) is dict and set(tool) == {"path", "identity", "sha256", "machine", "file_info", "file_version", "product_version"}, "ledger_tool")
        require(type(tool["path"]) is str and Path(tool["path"]).is_absolute()
                and Path(tool["path"]).name == "CheckNetIsolation.exe" and type(tool["sha256"]) is str
                and re.fullmatch(r"[0-9a-f]{64}", tool["sha256"])
                and type(tool["machine"]) is int and tool["machine"] == {"x64": 0x8664, "ARM64": 0xAA64}[data["context"]["matrix"]], "ledger_tool_binding")
        file_identity(tool["identity"])
        image_info(tool["file_info"])
        require(tool["identity"] == tool["file_info"]["identity"], "ledger_tool_identity")
        version(tool["file_version"])
        version(tool["product_version"])
    if data["readonly_prepare"] is not None:
        private_images = () if private_root is None else (
            Path(private_root) / item["path"] for item in data["frozen_files"])
        admission(data["readonly_prepare"], data["context"]["matrix"],
                  private_images=private_images, system_directory=system_directory)
    return data


class Native:
    def now_ms(self):
        return int(time.monotonic() * 1000)

    def checkpoint(self):
        limit = getattr(self, "recovery_deadline", None)
        require(limit is None or self.now_ms() < limit, "recovery_deadline")

    def _run(self, store, kind):
        self.checkpoint()
        limit = getattr(self, "recovery_deadline", None)
        if limit is None:
            result = run_fixed(store, kind)
        else:
            remaining = min(5000, limit - self.now_ms())
            require(remaining > 0, "recovery_deadline")
            result = run_fixed(store, kind, budget_ms=remaining)
        self.checkpoint()
        return result

    def _account(self, w, name, *, absent=False, allow_absent=False):
        size, domain_size, use = t.DWORD(), t.DWORD(), t.DWORD()
        c.set_last_error(0)
        ok = w.a.LookupAccountNameW(None, name, None, c.byref(size), None, c.byref(domain_size), c.byref(use))
        error = c.get_last_error()
        if absent:
            require(not ok and error == 1332, "account_must_not_exist")
            return None
        if allow_absent and not ok and error == 1332:
            return None
        require(not ok and error == 122 and 12 <= size.value <= 68 and 0 < domain_size.value <= 32768, "account_size")
        allocated = int(size.value)
        sid = c.create_string_buffer(allocated)
        domain = c.create_unicode_buffer(domain_size.value)
        checked(w.a.LookupAccountNameW(None, name, sid, c.byref(size), domain, c.byref(domain_size), c.byref(use)), "account_lookup")
        require(size.value <= allocated and use.value == 1 and w.a.IsValidSid(sid), "account_identity")
        length = int(w.a.GetLengthSid(sid))
        require(12 <= length <= allocated, "account_sid_length")
        result = _text_sid(c.string_at(sid, length))
        require(result.startswith("S-1-5-21-"), "account_not_local_user")
        return result

    def _derived(self, w, name):
        pointer = c.c_void_p()
        require(int(w.u.DeriveAppContainerSidFromAppContainerName(name, c.byref(pointer))) == 0 and pointer.value, "derive_sid")
        try:
            require(bool(w.a.IsValidSid(pointer)), "derive_invalid_sid")
            length = int(w.a.GetLengthSid(pointer))
            require(12 <= length <= 68, "derive_sid_size")
            value = _text_sid(c.string_at(pointer, length))
            require(value.startswith("S-1-15-2-"), "derive_sid_domain")
            return value
        finally:
            _release_owned(sys.exception(),
                lambda: checked(not w.a.FreeSid(pointer), 'derive_free_sid'),
            )

    def _copy_file(self, store, source, relative):
        source = Path(source).absolute()
        for path in reversed((source, *source.parents)):
            require(not path.is_symlink() and not getattr(path.lstat(), "st_file_attributes", 0) & 0x400, "freeze_reparse")
        require(source.resolve(strict=True) == source, "freeze_namespace")
        handle = store.w.k.CreateFileW(str(source), 0x80020080, 1, None, 3, 0x00200000, None)
        require(handle not in (None, c.c_void_p(-1).value), "freeze_source_open")
        out = None
        try:
            identity = store.w.info(handle)
            size = source.stat().st_size
            require(0 <= size <= 268435456, "freeze_size")
            raw = store.w.read(handle, size)
            require(len(raw) == size and store.w.info(handle) == identity, "freeze_source_changed")
            target = store.root / relative
            out, target_id = store.w.open_file(target, PRIVATE, create=True, write=True)
            store.w.write(out, raw)
            return dict(path=Path(relative).as_posix(), identity=list(target_id), size=size, sha256=hashlib.sha256(raw).hexdigest())
        finally:
            _release_owned(sys.exception(),
                lambda: store.w.close(out) if out else None,
                lambda: store.w.close(handle),
            )

    def _source_tree(self, store, source, destination, deadline):
        source = Path(source).absolute()
        pins, original = [], {}
        def failed(error):
            raise Failure("freeze_enumeration") from error
        def members():
            for current, directories, files in os.walk(source, topdown=True, followlinks=False, onerror=failed):
                require(time.monotonic() <= deadline, "freeze_deadline")
                directories[:] = [name for name in directories if name.casefold() not in
                                  {"site-packages", "__pycache__", "test", "tests", "idlelib", "tkinter", "ensurepip"}]
                yield Path(current), tuple(sorted(directories)), tuple(sorted(files))
        try:
            # Preserve the original namespace, not the resolved link target.
            for path in reversed((source, *source.parents)):
                require(not path.is_symlink() and not getattr(path.lstat(), "st_file_attributes", 0) & 0x400, "freeze_reparse")
                handle = store.w.pin_ancestor(path, observe_only=True)
                pins.append((path, handle, None))
                pins[-1] = (path, handle, store.w.info(handle, directory=True))
            require(source.resolve(strict=True) == source, "freeze_source_namespace")
            for path, directories, files in members():
                require(len(original) < 10000, "freeze_directory_count")
                handle = store.w.pin_ancestor(path, observe_only=True)
                pins.append((path, handle, None))
                identity = store.w.info(handle, directory=True)
                pins[-1] = (path, handle, identity)
                original[path] = (directories, files, identity)
            records = copy_private_tree(store, source, destination, deadline=deadline)
            after = {}
            for path, directories, files in members():
                handle = store.w.pin_ancestor(path, observe_only=True)
                try:
                    after[path] = (directories, files, store.w.info(handle, directory=True))
                finally:
                    _release_owned(sys.exception(),
                        lambda: store.w.close(handle),
                    )
            require(after == original, "freeze_directory_changed")
            for path, handle, identity in pins:
                require(store.w.info(handle, directory=True) == identity, "freeze_directory_changed")
            # Re-read each original file using a held no-write/no-delete handle;
            # compare its bytes with the complete protected copy's digest.
            for item in records:
                relative = Path(item["path"]).relative_to(Path(destination))
                path = source / relative
                handle = store.w.k.CreateFileW(str(path), 0x80020080, 1, None, 3, 0x00200000, None)
                require(handle not in (None, c.c_void_p(-1).value), "freeze_source_reopen")
                try:
                    identity = store.w.info(handle)
                    raw = store.w.read(handle, item["size"])
                    require(len(raw) == item["size"] and hashlib.sha256(raw).hexdigest() == item["sha256"]
                            and store.w.info(handle) == identity, "freeze_source_changed")
                finally:
                    _release_owned(sys.exception(),
                        lambda: store.w.close(handle),
                    )
                require(time.monotonic() <= deadline, "freeze_deadline")
            return records
        finally:
            _release_owned(sys.exception(),
                *(lambda _path=_path, handle=handle, _identity=_identity: store.w.close(handle) for (_path, handle, _identity) in reversed(pins)),
            )

    def freeze(self, trusted_context, account_name):
        w = Win32()
        w.assert_admin()
        trusted_context = context(trusted_context)
        require(type(account_name) is str and re.fullmatch(r"icodeprobe_[A-Za-z0-9]{1,9}", account_name), "account_name")
        self._account(w, account_name, absent=True)
        # Only the originally trusted parent may enter this path, before any
        # temporary account exists. No code is copied from a request field.
        checkout = Path(__file__).resolve(strict=True).parents[1]
        require(Path(os.environ.get("GITHUB_WORKSPACE", "")).resolve(strict=True) == checkout, "checkout_origin")
        runtime = Path(sys.base_prefix).absolute()
        require(Path(sys.executable).absolute() == runtime / "python.exe", "runtime_origin")
        for parent in (runtime, runtime.parent):
            require(not (parent / "pyvenv.cfg").exists(), "runtime_cfg")
            require(not list(parent.glob("*._pth")), "runtime_pth")
        temp = c.create_unicode_buffer(32768)
        length = w.k.GetTempPathW(len(temp), temp)
        require(0 < length < len(temp), "temp_root")
        parent = Path(temp.value).resolve(strict=True)
        # One protected instance per exact candidate/run/job/matrix. CREATE_NEW
        # directory admission rejects repeat freeze instead of minting a second
        # authority. The independent session inside remains unpredictable.
        root = parent / ("icode-positive-admin-" + hashlib.sha256(wire(trusted_context)).hexdigest()[:32])
        data = dict(schema=1, context=trusted_context, account_name=account_name, account_sid=None,
                    session=uuid.uuid4().hex, root_identity=None, phase="frozen", bootstrap=None,
                    operation_manifest=None, owned_intent=False, intent_ms=None, target_attributes=None,
                    commands=[], observations={}, file_identities={}, frozen_files=[], frozen_directories=[],
                    system_tool=None, consumed={key: False for key in SLOTS}, parent=None, outer_job=None,
                    first_error=None, cleanup_error=None, add_verified=False, delete_verified=False,
                    others_preserved=False, exact_restoration=False, readonly_prepare=None,
                    operation_completed_ms=None, prepared_ms=None,
                    profile_names=["icode-" + uuid.uuid4().hex, "icode-" + uuid.uuid4().hex],
                    nonce=uuid.uuid4().hex, ports=[], reads=[])
        store = Store.create(root, data)
        try:
            deadline = time.monotonic() + 180
            store.create_directory("runtime")
            records = []
            for name in ("python.exe", "python312.dll", "python3.dll", "vcruntime140.dll", "vcruntime140_1.dll"):
                source = runtime / name
                # Optional VC CRT variants may live solely in System32; record
                # present runtime copies, then loader admission checks reality.
                if name in ("vcruntime140.dll", "vcruntime140_1.dll") and not source.exists():
                    continue
                records.append(self._copy_file(store, source, "runtime/" + name))
            for name in ("Lib", "DLLs"):
                records.extend(self._source_tree(store, runtime / name, "runtime/" + name, deadline))
            zip_source = runtime / "python312.zip"
            if zip_source.exists():
                records.append(self._copy_file(store, zip_source, "runtime/python312.zip"))
            store.create_directory("trusted")
            store.create_directory("trusted/scripts")
            store.create_directory("trusted/src")
            store.create_directory("trusted/src/icode")
            names = ("windows_positive_loopback_admin", "windows_positive_loopback_admin_native",
                     "windows_positive_loopback_admin_win32", "windows_positive_loopback_admin_store",
                     "windows_positive_loopback_admin_jobs", "windows_positive_loopback_full_get",
                     "windows_positive_loopback_admin_entry")
            for name in names:
                records.append(self._copy_file(store, checkout / "scripts" / (name + ".py"), "trusted/scripts/" + name + ".py"))
            records.append(self._copy_file(store, checkout / "src/icode/windows_positive_loopback_policy.py",
                                           "trusted/src/icode/windows_positive_loopback_policy.py"))
            for name in ("trusted/scripts/__init__.py", "trusted/src/icode/__init__.py"):
                handle, identity = store.w.open_file(root / name, PRIVATE, create=True, write=True)
                try:
                    store.w.write(handle, b"")
                    records.append(dict(path=name, identity=list(identity), size=0, sha256=hashlib.sha256(b"").hexdigest()))
                finally:
                    _release_owned(sys.exception(),
                        lambda: store.w.close(handle),
                    )
            records.append(self._copy_file(store, checkout / "build/positive-admin-abi/Release/icode-positive-loopback-admin-abi.exe",
                                           "icode-positive-loopback-admin-abi.exe"))
            store.data["frozen_files"] = records
            directories = []
            def failed(error):
                raise Failure("freeze_enumeration") from error
            for current, children, files in os.walk(root, followlinks=False, onerror=failed):
                if Path(current) == root:
                    children[:] = [name for name in children if name in ("runtime", "trusted")]
                handle = store.w.pin_ancestor(Path(current))
                try:
                    directories.append(dict(path=Path(current).relative_to(root).as_posix(),
                                            identity=list(store.w.info(handle, directory=True))))
                finally:
                    _release_owned(sys.exception(),
                        lambda: store.w.close(handle),
                    )
            store.data["frozen_directories"] = directories
            require(time.monotonic() <= deadline, "freeze_deadline")
            self._account(store.w, account_name, absent=True)
            store.data["prepared_ms"] = self.now_ms()
            ledger(store.data, private_root=store.root, system_directory=store.w.system_directory)
            store.flush()
            return root
        finally:
            _release_owned(sys.exception(),
                lambda: store.close(),
            )

    def reopen(self, root):
        store = Store(root)
        try:
            self.verify_store(store)
            return store
        except BaseException:
            _release_owned(sys.exception(), lambda: store.close())
            raise

    def verify_store(self, store):
        self.checkpoint()
        store.w.assert_admin()
        ledger(store.data, private_root=store.root, system_directory=store.w.system_directory)
        durable = ledger(decode(store.read("ledger.json", PRIVATE, 8388608), 8388608),
                         private_root=store.root, system_directory=store.w.system_directory)
        require(wire(durable) == wire(store.data), "ledger_memory_not_durable")
        require(store.root.name == "icode-positive-admin-" + hashlib.sha256(wire(store.data["context"])).hexdigest()[:32], "root_name")
        require(list(store.w.info(store.root_handle, directory=True)) == store.data["root_identity"], "root_identity")
        root_sddl = PRIVATE if store.data["account_sid"] is None else PRIVATE + "(A;;0x1200a9;;;" + store.data["account_sid"] + ")"
        store.w.verify_security(store.root_handle, root_sddl)
        for item in store.data["frozen_directories"]:
            relative = Path(item["path"])
            require(not relative.is_absolute() and not any(part == ".." for part in relative.parts), "frozen_directory_path")
            handle = store.w.pin_ancestor(store.root / relative)
            try:
                require(list(store.w.info(handle, directory=True)) == item["identity"], "frozen_directory_identity")
                # Root alone has explicit traverse; every loaded child is private.
                store.w.verify_security(handle, root_sddl if relative == Path(".") else PRIVATE)
            finally:
                _release_owned(sys.exception(),
                    lambda: store.w.close(handle),
                )
        for item in store.data["frozen_files"]:
            self.checkpoint()
            handle, identity = store.w.open_file(store.root / item["path"], PRIVATE)
            try:
                require(list(identity) == item["identity"], "frozen_file_identity")
                raw = store.w.read(handle, item["size"])
                require(len(raw) == item["size"] and hashlib.sha256(raw).hexdigest() == item["sha256"], "frozen_file_hash")
                require(store.w.info(handle) == identity, "frozen_file_changed")
                self.checkpoint()
            finally:
                _release_owned(sys.exception(),
                    lambda: store.w.close(handle),
                )
        # Full membership, including absent startup slots: an extra importable
        # file is not made trustworthy merely because recorded files match.
        actual_files, actual_directories = set(), {"."}
        def failed(error):
            raise Failure("frozen_enumeration") from error
        for base in ("runtime", "trusted"):
            for current, directories, files in os.walk(store.root / base, followlinks=False, onerror=failed):
                path = Path(current)
                require(not path.is_symlink() and not getattr(path.lstat(), "st_file_attributes", 0) & 0x400, "frozen_reparse")
                actual_directories.add(path.relative_to(store.root).as_posix())
                for name in directories + files:
                    child = path / name
                    require(not child.is_symlink() and not getattr(child.lstat(), "st_file_attributes", 0) & 0x400, "frozen_reparse")
                actual_files.update((path / name).relative_to(store.root).as_posix() for name in files)
        expected_files = {item["path"] for item in store.data["frozen_files"] if item["path"].startswith(("runtime/", "trusted/"))}
        require(actual_files == expected_files and actual_directories == {
            item["path"] for item in store.data["frozen_directories"]}, "frozen_membership")
        for path in (store.root, store.root / "runtime"):
            require(not (path / "pyvenv.cfg").exists() and not list(path.glob("*._pth")), "frozen_layout")
        zip_item = [item for item in store.data["frozen_files"] if item["path"] == "runtime/python312.zip"]
        require((store.root / "runtime/python312.zip").exists() == bool(zip_item), "frozen_zip_slot")
        if store.data["account_sid"] is not None:
            require(self._account(store.w, store.data["account_name"], allow_absent=True) in
                    (None, store.data["account_sid"]), "account_rebound")
        if store.data["readonly_prepare"] is not None:
            observation = store.data["readonly_prepare"]
            private_images = {store.root / item["path"] for item in store.data["frozen_files"]}
            records = observation["routes"] + observation["loader_images"] + observation["tool"]
            for item in records:
                path = Path(item["path"])
                require(path.is_absolute() and path.resolve(strict=True) == path, "admission_path_changed")
                image = "file_info" in item
                handle = None
                try:
                    if image:
                        private = path in private_images
                        require((private and item["file_info"] is None and item["provenance"] is None)
                                or (not private and path.parent == store.w.system_directory
                                    and item["file_info"] is not None and item["provenance"] is not None), "admission_image_role")
                        handle = store.w.k.CreateFileW(str(path), 0x80020080, 1, None, 3, 0x00200000, None)
                        require(handle not in (None, c.c_void_p(-1).value), "admission_image_reopen")
                        if private:
                            require(list(store.w.info(handle)) == item["identity"], "admission_image_changed")
                        else:
                            require(self._image_info(store, handle, path) == item["file_info"], "admission_image_changed")
                            proof = self._image_provenance(store, handle, path,
                                dll=path.name != "CheckNetIsolation.exe")
                            require(proof == item["provenance"], "admission_image_proof_changed")
                    else:
                        handle = store.w.pin_ancestor(path, observe_only=True)
                        require(list(store.w.info(handle, directory=True)) == item["identity"], "admission_route_changed")
                    require(store.w.observe_security(handle) == item["security"], "admission_security_changed")
                finally:
                    _release_owned(sys.exception(),
                        lambda: store.w.close(handle) if handle and handle != c.c_void_p(-1).value else None,
                    )
        self.checkpoint()
        return store

    def _image_info(self, store, handle, path):
        # Only this fixed OS role admits shared-file hardlinks. Private Store
        # and frozen copies continue using Win32.info's links==1 contract.
        require(Path(path).parent == store.w.system_directory, "system_image_role")
        info = abi.FILE_INFO()
        checked(store.w.k.GetFileInformationByHandle(handle, c.byref(info)), "system_image_information")
        require(not info.attributes & (0x10 | 0x400) and info.links >= 1, "system_image_shape")
        identity = [int(info.volume), (int(info.index_high) << 32) | int(info.index_low)]
        require(identity[1] > 0, "system_image_identity")
        return dict(identity=identity, links=int(info.links), attributes=int(info.attributes),
                    size=(int(info.size_high) << 32) | int(info.size_low))

    def _image_provenance(self, store, handle, path, *, dll):
        # Fixed OS roles only, never selected by a client request. Versions are
        # observed OS versions, not required to equal the Python version.
        require(type(dll) is bool and Path(path).parent == store.w.system_directory, "system_image_role")
        require((dll and Path(path).suffix.casefold() == ".dll")
                or (not dll and Path(path).name == "CheckNetIsolation.exe"), "system_image_role")
        metadata = self._image_info(store, handle, path)
        raw = store.w.read(handle, 16777216)
        require(len(raw) >= 256 and raw[:2] == b"MZ" and len(raw) == metadata["size"], "image_pe")
        offset = int.from_bytes(raw[60:64], "little")
        require(64 <= offset <= len(raw) - 24 and raw[offset:offset + 4] == b"PE\0\0", "image_pe")
        machine = int.from_bytes(raw[offset + 4:offset + 6], "little")
        require(machine == {"x64": 0x8664, "ARM64": 0xAA64}[store.data["context"]["matrix"]], "image_machine")
        require(bool(int.from_bytes(raw[offset + 22:offset + 24], "little") & 0x2000) == dll, "image_kind")
        final = c.create_unicode_buffer(32768)
        length = store.w.k.GetFinalPathNameByHandleW(handle, final, len(final), 0)
        require(0 < length < len(final) and os.path.normcase(final.value.removeprefix("\\\\?\\")) == os.path.normcase(str(path)), "image_namespace")
        library = c.WinDLL(str(store.w.system_directory / "version.dll"), use_last_error=True, winmode=0x800)
        if not hasattr(store, "version_libraries"):
            store.version_libraries = []
        store.version_libraries.append(library)
        library.GetFileVersionInfoSizeW.restype = t.DWORD
        library.GetFileVersionInfoSizeW.argtypes = [t.LPCWSTR, c.POINTER(t.DWORD)]
        library.GetFileVersionInfoW.restype = t.BOOL
        library.GetFileVersionInfoW.argtypes = [t.LPCWSTR, t.DWORD, t.DWORD, c.c_void_p]
        library.VerQueryValueW.restype = t.BOOL
        library.VerQueryValueW.argtypes = [c.c_void_p, t.LPCWSTR, c.POINTER(c.c_void_p), c.POINTER(t.UINT)]
        unused = t.DWORD()
        size = int(library.GetFileVersionInfoSizeW(str(path), c.byref(unused)))
        require(52 <= size <= 1048576, "image_version_size")
        buffer = c.create_string_buffer(size)
        checked(library.GetFileVersionInfoW(str(path), 0, size, buffer), "image_version_read")
        pointer, count = c.c_void_p(), t.UINT()
        checked(library.VerQueryValueW(buffer, "\\", c.byref(pointer), c.byref(count)), "image_version_query")
        require(pointer.value is not None and c.addressof(buffer) <= pointer.value
                and pointer.value + count.value <= c.addressof(buffer) + len(buffer) and count.value == 52, "image_version_pointer")
        value = c.string_at(pointer, 52)
        words = [int.from_bytes(value[index:index + 4], "little") for index in range(0, 52, 4)]
        require(words[0] == 0xFEEF04BD and words[1] == 0x10000 and words[9] == (2 if dll else 1), "image_version_resource")
        require(self._image_info(store, handle, path) == metadata, "image_changed")
        return dict(file_info=metadata, sha256=hashlib.sha256(raw).hexdigest(), machine=machine,
                    file_version=[words[2] >> 16, words[2] & 65535, words[3] >> 16, words[3] & 65535],
                    product_version=[words[4] >> 16, words[4] & 65535, words[5] >> 16, words[5] & 65535])

    def _tool(self, store):
        path = store.w.system_directory / "CheckNetIsolation.exe"
        handle = store.w.k.CreateFileW(str(path), 0x80020080, 1, None, 3, 0x00200000, None)
        require(handle not in (None, c.c_void_p(-1).value), "tool_open")
        try:
            proof = self._image_provenance(store, handle, path, dll=False)
            record = dict(path=str(path), identity=proof["file_info"]["identity"], **proof)
            old = store.data["system_tool"]
            require(old is None or old == record, "tool_changed")
            store.handles.append(handle)
            handle = None
            return record
        finally:
            _release_owned(sys.exception(),
                lambda: store.w.close(handle) if handle else None,
            )

    def prepare(self, root, account_sid):
        store = self.reopen(root)
        try:
            require(store.data["phase"] == "frozen", "prepare_reentry")
            require(type(account_sid) is str and self._account(store.w, store.data["account_name"]) == account_sid, "account_binding")
            policy.sid_bytes(account_sid)
            store.data["account_sid"] = account_sid
            writable_root, _ = store.w.open_file(store.root, PRIVATE, directory=True, write=True)
            try:
                store.w.set_root_dacl(writable_root, PRIVATE, PRIVATE + "(A;;0x1200a9;;;" + account_sid + ")")
            finally:
                _release_owned(sys.exception(),
                    lambda: store.w.close(writable_root),
                )
            endpoints = []
            for family, host in ((socket.AF_INET, "127.0.0.1"), (socket.AF_INET6, "::1")):
                listener = socket.socket(family, socket.SOCK_STREAM)
                try:
                    listener.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
                    listener.bind((host, 0))
                    endpoints.append(listener.getsockname()[1])
                finally:
                    _release_owned(sys.exception(), listener.close)
            store.data["ports"] = endpoints
            store.data["system_tool"] = self._tool(store)
            for name in SLOTS.values():
                store.write(name, b"", "request", create=True)
            for name in PUBLIC.values():
                store.write(name, b"", "public", create=True)
            store.write("readonly-private.canary", b"private", create=True)
            store.write("readonly-public.canary", b"public", "public", create=True)
            store.write("readonly-request.canary", b"", "request", create=True)
            require(store.data["prepared_ms"] is not None and self.now_ms() < store.data["prepared_ms"] + 180000, "preparation_deadline")
            store.data.update(phase="prepared")
            store.flush()
            self.verify_store(store)
            return store
        except BaseException:
            _release_owned(sys.exception(), lambda: store.close())
            raise

    def _process(self, store, identity, *, allow_gone=False):
        handle = store.w.k.OpenProcess(0x00101501, False, identity["pid"])
        if not handle:
            require(allow_gone and c.get_last_error() == 87, "process_open")
            return None
        transferred = False
        try:
            created = store.w.process_created(handle)
            if created != identity["process_created"]:
                require(allow_gone, "process_reused")
                return None
            if allow_gone and store.w.k.WaitForSingleObject(handle, 0) == 0:
                return None
            transferred = True
            return handle
        finally:
            _release_owned(sys.exception(),
                lambda: store.w.close(handle) if not transferred else None,
            )

    def attach_parent(self, store, pid):
        self.verify_store(store)
        require(store.data["phase"] == "prepared" and store.data["parent"] is None
                and integer(pid, 1, 0xFFFFFFFF), "attach_phase")
        process = store.w.k.OpenProcess(0x00101501, False, pid)
        require(bool(process), "parent_open")
        job = None
        authenticated = transferred = False
        try:
            require(store.w.k.WaitForSingleObject(process, 0) == 258
                    and store.w.process_user(process) == store.data["account_sid"], "parent_identity")
            created = store.w.process_created(process)
            require(integer(created, 1, (1 << 64) - 1), "parent_creation")
            identity = dict(pid=pid, process_created=created)
            authenticated = True
            name = "Local\\ICODE.Positive." + store.data["session"] + ".parent"
            job = create_job(store, name)
            checked(store.w.k.AssignProcessToJobObject(job, process), "parent_assign_job")
            inside = t.BOOL()
            checked(store.w.k.IsProcessInJob(process, job, c.byref(inside)), "parent_membership")
            require(inside.value and store.w.job_pids(job) == (pid,), "parent_job_exact")
            store.data.update(parent=identity, outer_job=name)
            store.flush()
            store.parent_handle, store.parent_job = process, job
            store.handles.extend((process, job))
            transferred = True
            process = job = None
            self.readonly_prepare(store)
            positive = self._derived(store.w, store.data["profile_names"][0])
            reviewer = self._derived(store.w, store.data["profile_names"][1])
            require(positive != reviewer, "profile_sid_collision")
            bootstrap = dict(schema=1, domain="icode_positive_bootstrap_v1", **store.data["context"],
                             session=store.data["session"], account_sid=store.data["account_sid"], **identity,
                             positive_profile=store.data["profile_names"][0], reviewer_profile=store.data["profile_names"][1],
                             positive_sid=positive, reviewer_sid=reviewer, nonce=store.data["nonce"],
                             ipv4_port=store.data["ports"][0], ipv6_port=store.data["ports"][1],
                             prepared_ms=store.data["prepared_ms"], preparation_deadline_ms=store.data["prepared_ms"] + 180000)
            from scripts.windows_positive_loopback_admin import _bootstrap_expected
            _bootstrap_expected(bootstrap)
            require(self.now_ms() < bootstrap["preparation_deadline_ms"], "preparation_deadline")
            store.data["bootstrap"] = bootstrap
            store.flush()
        except BaseException:
            # Holding a process handle is not termination authority. Only the
            # live/token/creation-authenticated exact object may be compensated;
            # after transfer the Store and trusted upper finally own cleanup.
            actions = []
            if process and authenticated and not transferred:
                def terminate_live_parent():
                    status = int(store.w.k.WaitForSingleObject(process, 0))
                    require(status in (0, 258), "attach_compensation_liveness")
                    if status == 0:
                        return
                    # Assign failure is neither proof of nonmembership nor of
                    # survival. Query the current association of this held
                    # process instead of inferring it from the API return.
                    if job:
                        member = t.BOOL()
                        checked(store.w.k.IsProcessInJob(process, job, c.byref(member)), "attach_compensation_membership")
                        if member.value:
                            checked(store.w.k.TerminateJobObject(job, 1), "attach_terminate_job")
                            return
                    checked(store.w.k.TerminateProcess(process, 1), "attach_terminate_process")
                actions.append(terminate_live_parent)
                if job:
                    # A signaled parent does not prove an empty Job: descendants
                    # remain an independently observed obligation or unknown.
                    actions.append(lambda: wait_empty(store, job, 2000))
                actions.append(lambda: checked(store.w.k.WaitForSingleObject(process, 2000) == 0, "attach_reap"))
            _release_owned(sys.exception(), *actions)
            raise
        finally:
            _release_owned(sys.exception(),
                lambda: store.w.close(process) if process else None,
                lambda: store.w.close(job) if job else None,
            )

    def _outer(self, store):
        name = store.data["outer_job"]
        require(type(name) is str, "outer_job_missing")
        job = store.w.k.OpenJobObjectW(0x1F003F, False, name)
        require(bool(job), "outer_job_open")
        try:
            store.w.verify_security(job, PRIVATE, object_type=6)
            return job
        except BaseException:
            _release_owned(sys.exception(), lambda: store.w.close(job))
            raise

    def verify_parent(self, store):
        self.verify_store(store)
        require(store.data["parent"] is not None and store.data["readonly_prepare"] is not None, "parent_unbound")
        require(self._account(store.w, store.data["account_name"]) == store.data["account_sid"], "parent_account_missing")
        parent = self._process(store, store.data["parent"])
        job = None
        try:
            job = self._outer(store)
            require(store.w.k.WaitForSingleObject(parent, 0) == 258
                    and store.w.process_user(parent) == store.data["account_sid"], "parent_not_live")
            inside = t.BOOL()
            checked(store.w.k.IsProcessInJob(parent, job, c.byref(inside)), "parent_job_query")
            require(bool(inside.value) and store.data["parent"]["pid"] in store.w.job_pids(job), "parent_not_in_job")
        finally:
            _release_owned(sys.exception(),
                lambda: store.w.close(job) if job else None,
                lambda: store.w.close(parent),
            )

    def parent_only(self, store):
        self.verify_parent(store)
        job = self._outer(store)
        try:
            return store.w.job_pids(job) == (store.data["parent"]["pid"],)
        finally:
            _release_owned(sys.exception(),
                lambda: store.w.close(job),
            )

    def stop_parent_job(self, store):
        if store.data["parent"] is None:
            return
        parent = self._process(store, store.data["parent"], allow_gone=True)
        job = None
        try:
            c.set_last_error(0)
            job = store.w.k.OpenJobObjectW(0x1F003F, False, store.data["outer_job"])
            if not job:
                require(c.get_last_error() == 2 and parent is None, "parent_job_unknown")
                return
            store.w.verify_security(job, PRIVATE, object_type=6)
            _release_owned(None,
                lambda: checked(store.w.k.TerminateJobObject(job, 1), "parent_terminate"),
                lambda: wait_empty(store, job, 2000),
                lambda: checked(store.w.k.WaitForSingleObject(parent, 2000) == 0, "parent_reap") if parent else None,
            )
        finally:
            _release_owned(sys.exception(),
                lambda: store.w.close(job) if job else None,
                lambda: store.w.close(parent) if parent else None,
            )

    def reap_commands(self, store):
        self.verify_store(store)
        persisted = decode(store.read("ledger.json", PRIVATE, 8388608), 8388608)
        ledger(persisted, private_root=store.root, system_directory=store.w.system_directory)
        require(persisted["session"] == store.data["session"], "recovery_session")
        for record in persisted["commands"]:
            self.checkpoint()
            identity = dict(pid=record["pid"], process_created=record["process_created"])
            process = self._process(store, identity, allow_gone=True) if record["pid"] is not None else None
            job = None
            try:
                c.set_last_error(0)
                job = store.w.k.OpenJobObjectW(0x1F003F, False, record["job"])
                if not job:
                    require(c.get_last_error() == 2 and process is None, "command_job_unknown")
                    require(record["pid"] is not None, "command_identity_unknown")
                    # Both the exact process identity and named Job are absent.
                    continue
                store.w.verify_security(job, PRIVATE, object_type=6)
                members = store.w.job_pids(job)
                if process:
                    inside = t.BOOL()
                    checked(store.w.k.IsProcessInJob(process, job, c.byref(inside)), "command_membership")
                    require(bool(inside.value) or store.w.k.WaitForSingleObject(process, 0) == 0, "command_not_owned")
                _release_owned(None,
                    lambda: checked(store.w.k.TerminateJobObject(job, 1), "recover_command_terminate"),
                    lambda: wait_empty(store, job, 2000),
                    lambda: checked(store.w.k.WaitForSingleObject(process, 2000) == 0, "recover_command_reap") if process else None,
                )
                if members and record["pid"] is None:
                    raise Failure("command_identity_unknown")
            finally:
                _release_owned(sys.exception(),
                    lambda: store.w.close(job) if job else None,
                    lambda: store.w.close(process) if process else None,
                )
            self.checkpoint()
        require(persisted["commands"] == store.data["commands"], "recovery_memory_not_durable")
        self.checkpoint()

    def has_add_attempt(self, store):
        persisted = ledger(decode(store.read("ledger.json", PRIVATE, 8388608), 8388608),
                           private_root=store.root, system_directory=store.w.system_directory)
        require(persisted["session"] == store.data["session"], "recovery_session")
        return any(record["kind"] == "add" and record["resume_permitted"] is True and record["resume_attempted"] is not False
                   and record["pid"] is not None and record["process_created"] is not None
                   for record in persisted["commands"])

    def bootstrap(self, store):
        self.verify_store(store)
        require(store.data["bootstrap"] is not None, "bootstrap_missing")
        return dict(store.data["bootstrap"])

    def freeze_operation(self, store):
        self.verify_parent(store)
        require(store.data["consumed"]["profile_created"] and store.data["operation_manifest"] is None
                and store.data["phase"] == "bound", "operation_reentry")
        baseline = store.data["observations"]
        from scripts.windows_positive_loopback_admin import _mapping
        require(_mapping(baseline["baseline_first"]) == _mapping(baseline["baseline"]), "operation_baseline")
        body = self.bootstrap(store)
        for key in ("schema", "domain", "session", "prepared_ms", "preparation_deadline_ms"):
            del body[key]
        start = self.now_ms()
        operation = policy.Manifest(policy.AdmissionFacts(True, True, True, True, True),
                                    **body, started_ms=start, deadline_ms=start + 60000)
        store.data["operation_manifest"] = asdict(operation)
        store.flush()
        self.publish_manifest(store, operation=True)
        return operation

    def manifest(self, store):
        self.verify_store(store)
        require(store.data["operation_manifest"] is not None, "operation_missing")
        return manifest_from(store.data["operation_manifest"])

    def consume_request(self, store, kind):
        require(kind in SLOTS and store.data["consumed"][kind] is False, "request_replay")
        self.verify_parent(store)
        require((kind == "profile_created" and store.data["phase"] == "bound"
                 and store.data["operation_manifest"] is None and not store.data["owned_intent"])
                or (kind == "probe_finished" and store.data["phase"] == "added"
                    and store.data["operation_manifest"] is not None and store.data["owned_intent"]
                    and store.data["add_verified"]), "request_phase")
        data = store.read(SLOTS[kind], store.file_descriptor("request"), 4096)
        require(0 < len(data) <= 4096, "request_size")
        store.data["consumed"][kind] = True
        store.flush()
        return data

    def wait_request(self, store, kind, timeout_ms):
        require(kind in SLOTS and integer(timeout_ms, 0, 180000), "wait_kind")
        absolute = store.data["prepared_ms"] + 180000 if kind == "profile_created" else self.manifest(store).deadline_ms
        deadline = min(self.now_ms() + timeout_ms, absolute)
        while self.now_ms() < deadline:
            self.verify_parent(store)
            try:
                if store.read(SLOTS[kind], store.file_descriptor("request"), 4096):
                    return
            except Failure as error:
                if error.args != ("open_file", 32):
                    raise
            time.sleep(0.01)
        raise Failure("request_timeout")

    def full_get(self, store):
        started = self.now_ms()
        self.verify_store(store)
        result = self._run(store, "get")
        require(result["reaped"] and not result["timed_out"] and result["exit_code"] == 0, "get_process")
        raw = decode(store.read(result["output"], PRIVATE, 1048576), 1048576)
        require(type(raw) is dict and "process_reaped" in raw and raw["process_reaped"] is None, "get_worker_self_credit")
        raw["process_reaped"] = True
        from scripts.windows_positive_loopback_admin import _mapping
        _mapping(raw)
        reader = [item for item in store.data["frozen_files"]
                  if item["path"] == "trusted/scripts/windows_positive_loopback_full_get.py"]
        require(len(reader) == 1, "get_reader_binding")
        store.data["reads"].append(dict(started_ms=started, finished_ms=self.now_ms(),
            command_index=len(store.data["commands"]) - 1,
            raw_sha256=hashlib.sha256(wire(raw)).hexdigest(), reader_sha256=reader[0]["sha256"]))
        store.flush()
        return raw

    def command(self, store, kind):
        require(kind in ("add", "delete"), "command_kind")
        self.verify_store(store)
        require(store.data["readonly_prepare"] is not None, "readonly_required")
        self._tool(store)
        self.reap_commands(store)
        return self._run(store, kind)

    def publish_manifest(self, store, *, operation=False):
        if operation:
            value = {"schema": 1, "domain": "icode_positive_operation_v1", "session": store.data["session"],
                     "manifest": asdict(self.manifest(store)), "binding": self.manifest(store).digest}
            name = "operation"
        else:
            identity = self.bootstrap(store)
            value = dict(identity=identity, binding=hashlib.sha256(wire(identity)).hexdigest())
            name = "bootstrap"
        store.write(PUBLIC[name], wire(value), "public")
        store.flush()

    def publish(self, store, kind, value):
        require(kind in ("add", "cleanup") and type(value) is dict, "receipt_kind")
        encoded = wire(value)
        require(len(encoded) <= 500, "receipt_limit")
        store.write(PUBLIC[kind], encoded, "public")
        store.flush()
        return dict(value)

    def readonly_prepare(self, store):
        require(store.data["readonly_prepare"] is None and store.data["parent"] is not None, "readonly_reentry")
        parent = self._process(store, store.data["parent"])
        try:
            routes = []
            for entry, handle in zip(store.route_records, store.pins):
                require(store.w.info(handle, directory=True) == tuple(entry["identity"])
                        and store.w.observe_security(handle) == entry["security"], "route_changed")
                access = store.w.effective_access(handle, parent)
                routes.append(dict(**entry, effective=access))
                require(access["api_completed"] is True and access["access_status"] is True
                        and access["granted"] & ROUTE_MUTATION == 0, "route_mutation_access")
            protected = store.w.observe_security(store.root_handle)
            require(protected["protected"] is True, "private_root_unprotected")
            access = store.w.effective_access(store.root_handle, parent)
            require(access["api_completed"] is True and access["access_status"] is True
                    and access["granted"] & LEAF_MUTATION == 0, "private_root_mutation_access")
            self._loader(store, parent)
            self._tool_admission(store, parent)
            self._abi(store)
            self._canaries(store, parent)
            store.data["readonly_prepare"] = dict(schema=1, routes=routes,
                root_security=protected, root_effective=access, sdk_layout_verified=True,
                python_binding_verified=True, loader_verified=True, canaries_verified=True)
            store.data["readonly_prepare"]["loader_images"] = store.loader_observations
            store.data["readonly_prepare"]["tool"] = store.tool_observations
            store.data["readonly_prepare"]["runner_arch_raw"] = os.environ["RUNNER_ARCH"]
            store.flush()
        finally:
            _release_owned(sys.exception(),
                lambda: store.w.close(parent),
            )

    def _loader(self, store, parent):
        require(Path(sys.executable).absolute() == store.root / "runtime/python.exe", "loader_interpreter")
        require(sys.flags.isolated == 1 and sys.flags.no_site == 1 and sys.flags.dont_write_bytecode == 1, "loader_flags")
        allowed = {str((store.root / item["path"]).resolve(strict=True)).casefold() for item in store.data["frozen_files"]}
        def module_origin(path):
            text = str(Path(path).absolute()).casefold()
            if text in allowed:
                return True
            archive = str(store.root / "runtime/python312.zip").casefold()
            prefix = archive + os.sep
            return (archive in allowed and text.startswith(prefix)
                    and not any(part == ".." for part in Path(text[len(prefix):]).parts))
        expected_path = {str(store.root / name).casefold() for name in
                         ("runtime/python312.zip", "runtime/DLLs", "runtime/Lib", "runtime", "trusted", "trusted/src")}
        observed_path = [str(Path(path)).casefold() for path in sys.path]
        require(len(observed_path) == len(expected_path) and len(observed_path) == len(set(observed_path)) and set(observed_path) == expected_path,
                "loader_sys_path")
        for module in tuple(sys.modules.values()):
            path = getattr(module, "__file__", None)
            if path and not path.startswith("<"):
                require(module_origin(path), "loader_module_origin")
        # Force consumed extension modules now, not after the first CLI write.
        for name in ("_ctypes", "_socket", "select", "_hashlib", "_ssl", "unicodedata"):
            module = importlib.import_module(name)
            require(str(Path(module.__file__).resolve(strict=True)).casefold() in allowed, "loader_extension_origin")
        # Force the stable-ABI stub using an absolute private file; keep the
        # module object alive for this admin process's complete lifetime.
        if not hasattr(store, "dll_pins"):
            store.dll_pins = []
        store.dll_pins.append(c.WinDLL(str(store.root / "runtime/python3.dll"), use_last_error=True, winmode=0x900))
        store.dll_pins.append(c.WinDLL(str(store.w.system_directory / "FirewallAPI.dll"), use_last_error=True, winmode=0x800))
        names = ("python312.dll", "python3.dll", "advapi32.dll", "userenv.dll", "kernel32.dll")
        for name in names:
            module = store.w.k.GetModuleHandleW(name)
            require(bool(module), "loader_dll_missing")
            path = c.create_unicode_buffer(32768)
            length = store.w.k.GetModuleFileNameW(module, path, len(path))
            require(0 < length < len(path), "loader_dll_path")
            expected = store.root / "runtime" / name if name.startswith("python") else store.w.system_directory / name
            require(os.path.normcase(path.value) == os.path.normcase(str(expected)), "loader_dll_origin")
        # The actual process module list includes transitive native imports,
        # not merely the Python modules we happened to name above.
        modules = (t.HANDLE * 4096)()
        returned = t.DWORD()
        checked(store.w.k.K32EnumProcessModules(store.w.k.GetCurrentProcess(), modules,
                                               c.sizeof(modules), c.byref(returned)), "loader_module_list")
        require(0 < returned.value <= c.sizeof(modules) and returned.value % c.sizeof(t.HANDLE) == 0,
                "loader_module_list_incomplete")
        observations, pinned_routes = [], set()
        for module in modules[:returned.value // c.sizeof(t.HANDLE)]:
            path_buffer = c.create_unicode_buffer(32768)
            length = store.w.k.GetModuleFileNameW(module, path_buffer, len(path_buffer))
            require(0 < length < len(path_buffer), "loader_image_path")
            path = Path(path_buffer.value)
            require(path.is_absolute() and path.resolve(strict=True) == path, "loader_image_namespace")
            private = str(path).casefold() in allowed
            require(private or path.parent == store.w.system_directory, "loader_dependency_origin")
            for ancestor in reversed(path.parents):
                if ancestor in pinned_routes:
                    continue
                route = store.w.pin_ancestor(ancestor, observe_only=True)
                store.pins.append(route)
                access = store.w.effective_access(route, parent)
                require(access["api_completed"] is True and (access["access_status"] is True or access["granted"] == 0)
                        and (access["granted"] & ROUTE_MUTATION) == 0, "loader_route_mutation")
                observations.append(dict(path=str(ancestor), identity=list(store.w.info(route, directory=True)),
                                         security=store.w.observe_security(route), effective=access))
                pinned_routes.add(ancestor)
            handle = store.w.k.CreateFileW(str(path), 0x80020080, 1, None, 3, 0x00200000, None)
            require(handle not in (None, c.c_void_p(-1).value), "loader_image_open")
            store.handles.append(handle)
            proof = None if private else self._image_provenance(store, handle, path, dll=True)
            metadata = None if private else proof["file_info"]
            identity = store.w.info(handle) if private else tuple(metadata["identity"])
            access = store.w.effective_access(handle, parent)
            require(access["api_completed"] is True and (access["access_status"] is True or access["granted"] == 0)
                    and (access["granted"] & LEAF_MUTATION) == 0, "loader_image_mutation")
            observations.append(dict(path=str(path), identity=list(identity),
                                     security=store.w.observe_security(handle), effective=access,
                                     file_info=metadata, provenance=proof))
        store.loader_observations = observations

    def _tool_admission(self, store, parent):
        require(store.data["system_tool"] == self._tool(store), "tool_binding")
        path = Path(store.data["system_tool"]["path"])
        observations = []
        for ancestor in reversed(path.parents):
            handle = store.w.pin_ancestor(ancestor, observe_only=True)
            store.pins.append(handle)
            access = store.w.effective_access(handle, parent)
            require(access["api_completed"] is True and (access["access_status"] is True or access["granted"] == 0)
                    and (access["granted"] & ROUTE_MUTATION) == 0, "tool_route_mutation")
            observations.append(dict(path=str(ancestor), identity=list(store.w.info(handle, directory=True)),
                                     security=store.w.observe_security(handle), effective=access))
        handle = store.w.k.CreateFileW(str(path), 0x80020080, 1, None, 3, 0x00200000, None)
        require(handle not in (None, c.c_void_p(-1).value), "tool_admission_open")
        store.handles.append(handle)
        metadata = self._image_info(store, handle, path)
        require(metadata == store.data["system_tool"]["file_info"], "tool_admission_identity")
        access = store.w.effective_access(handle, parent)
        require(access["api_completed"] is True and (access["access_status"] is True or access["granted"] == 0)
                and (access["granted"] & LEAF_MUTATION) == 0, "tool_mutation")
        observations.append(dict(path=str(path), identity=metadata["identity"], file_info=metadata,
                                 security=store.w.observe_security(handle), effective=access,
                                 provenance={key: store.data["system_tool"][key] for key in
                                             ("file_info", "sha256", "machine", "file_version", "product_version")},
                                 file_version=store.data["system_tool"]["file_version"],
                                 product_version=store.data["system_tool"]["product_version"]))
        store.tool_observations = observations

    def _abi(self, store):
        result = self._run(store, "abi")
        require(result["reaped"] and not result["timed_out"] and result["exit_code"] == 0, "sdk_process")
        raw = decode(store.read(result["output"], PRIVATE, 32768), 32768)
        names = {"SA": abi.SA, "FILE_INFO": abi.FILE_INFO, "STARTUP": abi.STARTUP,
                 "STARTUP_EX": abi.STARTUP_EX, "PROCESS": abi.PROCESS, "TOKEN_USER": abi.TOKEN_USER,
                 "GENERIC_MAPPING": abi.GENERIC_MAPPING, "EXTENDED_LIMITS": abi.EXTENDED_LIMITS}
        expected = {"schema": 1, "machine": store.data["context"]["matrix"], "DWORD": c.sizeof(t.DWORD),
                    "BOOL": c.sizeof(t.BOOL), "FILETIME": c.sizeof(t.FILETIME), "HANDLE": c.sizeof(t.HANDLE)}
        expected.update({name: c.sizeof(kind) for name, kind in names.items()})
        expected.update(sa_descriptor=abi.SA.descriptor.offset, file_volume=abi.FILE_INFO.volume.offset,
                        file_links=abi.FILE_INFO.links.offset, startup_stdin=abi.STARTUP.stdin.offset,
                        startup_attributes=abi.STARTUP_EX.attributes.offset, process_pid=abi.PROCESS.pid.offset,
                        token_sid=abi.TOKEN_USER.sid.offset, job_pid_list=8, job_list_attribute=0x2000D,
                        calling_convention_verified=True, owned_buffer_freed=True)
        layout = {"WORD": c.sizeof(t.WORD), "LONG": c.sizeof(t.LONG), "ULONG_PTR": c.sizeof(c.c_size_t),
                  "IO": c.sizeof(abi.IO), "LIMITS": c.sizeof(abi.LIMITS), "SID_AND_ATTRIBUTES": c.sizeof(SID_AND_ATTRIBUTES)}
        for name, kind in {**names, "IO": abi.IO, "LIMITS": abi.LIMITS, "FILETIME": t.FILETIME,
                           "SID_AND_ATTRIBUTES": SID_AND_ATTRIBUTES}.items():
            for field, _kind in kind._fields_:
                layout[name + "." + field] = getattr(kind, field).offset
        layout.update({"JOB_PID.assigned": 0, "JOB_PID.count": 4, "JOB_PID.pids": 8})
        expected["layout"] = layout
        require(type(raw) is dict and set(raw) == set(expected), "sdk_schema")
        require(wire(raw) == wire(expected), "sdk_layout")
        current = store.w.k.GetCurrentProcess()
        first = store.w.process_created(current)
        require(first > 0 and store.w.process_created(current) == first
                and store.w.k.WaitForSingleObject(current, 0) == 258, "python_get_process_times")
        # Real API-owned allocation/release in the Python consumer, independent
        # of the C probe's own HeapAlloc/HeapFree observation.
        descriptor = store.w.descriptor(PRIVATE)
        _release_owned(None, lambda: checked(not store.w.k.LocalFree(descriptor), "python_descriptor_free"))
        self._derived(store.w, store.data["profile_names"][0])

    def _canaries(self, store, parent):
        token, duplicate = t.HANDLE(), t.HANDLE()
        checked(store.w.a.OpenProcessToken(parent, 10, c.byref(token)), "canary_token")
        try:
            checked(store.w.a.DuplicateToken(token, 2, c.byref(duplicate)), "canary_duplicate")
            checked(store.w.a.ImpersonateLoggedOnUser(duplicate), "canary_impersonate")
            try:
                # Fixed request slots deliberately grant only FILE_WRITE_DATA,
                # not GENERIC_WRITE/WRITE_EA/WRITE_ATTRIBUTES. Future fixed
                # consumer uses this exact narrow CreateFile/WriteFile/Close.
                path = store.root / "readonly-request.canary"
                handle = store.w.k.CreateFileW(str(path), 2, 0, None, 3, 0x00200000, None)
                require(handle not in (None, c.c_void_p(-1).value), "request_positive_open")
                try:
                    count = t.DWORD()
                    checked(store.w.k.WriteFile(handle, b"ok", 2, c.byref(count), None), "request_positive_write")
                    require(count.value == 2, "request_positive_short")
                finally:
                    _release_owned(sys.exception(),
                        lambda: store.w.close(handle),
                    )
                public = store.root / "readonly-public.canary"
                handle = store.w.k.CreateFileW(str(public), 0x80000000, 1, None, 3, 0x00200000, None)
                require(handle not in (None, c.c_void_p(-1).value), "public_positive_read")
                try:
                    require(store.w.read(handle, 6) == b"public", "public_positive_bytes")
                finally:
                    _release_owned(sys.exception(),
                        lambda: store.w.close(handle),
                    )
                private = store.root / "readonly-private.canary"
                for path, mask in ((private, 2), (private, 0x10), (private, 0x100),
                                   (private, 0x10000), (private, 0x40000), (private, 0x80000),
                                   (public, 2), (store.root, 2), (store.root, 4), (store.root, 0x100)):
                    c.set_last_error(0)
                    handle = store.w.k.CreateFileW(str(path), mask, 3, None, 3,
                        0x00200000 | (0x02000000 if path == store.root else 0), None)
                    if handle not in (None, c.c_void_p(-1).value):
                        try:
                            raise Failure("private_negative_open")
                        finally:
                            _release_owned(sys.exception(), lambda: store.w.close(handle))
                    require(c.get_last_error() == 5, "private_negative_error")
                c.set_last_error(0)
                require(not store.w.k.SetFileAttributesW(str(private), 2) and c.get_last_error() == 5, "attributes_negative")
                c.set_last_error(0)
                require(not store.w.k.MoveFileExW(str(private), str(store.root / "renamed.canary"), 0)
                        and c.get_last_error() == 5, "replace_negative")
            finally:
                _release_owned(sys.exception(),
                    lambda: checked(store.w.a.RevertToSelf(), "canary_revert"),
                )
        finally:
            _release_owned(sys.exception(),
                *(lambda owned=owned: store.w.close(owned) for owned in (duplicate, token) if owned),
            )
        require(store.read("readonly-request.canary", store.file_descriptor("request"), 2) == b"ok", "request_positive_observed")
        require(store.read("readonly-private.canary", PRIVATE, 7) == b"private", "private_unchanged")
```

## Asset: `scripts/windows_positive_loopback_admin_entry.py`

固定受信 admin CLI，不是客户端协议。`freeze` 只能在临时账号不存在时从本候选 checkout 调用；其后所有 admin 执行一律重启到返回目录的 private python + private entry。`serve`/`readonly` 由受信 workflow parent 传精确账号 SID 和已创建、尚未 Resume 的固定标准用户父 PID；在完整 bootstrap 发布且 admin 进程仍活之前，parent 不得 Resume。此 thread 句柄只在受信 parent 本地持有，不新增请求或客户端句柄交接。下一片必须提供真实 CreateProcessWithLogonW 的 suspended 创建／失败回收接线，不能继续用当前 Start-Process 先运行后验证。

普通 JSON 仅固定有界摘要；Get/CLI 输出始终是 private command-N.out，不上传全 SID 名单。正常 clean receipt 返回后仍持有 outer Job，给标准用户原 finally 完成 ACL/profile 清理并退出的有界机会；不能因为 admin 进程先 CloseHandle 而杀掉尚在执行原 finally 的父。独立 always 仍从受信 parent 保存的精确 root 调 recover，不扫描路径。

```python
"""Fixed trusted-workflow entry; no user-controlled privileged command."""
from __future__ import annotations
import argparse
import json
import os
from pathlib import Path
import sys


def emit(value):
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("ascii")
    if len(encoded) > 500:
        raise RuntimeError("entry_receipt_limit")
    sys.stdout.buffer.write(encoded + b"\n")
    sys.stdout.buffer.flush()


def main(argv=None):
    parser = argparse.ArgumentParser(allow_abbrev=False)
    parser.add_argument("operation", choices=("freeze", "serve", "readonly", "recover"))
    parser.add_argument("--account")
    parser.add_argument("--root")
    parser.add_argument("--account-sid")
    parser.add_argument("--parent", type=int)
    args = parser.parse_args(argv)
    if sys.platform != "win32" or sys.version_info < (3, 12):
        raise RuntimeError("entry_windows312")
    if not (sys.flags.isolated and sys.flags.no_site and sys.flags.dont_write_bytecode):
        raise RuntimeError("entry_flags")
    script = Path(__file__).absolute()
    private = script.parent.parent.name == "trusted" and script.parent.name == "scripts"
    if args.operation == "freeze":
        if private or args.account is None or any(value is not None for value in (args.root, args.account_sid, args.parent)):
            raise RuntimeError("entry_freeze_arguments")
        checkout = script.parents[1]
        # This branch is reached only before the temporary account exists.
        sys.path.insert(0, str(checkout))
        sys.path.insert(0, str(checkout / "src"))
    else:
        if not private or args.root is None or args.account is not None:
            raise RuntimeError("entry_private_arguments")
        root = Path(args.root)
        if not root.is_absolute() or root.resolve(strict=True) != root or root != script.parents[2]:
            raise RuntimeError("entry_private_root")
        runtime = root / "runtime"
        if Path(sys.executable).absolute() != runtime / "python.exe":
            raise RuntimeError("entry_private_python")
        # Preserve exactly the approved private stdlib/extension slots and two
        # explicit candidate package roots, never checkout/cwd/site-packages.
        sys.path[:] = [str(runtime / "python312.zip"), str(runtime / "DLLs"), str(runtime / "Lib"),
                       str(runtime), str(root / "trusted"), str(root / "trusted/src")]
    from scripts.windows_positive_loopback_admin import Admin, _mapping
    from scripts.windows_positive_loopback_admin_native import Native, context
    from scripts.windows_positive_loopback_admin_win32 import _release_owned
    binding = context(dict(repository=os.environ.get("GITHUB_REPOSITORY"), source_sha=os.environ.get("GITHUB_SHA"),
        run_id=os.environ.get("GITHUB_RUN_ID"), run_attempt=int(os.environ.get("GITHUB_RUN_ATTEMPT", "0")),
        job=os.environ.get("GITHUB_JOB"), matrix={"X64": "x64", "ARM64": "ARM64"}.get(os.environ.get("RUNNER_ARCH"))))
    if args.operation == "freeze":
        root = Admin.freeze_before_user(binding, args.account)
        emit(dict(schema=1, stage="frozen", root=str(root)))
        return 0
    if args.operation == "recover":
        if args.account_sid is not None or args.parent is not None:
            raise RuntimeError("entry_recover_arguments")
        receipt = Admin.recover(root)
        emit(dict(schema=1, stage="recovery", cleanup_state=receipt["stage"], binding=receipt["binding"],
                  native_restoration_verified=receipt.get("native_restoration_verified")))
        return 0 if receipt.get("native_restoration_verified") is True else 4
    if args.account_sid is None or args.parent is None:
        raise RuntimeError("entry_parent_arguments")
    admin = Admin.prepare(root, args.account_sid)
    try:
        admin.attach_parent(args.parent)
        if args.operation == "readonly":
            before = _mapping(admin.native.full_get(admin.store))
            admin.native.stop_parent_job(admin.store)
            after = _mapping(admin.native.full_get(admin.store))
            if before != after:
                raise RuntimeError("readonly_configuration_changed")
            emit(dict(schema=1, stage="readonly_ready", sdk=True, loader=True, storage=True,
                      standard_token=True, configuration_unchanged=True))
            return 0
        receipt = admin.serve()
        # The client receives the receipt before deleting its profile. Keep the
        # outer Job alive until its real parent exits or bounded recovery fails.
        parent = admin.native._process(admin.store, admin.data["parent"], allow_gone=True)
        if parent:
            try:
                if admin.store.w.k.WaitForSingleObject(parent, 30000) != 0:
                    admin._failure("parent_failed")
                    admin.native.stop_parent_job(admin.store)
                    raise RuntimeError("parent_finally_not_reaped")
            finally:
                _release_owned(sys.exception(),
                    lambda: admin.store.w.close(parent),
                )
        admin.native.reap_commands(admin.store)
        emit(dict(schema=1, stage="completed", cleanup_state=receipt["stage"], binding=receipt["binding"],
                  native_restoration_verified=receipt.get("native_restoration_verified")))
        return 0 if receipt.get("native_restoration_verified") is True else 4
    finally:
        # Failure before serve() also owns a suspended/started parent. Cleanup
        # precedes closing the last owned Job handle; errors never grant ready.
        _release_owned(sys.exception(),
            lambda: admin.cleanup(abnormal=True) if admin.data["phase"] != "cleaned" else None,
            lambda: admin.store.close(),
        )


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception:
        emit(dict(schema=1, stage="failed", state="unknown"))
        raise SystemExit(4)
```

## 全 owner acquisition／transfer／release 与异常清单

本表对应全部七个 Python 围栏，不把“调用过close”写成“已确认释放”。唯一新增窄私有原语是既有Win32模块的`_release_owned(primary, *actions)`：只接收本链已拥有资源的零参释放/补偿callable，逐个attempt；body原异常对象与args不改，每个释放失败以`cleanup_unknown: {error!r}`加note；无body异常则抛首个实际释放异常。不管理启动/授权/路径，不新增模块、权限、依赖或账本字段。调用者仍拥有原异常的raise/unwind，primitive不将已存在body异常转成成功返回。

| 资产／实际方法 | acquisition与移交 | release／补偿与失败义务 |
| --- | --- | --- |
| Admin `__init__`／`prepare` | Native成功返回完整Store后归controller，类构造只赋既有引用 | `serve`、entry finally及独立`recover`负责生命周期；不因Python引用释放授OS信用 |
| Admin `serve`／`recover` | 已拥有Store，serve还拥有请求处理首错 | wait/freeze/publish首错先记录原durable first_error；cleanup异常不得覆盖原Python对象；recover最终Store.close同政策 |
| Get `_load` | 固定System32 FirewallAPI加载后才绑定唯一Get export | bind失败仍尝试显式FreeLibrary；释放异常/false留原bind首错及unknown note |
| Get `collect` | 仅完整、无别名、安全SID指针图才认领逐SID及array | 每SID独立HeapFree，单次抛错不跳其它SID/array/library；既有freed计数及complete=False表达unknown，不添wire字段，不猜坏图 |
| Win32 `__init__`／Native `_derived`、`_image_provenance`、`_loader` | kernel/advapi/userenv/version与明确DLL pin是固定admin进程生命周期加载引用；version/dll引用保留，不视为Store短生命周期 | 不在Store.close盲FreeLibrary使活跃ctypes函数指针失效；不将丢Python引用当卸载。仅实际进程exit/reap门闭合，软件fake不授原生证明；与Get显式FirewallAPI计数区分 |
| Win32 `descriptor`／`sid_binary`／`assert_admin` | API成功取得SD或SID，descriptor返回将所有权交给调用者，其余在本方法拥有 | 已取得指针由LocalFree释放；验证body失败与释放失败并存时保原对象/notes，不误称已free |
| Win32 `verify_security`／`effective_access`／`process_user` | actual+expected SD；SD+token+duplicate；token+SID text分别归本方法 | 所有已拥有对象均attempt：两SD、两个token及SD、text及token；内层失败不跳外层，不盖原body |
| Win32 `open_file`／`pin_ancestor` | 成功Create取得句柄；SD属于open_file本地 | open_file仅descriptor释放成功后transfer返回file；失败时SD与未返回file均attempt。pin验证失败仅一次close，不盲重试 |
| Win32 `create_directory`／`set_root_dacl`／`verify_ancestor`／`observe_security` | 本地SD/安全观察分配归本方法 | 每个单owner finally也保原body首因；释放失败不得借单资源而省略unknown |
| Win32 `security/info/read/write/process_created/job_pids/close` | 除调用者传入的borrowed handle外仅ctypes栈/缓冲区；close是释放入口，不自授新handle | 访问/布局/返回失败仍failclosed；不得将关闭process handle等同终止process |
| Store `__init__`／`create` | route pins、root pin、lock、各新file句柄先登记；完成后移交Store或重开Store | 构造失败close整个已登记集合；create内file和外pins全attempt，即使首pin关闭失败仍尝试其它pin并保原body |
| Store `flush/read/write/create_directory` | 单file归当前调用；目录每prefix经PRIVATE及identity准入后暂held | file单owner finally保body；目录失败释放全部held，成功才整体转Store.pins；仍拒既有leaf，不exists_ok绕门 |
| Store `close` | 已登记handles/pins属于该Store实例 | 每个pop仅表示本实例attempt，不表示OS已关闭；全部集合attempt，首失败抛出/unknown notes，不返回伪成功 |
| Store `copy_private_tree`／Native `_copy_file` | source file先归当前调用，destination成功打开后也归当前调用 | destination关闭失败不跳source，write/body错误原对象不被覆盖；源身份/无reparse/有界完整遍历合同不变 |
| Native `_source_tree` | 每个ancestor/目录pin取得即登记，再读info；复读文件和after目录handle归局部 | pins全部attempt；每个局部file/dir单finally同政策；info失败也不遗漏新pin，不以partial目录集通过 |
| Native `freeze/reopen/prepare` | Store创建/重开后归本方法；freeze成功仅返回root，prepare成功转交Store；writable_root/socket为局部 | Store失败/最终close保首因；writable_root单handle释放；socket显式try/finally，不让context exit遮bind/body错误 |
| Native `verify_store/_tool/readonly_prepare` | 每次目录/file/rawimage/parent handle归局部；tool成功转Store.handles | 每个局部finally保首因；tool只有完整proof后移交；重核失败仍释放，不降低private/System32角色门 |
| Native `_loader/_tool_admission` | route/file首次拥有即加入Store.pins/handles，然后才做rights/identity/PE检查 | 后续失败由Store生命周期统一attempt；不在require前丢句柄，不把成功append当完整准入 |
| Native `_process/_outer/parent_only` | OpenProcess/Job成功后本方法拥有；_process/_outer仅完整验证后transfer | _process用transfer flag，gone/reused/失败只释放一次；close失败不落入except再盲重close；parent_only持Job至finally |
| Native `attach_parent` | 持handle不等于终止权限；实际live、冻结token user及有效uint64 creation全部成功后才认证。正常Job成员/完整PID表验证及持久身份后登记转Store | 未认证零终止，仅close；认证未transfer失败时重新Wait(0)，已退出不盲终止，仍活则fresh IsProcessInJob决定ownedJob或精确heldprocess。查询失败unknown、不猜；独立Job empty/process wait/所有close仍attempt。transfer后readonly/bootstrap失败仍由Store/上层负责；父suspended原句柄仍属下一片受信parent |
| Native `verify_parent/stop_parent_job/reap_commands` | parent/process与namedJob是独立拥有对象；OpenJob本身也在process的finally范围 | Job关闭失败不跳parent/process；终止失败不跳独立wait/empty与释放；身份验证失败不猜权终止；缺Job仍保真实identity首错并释放一次process |
| Native `_derived/_abi/_canaries` | derived SID／ABI SD／standard token+duplicate及各file分别拥有；Impersonate后还拥有Revert义务 | FreeSid/LocalFree保持unknown；canary每个file、Revert及两个token全同首因政策；不能将失败negative open当成功，所有负控仍限自有canary |
| Jobs `create_job` | SD与Job局部拥有，设置limits/安全验证完成且SD成功释放后才transfer Job | SD释放失败仍attempt未返回Job；不以最后CloseJob代替已观察回收，也不盖碰撞/body首错 |
| Jobs `run_fixed` | Job、out、NUL、attribute list、process/thread归当前命令，已持久PID/creation+ready后才Resume | 独立Terminate/Wait/Job-empty、DeleteAttributeList、每个Close及durable写全attempt；任何cleanup失败record.reaped=False/state=cleanup_unknown，原body对象保留，Flush再失败也notes未知；没有新deadline重置 |
| Entry `main` | controller Store及等待父退出的局部process由固定可信入口拥有 | 该父handle、admin cleanup、Store.close均attempt并保原body；完整exit0才授只读成功，首行readonly_ready不够；顶层仍仅输出固定失败收据，无新增请求 |

ctypes缓冲区、结构体、attribute storage、JSON/PE字节是Python管理内存；跨调用原件的实际pointer生命周期仍由源实现保持。表中所有transfer以源码实际分支为准；坏账本/身份/释放未知仍候选失败，不靠notes或模型bool创造恢复authority。

## 冻结输入与完整资产清单

权威根均为 `/home/orbbec/projects/icode`。本轮仅编辑本文；下表新增 SOURCE/TEST 当前不存在，唯一旧文件 CMake 保留原字节，不能把围栏当实际实现。HEAD 绑定 root 提供的 `619ed7771d9741eab11cb8a333965521d0c8d228`；保留前述 e94 历史，不执行 Git 来改写任何候选。输入漂移先停审查，不自动更新资产迎合新输入。

| 实际输入（根下相对路径） | 行 / bytes | SHA256 |
| --- | ---: | --- |
| `AGENTS.md` | 27 / 3559 | `f447a737997bdf7bcb324fa3ae1c5ac84c3ef9af9a8ebd405da965b9b6512f39` |
| `docs/nbl/specs/2026-10-15-windows-ci-positive-loopback-exemption-design.md` | 109 / 20640 | `62f1ffa91d51ea837371a392f807d7bd325cf64c0e7cb1fc277030413324606c` |
| `docs/nbl/specs/2026-10-15-windows-ci-positive-loopback-admin-binding-design.md` | 113 / 7082 | `8d3f0a749962f8f25b6cc3ee1aab42e613f1d7d27d4851613aa345e4e74726ae` |
| `.github/workflows/ci.yml` | 2541 / 136918 | `b4e10208ee1c28ddc45d9bc81365791ec58af5ada34aba220182700fdd01cb18` |
| `src/icode/windows_appcontainer.py` | 1810 / 79521 | `307dc730bf28bc661ad99b8d02dc9093b51c1dcdf45f993b470e68a5562f1a1f` |
| `src/icode/windows_job.py` | 1338 / 60437 | `ac2bfbe924a9b03b68ab0304f55cfcfde7b79615c3563c0db61ca099d335d640` |
| `native/windows/icode_positive_loopback_config.inc` | 147 / 6776 | `194a6902cb828a71cac25c10b3bb66a1189355c888f7d51b724cc31c895de977` |
| `native/windows/CMakeLists.txt` | 159 / 6950 | `6b7049f6cebc4a689efa47519dbdecd86686fd072a9d53fbce94d235699ffa31` |
| `src/icode/windows_positive_loopback_policy.py` | 402 / 16686 | `0598a314200dd69258bd0e9c2db2d38eaecb5037580799890672047d26d0298c` |
| `tests/test_windows_positive_loopback_policy.py` | 356 / 18847 | `49bf9718468002078cfc62eeccd877e3967a69c92b8b40fd9f2c15db3f9c2cf1` |
| `pyproject.toml` | 41 / 1303 | `6c04d0b112854931228f081e46fce016f46acf00072cb2d11611926a17e1357a` |

完整 TEST 真源为 `/home/orbbec/projects/icode/docs/nbl/plans/2026-10-15-windows-ci-positive-loopback-admin-tests.md`，3826 行 / 267198 bytes，SHA256 `8d473397fcd5fec57586c0287575d6e905135d9e592859b03eb595eb3ebc836f`。必须完整读取该文八个 Python 围栏；本文只作冻结索引，不复制第二份会漂移的 TEST 实现。TEST 与 SOURCE 作者独立；SOURCE 作者不得自行改已冻结 TEST 取绿。

| 完整未来 TEST 路径 | 行 / bytes / 方法 | 围栏 UTF-8 LF SHA256 |
| --- | ---: | --- |
| `/home/orbbec/projects/icode/tests/test_windows_positive_loopback_admin_get.py` | 291 / 13757 / 13 | `e6a12c31a2c892171f9fc86a9315205b6b04a73ff4bf574621b5ca50b512dda6` |
| `/home/orbbec/projects/icode/tests/test_windows_positive_loopback_admin_binding.py` | 157 / 8584 / 7 | `166cf869042951ac6a8e56ac929ef9c6edd0a667959506dcef1cb59475c27b21` |
| `/home/orbbec/projects/icode/tests/test_windows_positive_loopback_admin_win32.py` | 428 / 25692 / 15 | `8dd0535ed8dce763c1318a027a697b7881c693cfedd9079a90f0bb8e6b6b4582` |
| `/home/orbbec/projects/icode/tests/test_windows_positive_loopback_admin.py` | 319 / 17194 / 16 | `5af0dce6810fea898e70c61bd9f790f371192d961bf47add388ce5e87dfec770` |
| `/home/orbbec/projects/icode/tests/test_windows_positive_loopback_admin_store.py` | 351 / 20080 / 17 | `d4d5cb7d3f54ca1ce7589ca6ce9803a9ef877bd7e6775385ace16e879d2583ad` |
| `/home/orbbec/projects/icode/tests/test_windows_positive_loopback_admin_jobs.py` | 342 / 18823 / 16 | `cc92211105763ba104c1bcd382aefcd8c12db46676978ba1eeef4ccb608a9e46` |
| `/home/orbbec/projects/icode/tests/test_windows_positive_loopback_admin_native.py` | 1383 / 90222 / 58 | `a1bb44a91775b91153cf5bd0ddae0631e39710fd10c481293d8c04d9f3aabc76` |
| `/home/orbbec/projects/icode/tests/test_windows_positive_loopback_admin_entry.py` | 192 / 11446 / 10 | `fefa7004009ccf26a4809ca2f795a00943166d8c894df59296e22b4ab189eb17` |

下表是本文全部九个完整 SOURCE 资产；Python 文件以围栏完整替换为新文件，八 TEST 文件之外不改既存 TEST。CMake 是唯一旧 SOURCE 改动：原 159 行完整保留，在 EOF 加一个空行及 18 行精确围栏。投影文件 178 行 / 7573 bytes，SHA256 `0956a4d69338c37bafea1a442f0898ff766e3d9d1c2be19818ffc3b152a8f2ce`。原生产源码／core／已有 98 方法及 13 post-observation 集合不改。

| 完整未来 SOURCE 路径 | 围栏行 / bytes | 围栏 SHA256 |
| --- | ---: | --- |
| `/home/orbbec/projects/icode/scripts/windows_positive_loopback_admin.py` | 417 / 19541 | `772accbf1b09c08e5b89e8a71a935b805fb28824d7cb104b1d607996b68c9c21` |
| `/home/orbbec/projects/icode/scripts/windows_positive_loopback_full_get.py` | 151 / 6275 | `918b4450dfcfbc531051b172cadc3a4d382b9824dfb4c6245fbbf4c6d7431a88` |
| `/home/orbbec/projects/icode/scripts/windows_positive_loopback_admin_win32.py` | 457 / 24203 | `50f5ecf701cd4285e72f3faa77ab7e0bdeaa5e80008ac2cd52d3392c0d7b585d` |
| `/home/orbbec/projects/icode/scripts/windows_positive_loopback_admin_store.py` | 277 / 12286 | `ab2f14cc558a7df4c792810b04b219cd25a654ee406c52be1b249a02c6c93c0c` |
| `/home/orbbec/projects/icode/scripts/windows_positive_loopback_admin_jobs.py` | 222 / 10312 | `2e25994c61017ce4a21a69c28aba190beb1f572900c0e77fc463e359519c910e` |
| `/home/orbbec/projects/icode/scripts/windows_positive_loopback_admin_native.py` | 1371 / 86731 | `d4761232e46876996d077bcab796e96935bcb40395618c19bb171c9e30e81012` |
| `/home/orbbec/projects/icode/scripts/windows_positive_loopback_admin_entry.py` | 115 / 5975 | `667cde741a5e135121b5894b598c4d55c6ecbb7d5da9365f6d1cb8141443bf7e` |
| `/home/orbbec/projects/icode/native/windows/icode_positive_loopback_admin_abi.c` | 138 / 7695 | `d0ac23e8b63e399da0a8948689f01ba0fcfe4d548943b13f962dabbee7d4cfc0` |
| `/home/orbbec/projects/icode/native/windows/CMakeLists.txt`（仅新增尾部） | 18 / 622 | `6708dd5adf2b74d68b889d5180e68a4bdec39d9d9313e0ddddbf81e4cedc4b12` |

## 正式实施任务（本轮一项也不执行）

### Task 1：冻结整片输入、独立审查和 TEST-only RED

**Dependencies:** root 全文读取本文与 TEST 真源；fresh SPEC 及另一名 QUALITY 均审完整十七个代码围栏、两份 SPEC 和实际 Create/launch/delete 调用链，零未闭合阻断后 root 明确解冻。
**Parallelizable:** No。

- [ ] 核 HEAD、全部输入和围栏 hash；任何漂移停下，不触 core 或用户 dirty。
- [ ] 独立 TEST 作者只用 apply_patch 新增八个完整 TEST 文件；不先落任何新 SOURCE，不改旧 TEST。
- [ ] 用支持的 Python 3.12 实际文件执行下列同一命令并保存原始退出／日志 SHA；期望 **152 Assertion FAIL / 0 PASS / 0 ERROR / 0 skip，exit 1**，各模块 13/7/15/16/17/16/58/10。缺组件由 assert callable/module 明确失败；ImportError、语法错、fixture错不是需求 RED。若发现 TEST 自身错误，先恢复冻结评审流程，不能由 SOURCE 作者顺手修。
- [ ] root 亲读实际 RED 与 TEST-only diff；记录实际文件 hash。没有实际 RED 不进入 SOURCE 阶段。若本机只允许既有 3.11，任何运行另记诊断；正式目标 3.12 的事实留线上，不能安装／扩大本机验收。

在仓库根、支持的 Python 3.12 runner 上执行；Windows 使用相同参数的 `$python`，不通过 shell 拼接客户端输入：

```bash
PYTHONPATH=src python3.12 -B -m unittest -v tests.test_windows_positive_loopback_admin_get tests.test_windows_positive_loopback_admin_binding tests.test_windows_positive_loopback_admin_win32 tests.test_windows_positive_loopback_admin tests.test_windows_positive_loopback_admin_store tests.test_windows_positive_loopback_admin_jobs tests.test_windows_positive_loopback_admin_native tests.test_windows_positive_loopback_admin_entry
```

八个模块均只在最低层使用假 Win32、真实 ctypes 内存／句柄／持久字节模型；不需要也不得因软件命令取得管理员权限。每一 `test_` 方法只发现一次，152 是完整集合，不选子集藏错。

### Task 2：不同作者落全部 SOURCE，原 TEST 不变取 GREEN

**Dependencies:** Task 1 实际预期 RED 已经 root 确认；SOURCE 作者不同于 TEST 作者。
**Parallelizable:** No（共享真实账本和失效语义）。

- [ ] apply_patch 新增七个完整 Python 文件、一个完整 C 文件，只在原 CMake EOF 加空行＋精确追加资产。确认所有输出字节等于表中围栏，CMake 投影 hash 相等。
- [ ] 原封不动运行 Task 1 命令，期望 **152 PASS / 0 FAIL / 0 ERROR / 0 skip，exit 0**。不通过时修 SOURCE；若确属 TEST/SPEC 缺陷先报告并重新冻结，不能偷偷改 TEST。
- [ ] 重跑下面既有 35 项相关软件，期望 35 PASS、零 skip、exit 0；不本机运行整套／native。hash 对照 core 402/356 行及生产入口均原样。

```bash
PYTHONPATH=src python3.12 -B -m unittest -v tests.test_windows_positive_loopback_policy tests.test_full_suite_ci_budget tests.test_windows_runner_protocol
```

- [ ] 审实际 Win32 restype/argtypes、所有持有路径异常释放、Flush→Resume 顺序、ready False/None/True、进程 PID reuse、完整 Job list、账户删除后窄恢复、核心／准备／fallback 时钟无重置。
- [ ] fresh 实际 SOURCE SPEC／不同 QUALITY 复审；152 软件绿仅关闭本片软件，不授 Windows API/ABI、ACL、来源、连通、系统恢复或 R2/R3 完成。

### Task 3：同候选双 Windows 的只读 prepare 先行门

**Dependencies:** Task 2 与完整下一片实际 consumer/workflow PLAN 均双审通过并实际实现。该下一片必须提供受信 parent 的真实 suspended 创建与 finally／always 接线；当前 `ci.yml` 不启用本片，不用任意 callback／caller bool 代替。
**Parallelizable:** x64/ARM64 各平台独立，但同一 runner 上所有实例串行、同候选 SHA。任一平台 unknown/失败即不进入任何 exemption CLI 写。

- [ ] 沿用现 Reviewer helper 构建模式，为只读 SDK target 使用独立 build directory；不关闭或修改既有 bootstrap/sign/provenance 必需门，不扩大 -j1，也不安装新工具。未来受信 workflow 的固定命令为：

```powershell
cmake -S native/windows -B build/positive-admin-abi -A '${{ matrix.cmake-architecture }}' -DICODE_BUILD_WINDOWS_BOOTSTRAP=OFF
if ($LASTEXITCODE -ne 0) { throw 'positive_admin_abi_configure_failed' }
cmake --build build/positive-admin-abi --config Release --target icode_positive_loopback_admin_abi --parallel 1
if ($LASTEXITCODE -ne 0) { throw 'positive_admin_abi_build_failed' }
```

这里 OFF 仅是当前 Reviewer 独立只读 helper 目录已有的构建方式；产品 bootstrap 使用自己的原 build 目录和 verifier 参数，原 job 不变。SDK C 本身调用成功不授 Python ABI；Native._abi 必须独立读取 JSON 的全 77 layout 键并比较真实 Python sizeof/offsetof，真实调用 GetProcessTimes、descriptor LocalFree 和 derived SID FreeSid。

- [ ] 在 New-LocalUser **之前**由受信 admin parent 设置本固定 workflow 的显式 `ICODE_CI_POSITIVE_LOOPBACK_ADMIN=1`、`ICODE_CI_POSITIVE_LOOPBACK_DEDICATED_WRITER=1`，从 GitHub 原始上下文得到候选/run/job；声明专用临时 runner 没有其它 exemption writer。所有这些声明只是前提，必须再过真实 admin/token/句柄/ACL/Job 门，不由环境变量本身授信。
- [ ] 受信 parent 先以已选 Python 3.12 `-I -S -B scripts/windows_positive_loopback_admin_entry.py freeze --account $accountName` 创建唯一保护实例，完整解析 exit0 和固定 frozen JSON，保存精确 root；重复 freeze 同上下文失败。该调用不能放在新账号存在之后。
- [ ] 然后仍由受信 parent 创建原临时账号，获取真实本地 SID；以完整下一片固定 launcher 创建标准用户测试父 **SUSPENDED**。parent 持有真实 process/initial-thread 句柄，不向客户端传句柄、不传第三请求，也不让用户继承 `GITHUB_ENV`／`GITHUB_OUTPUT` 等 workflow 控制文件能力。
- [ ] 只能用 `$root/runtime/python.exe -I -S -B $root/trusted/scripts/windows_positive_loopback_admin_entry.py readonly --root $root --account-sid $accountSid --parent $parentPid`。此参数来自受信 parent 实际进程，不是用户请求。readonly 模式不 Resume 该父，不执行 -a/-d，完整 Get 前后相同；它核真实标准 token 访问、实际请求写／公有读正控、私有 data/EA/attributes/owner/DACL/rename/route 替换负控及 SDK／loader。受信 parent 无论准备或入口失败都必须用其原持有句柄回收尚未 Resume 的父；不是靠 JSON 的 reaped。
- [ ] `readonly_ready` 在 finally 之前输出，因此必须等待完整进程 **exit0**、完整 JSON、private 账本原件及 cleanup/Store.close 完成才接受。只 grep 首行、安装成功、sign 成功或所有负控都拒绝均不能代替正控。
- [ ] 原始只读证明包括 System32 工具 PE/真实版本/架构/hash/ID/links、全部 route owner原件／DACL／实际 token effective rights、private 文件 links==1、完整目录成员及缺席 cfg/_pth/zip 槽、真实 loaded DLL/pyd 路径、Job nested/empty事实。未知 owner 原样记，不猜 TrustedInstaller，不为变绿添加 owner 白名单。

OS shared image 角色只限 GetSystemDirectoryW 确定的 System32 工具和实际已加载的 System32 image。其 raw links>=1 不单独授信，必须和原 file ID、leaf+全 route 无 mutation、持有无 write/delete sharing、版本/hash/PE及原始安全描述符共同成立；private副本／请求／账本始终 single-link。依据 [CreateHardLinkW](https://learn.microsoft.com/zh-cn/windows/win32/api/winbase/nf-winbase-createhardlinkw) 的同底层 file 共享 SD/sharing 合同，不泛化到任意 hardlink。依据 [CreateFileW](https://learn.microsoft.com/en-us/windows/win32/api/fileapi/nf-fileapi-createfilew)，share lock **不**影响 attributes/EA，故仍必须独立验证这两类有效权限与原生负控。x64/ARM64 任何未知均失败；这只是待原生证实的角色设计，不是现 runner 已通过。

### Task 4：第二片实际 consumer 与 finally／always 的硬依赖

**Dependencies:** Task 3 同 SHA 双 Windows 完整只读正负控通过，并且下一片所有完整 TEST/SOURCE/workflow patch 双审、实际 TDD 后才允许启用。
**Parallelizable:** No（原 Create hr0→launch→profile delete、标准父、admin server 与 always 是同一生命周期）。

下一完整 PLAN 必须实际闭合下面每个接点，不能把本片模型／readiness 文件当替代，也不能在本文任务打勾：

| 真实 consumer 接点 | 必须使用的本片接口／事实 | 失败义务 |
| --- | --- | --- |
| admin runtime 及临时账号之前 | freeze 保护加载边界；精确 root 由受信 parent 保存，不扫目录；同上下文仅一实例 | 不创建可执行 admin 入口于 probeRoot；失败不 Resume |
| 原标准用户父创建 | 真实 CreateProcessWithLogonW SUSPENDED；受信 parent 持初始 thread，Native.attach_parent 加 admin-only outer Job、真实 token/PID/creation 与 readonly准入 | Create/assign/flush/prepare 任一失败，parent 实际回收原 suspended handle；无残留证据为 unknown |
| bootstrap 就绪后 | parent 核完整受保护 bootstrap 身份、admin server仍活后才 Resume；标准用户使用 frozen 两 profiles、SID、nonce、两端口，冲突不重选 | 不改现 capability/fixed argv guard；不用新 bootstrap 消息 |
| windows_appcontainer 真正 CreateProfile hr==0 后、任何 payload launch 前 | 固定私有 session 读取 `{identity,binding}`；实际 SID match；窄 WriteFile-only 固定 profile-created.request（不 GENERIC_WRITE、不需要 client Flush）；同步等 admin add.json | hr非0/已存在/错SID不发送、不接管；缺/错/迟到回执绝不 launch |
| add 后原 fixed payload | 读取独立 operation.json；保持原标准 token、单 private capability、12s Job预算、固定地址、真实 host canary及双 nonce JSON | manifest/receipt 不是网络成功；坏 nonce、重包、单栈或105均失败并清理 |
| 原 positive scope 的 helper | 原前后 `_observe_positive_loopback_config` 有界停止／回收后才 finished；Reviewer WFP helper 不提前跨此 gate | 全 PID list>1 就先停止自有 helper；不省略 PID、不把多个降为通过 |
| payload finally、profile delete之前 | fixed probe-finished.request 绑定 **operation**，admin 正常只接受 live bound parent唯一PID；等精确 cleanup receipt | 无论 payload结果、异常或断言都尝试 owned清理；未回收先 admin TerminateJob+empty |
| 原 ACL/profile finally | cleanup receipt 后运行原恢复并退出；admin server 持 outer Job 到实际父退出，保留原 ACL/profile 各自证据 | config restored 不抵 ACL/profile失败；parent 不退出30s则回收且失败，不授正常完成 |
| workflow parent finally | admin server真实退出／有界回收；原账号与probeRoot删除不得先删admin ledger；精确 root记录持续可用 | 不让临时账号删除或进程结束抵销 exemption restore未知 |
| 独立 `if: always()` | 从受信精确 root以 frozen python／entry `recover --root $root`；启动即唯一30s软件预算，先重核 durable账本、命名Job/原PIDcreation，再 fresh Get/owned delete/验证 | 坏账本不猜SID；reaped bool/ready False不授删；未排除 late add不并发delete；原首错保留、cleanup错另列 |

仅 Bootstrap 的 profile_created 和 operation 的 probe_finished 两种客户端请求。标准用户固定写入实现必须使用 FILE_WRITE_DATA 的 CreateFileW＋WriteFile＋Close，先写一次后关闭；其请求不是恢复 authority，不要求给它 GENERIC_WRITE／WRITE_EA／WRITE_ATTRIBUTES 或 Flush 权限。读取期间 share 与 file identity 门防并发替换，admin 消费标志实际 Flush 后才可能 CLI。

独立 always 用完整原账本重新认证；允许临时账号已经被原 finally 删除，但不接受同名新 SID。core/admission JSON、durable intent、ready-to-resume 和执行结果是四件不同事：仅 intent 不够；ready＋attempted=None/True 只表示可能执行；同实例明确 attempted=False 不能接管之后出现的 target。所有窄删除前仍必须实际观察命令 Job/PID 无 late add。若账本撕裂／缺失或 PID身份未持久化，只能 unknown/候选失败，不能猜 SID或声称零残留。

这次不修改实际 workflow、不启用任何 CLI、不增加权限/安装、service、PATH、自由 argv、timeout/pin 或日志 annotation 槽。下一片通过之前，本片即使软件及只读门通过，也不能将 core GREEN/admin restoration 赋给原生正控、Reviewer DENY、WP0b sourcechain准入或产品 readiness。原来源链 owner_untrusted/launch_authorized=false 的实际风险独立保留；另起此 admin 存储合同不绕过它。

## 已发生的诊断与证据边界

最终attach局部修订的整片证据：独立作者`b0f335`以显式既有3.11.17，对 SOURCE `c35d140264186a3a1d47ece71a49c6cf86484fe56f1ab4e6d028995be8bede86` / TEST运行DOC `3c0bd0d314d5b5de896851f5150a27f076370985f5a3fed80da34eae3e16f890` 完整152P/0F/E/skip、真实exit0、11.931s；合并日志952 bytes SHA256 `425bf66533047268f45486ed05f13c2a01aefd528d79e698b9abd480a09c6952`。原26dfbd／7cdac7同TEST围栏RED原日志40920 bytes SHA256 `33383fe39f4750bd064811174525f157ad9f9e5fdf3249095a71e59edef78565`。root `bfeee6/1f7dd6` 独立同c35d140／3c0bd0完整152P/0F/E/skip、exit0、11.221s，完整原输出`windows-root-152-green-raw`。最终TEST04670只改metadata，八围栏与原RED及该GREEN逐字相同；c35d140之后主PLAN仅owner说明/清单/计数/证据文字，九SOURCE围栏不变。仅DOC RAM，不授正式TDD、Windows3.12/ABI/系统恢复/native。

后续fresh QUALITY C0/I1/M0拒绝26dfbd实施：attach未认证PID被终止，Assign失败的空Job不能回收仍活parent。root实际MCP `a63d6b` 与批准局部方案后，独立TEST `e29884` 对 SOURCE `26dfbd2748e47a193bb8bd4b9eb4c9703c0d9d087200848ae8eabb7b1739ed40` / TEST `7cdac7a19acb967dd9334359c747697c6b580bbf05270d64b51e9d98a704d1bd` 显式3.11.17完整152方法、11Assertion/0ERROR/skip、exit1、10.267s；原146P保留。负控包含未认证、creation 0/bool/2^64、认证未入组、Assign失败但已退出、多清理失败；真实membership及transfer后Store拥有正控未删。仅Native.attach_parent修改后的root `348c9f` 七attach方法全P、0F/E/skip、exit0，明确是GREEN不是RED。无新字段/协议/权限/依赖；parent已退出不证明Job无成员，独立wait_empty未知仍失败。

独立TEST作者最终`366afa`以显式既有3.11.17，对10e1bed SOURCE／3d4e TEST同完整围栏146P/0F/E/skip、exit0、11.800s，原合并日志952 bytes SHA256 `2e236cf90fd8ef275b698768a3657f0428db9c3bfc90d50cd1342c4258ed321d`；最终TEST DOC71079只改metadata，八围栏与3d4e相同。此日志与下述root独立完整原输出分开保存，不当正式TDD或原生证据。

最终全owner修订：fresh QUALITY对原949判C0/I1/M0，要求同根完整修复而非仅三方法。原949 SOURCE / TEST `0ddd5c441d533f364ccbe3b5ea27b16314244104e3daaddb6fb39f40acf47d19` 的原件诊断记录146方法、原127P、新19失败方法含80Assertion subfail、0ERROR/skip、exit1。但后续修正了递进monotonic、entry真实sys.exception委托、Store假关闭异常类型、body_entered替代不适用的traceback guard、DACL故障注入时机等夹具问题，不能把80条全部当最终TEST同字节语义RED，更不能追认正式TDD。root `72612c` 对原949/9338b3独立copytree+Store.create两方法10Assertion/0ERROR/skip、exit1的有效因果单独保留。不逆patch重构原源码追认缺失快照；正式TEST-only仍必须未来实际执行。

全七Python owner路径及最后三处立即LocalFree notes修订后，root `2452a1`（启动`e2a885`）明确既有Python3.11.17，对 SOURCE DOC `10e1bedb316bc84b22f6705dc393791bbd1ed2be3265916464da1a059f640ba2` / TEST DOC `3d4e199674e6c15335a5f212163e8bf4a3e25cf9b7bd04536fc1b6b8940d0e42` 独立完整146P/0F/E/skip、真实exit0、11.204s；完整原日志保存在`windows-root-146-final-raw`。方法分布13/7/15/16/17/16/52/10。10e1→26dfbd阶段只改资产清单/owner清单/Task计数及证据说明，九SOURCE围栏完全相同；软件假API不授实际回收、ABI或系统恢复信用。

以下146/127/124/123/110记录均为各自历史冻结阶段；其中“围栏不变”仅约束所列相邻快照，不指当前全owner修订。当前唯一实施预期以Task 1的152方法及上表字节为准。

当前AGENTS输入已由root明确批准重绑定f447：原21行/2833B/`0ba269a024355705ca4a9f5abbac70096c26c2b04ffdc5da97854121279dc7e6`保留为历史；用户要求去机器专属路径并增加ICODE-SKILL逐批授权/验证提交推送义务，现27行/3559B见上表。已全文重读；不改变本片实际代码禁止范围，也不授新增Skill修改。

独立TEST作者最终 `41360f` 对同修订围栏、TEST运行快照`981a3256d35c3acbe97962485589d7d52e1ab2ab4e5302b7eae459f13c1c1639`完整127P/0F/E/skip、exit0，日志26736 bytes SHA256 `316d413278743e6cc55753e4944ee3469b5390e8cc76b284a6170a873d81a85d`；最终TEST DOC仅metadata变更为上表4af43，八围栏未变。

fresh Windows SPEC 对a8d发现同根attempt-all/首因缺口（C0/I1/M0）：effective_access、verify_security、_canaries首个释放失败会跳后续资源，并可能盖原body异常。独立TEST作者 `d0d0e9` 对原 SOURCE `a8d439041767efd04b34caa3eff91664d2900912966fdca3b6688e685185060f` / TEST `4975a1383e089b668300bc0686c5967f8333409073e533ea959a039d32bffd7b` 显式3.11.17完整127方法，原124P、新三方法18Assertion subfail、0ERROR/skip、exit1。修订仅两SOURCE围栏三方法：每个已拥有资源均attempt，body原异常对象/args不变，释放错误逐条以`cleanup_unknown: {error!r}`异常notes记录；body成功但释放失败抛首个释放异常，不授回收成功。RevertToSelf同样保留body首因。root `13c954` 独立绑定 SOURCE `b046f25ea61f4ee63be6964b63a8875939bb3eb2855edc884eae3dc5afe842d1` / TEST `981a3256d35c3acbe97962485589d7d52e1ab2ab4e5302b7eae459f13c1c1639`，显式既有3.11.17完整127P/0F/E/skip、真实exit0，完整原日志`admin-root-127-raw`。b046→949阶段仅metadata收尾，两修订围栏及其它七围栏不变。仍非正式TDD或原生验收。

最终角色修订的完整诊断：独立TEST作者 `b780ae`，显式既有3.11.17，SOURCE DOC `ea31789d28d7280730ee36ce7f5c8427e6a5f7ea807ac6f9376adab45bb9814d` / TEST DOC `a8a1c3305bce86ace8cad59c0e5e742ebaedc121b6cc018b7de1784fd278d5a8`，124P/0F/E/skip、真实exit0；完整日志26059 bytes、SHA256 `8d9d5ffebe70d10dfee1a5f8eab5a646e68275ab08fab4d4d214683c455e5ff4`。root `bdfc90` 另以同一显式3.11.17独立完整124P/0F/E/skip、exit0，绑定 SOURCE DOC `4aaeeb6c0bc883ae03930885487ecf92a9e20414d5a77919dcb11001a22c8d60` / 同a8a1 TEST，完整原日志保存在其 `admin-root-124-raw`。792535→ea317→4aae→949之前的收尾阶段只更新表格/计数/说明，九SOURCE围栏字节保持不变；TEST最终metadata也未改八围栏。完整方法数12/7/12/14/13/14/43/9。以上仅DOC RAM诊断，不是正式文件TDD或原生通过。

以下110方法记录仅属首次冻结历史，不是本次修订代码的通过证据。fresh SPEC 对原 `f68bdea3aad642db88d6f01ba6c90fb1a898f81105de2c7c6a5bfb83c1a2006e` 判 C0/I5/M0 不通过；独立 TEST `29749020c2325ae67524020dd9f5a3046de43467dfe05f8cbccb444281a14422` 的121方法由作者 `7541a1` 和 root `7baafb` 显式3.11.17独立重现14个Assertion失败条目、0ERROR/skip、exit1。原失败未删：嵌套目录安全复用、真实首次cleanup产物独立重开、LocalFree失败双句柄回收、serve四外围首错、baseline及after-add跨字段约束。

本次源码围栏修复上述五项，并为每个实际共享System32 image加入PE/架构/版本/hash/ID及安全事实重验。root `f4aeeb` 对 SOURCE DOC `d65a95ac1a6356f3417cbba2e26bbc5d31bba241db8212b180f76a99e91be953` / TEST DOC `534c0080a2461d8b5ee5754e44676348340ded1ddac66f16964992a518a25c73` 独立完整123P/0F/E/skip、exit0。随后发现同路径single-link DLL可清空proof降格：独立作者 `b0ef02` 对同d65 / TEST `8334dbfcdaccd4c1abf8d6ef252c65fbeefea80c25967d82f1e2570e7d75fbad`，Native43方法42P、2Assertion subfail、0ERROR/skip、exit1；root `0d494c` 独立重现同一方法两失败。最终角色修订不增加字段：private仅取真实root下完整frozen_files批准集合；集合外必须真实GetSystemDirectory路径和完整proof，nullable值不能自授角色。解析器本身仍不授OS authority。

首次冻结独立 TEST 作者明确使用 `/home/orbbec/icode-r2r3-env.DL2JQJ/bin/python`，实际 3.11.17，工具 `e7c6cb`：当时八 TEST 围栏 **110 PASS / 0 FAIL / 0 ERROR / 0 skip、真实总 exit0**；模块方法数为 12/7/11/13/10/13/35/9。SOURCE DOC 快照 `d37fe1a0d57669ac6b10f404fba13af1aa682eca05a7332bf4703b5d16c1246c`，TEST DOC 快照 `5244ce1f0799cd911244da81ea3c39f5e3fd472340fc00ccd7661838bef176c0`，原输出 SHA256 `5dbd943a7628e84fb82690ffea7eeb99d324f9fc77794697cf282cbb854c07f8`。当时metadata更新未改围栏；本次I1–5修订已改变五个SOURCE围栏，绝不转移旧110信用。

root 当时亲自独立以同一显式 3.11.17 harness 复跑八组件，110P／零 F/E/skip、总 exit0，完整原输出 24695 字符留在其工具内存；绑定 SOURCE DOC `cc969f456baa7c3a0cdddfc2a979e8a2a565eb4864444148f6c9dbdbe4975c6f`／TEST DOC `821d9afa74011d42f8a3adf2ecaab9773f9ee843059c297727a3515412b4805d`。仅d37fe→cc969阶段围栏相同，不能描述本次修订为相同代码。当前正式TEST-only预期以Task 1的146为准，仍未正式落地执行。

这只是 DOC 中完整代码的 RAM 预演：没有实际 SOURCE/TEST 文件、没有正式 TDD、没有目标 Python3.12／Windows API／SDK编译／NTFS／管理员／CLI／网络操作。本机平台 ctypes.wintypes 的 DWORD/LONG/BOOL可能8bytes、FILETIME16，软件 fixture同布局不授 Windows ABI；C全77键的静态覆盖也不授实际值。历史前六61/65项诊断曾误用WSL默认3.10，独立 TEST DOC保留并纠正，不重命名成3.11或正式成功；实际Fixture错误不当源码RED，真实两Store缺口修SOURCE且原负控保留的历史分账也保留。

## 自 SPEC／QUALITY 与七维自检

自 SPEC：完整 Get、逐 SID+array HeapFree／派生 FreeSid、无 Set export；系统唯一 SID CLI；protected ledger／loading boundary、两 immutable domain、三个独立时钟及可恢复／未知故障分账；正常 finally及always；原wrapper/Job/nonce/ACL/profile链与下一片硬依赖逐项对应两份 SPEC。不以可构造 State、JSON、receipt、安装/sign或时间耗尽改写授权。

自 QUALITY：反查 preexisting误删、ready但未Resume误接管、target属性冲突、foreign快照回滚、PID reuse、namedJob丢失、Flush撕裂、原入口resolve吃掉reparse、walk吞错、extra import文件／sys.path、System32硬链接及nullable-proof角色降格、只denyall假ready、首行日志先于finally、原生ABI假阳性、正常close杀掉原profile finally及释放失败跳过后续资源/覆盖首因等反向场景。完整152个软件方法保留全部历史有效负控，不声称穷尽所有race或原生行为；fresh 独立SPEC／QUALITY仍必须执行。

【架构级自检报告】

- ✅ 语法／编译：七个 SOURCE Python、八个 TEST Python 围栏 AST通过；SDK C与CMake资产已完整静态核对，未编译，不写原生编译通过。
- ✅ 依赖／调用链：所有新import均有完整资产，CMake仅追加；真实Create／launch／delete、outer/command Job与两种恢复、下一片实际parent接口已逐项列出，无占位callback。
- ✅ 逻辑／边界：完整映射、exact types、单SID、foreign保留、双domain、one-shot、原始/ready/attempt/reap与三个不重置预算均有源实现和负控；以最终绑定快照的完整诊断为准，旧110P不移植。
- ✅ 异常处理：首次拥有即finally／登记，坏账本／身份／回收／预算未知拒绝；不猜SID、不把失败日志或退出0片段当完整成功，首错与cleanup分账。
- ✅ 关联模块：本轮仅本文；实际core、旧wrapper、原98及13post集合、现workflow、权限、timeout、pin和其它dirty未动。未来仅九SOURCE及八TEST；真正consumer/workflow修改必须下一完整PLAN。
- ✅ 兼容安全：缺省产品路径完全未接本片；固定CI显式opt-in；private single-link与OS共享image分角色，标准用户无自由admin命令或加载路径；前置双Windows只读正负控未通过前不可启CLI。
- ✅ 可运行性：同九SOURCE及八TEST围栏由root显式3.11.17完整RAM152P；正式文件RED→GREEN／Python3.12／SDK与同SHA双Windows／实际consumer仍未执行；这是可审查实施候选，不是100%产品或native通过。

**最终 STOP：** root 完整阅读两份 PLAN、fresh SPEC 与不同 QUALITY零阻断前不落实际 TEST/SOURCE/CI、不Git。双审以后仍先实际 TEST-only取预期RED，再不同作者精确SOURCE取GREEN；actual consumer 和同SHA双Windows全门未闭合，不授系统/网络/R2R3完成。
