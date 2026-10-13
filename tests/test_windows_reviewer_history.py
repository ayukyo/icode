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
