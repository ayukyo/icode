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
from scripts.windows_positive_loopback_admin_store import Store, PRIVATE, KERNEL_PRIVATE, wire, decode, copy_private_tree
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
        store.w.verify_security(store.root_handle, root_sddl, category="root_security_changed")
        for item in store.data["frozen_directories"]:
            relative = Path(item["path"])
            require(not relative.is_absolute() and not any(part == ".." for part in relative.parts), "frozen_directory_path")
            handle = store.w.pin_ancestor(store.root / relative)
            try:
                require(list(store.w.info(handle, directory=True)) == item["identity"], "frozen_directory_identity")
                # Root alone has explicit traverse; every loaded child is private.
                store.w.verify_security(handle, root_sddl if relative == Path(".") else PRIVATE,
                                        category="directory_security_changed")
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
        # Windows system executables routinely self-report VFT_DLL in their
        # version resource (CheckNetIsolation.exe does), so the resource must
        # report a known application or library type, not the caller's guess.
        require(words[0] == 0xFEEF04BD and words[1] == 0x10000 and words[9] in (1, 2),
                "image_version_resource")
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
            for family, host, category in ((socket.AF_INET, "127.0.0.1", "loopback_socket4"),
                                           (socket.AF_INET6, "::1", "loopback_socket6")):
                # Provider initialization on hosted runners fails transiently
                # (WSAEPROVIDERFAILEDINIT); observed failures clear on the next
                # spawn, so retry is bounded and the last error stays chained.
                last = None
                for attempt in range(3):
                    try:
                        listener = socket.socket(family, socket.SOCK_STREAM)
                        last = None
                        break
                    except OSError as error:
                        last = error
                        time.sleep(0.2 * (attempt + 1))
                if last is not None:
                    raise Failure(category) from last
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
            store.w.verify_security(job, KERNEL_PRIVATE, object_type=6, category="outer_job_security_changed")
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
            store.w.verify_security(job, KERNEL_PRIVATE, object_type=6, category="stop_job_security_changed")
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
                store.w.verify_security(job, KERNEL_PRIVATE, object_type=6, category="reap_job_security_changed")
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
