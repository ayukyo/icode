"""CI positive-loopback software policy only: no OS authorization or restoration.

Inputs are caller assertions, not authenticated OS evidence. No result from this
module permits mutation. The future admin adapter must authenticate context,
persist intents, observe actual operations and independently verify restoration.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, replace
import hashlib
import json
import re
import struct

MAX_ENTRIES = 4096
MAX_REQUEST_BYTES = 4096
MAX_RECEIPT_BYTES = 500
WINDOW_MS = 60000
UINT32_MAX = (1 << 32) - 1
_ERRORS = frozenset({"add_failed", "deadline", "add_delta", "probe_failed",
                     "foreign_delta", "owner_conflict", "unreaped",
                     "cleanup_failed", "observation_failed"})
_PHASES = frozenset({"baseline", "created", "add_intent", "added", "probe",
                     "cleanup", "restored", "unknown"})


class PolicyError(ValueError):
    """Invalid software policy input; never a Windows DENY observation."""


def _require(condition: bool, code: str) -> None:
    if not condition:
        raise PolicyError(code)


def _uint(value: object, maximum: int = UINT32_MAX, minimum: int = 0) -> bool:
    return type(value) is int and minimum <= value <= maximum


def sid_bytes(text: str) -> bytes:
    """Validate canonical decimal SID text and return Windows binary SID bytes."""
    _require(type(text) is str and len(text) <= 184, "invalid_sid")
    parts = text.split("-")
    _require(len(parts) >= 4 and parts[:2] == ["S", "1"]
             and len(parts) <= 18, "invalid_sid")
    _require(all(re.fullmatch(r"0|[1-9][0-9]*", part) for part in parts[2:]),
             "invalid_sid")
    values = [int(part) for part in parts[2:]]
    _require(values[0] < (1 << 48)
             and all(value <= UINT32_MAX for value in values[1:]), "invalid_sid")
    return bytes((1, len(values) - 1)) + values[0].to_bytes(6, "big") + b"".join(
        struct.pack("<I", value) for value in values[1:])


@dataclass(frozen=True)
class AdmissionFacts:
    """Caller assertions only, not proof of GitHub identity or administrator rights."""
    github_actions: bool
    windows: bool
    github_hosted: bool
    explicitly_authorized: bool
    dedicated_runner: bool

    def __post_init__(self):
        _require(all(type(value) is bool and value for value in (
            self.github_actions, self.windows, self.github_hosted,
            self.explicitly_authorized, self.dedicated_runner)), "admission")


@dataclass(frozen=True)
class Manifest:
    admission: AdmissionFacts
    repository: str
    source_sha: str
    run_id: str
    run_attempt: int
    job: str
    matrix: str
    account_sid: str
    pid: int
    process_created: int
    positive_profile: str
    reviewer_profile: str
    positive_sid: str
    reviewer_sid: str
    nonce: str
    ipv4_port: int
    ipv6_port: int
    started_ms: int
    deadline_ms: int

    def __post_init__(self):
        _require(type(self.admission) is AdmissionFacts, "admission_type")
        _require(self.repository == "ayukyo/icode"
                 and type(self.repository) is str, "repository")
        for value, pattern in ((self.source_sha, r"[0-9a-f]{40}"),
                               (self.run_id, r"[1-9][0-9]{0,19}"),
                               (self.nonce, r"[0-9a-f]{32}"),
                               (self.positive_profile, r"icode-[0-9a-f]{32}"),
                               (self.reviewer_profile, r"icode-[0-9a-f]{32}")):
            _require(type(value) is str and re.fullmatch(pattern, value) is not None,
                     "manifest_text")
        _require(type(self.job) is str and self.job == "windows-reviewer-snapshot-probe"
                 and type(self.matrix) is str and self.matrix in ("x64", "ARM64"),
                 "job_identity")
        for value in (self.account_sid, self.positive_sid, self.reviewer_sid):
            sid_bytes(value)
        _require(self.account_sid.startswith("S-1-5-21-")
                 and self.positive_sid.startswith("S-1-15-2-")
                 and self.reviewer_sid.startswith("S-1-15-2-")
                 and self.positive_sid != self.reviewer_sid
                 and self.positive_profile != self.reviewer_profile, "profile_identity")
        _require(_uint(self.run_attempt, minimum=1) and _uint(self.pid, minimum=1)
                 and _uint(self.process_created, (1 << 64) - 1, 1), "process_identity")
        _require(_uint(self.ipv4_port, 65535, 1)
                 and _uint(self.ipv6_port, 65535, 1), "endpoint")
        _require(_uint(self.started_ms, (1 << 63) - 1)
                 and _uint(self.deadline_ms, (1 << 63) - 1)
                 and 0 < self.deadline_ms - self.started_ms <= WINDOW_MS, "window")

    @property
    def digest(self) -> str:
        return hashlib.sha256(_json(asdict(self))).hexdigest()


def _json(value: object) -> bytes:
    return json.dumps(value, ensure_ascii=True, sort_keys=True,
                      separators=(",", ":"), allow_nan=False).encode("ascii")


def _clock(manifest: Manifest, now_ms: int) -> bool:
    _require(type(manifest) is Manifest, "manifest_type")
    _require(_uint(now_ms, (1 << 63) - 1) and now_ms >= manifest.started_ms, "clock")
    return now_ms < manifest.deadline_ms


def _live(manifest: Manifest, now_ms: int) -> None:
    _require(_clock(manifest, now_ms), "deadline")


def _request(manifest: Manifest, kind: str) -> dict:
    _require(type(manifest) is Manifest, "manifest_type")
    _require(type(kind) is str and kind in ("profile_created", "probe_finished"), "kind")
    return dict(version=1, kind=kind, binding=manifest.digest,
                positive_profile=manifest.positive_profile,
                positive_sid=manifest.positive_sid, reviewer_sid=manifest.reviewer_sid,
                nonce=manifest.nonce, ipv4_port=manifest.ipv4_port,
                ipv6_port=manifest.ipv6_port, pid=manifest.pid,
                process_created=manifest.process_created)


def encode_request(manifest: Manifest, kind: str) -> bytes:
    wire = _json(_request(manifest, kind))
    _require(len(wire) <= MAX_REQUEST_BYTES, "request_size")
    return wire


def _unique(pairs):
    value = {}
    for key, item in pairs:
        _require(key not in value, "duplicate_key")
        value[key] = item
    return value


def validate_request(wire: bytes, manifest: Manifest, kind: str, now_ms: int) -> str:
    """Correlation only: this does not authenticate the sender or filesystem."""
    _live(manifest, now_ms)
    _require(type(wire) is bytes and 0 < len(wire) <= MAX_REQUEST_BYTES, "request_size")
    expected = _request(manifest, kind)
    try:
        body = json.loads(wire.decode("utf-8"), object_pairs_hook=_unique,
                          parse_constant=lambda _: (_ for _ in ()).throw(
                              PolicyError("json_constant")))
    except (UnicodeError, ValueError, RecursionError) as exc:
        raise PolicyError("request_json") from exc
    _require(type(body) is dict and set(body) == set(expected), "request_fields")
    _require(all(type(body[key]) is type(value) and body[key] == value
                 for key, value in expected.items()), "request_binding")
    return kind


@dataclass(frozen=True)
class Snapshot:
    entries: tuple[tuple[str, int], ...]
    api_code: int
    complete: bool
    released: bool
    reaped: bool

    def __post_init__(self):
        _require(type(self.entries) is tuple and len(self.entries) <= MAX_ENTRIES,
                 "snapshot_entries")
        _require(type(self.api_code) is int and self.api_code == 0
                 and all(type(flag) is bool and flag
                         for flag in (self.complete, self.released, self.reaped)),
                 "snapshot_unverified")
        binary = set()
        for entry in self.entries:
            _require(type(entry) is tuple and len(entry) == 2, "snapshot_entry")
            sid, attributes = entry
            value = sid_bytes(sid)
            _require(value not in binary and _uint(attributes), "snapshot_identity")
            binary.add(value)
        object.__setattr__(self, "entries", tuple(sorted(
            self.entries, key=lambda entry: sid_bytes(entry[0]))))

    @property
    def digest(self) -> str:
        return hashlib.sha256(_json(self.entries)).hexdigest()


@dataclass(frozen=True)
class CommandResult:
    exit_code: int | None
    timed_out: bool
    reaped: bool

    def __post_init__(self):
        _require((self.exit_code is None or _uint(self.exit_code))
                 and type(self.timed_out) is bool and type(self.reaped) is bool
                 and (self.exit_code is not None or self.timed_out), "command_result")

    @property
    def ok(self) -> bool:
        return self.exit_code == 0 and not self.timed_out and self.reaped


@dataclass(frozen=True)
class State:
    manifest: Manifest
    baseline: Snapshot
    phase: str
    target_attributes: int | None = None
    both_nonce_received: bool = False
    first_error: str | None = None
    modeled_restoration: bool = False
    owned_intent: bool = False

    def __post_init__(self):
        _require(type(self.manifest) is Manifest and type(self.baseline) is Snapshot
                 and type(self.phase) is str and self.phase in _PHASES, "state")
        _require(self.target_attributes is None or _uint(self.target_attributes), "state_attr")
        _require(type(self.both_nonce_received) is bool
                 and type(self.modeled_restoration) is bool
                 and (self.first_error is None or (type(self.first_error) is str
                      and self.first_error in _ERRORS))
                 and type(self.owned_intent) is bool, "state_flags")
        _require(self.manifest.positive_sid not in dict(self.baseline.entries)
                 and self.manifest.reviewer_sid not in dict(self.baseline.entries), "state_baseline")
        _require((self.phase not in ("baseline", "created") or not self.owned_intent)
                 and (self.phase not in ("add_intent", "added", "probe", "cleanup", "restored")
                      or self.owned_intent)
                 and (not self.modeled_restoration or self.phase == "restored"), "state_ownership")


def _state(state: State, phases: tuple[str, ...]) -> None:
    _require(type(state) is State and state.phase in phases, "phase")


def _map(snapshot: Snapshot) -> dict:
    _require(type(snapshot) is Snapshot, "snapshot_type")
    return dict(snapshot.entries)


def begin(manifest: Manifest, first: Snapshot, second: Snapshot, now_ms: int) -> State:
    _live(manifest, now_ms)
    before, after = _map(first), _map(second)
    _require(before == after and manifest.positive_sid not in before
             and manifest.reviewer_sid not in before, "baseline")
    return State(manifest, first, "baseline")


def profile_created(state: State, profile: str, sid: str,
                    hresult: int, now_ms: int) -> State:
    _state(state, ("baseline",))
    _live(state.manifest, now_ms)
    _require(type(profile) is str and profile == state.manifest.positive_profile
             and type(sid) is str and sid == state.manifest.positive_sid
             and type(hresult) is int and hresult == 0, "creation")
    return replace(state, phase="created")


def add_intent(state: State, now_ms: int) -> State:
    """In-memory intent only; future adapter must durably persist before add."""
    _state(state, ("created",))
    _live(state.manifest, now_ms)
    return replace(state, phase="add_intent", owned_intent=True)


def fail(state: State, error: str) -> State:
    _require(type(state) is State and type(error) is str and error in _ERRORS, "error")
    return replace(state, phase="unknown", first_error=state.first_error or error,
                   modeled_restoration=False)


def add_observed(state: State, snapshot: Snapshot,
                 command: CommandResult, now_ms: int) -> State:
    _state(state, ("add_intent",))
    _require(type(command) is CommandResult, "command_type")
    current = _map(snapshot)
    sid = state.manifest.positive_sid
    target = current.pop(sid, None)
    result = replace(state, target_attributes=target)
    if not _clock(state.manifest, now_ms):
        return fail(result, "deadline")
    if not command.ok:
        return fail(result, "add_failed")
    if target is None or current != _map(state.baseline):
        return fail(result, "add_delta")
    return replace(result, phase="added")


def probe_payload(manifest: Manifest) -> bytes:
    _require(type(manifest) is Manifest, "manifest_type")
    return _json(dict(nonce=manifest.nonce, appcontainer=True,
                      package_sid=manifest.positive_sid, capability_count=1,
                      capability_sid="S-1-15-3-3"))


def probe_observed(state: State, ipv4: tuple[bytes, ...], ipv6: tuple[bytes, ...],
                   token_verified: bool, job_reaped: bool, exit_code: int,
                   now_ms: int) -> State:
    _state(state, ("added",))
    _require(type(ipv4) is tuple and type(ipv6) is tuple
             and all(type(value) is bytes for value in (*ipv4, *ipv6))
             and type(token_verified) is bool and type(job_reaped) is bool
             and _uint(exit_code), "probe_type")
    if not _clock(state.manifest, now_ms):
        return fail(state, "deadline")
    expected = (probe_payload(state.manifest),)
    if not (ipv4 == ipv6 == expected and token_verified and job_reaped and exit_code == 0):
        return fail(state, "probe_failed")
    return replace(state, phase="probe", both_nonce_received=True)


@dataclass(frozen=True)
class CleanupPlan:
    state: State
    before: Snapshot
    action: str

    def __post_init__(self):
        _require(type(self.state) is State and self.state.phase == "cleanup"
                 and type(self.before) is Snapshot
                 and type(self.action) is str
                 and self.action in ("delete", "absent", "refuse"), "cleanup_plan")


def cleanup_plan(state: State, current: Snapshot, last_command_reaped: bool,
                 now_ms: int) -> CleanupPlan:
    """Model a narrow cleanup decision, never an executable deletion grant."""
    _state(state, ("add_intent", "added", "probe", "unknown"))
    _require(state.owned_intent, "no_owned_intent")
    _require(type(last_command_reaped) is bool, "reaped_type")
    if not _clock(state.manifest, now_ms):
        state = fail(state, "deadline")
    observed = _map(current)
    target = observed.pop(state.manifest.positive_sid, None)
    if observed != _map(state.baseline):
        state = fail(state, "foreign_delta")
    if not last_command_reaped:
        state, action = fail(state, "unreaped"), "refuse"
    elif target is None:
        action = "absent"
    elif state.target_attributes is not None and target != state.target_attributes:
        state, action = fail(state, "owner_conflict"), "refuse"
    else:
        action = "delete"
    return CleanupPlan(replace(state, phase="cleanup"), current, action)


def cleanup_complete(plan: CleanupPlan, post: Snapshot,
                     command: CommandResult | None, now_ms: int) -> State:
    _require(type(plan) is CleanupPlan, "cleanup_type")
    state = plan.state
    if not _clock(state.manifest, now_ms):
        state = fail(state, "deadline")
    expected = _map(plan.before)
    expected.pop(state.manifest.positive_sid, None)
    actual = _map(post)
    command_ok = ((plan.action == "absent" and command is None)
                  or (plan.action == "delete" and type(command) is CommandResult
                      and command.ok))
    if plan.action == "refuse" or not command_ok or actual != expected:
        return fail(state, "cleanup_failed")
    return replace(state, phase="restored", modeled_restoration=True)


def encode_receipt(state: State, now_ms: int) -> bytes:
    """Export only model outcomes. Native authority is false; restoration null."""
    _require(type(state) is State, "state_type")
    live = _clock(state.manifest, now_ms)
    passed = (live and state.phase == "restored" and state.modeled_restoration
              and state.both_nonce_received and state.first_error is None)
    wire = _json(dict(schema_version=1, scope="positive_loopback_software_policy",
                      binding=state.manifest.digest, status="modeled" if passed else "unknown",
                      modeled_restoration=state.modeled_restoration,
                      native_authorized=False, native_restoration_verified=None,
                      first_error=state.first_error or (None if live else "deadline")))
    _require(len(wire) <= MAX_RECEIPT_BYTES, "receipt_size")
    return wire
