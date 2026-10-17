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


STAGE = re.compile(r"[a-z][a-z0-9_]{0,31}")


def _parent_stage(error):
    """Bounded native attach stage; never a path, SID, secret or message body."""
    text = str(error)
    if type(error) is not str and STAGE.fullmatch(text):
        return "parent_failed_" + text
    return "parent_failed"


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
        except Exception as error:
            self._failure("parent_failed")
            # Native stages stay bounded; the ledger code above stays exact.
            bounded = AdminError(_parent_stage(error))
            # A bounded first-differing offset (never a path, SID or message)
            # rides along on the same receipt field the entry already prints.
            winerror = getattr(error, "winerror", None)
            if type(winerror) is int and 0 < winerror < 65536:
                bounded.winerror = winerror
            raise bounded from None
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
