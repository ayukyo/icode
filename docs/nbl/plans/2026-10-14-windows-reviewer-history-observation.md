# Windows Reviewer History Observation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use nbl.subagent-driven-development to implement this plan task-by-task. 所有实现、测试、CI操作待本PLAN fresh SPEC及不同QUALITY批准；本次只冻结文档。

**Goal:** 实际Reviewer payload入口执行既有单页历史查询，持久保存脱敏状态和事件字段，严格区分未尝试、空匹配、错误与不完整观察。

**Architecture:** 复用当前C collector的两个精确订阅、UTC窗口和Enum3单页64预算。history先核scope再校验payload scalar，schema9保留callback独立合同；两个PS消费者通过同一只读Python白名单投影保存固定job日志，历史字段不授网络DENY。

**Tech Stack:** Windows SDK C / FWPM_NET_EVENT3 / Enum3、Python stdlib unittest/AST/json、现GitHub CI Windows x64/ARM64、PowerShell。

---

## 冻结边界与文件职责

DESIGN `2378f25f3a6ca91eb2de9bd1659d074da8325f7f74c34c367ff6341f966701ac` 经root报告fresh SPEC→不同QUALITY均C0/I0/M0。本PLAN只写本文；权威根 `/home/orbbec/projects/icode`，基线 `6e893f0170b74c32d7143680636d85f400ecc7c9`。用户main-only覆盖技能worktree习惯；PLAN-only覆盖技能自动转执行要求。禁止现在修改SOURCE/TEST/CI、运行native、本机全量或git操作。

未来精确修改：新 `tests/test_windows_reviewer_history.py` 为stdlib portable语义/合同测试；C helper负责history scope/scalar/query及schema9；既有Python诊断脚本负责schema9验证/固定日志投影；CI只把该投影接到两个既有消费者及实际history请求验收；ABI三文件成对增CLASSIFY_DROP2布局；旧workflow合同两处8改9及WFP旧matcher断言迁移至三阶段helper。合计九个实现路径。无新运行依赖、filter/layer对象查询、权限、exemption、SetOption/SetLoopbackConfig、timeout、artifact或网络目标。

下列资产为实施输入，尚未应用。补丁均用apply_patch格式和精确旧context，旧context不匹配即停止并绑定新基线重审，不模糊套用。SOURCE作者与TEST作者不同，SPEC与QUALITY不同；本文作者不预报GREEN。Task0的测试仅解析/解释源文本，不导入Windows/ICODE模块、调用DLL、编译C或联网；真正SDK/原生门留给现CI双架构。

## Task 0：冻结portable TEST并取得语义RED

**状态**
- [ ] 任务完成

**Dependencies:** None
**Parallelizable:** No（RED须绑定未改SOURCE基线，禁止并行SOURCE提前转GREEN）

- [ ] TEST作者按T0完整正文新增文件，同时按T0b冻结三份既有文本合同断言更新；SOURCE作者不得修改这些TEST。
- [ ] 执行 `python3 -m unittest tests.test_windows_reviewer_history -v`；保留基线SHA、原日志、退出码。合格RED必须来自actual wait-profile参数FALSE、BOOL2被旧matcher视作nonmatch、旧summary未保留history API错误、合法schema9不能被旧classifier接受的断言；ImportError/语法/编译/测试harness失败不是RED。
- [ ] SOURCE作者之前先让不同审查者核RED归因与TEST正文；修TEST harness不顺带改SOURCE。

### T0完整文件 `tests/test_windows_reviewer_history.py`

```python
from __future__ import annotations
import ast
import copy
import json
import re
from pathlib import Path
from types import SimpleNamespace as N
import unittest

ROOT = Path(__file__).resolve().parents[1]
C = ROOT / "native/windows/icode_wfp_event_probe.c"
P = ROOT / "scripts/run_windows_appcontainer_read_probe.py"

def c_body(source, name):
    match = re.search(r"\b" + re.escape(name) + r"\s*\([^;]*?\)\s*\{", source)
    if not match:
        return None
    start = match.end()
    depth = 1
    for i in range(start, len(source)):
        depth += (source[i] == "{") - (source[i] == "}")
        if depth == 0:
            return source[start:i]
    raise AssertionError("unclosed_c_function")

def pure_python():
    tree = ast.parse(P.read_text(encoding="utf-8"))
    names = {"_classify_wfp_ipv6_loopback_receipt", "_wfp_observer_diagnostic_summary",
             "_wfp_history_receipt_valid", "_wfp_history_projection",
             "_wfp_history_cli", "_wfp_history_no_duplicates"}
    nodes = [ast.ImportFrom(module="__future__", names=[ast.alias(name="annotations")], level=0)]
    nodes.extend(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name in names)
    env = {"json": json, "re": re, "Path": Path, "sys": N(argv=[]),
           "_WFP_NETWORK_CAPABILITY_LABELS": {0: "internet", 1: "server", 2: "private"}}
    exec(compile(ast.fix_missing_locations(ast.Module(body=nodes, type_ignores=[])), str(P), "exec"), env)
    return env

def receipt():
    r = {"schema_version": 9, "target_ip_version": 6, "target_is_loopback": True,
         "subscription_attempted": True, "subscription_return_code": 0,
         "subscription_handle_present": True, "subscription_ok": True,
         "unsubscribe_ok": True, "network_events_collected": True,
         "event_callback_count": 1, "capability_drop_event_count": 1,
         "classify_drop_event_count": 0, "matched_capability_drop_count": 1,
         "matched_classify_drop_count": 0, "matched_network_capability_id": 2,
         "network_capability_id_consistent": True, "history_requested": True,
         "history_time_window_valid": True}
    for kind in ("capability", "classify"):
        for key, value in {"attempted": True, "return_code": 0, "handle_present": True,
                           "ok": True, "unsubscribe_ok": True}.items():
            prefix = kind + "_subscription_" if key != "unsubscribe_ok" else kind + "_"
            r[prefix + key] = value
        r.update({f"history_{kind}_status": "complete", f"history_{kind}_api_stage": "none",
                  f"history_{kind}_api_code": None, f"history_{kind}_returned_count": 1,
                  f"history_{kind}_matched_count": 1,
                  f"history_{kind}_attribution": {
                      "status": "consistent", "filter_id": "18446744073709551615",
                      "layer_id": None if kind == "capability" else 65535,
                      "is_loopback": True,
                      "network_capability_id": 2 if kind == "capability" else None}})
    return r

def history_semantics(source, *, scope=True, loopback=1, capability=2):
    drop = N(isLoopback=loopback, networkCapabilityId=capability)
    event = N(type=1, header=N(timeStamp=100), capabilityDrop=drop, classifyDrop=drop)
    context = N(expected_loopback=True)
    env = {"event": event, "context": context, "classify_drop": False,
           "start_time": 100, "end_time": 200, "NULL": None,
           "filetime_value": lambda x: x, "event_header_matches_target": lambda e, c: scope,
           "FWPM_NET_EVENT_TYPE_CAPABILITY_DROP": 1, "FWPM_NET_EVENT_TYPE_CLASSIFY_DROP": 2,
           "TRUE": 1, "FALSE": 0,
           "FWPM_APPC_NETWORK_CAPABILITY_INTERNET_CLIENT": 0,
           "FWPM_APPC_NETWORK_CAPABILITY_INTERNET_PRIVATE_NETWORK": 2}
    def evaluate(text):
        text = text.replace("->", ".").replace("&&", " and ").replace("||", " or ")
        text = re.sub(r"!(?!=)", " not ", text).replace("&event.header.timeStamp", "event.header.timeStamp")
        return eval("(" + text.strip() + ")", {"__builtins__": {}}, env)
    new = c_body(source, "history_event_result")
    if new is None:
        old = c_body(source, "event_matches_target")
        expression = old.split("return", 1)[1].split(";", 1)[0]
        return "MATCHED" if evaluate(expression) else "NONMATCH"
    for expression, result in re.findall(r"if\s*\((.*?)\)\s*\{\s*return\s+HISTORY_(\w+);", new, re.S):
        if evaluate(expression):
            return result
    return "MATCHED"

class TestWindowsReviewerHistory(unittest.TestCase):
    def test_actual_wait_profile_argv_requests_history(self):
        source = C.read_text(encoding="utf-8")
        block = source.split('wcscmp(argv[1], L"--collect-ipv6-loopback-wait-profile") == 0', 1)[1]
        args = re.search(r"return run_collector\((.*?)\);", block, re.S).group(1)
        self.assertIn("TRUE, TRUE, TRUE, TRUE,", args)

    def test_scalar_rejection_is_scope_bound_and_not_no_match(self):
        source = C.read_text(encoding="utf-8")
        for loopback in (2, -1):
            self.assertEqual(history_semantics(source, loopback=loopback), "INVALID_DATA")
            self.assertEqual(history_semantics(source, scope=False, loopback=loopback), "OUTSIDE_SCOPE")
        self.assertEqual(history_semantics(source, loopback=0), "NONMATCH")
        self.assertEqual(history_semantics(source, capability=3), "INVALID_DATA")
        self.assertEqual(history_semantics(source, scope=False, capability=3), "OUTSIDE_SCOPE")
        self.assertEqual(history_semantics(source), "MATCHED")

    def test_schema9_positive_and_legacy_callback_contract(self):
        f = pure_python()["_classify_wfp_ipv6_loopback_receipt"]
        r = receipt()
        self.assertEqual(f(r, collector_exit_code=0), "capability_drop_matched")
        r["schema_version"] = 8
        self.assertEqual(f(r, collector_exit_code=0), "capability_drop_matched")
        for version in (6, 7):
            r["schema_version"] = version
            self.assertEqual(f(r, collector_exit_code=0), "capability_drop_ipv6_loopback_attributed")

    def test_history_error_is_retained_by_summary(self):
        r = receipt()
        r.update(history_capability_status="api_error", history_capability_api_stage="enumerate",
                 history_capability_api_code=5, history_capability_returned_count=0,
                 history_capability_matched_count=0)
        r["history_capability_attribution"] = dict.fromkeys(
            ("filter_id", "layer_id", "is_loopback", "network_capability_id"))
        r["history_capability_attribution"]["status"] = "unavailable"
        summary = pure_python()["_wfp_observer_diagnostic_summary"](
            process_started=True, paths=None, receipt=r, collector_exit_code=1)
        self.assertEqual(summary.get("history_capability_api_code"), 5)
        self.assertEqual(summary.get("history_capability_api_stage"), "enumerate")

    def test_wire_boundaries_and_log_precision(self):
        env = pure_python()
        # Legacy baseline executes its real classifier: no missing helper import is a RED oracle.
        valid = env.get("_wfp_history_receipt_valid", lambda r:
            env["_classify_wfp_ipv6_loopback_receipt"](r, collector_exit_code=0) != "evidence_unavailable")
        r = receipt()
        self.assertTrue(valid(r))
        mutations = [("history_requested", 1), ("history_time_window_valid", None),
                     ("history_capability_returned_count", 64),
                     ("history_capability_matched_count", True),
                     ("history_capability_api_code", 0)]
        for key, value in mutations:
            bad = copy.deepcopy(r); bad[key] = value
            self.assertFalse(valid(bad), key)
        for key, value in (("filter_id", "01"), ("filter_id", "18446744073709551616"),
                           ("layer_id", 1), ("is_loopback", 2), ("unknown", "SID-path")):
            bad = copy.deepcopy(r); bad["history_capability_attribution"][key] = value
            self.assertFalse(valid(bad), key)
        if "_wfp_history_projection" in env:
            lines = env["_wfp_history_projection"](r, "reviewer_payload")
            self.assertEqual(len(lines), 2)
            self.assertTrue(all(len(x.encode("ascii")) <= 1024 for x in lines))
            self.assertIn("filter_id=18446744073709551615", lines[0])
            self.assertNotIn("{", "".join(lines))
        self.assertLessEqual(len(json.dumps(r, separators=(",", ":")).encode("ascii")), 4096)

    def test_finite_page_cleanup_and_two_ci_log_consumers(self):
        source = C.read_text(encoding="utf-8")
        query = c_body(source, "run_historical_event_query")
        self.assertEqual(query.count("FwpmNetEventEnum3("), 1)
        self.assertIn("returned_count == MAX_WFP_HISTORY_PAGE_SIZE", query)
        self.assertLess(query.index("FwpmFreeMemory0"), query.index("FwpmNetEventDestroyEnumHandle0"))
        collector = c_body(source, "run_collector")
        self.assertLess(collector.index("FwpmNetEventUnsubscribe0"), collector.index("run_historical_event_query("))
        self.assertLess(collector.index("run_historical_event_query("), collector.index("FwpmEngineClose0"))
        self.assertNotIn("FwpmEngineSetOption0(", source)
        self.assertNotIn("SetLoopbackConfig(", source)
        workflow = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
        self.assertEqual(workflow.count("--history-receipt"), 2)
        self.assertIn("subscription_probe", workflow)
        self.assertIn("reviewer_payload", workflow)

    def test_worst_legal_wire_and_distinct_query_states(self):
        env = pure_python()
        valid = env.get("_wfp_history_receipt_valid", lambda r:
            env["_classify_wfp_ipv6_loopback_receipt"](r, collector_exit_code=0) != "evidence_unavailable")
        r = receipt()
        r.update(event_callback_count=65535, capability_drop_event_count=65535,
                 matched_capability_drop_count=65535)
        for kind in ("capability", "classify"):
            r[f"history_{kind}_returned_count"] = 63
            r[f"history_{kind}_matched_count"] = 63
        self.assertTrue(valid(r))
        self.assertLessEqual(len(json.dumps(r, separators=(",", ":")).encode("ascii")), 4096)
        for status, returned, matched, attribution in (
            ("complete", 0, 0, "no_match"), ("limit_reached", 64, 64, "unavailable"),
            ("invalid_data", 63, 62, "unavailable"), ("api_error", 63, 63, "unavailable")):
            case = copy.deepcopy(r)
            for kind in ("capability", "classify"):
                case[f"history_{kind}_status"] = status
                case[f"history_{kind}_returned_count"] = returned
                case[f"history_{kind}_matched_count"] = matched
                case[f"history_{kind}_api_stage"] = "destroy" if status == "api_error" else "none"
                case[f"history_{kind}_api_code"] = 4294967295 if status == "api_error" else None
                case[f"history_{kind}_attribution"] = {
                    "status": attribution, "filter_id": None, "layer_id": None,
                    "is_loopback": None, "network_capability_id": None}
            self.assertTrue(valid(case), status)
            self.assertLessEqual(len(json.dumps(case, separators=(",", ":")).encode("ascii")), 4096)
        case = copy.deepcopy(r)
        case["history_requested"] = False
        case["history_time_window_valid"] = None
        for kind in ("capability", "classify"):
            case[f"history_{kind}_status"] = "not_attempted"
            case[f"history_{kind}_returned_count"] = case[f"history_{kind}_matched_count"] = 0
            case[f"history_{kind}_attribution"] = {
                "status": "not_attempted", "filter_id": None, "layer_id": None,
                "is_loopback": None, "network_capability_id": None}
        self.assertTrue(valid(case))
        if "_wfp_history_no_duplicates" in env:
            with self.assertRaises(ValueError):
                json.loads('{"schema_version":9,"schema_version":9}',
                           object_pairs_hook=env["_wfp_history_no_duplicates"])

    def test_error_stage_null_relation_and_malformed_wire(self):
        env = pure_python()
        valid = env.get("_wfp_history_receipt_valid", lambda r:
            env["_classify_wfp_ipv6_loopback_receipt"](r, collector_exit_code=0) != "evidence_unavailable")
        r = receipt()
        for stage in ("create", "enumerate", "destroy"):
            bad = copy.deepcopy(r)
            bad.update(history_capability_status="api_error", history_capability_api_stage=stage,
                       history_capability_api_code=5)
            if stage in ("create", "enumerate"):
                bad["history_capability_returned_count"] = bad["history_capability_matched_count"] = 0
            bad["history_capability_attribution"] = {
                "status": "unavailable", "filter_id": None, "layer_id": None,
                "is_loopback": None, "network_capability_id": None}
            self.assertTrue(valid(bad))
            for code in (None, True, 0, -1, 4294967296):
                changed = copy.deepcopy(bad); changed["history_capability_api_code"] = code
                self.assertFalse(valid(changed))
        for key, value in (("history_time_window_valid", False), ("history_requested", False),
                           ("history_classify_returned_count", -1), ("history_classify_matched_count", 2),
                           ("history_classify_api_stage", "create"), ("history_extra", "SID-path")):
            bad = copy.deepcopy(r); bad[key] = value
            self.assertFalse(valid(bad), key)
        bad = copy.deepcopy(r); del bad["history_capability_api_stage"]
        self.assertFalse(valid(bad))
        bad = copy.deepcopy(r); bad["history_classify_attribution"]["layer_id"] = 65536
        self.assertFalse(valid(bad))
        bad = copy.deepcopy(r); bad["history_classify_attribution"]["network_capability_id"] = 0
        self.assertFalse(valid(bad))

if __name__ == "__main__":
    unittest.main()
```

### T0b TEST作者冻结的旧schema/matcher合同补丁

```diff
*** Begin Patch
*** Update File: tests/test_ci_workflow_contracts.py
@@
-            "$observerSchema -eq 8",
+            "$observerSchema -eq 9",
@@
-        self.assertIn("$schemaVersion -eq 8", identity_step)
+        self.assertIn("$schemaVersion -eq 9", identity_step)
*** Update File: tests/test_windows_wfp_capture.py
@@
-        self.assertIn("history_event_matches_target(", history_query)
+        self.assertIn("history_event_result(", history_query)
*** Update File: tests/test_windows_wfp_abi.py
@@
-        self.assertIn(r'\"schema_version\":8', source)
+        self.assertIn(r'\"schema_version\":9', source)
*** End Patch
```

这些结构合同不是独立语义RED依据；T0真实断言仍须证明actual argv FALSE / BOOL2误吞 / error丢失 / schema9不支持。新三阶段helper承担history scope判断；旧bool matcher留在callback与既有self-test，不能把“找不到旧helper字串”算产品功能失败。TEST作者还在此冻结 `test_subscription_return_code_is_preserved_in_bounded_native_receipt` 的唯一IPv6 writer schema8→9断言；IPv4 schema6断言维持，SOURCE作者不得临场修改TEST。

## Task 1：C SOURCE与原生自测资产

**状态**
- [ ] 任务完成

**Dependencies:** Task 0
**Parallelizable:** No（独立SOURCE作者消费已绑定RED，不得改冻结TEST）

- [ ] SOURCE作者先完整读C，再应用S1；保持每类型一页64、UTC、两路unsubscribe、free/close顺序。
- [ ] portable T0部分GREEN且旧WFP/ABI/CI合同定向回归；不以C文本合同替原生验证。原生自测必须沿现CI编译后 `--self-test` 执行，不在本机运行。
- [ ] 独立SPEC和不同QUALITY核S1/scalar/资源生命周期；任一C/I/M未关闭不得进入候选提交。

### S1 `native/windows/icode_wfp_event_probe.c` 精确补丁

```diff
*** Begin Patch
*** Update File: native/windows/icode_wfp_event_probe.c
@@
     UINT32 matched_count;
+    BOOL attribution_present;
+    BOOL attribution_mixed;
+    UINT64 filter_id;
+    UINT16 layer_id;
+    BOOL is_loopback;
+    FWPM_APPC_NETWORK_CAPABILITY_TYPE network_capability_id;
 } WfpHistoryQueryResult;
@@
 typedef struct WfpHistoryDiagnostics {
+    BOOL requested;
*** End Patch
```

S1a：在 `static void run_historical_event_query(` 前完整插入以下定义。S1b是余下完整精确补丁；本资产用完整code形式冻结新增函数，禁止生成近似版本。

```c
enum WfpHistoryMatch {
    HISTORY_OUTSIDE_SCOPE, HISTORY_NONMATCH, HISTORY_MATCHED, HISTORY_INVALID_DATA
};

static enum WfpHistoryMatch history_event_result(
    const FWPM_NET_EVENT3 *event, const WfpProbeContext *context,
    const FILETIME *start_time, const FILETIME *end_time, BOOL classify_drop
) {
    if (event == NULL || context == NULL || start_time == NULL || end_time == NULL ||
        filetime_value(end_time) < filetime_value(start_time)) {
        return HISTORY_OUTSIDE_SCOPE;
    }
    if ((classify_drop && event->type != FWPM_NET_EVENT_TYPE_CLASSIFY_DROP) ||
        (!classify_drop && event->type != FWPM_NET_EVENT_TYPE_CAPABILITY_DROP) ||
        filetime_value(&event->header.timeStamp) < filetime_value(start_time) ||
        filetime_value(&event->header.timeStamp) > filetime_value(end_time) ||
        !event_header_matches_target(event, context)) {
        return HISTORY_OUTSIDE_SCOPE;
    }
    if ((classify_drop && event->classifyDrop == NULL) ||
        (!classify_drop && event->capabilityDrop == NULL)) {
        return HISTORY_INVALID_DATA;
    }
    if ((classify_drop && event->classifyDrop->isLoopback != FALSE &&
            event->classifyDrop->isLoopback != TRUE) ||
        (!classify_drop && event->capabilityDrop->isLoopback != FALSE &&
            event->capabilityDrop->isLoopback != TRUE) ||
        (!classify_drop &&
            (event->capabilityDrop->networkCapabilityId < FWPM_APPC_NETWORK_CAPABILITY_INTERNET_CLIENT ||
             event->capabilityDrop->networkCapabilityId > FWPM_APPC_NETWORK_CAPABILITY_INTERNET_PRIVATE_NETWORK))) {
        return HISTORY_INVALID_DATA;
    }
    if ((classify_drop && event->classifyDrop->isLoopback != context->expected_loopback) ||
        (!classify_drop && event->capabilityDrop->isLoopback != context->expected_loopback)) {
        return HISTORY_NONMATCH;
    }
    return HISTORY_MATCHED;
}

static void record_history_attribution(
    WfpHistoryQueryResult *result, const FWPM_NET_EVENT3 *event, BOOL classify_drop
) {
    UINT64 filter_id = classify_drop ? event->classifyDrop->filterId : event->capabilityDrop->filterId;
    UINT16 layer_id = classify_drop ? event->classifyDrop->layerId : 0;
    BOOL is_loopback = classify_drop ? event->classifyDrop->isLoopback : event->capabilityDrop->isLoopback;
    FWPM_APPC_NETWORK_CAPABILITY_TYPE capability = classify_drop
        ? FWPM_APPC_NETWORK_CAPABILITY_INTERNET_CLIENT : event->capabilityDrop->networkCapabilityId;
    if (result->attribution_present) {
        if (result->filter_id != filter_id || result->layer_id != layer_id ||
            result->is_loopback != is_loopback || result->network_capability_id != capability) {
            result->attribution_mixed = TRUE;
        }
    } else {
        result->attribution_present = TRUE;
        result->filter_id = filter_id;
        result->layer_id = layer_id;
        result->is_loopback = is_loopback;
        result->network_capability_id = capability;
    }
}

static BOOL format_history_attribution(
    char *out, size_t capacity, const WfpHistoryQueryResult *result, BOOL classify_drop
) {
    const char *status = "unavailable";
    char filter_id[24] = "null";
    char layer_id[8] = "null";
    char capability_id[8] = "null";
    const char *loopback = "null";
    int written;
    if (result->status == WFP_HISTORY_NOT_ATTEMPTED) {
        status = "not_attempted";
    } else if (result->status == WFP_HISTORY_COMPLETE && result->matched_count == 0) {
        status = "no_match";
    } else if (result->status == WFP_HISTORY_COMPLETE && result->attribution_present) {
        status = result->attribution_mixed ? "mixed" : "consistent";
        if (!result->attribution_mixed) {
            if (_snprintf_s(filter_id, sizeof(filter_id), _TRUNCATE, "\"%llu\"",
                    (unsigned long long)result->filter_id) < 0) { return FALSE; }
            if (classify_drop) {
                if (_snprintf_s(layer_id, sizeof(layer_id), _TRUNCATE, "%u",
                        (unsigned int)result->layer_id) < 0) { return FALSE; }
            } else {
                if (_snprintf_s(capability_id, sizeof(capability_id), _TRUNCATE, "%u",
                        (unsigned int)result->network_capability_id) < 0) { return FALSE; }
            }
            loopback = result->is_loopback ? "true" : "false";
        }
    }
    written = _snprintf_s(out, capacity, _TRUNCATE,
        "{\"status\":\"%s\",\"filter_id\":%s,\"layer_id\":%s,\"is_loopback\":%s,\"network_capability_id\":%s}",
        status, filter_id, layer_id, loopback, capability_id);
    return written > 0 && (size_t)written < capacity;
}

static BOOL history_scalar_self_test(void) {
    BYTE sid_buffer[SECURITY_MAX_SID_SIZE];
    DWORD sid_size = sizeof(sid_buffer);
    WfpProbeContext context = {0};
    FWPM_NET_EVENT3 event = {0};
    FWPM_NET_EVENT_CAPABILITY_DROP0 capability = {0};
    FWPM_NET_EVENT_CLASSIFY_DROP2 classify = {0};
    FILETIME start = {100, 0}, end = {200, 0};
    WfpHistoryQueryResult result = {0};
    char formatted[256];
    if (!CreateWellKnownSid(WinWorldSid, NULL, sid_buffer, &sid_size)) { return FALSE; }
    context.expected_package_sid = sid_buffer;
    context.expected_ip_version = FWP_IP_VERSION_V6;
    context.expected_loopback = TRUE;
    context.expected_remote_address_v6[15] = 1;
    context.expected_remote_port = 43210;
    event.header.flags = FWPM_NET_EVENT_FLAG_IP_VERSION_SET | FWPM_NET_EVENT_FLAG_IP_PROTOCOL_SET |
        FWPM_NET_EVENT_FLAG_REMOTE_ADDR_SET | FWPM_NET_EVENT_FLAG_REMOTE_PORT_SET | FWPM_NET_EVENT_FLAG_PACKAGE_ID_SET;
    event.header.packageSid = sid_buffer;
    event.header.ipVersion = FWP_IP_VERSION_V6;
    event.header.ipProtocol = IPPROTO_TCP;
    event.header.remoteAddrV6.byteArray16[15] = 1;
    event.header.remotePort = context.expected_remote_port;
    event.header.timeStamp = start;
    event.type = FWPM_NET_EVENT_TYPE_CAPABILITY_DROP;
    event.capabilityDrop = &capability;
    capability.isLoopback = 2;
    if (history_event_result(&event, &context, &start, &end, FALSE) != HISTORY_INVALID_DATA) { return FALSE; }
    event.header.remotePort++;
    if (history_event_result(&event, &context, &start, &end, FALSE) != HISTORY_OUTSIDE_SCOPE) { return FALSE; }
    event.header.remotePort--;
    capability.isLoopback = FALSE;
    if (history_event_result(&event, &context, &start, &end, FALSE) != HISTORY_NONMATCH) { return FALSE; }
    capability.isLoopback = TRUE;
    capability.networkCapabilityId = (FWPM_APPC_NETWORK_CAPABILITY_TYPE)3;
    if (history_event_result(&event, &context, &start, &end, FALSE) != HISTORY_INVALID_DATA) { return FALSE; }
    capability.networkCapabilityId = FWPM_APPC_NETWORK_CAPABILITY_INTERNET_PRIVATE_NETWORK;
    capability.filterId = ~(UINT64)0;
    if (history_event_result(&event, &context, &start, &end, FALSE) != HISTORY_MATCHED) { return FALSE; }
    event.header.timeStamp.dwLowDateTime = 99;
    if (history_event_result(&event, &context, &start, &end, FALSE) != HISTORY_OUTSIDE_SCOPE) { return FALSE; }
    event.header.timeStamp = end;
    if (history_event_result(&event, &context, &start, &end, FALSE) != HISTORY_MATCHED) { return FALSE; }
    event.header.timeStamp.dwLowDateTime++;
    if (history_event_result(&event, &context, &start, &end, FALSE) != HISTORY_OUTSIDE_SCOPE) { return FALSE; }
    event.header.timeStamp = start;
    event.capabilityDrop = NULL;
    if (history_event_result(&event, &context, &start, &end, FALSE) != HISTORY_INVALID_DATA) { return FALSE; }
    event.capabilityDrop = &capability;
    result.status = WFP_HISTORY_COMPLETE;
    result.matched_count = 1;
    record_history_attribution(&result, &event, FALSE);
    if (!format_history_attribution(formatted, sizeof(formatted), &result, FALSE) ||
        strstr(formatted, "\"18446744073709551615\"") == NULL) { return FALSE; }
    capability.filterId--;
    record_history_attribution(&result, &event, FALSE);
    if (!result.attribution_mixed) { return FALSE; }
    result.status = WFP_HISTORY_LIMIT_REACHED;
    if (!format_history_attribution(formatted, sizeof(formatted), &result, FALSE) ||
        strstr(formatted, "\"status\":\"unavailable\"") == NULL) { return FALSE; }
    result.status = WFP_HISTORY_COMPLETE;
    result.matched_count = 0;
    if (!format_history_attribution(formatted, sizeof(formatted), &result, FALSE) ||
        strstr(formatted, "\"status\":\"no_match\"") == NULL) { return FALSE; }
    result.status = WFP_HISTORY_NOT_ATTEMPTED;
    if (!format_history_attribution(formatted, sizeof(formatted), &result, FALSE) ||
        strstr(formatted, "\"status\":\"not_attempted\"") == NULL) { return FALSE; }
    event.type = FWPM_NET_EVENT_TYPE_CLASSIFY_DROP;
    event.classifyDrop = &classify;
    classify.isLoopback = -1;
    if (history_event_result(&event, &context, &start, &end, TRUE) != HISTORY_INVALID_DATA) { return FALSE; }
    classify.isLoopback = TRUE;
    classify.layerId = 65535;
    if (history_event_result(&event, &context, &start, &end, TRUE) != HISTORY_MATCHED) { return FALSE; }
    return TRUE;
}
```

### S1b history query / writer / lifecycle精确补丁

```diff
*** Begin Patch
*** Update File: native/windows/icode_wfp_event_probe.c
@@
     UINT32 index;
+    enum WfpHistoryMatch match;
     DWORD api_result;
@@
-            if (history_event_matches_target(
-                    entries[index], context, start_time, end_time,
-                    classify_drop)) {
+            match = history_event_result(entries[index], context, start_time, end_time, classify_drop);
+            if (match == HISTORY_INVALID_DATA) {
+                result->status = WFP_HISTORY_INVALID_DATA;
+                break;
+            }
+            if (match == HISTORY_MATCHED) {
                 ++result->matched_count;
+                record_history_attribution(result, entries[index], classify_drop);
@@
-    char json[2048];
+    char json[4096];
+    char capability_attribution[256];
+    char classify_attribution[256];
@@
     if (ipv6_loopback) {
+        if (!format_history_attribution(capability_attribution, sizeof(capability_attribution),
+                &history_values->capability, FALSE) ||
+            !format_history_attribution(classify_attribution, sizeof(classify_attribution),
+                &history_values->classify, TRUE)) { return FALSE; }
         written = _snprintf_s(
@@
-            "{\"schema_version\":8,\"target_ip_version\":6,"
+            "{\"schema_version\":9,\"target_ip_version\":6,"
@@
-            "\"history_classify_matched_count\":%lu}\n",
+            "\"history_classify_matched_count\":%lu,"
+            "\"history_requested\":%s,"
+            "\"history_capability_attribution\":%s,"
+            "\"history_classify_attribution\":%s}\n",
@@
-            (unsigned long)history_values->classify.matched_count
+            (unsigned long)history_values->classify.matched_count,
+            history_values->requested ? "true" : "false",
+            capability_attribution, classify_attribution
@@
-    history_diagnostics.capability.status = enumerate_history
+    history_diagnostics.requested = enumerate_history;
+    history_diagnostics.capability.status = enumerate_history
@@
     if (engine != NULL) {
         close_result = FwpmEngineClose0(engine);
         engine = NULL;
     }
+    if (enumerate_history && close_result != ERROR_SUCCESS) {
+        /* Preserve earlier API stage/code; complete queries lose cleanup credit. */
+        if (history_diagnostics.capability.status == WFP_HISTORY_COMPLETE) {
+            history_diagnostics.capability.status = WFP_HISTORY_UNAVAILABLE;
+        }
+        if (history_diagnostics.classify.status == WFP_HISTORY_COMPLETE) {
+            history_diagnostics.classify.status = WFP_HISTORY_UNAVAILABLE;
+        }
+    }
@@
     if (result_written && ready_written && close_result == ERROR_SUCCESS &&
-        (!subscription_ok || (stop_seen && unsubscribe_ok))) {
+        (!subscription_ok || (stop_seen && unsubscribe_ok)) &&
+        (!enumerate_history ||
+         (history_diagnostics.capability.status == WFP_HISTORY_COMPLETE &&
+          history_diagnostics.classify.status == WFP_HISTORY_COMPLETE))) {
@@
-        return classifier_self_test() ? 0 : 1;
+        return classifier_self_test() && history_scalar_self_test() ? 0 : 1;
@@
-            argv[2], 0, remote_port, TRUE, TRUE, TRUE, FALSE,
+            argv[2], 0, remote_port, TRUE, TRUE, TRUE, TRUE,
*** End Patch
```

S1/S1b中每实际hunk均有加减行；新增函数S1a完整插入指定唯一锚点。禁止以修补丁为由扩展SOURCE范围。

## Task 2：Python schema9严格验证及固定日志CLI

**状态**
- [ ] 任务完成

**Dependencies:** Task 1
**Parallelizable:** No（必须承接C冻结wire，旧6/7/8兼容同步）

- [ ] 不同SOURCE作者完整读脚本，按S2插入全部pure函数并用S2b接现classifier/summary/main；不新增文件或公开网络路径。
- [ ] T0全Python GREEN；执行旧 `tests.test_windows_appcontainer_read_probe` 定向回归；schema6/7/8原fixture不删除、不以9默认值升级。
- [ ] 独立双审确认非法/重复键、精度、stage/code、callback分账及非零exit错误信息保留。

### S2：在 `_classify_wfp_ipv6_loopback_receipt` 前插入完整函数

```python
def _wfp_history_receipt_valid(receipt: object) -> bool:
    if not isinstance(receipt, dict) or type(receipt.get("schema_version")) is not int or receipt["schema_version"] != 9:
        return False
    base_keys = {
        "schema_version", "target_ip_version", "target_is_loopback", "subscription_attempted",
        "subscription_return_code", "subscription_handle_present", "subscription_ok", "unsubscribe_ok",
        "network_events_collected", "event_callback_count", "capability_drop_event_count",
        "classify_drop_event_count", "matched_capability_drop_count", "matched_classify_drop_count",
        "matched_network_capability_id", "network_capability_id_consistent"}
    for kind in ("capability", "classify"):
        base_keys.update(kind + "_subscription_" + name for name in
                         ("attempted", "return_code", "handle_present", "ok"))
        base_keys.add(kind + "_unsubscribe_ok")
    history_keys = {"history_requested", "history_time_window_valid"}
    history_keys.update("history_" + kind + "_" + name for kind in ("capability", "classify")
                        for name in ("status", "api_stage", "api_code", "returned_count", "matched_count", "attribution"))
    if set(receipt) != base_keys | history_keys:
        return False
    requested = receipt.get("history_requested")
    window = receipt.get("history_time_window_valid")
    if type(requested) is not bool or (window is not None and type(window) is not bool):
        return False
    for kind in ("capability", "classify"):
        p = "history_" + kind + "_"
        status, stage, code = (receipt.get(p + name) for name in ("status", "api_stage", "api_code"))
        returned, matched = (receipt.get(p + name) for name in ("returned_count", "matched_count"))
        attr = receipt.get(p + "attribution")
        if status not in ("not_attempted", "complete", "limit_reached", "api_error", "invalid_data",
                          "invalid_window", "collection_disabled", "unavailable"):
            return False
        if stage not in ("none", "create", "enumerate", "destroy"):
            return False
        if type(returned) is not int or not 0 <= returned <= 64 or type(matched) is not int or not 0 <= matched <= returned:
            return False
        if status == "api_error":
            if stage == "none" or type(code) is not int or not 1 <= code <= 0xFFFFFFFF:
                return False
            if stage in ("create", "enumerate") and (returned or matched):
                return False
        elif stage != "none" or code is not None:
            return False
        if status == "complete" and (not requested or window is not True or returned == 64):
            return False
        if status == "limit_reached" and (not requested or window is not True or returned != 64):
            return False
        if status == "invalid_window" and window is not False:
            return False
        if not requested and (status != "not_attempted" or returned != 0 or matched != 0 or window is not None):
            return False
        if requested and status == "not_attempted":
            return False
        if status in ("not_attempted", "invalid_window", "collection_disabled") and (returned or matched):
            return False
        if type(attr) is not dict or set(attr) != {"status", "filter_id", "layer_id", "is_loopback", "network_capability_id"}:
            return False
        expected = "not_attempted" if not requested else "unavailable"
        if status == "complete":
            expected = "no_match" if matched == 0 else attr["status"]
            if matched and expected not in ("consistent", "mixed"):
                return False
        if attr["status"] != expected:
            return False
        if expected != "consistent":
            if any(attr[k] is not None for k in ("filter_id", "layer_id", "is_loopback", "network_capability_id")):
                return False
        else:
            filter_id = attr["filter_id"]
            if type(filter_id) is not str or not re.fullmatch(r"(?:0|[1-9][0-9]{0,19})", filter_id) or int(filter_id) > 0xFFFFFFFFFFFFFFFF:
                return False
            if attr["is_loopback"] is not True:
                return False
            if kind == "capability":
                if attr["layer_id"] is not None or type(attr["network_capability_id"]) is not int or attr["network_capability_id"] not in (0, 1, 2):
                    return False
            elif attr["network_capability_id"] is not None or type(attr["layer_id"]) is not int or not 0 <= attr["layer_id"] <= 65535:
                return False
    return True

def _wfp_history_projection(receipt: object, scope: str) -> tuple[str, ...]:
    if scope not in ("subscription_probe", "reviewer_payload") or not _wfp_history_receipt_valid(receipt):
        return ("wfp_history receipt_invalid",)
    def scalar(value):
        if value is None:
            return "null"
        if type(value) is bool:
            return "true" if value else "false"
        return str(value)
    lines = []
    for kind in ("capability", "classify"):
        prefix = "history_" + kind + "_"
        fields = [("scope", scope), ("kind", kind), ("requested", receipt["history_requested"]),
                  ("window", receipt["history_time_window_valid"])]
        fields.extend((name, receipt[prefix + name]) for name in
                      ("status", "api_stage", "api_code", "returned_count", "matched_count"))
        fields.extend(("attribution_" + name if name == "status" else name, receipt[prefix + "attribution"][name])
                      for name in ("status", "filter_id", "layer_id", "is_loopback", "network_capability_id"))
        line = "wfp_history " + " ".join(key + "=" + scalar(value) for key, value in fields)
        if len(line.encode("ascii")) > 1024:
            return ("wfp_history projection_failed",)
        lines.append(line)
    return tuple(lines)

def _wfp_history_no_duplicates(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate_key")
        result[key] = value
    return result

def _wfp_history_cli(path: Path, scope: str) -> int:
    try:
        if scope not in ("subscription_probe", "reviewer_payload"):
            raise ValueError("scope")
        with path.open("rb") as source:
            raw = source.read(4097)
        if len(raw) > 4096:
            raise ValueError("oversize")
        receipt = json.loads(raw.decode("ascii"), object_pairs_hook=_wfp_history_no_duplicates)
        lines = _wfp_history_projection(receipt, scope)
        if lines == ("wfp_history receipt_invalid",) or lines == ("wfp_history projection_failed",):
            for line in lines:
                print(line)
            return 1
        for line in lines:
            print(line)
        return 0
    except (OSError, ValueError, UnicodeError, TypeError, RecursionError):
        print("wfp_history receipt_invalid")
        return 1
```

### S2b现有函数精确补丁

```diff
*** Begin Patch
*** Update File: scripts/run_windows_appcontainer_read_probe.py
@@
-        or receipt.get("schema_version") not in (6, 7, 8)
+        or receipt.get("schema_version") not in (6, 7, 8, 9)
@@
     schema_version = receipt["schema_version"]
-    if schema_version == 8:
+    if schema_version == 9 and (not _wfp_history_receipt_valid(receipt) or
+            (receipt["history_requested"] and any(receipt["history_" + kind + "_status"] != "complete"
+                 for kind in ("capability", "classify")))):
+        return "evidence_unavailable"
+    if schema_version in (8, 9):
@@
-    if schema_version == 8:
+    if schema_version in (8, 9):
@@
         "network_capability_id_consistent": (
             capability_id_consistent
             if type(capability_id_consistent) is bool
             else None
         ),
+        **({"history_requested": receipt_dict["history_requested"],
+            "history_time_window_valid": receipt_dict["history_time_window_valid"],
+            **{"history_" + kind + "_" + name: receipt_dict["history_" + kind + "_" + name]
+               for kind in ("capability", "classify")
+               for name in ("status", "api_stage", "api_code", "returned_count", "matched_count")}}
+           if _wfp_history_receipt_valid(receipt_dict) else {}),
     }
@@
 def main() -> int:
+    if len(sys.argv) == 4 and sys.argv[1] == "--history-receipt":
+        return _wfp_history_cli(Path(sys.argv[2]), sys.argv[3])
     if len(sys.argv) != 3:
*** End Patch
```

## Task 3：两个PS消费者和SDK ABI成对接线

**状态**
- [ ] 任务完成

**Dependencies:** Task 2
**Parallelizable:** No（消费已冻结schema9和固定CLI，保留真实helper非零）

- [ ] 独立SOURCE作者应用S3；两个日志投影均在原目录清理之前。CLI仅读现回执并输出白名单，不运行原探针 `_run`。
- [ ] 不同TEST作者应用已冻结S4，完整同步ctypes、mapping、SDK输出、EXPECTED字典；SOURCE作者只消费、不改TEST；32位仍沿原不支持门，不把Linuxctypes代原生。
- [ ] T0与旧ABI/WFP/workflow/旧wire定向GREEN；按现CI windows reviewer两个job执行SDK对照/native self-test。
- [ ] 独立双审再核没有追加超时、权限、filter查询或DENY credit。

### S3 CI SOURCE精确补丁

```diff
*** Begin Patch
*** Update File: .github/workflows/ci.yml
@@
                 $observerReceipt = [IO.File]::ReadAllText($observerResultPath) |
                   ConvertFrom-Json -ErrorAction Stop
+                & python scripts/run_windows_appcontainer_read_probe.py --history-receipt $observerResultPath subscription_probe
+                $historyProjectionValid = $LASTEXITCODE -eq 0
@@
-                if ($schemaVersion -eq 8 -and $ipVersion -eq 6 -and
+                if ($schemaVersion -eq 9 -and $ipVersion -eq 6 -and $historyProjectionValid -and
@@
-                } elseif ($runnerWfpObserverProcessState -ne 'exit_zero') {
-                  $runnerWfpReceiptState = 'helper_nonzero'
-                  $runnerWfpCandidateEvent = 'receipt_unavailable'
@@
                 } else {
                   $observerReceiptText = $null
                   try {
                     $observerReceiptText = [IO.File]::ReadAllText($runnerWfpObserverResultPath)
+                    & python scripts/run_windows_appcontainer_read_probe.py --history-receipt $runnerWfpObserverResultPath reviewer_payload
+                    $runnerHistoryProjectionValid = $LASTEXITCODE -eq 0
@@
                       $observerHistoryFieldsValid = (
-                        $null -eq $observerHistoryWindowValid -or
-                        $observerHistoryWindowValid -is [bool]
+                        $runnerHistoryProjectionValid -and $observerReceipt.history_requested -eq $true -and
+                        ($null -eq $observerHistoryWindowValid -or $observerHistoryWindowValid -is [bool])
@@
-                        $observerSchema -eq 8 -and $observerIpVersion -eq 6 -and
+                        $observerSchema -eq 9 -and $observerIpVersion -eq 6 -and
@@
                       if ($observerSubscriptionValid -and $observerTargetValid -and
                           $observerMatchesValid -and $observerHistoryFieldsValid -and
+                          $runnerWfpObserverProcessState -eq 'exit_zero' -and
                           ($null -eq $observerNetworkEventsCollected -or
*** End Patch
```

S3各实际hunk独立应用。非零helper现在仍解析、打印历史错误，但最终receipt成功门仍要求exit_zero；已有helper exit notice保留，不伪装CLI exit0为helper exit0。订阅正控投影在原JSON parse成功后执行；若重复键，CLI返回1且原许可通过门被historyProjectionValid关闭，打印固定receipt_invalid。

### S4 ABI三文件精确补丁

S4a在 `_classify_windows_sdk_compile_failure` 前插入完整SDK同代ctypes结构：

```python
class _FwpmNetEventClassifyDrop2(ctypes.Structure):
    _fields_ = [
        ("filter_id", ctypes.c_uint64), ("layer_id", ctypes.c_uint16),
        ("reauth_reason", ctypes.c_uint32), ("original_profile", ctypes.c_uint32),
        ("current_profile", ctypes.c_uint32), ("direction", ctypes.c_uint32),
        ("is_loopback", ctypes.c_int32), ("vswitch_id", _FwpByteBlob),
        ("vswitch_source_port", ctypes.c_uint32), ("vswitch_destination_port", ctypes.c_uint32),
    ]
```

```diff
*** Begin Patch
*** Update File: tests/windows_wfp_abi_probe.py
@@
         "capability_drop.is_loopback": _FwpmNetEventCapabilityDrop0.is_loopback.offset,
+        "classify_drop.size": ctypes.sizeof(_FwpmNetEventClassifyDrop2),
+        "classify_drop.filter_id": _FwpmNetEventClassifyDrop2.filter_id.offset,
+        "classify_drop.layer_id": _FwpmNetEventClassifyDrop2.layer_id.offset,
+        "classify_drop.is_loopback": _FwpmNetEventClassifyDrop2.is_loopback.offset,
*** Update File: tests/fixtures/native/wfp_sdk_layout_probe.c
@@
     REPORT_OFFSET("capability_drop.is_loopback", FWPM_NET_EVENT_CAPABILITY_DROP0,
                   isLoopback);
+    REPORT_SIZE("classify_drop.size", FWPM_NET_EVENT_CLASSIFY_DROP2);
+    REPORT_OFFSET("classify_drop.filter_id", FWPM_NET_EVENT_CLASSIFY_DROP2, filterId);
+    REPORT_OFFSET("classify_drop.layer_id", FWPM_NET_EVENT_CLASSIFY_DROP2, layerId);
+    REPORT_OFFSET("classify_drop.is_loopback", FWPM_NET_EVENT_CLASSIFY_DROP2, isLoopback);
*** Update File: tests/test_windows_wfp_abi.py
@@
     "capability_drop.is_loopback": 16,
+    "classify_drop.size": 56,
+    "classify_drop.filter_id": 0,
+    "classify_drop.layer_id": 8,
+    "classify_drop.is_loopback": 28,
*** End Patch
```

56/0/8/28是完整64位Windows结构预期，native fixture实际SDK值须在x64/ARM64逐项验证，预期常数不是原生证明。既有两个SDK/ctypes比较断言引用同一EXPECTED字典，无需删除或宽松化断言。

## Task 4：候选前自检、独立双审与线上阶段验收

**状态**
- [ ] 任务完成

**Dependencies:** Task 3
**Parallelizable:** No（须全部资产GREEN/独立双审后绑定候选）

- [ ] 本机只定向运行 `python3 -m unittest tests.test_windows_reviewer_history tests.test_windows_wfp_capture tests.test_windows_wfp_abi tests.test_ci_workflow_contracts tests.test_windows_appcontainer_read_probe -v`，不调用整套全量、不运行native。保存run/skip明细，Linux SDK条件skip不叫原生通过。
- [ ] 不同SPEC和不同QUALITY独立核实际SOURCE/TEST与本PLAN；真实网络门、loopback/历史状态/原API错误/临时回执清理的日志投影和ABI四键全核。闭环前不靠假定GREEN。
- [ ] root执行现密钥/固定vendor pin必要检查并核精确修改列表，不打印密钥、不变vendor版本；检查失败先定位，不绕过。按用户候选授权仅main提交推送，无新branch/tag；此步由root执行，本文作者不执行。

未来root必要检查的确切命令（本PLAN不执行）：

```bash
python3 scripts/preflight.py --only secrets
python3 scripts/preflight.py --only submodule
git diff --check -- native/windows/icode_wfp_event_probe.c scripts/run_windows_appcontainer_read_probe.py .github/workflows/ci.yml tests/test_windows_reviewer_history.py tests/test_ci_workflow_contracts.py tests/test_windows_wfp_capture.py tests/windows_wfp_abi_probe.py tests/fixtures/native/wfp_sdk_layout_probe.c tests/test_windows_wfp_abi.py
```

预期：两道preflight独立PASS/exit0；whitespace exit0；任何原输出fail、missing pin或未确认dirty重叠先停止精确候选冻结，不执行全量guard。root核已批准SOURCE/TEST投影与worktree字节完全一致后，仅这些九个实现路径及本DESIGN/PLAN文档作为候选内容；不 `git add .`、不自动清理其他dirty、main提交推送不叫产品验收完成。
- [ ] 记录实际候选SHA、现Reviewer x64/ARM64 workflow/job/platform、完整原日志与exit；核helper编译/SDK四键/self-test及实际argv历史requested=true、两类query状态/阶段/code/计数、脱敏归因字符串与helper exit。其它workflow全量结果由线上原任务取得，不重复本机。
- [ ] history complete/no_match为观测范围结果；limit/api/error/collectiondisabled/unknown保留失败。private exit105或candidate10035/timeout/deniedfalse仍不授网络DENY、Reviewer/R2/R3/自动模式通过；本片不能承诺修复正控。
- [ ] 阶段需要的原生字段/原日志未出现即未完成；不得用SOURCE合同/collector成功代网络结果，也不得取消/retry掩盖失败。

## 作者自审与交接

本片冻结T0、S1/S1a/S1b、S2/S2b、S3及S4完整正文和精确context；所有实施仍待fresh独立PLAN SPEC→不同QUALITY批准。用户main-only/线上优先约束覆盖技能默认worktree/frequent task commits及本机全量。执行依赖单链0→1→2→3→4，选serial；root安排不同SOURCE作者/TEST作者与双审，本文不启动执行技能。

作者实际静态核验：2026-10-14 在WSL中仅内存读取本文与现八个目标文件，三段完整Python正文全部 `ast.parse` 成功；逐apply_patch hunk旧context能顺序精确匹配，内存组合后的Python SOURCE AST通过，旧matcher及新history helper共六个翻译条件表达式AST通过；未写SOURCE/TEST/CI/临时文件或执行测试/native。第一次Windows `python -` 入口退出1且没有输出，未当成TDD RED；改用WSL `python3 -` 得实际静态检查exit0。正文内新TEST/新SOURCE与标准库行为尚待独立PLAN审查及真实TDD，静态通过不是GREEN。

资产冻结：T0正文取首个python围栏正文加末尾LF的UTF8字节；其余资产在本文围栏出现顺序按 `language + LF + body + LF` 拼接。TEST为T0/T0b/S4a/S4；SOURCE为S1/S1a/S1b/S2/S2b/S3；bash候选检查不是SOURCE资产。无CRLF、无围栏标记、无Markdown说明文字混入摘要。

| 投影 | 实际字节 | SHA256 |
|---|---:|---|
| T0完整新TEST | 14082 | `6ff02880023abd156c95fb6949222ada37efbabc8ebaf9f6cde339eea3e9b28e` |
| TEST资产全集 | 16454 | `b6dd77e4f2cfa9fe21e9fde90fe682f24ac67667c945aebb5c3849d2db7dddfa` |
| SOURCE资产全集 | 23436 | `0f35259eb79563453cfc930c3a8c7646f3ed8306fab8c67c836a85be526eeb4e` |

SPEC覆盖自审：DESIGN真实payload请求与正控scope由T0/S1/S3承接；scope→scalar→loopback由S1a及T0语义oracle承接；schema9/null/APIstage/不完整观察由S1b/S2与T0边界fixture承接；两个PS清理前原日志、精度/隐私由S2投影/S3承接；旧6/7/8由S2b/旧fixture回归承接；ABI三文件由S4承接；有限本机检查/候选绑定/线上native/不授DENY由Task4承接。未发现未定义函数、无修改dummy hunk或占位实现。作者自审不替不同SPEC/QUALITY审查。

2026-10-14 fresh SPEC修订：首版PLAN `6ec204bd…` 为C0/I1/M0；I1是既有ABI模块的native receipt schema8断言遗漏。现已把它的8→9精确补丁纳入T0b、归TEST作者冻结；IPv4 schema6及旧Python wire6/7/8兼容保持。重新只读RAM组合所有patch/code及AST检查，实际3段Python/8旧目标/6翻译条件均静态exit0；TEST全集更新如表，T0完整正文和SOURCE全集字节/hash不变。未实际改TEST/SOURCE/CI或运行测试/native/git，修订仍待fresh双审。

【架构级自检报告】

✅ 语法/编译：本文Markdown/正文作者自审；未实际应用或编译。

✅ 依赖/调用链：实际argv→C history→schema9→两PS/Python→日志→SDK已列资产。

✅ 逻辑/边界：scope/scalar/loopback分离；BOOL2、capenum越界、零匹配/未尝试/满页及UINT64字符串有oracle。

✅ 异常处理：API/stage、stop/cleanup、buffer/投影失败关闭设计落实于资产，实际故障测试待实施。

✅ 关联模块：C/CLI/两个PS/ABI三文件/旧合同同步；无其它实际变更。

✅ 兼容安全：旧6/7/8保留，callback与history分账，无新增权限/豁免/查询/timeout。

✅ 可运行性：PLAN-only，测试/原生/线上未执行，不预报100%或R2/R3通过。

---
**Execution Mode:** serial

## 实施记录（2026-10-14，尚待线上原生验收）

冻结实施 PLAN 原摘要 `d9e2b8f2f4619796bf343d163446ef4c4031a6ac78ab28fa27ce956a9c3b7d33`、SOURCE/TEST 围栏资产保持原样。root 实际读全943行及三步 sequential-thinking `08617a`；独立 TEST 作者、不同 SOURCE 作者和独立 SPEC→不同 QUALITY 的分工实际执行。

TEST 六路径逐字重建一致，ROOT426459新8方法/.048s/8AssertionFail/0ERRORskip/exit1，独立 TEST 审查也实际8/.054s/8ASSERT/0Eskip/exit1，四种关键失败来自真实旧行为，不是 import/缺helper/编译错误。此前/tmp两日志现已不存在（e4af7c），原因未知，直接工具输出仍保留真实 RED；不能冒称当前原日志文件可重核。后续日志保存于/home/orbbec。

SOURCE 三路径逐字匹配冻结资产，作者新8方法/.078s/零失败错误跳过；五模块95/.269s/0F/E/1Linux SDK skip。root3b3c34另实际95/.427s/0F/E/同一SDK skip，日志 `/home/orbbec/icode-windows-history-root-green.ycpdsauo/targeted.log` SHA`68ae4a0a1f6582fa46b7d0c71f420c4c8f47d597ad33843047ef3722f1833cd8`。实际 SOURCE fresh SPEC→不同 QUALITY均C0/I0/M0，分别独立新8 GREEN；九实现路径从HEAD+冻结资产在RAM重建全部精确一致，AST/diffcheck通过。

候选三 SOURCE SHA：C `6d878e45a5b8f8938ab9a72040df2d1ec698d0e3e2953cc61d56a754d3b09dc5`；Python `d4f1e7c59af8d1d077d5fa2ec8dec46914f1e39b9e87ce82dba7952d88549b31`；CI `cdb3488ef905e77e4aed7ad3a49f526f5ae2fe863e88b1abeb72aa84751d071d`。Mac TESTOnly新文件独立不入本候选，未混入其CI。root原单门secret/submodule各通过，文档scanner的5疑似链接由da5df5逐一核为本T0 Python围栏中dict lookup后的函数调用，不是Markdown链接；没有改scanner或资产规避检查。

当前只授便携软件和候选审查证据。Windows SDK编译/ABI/self-test、实际历史requested/status/stage/code及两scope脱敏日志仍待新SHA线上验证；旧网络正控105、候选10035/timeout、DENY与Reviewer/R2/R3门没有因此关闭。
