"""In-memory Linux diagnostic format; never an execution admission grant."""

from dataclasses import asdict, dataclass
import json
from datetime import datetime, timezone
import hashlib
import platform
import re
import sys

from . import isolation, native_helper, sandbox_policy

MAX_DIAGNOSTIC_BYTES = 16 * 1024


@dataclass(frozen=True, slots=True)
class LinuxDiagnosticObservations:
    minimal_probe: bool | None
    protected_path_probe: bool | None


@dataclass(frozen=True, slots=True)
class LinuxAdmissionDiagnostic:
    scope: str
    schema_version: int
    platform: str
    os_build: str | None
    architecture: str | None
    helper_sha256: str | None
    policy_schema_version: int
    checked_at: str
    status: str
    reason: str
    observations: LinuxDiagnosticObservations
    observation_coverage: str
    cleanup_status: str


def _invalid():
    raise ValueError("invalid_linux_admission_diagnostic") from None


def _positive_int(value):
    return type(value) is int and value > 0


def _os_build_valid(value):
    return type(value) is str and 1 <= len(value) <= 256 and all(32 <= ord(c) <= 126 for c in value)


def _validate_report(report):
    if type(report) is not LinuxAdmissionDiagnostic or type(report.observations) is not LinuxDiagnosticObservations:
        _invalid()
    fixed = {"scope": "linux_admission_diagnostic", "platform": "linux", "status": "incomplete",
             "observation_coverage": "legacy_probe_summary_only", "cleanup_status": "unknown"}
    if any(type(getattr(report, k)) is not str or getattr(report, k) != v for k, v in fixed.items()):
        _invalid()
    if type(report.schema_version) is not int or report.schema_version != 1 or not _positive_int(report.policy_schema_version):
        _invalid()
    if report.os_build is not None and not _os_build_valid(report.os_build):
        _invalid()
    if report.architecture is not None and (type(report.architecture) is not str or report.architecture not in ("x86_64", "arm64")):
        _invalid()
    if report.helper_sha256 is not None and (type(report.helper_sha256) is not str or re.fullmatch("[0-9a-f]{64}", report.helper_sha256) is None):
        _invalid()
    if type(report.checked_at) is not str or re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z", report.checked_at) is None:
        _invalid()
    datetime.strptime(report.checked_at, "%Y-%m-%dT%H:%M:%SZ")
    obs = (report.observations.minimal_probe, report.observations.protected_path_probe)
    if any(value is not None and type(value) is not bool for value in obs):
        _invalid()
    complete_host = report.os_build is not None and report.architecture is not None
    reason = report.reason
    if type(reason) is not str:
        _invalid()
    if reason == "unsupported_environment":
        valid = not complete_host and report.helper_sha256 is None and obs == (None, None)
    elif reason in ("helper_unavailable", "helper_changed"):
        valid = complete_host and report.helper_sha256 is None and obs == (None, None)
    elif reason == "invalid_observation":
        valid = complete_host and report.helper_sha256 is not None and None in obs
    elif reason == "observation_incomplete":
        valid = complete_host and report.helper_sha256 is not None and all(type(value) is bool for value in obs)
    else:
        valid = False
    if not valid:
        _invalid()


def _canonical(report):
    return (json.dumps(asdict(report), sort_keys=True, separators=(",", ":"), ensure_ascii=True) + "\n").encode("ascii")


def serialize_linux_admission_diagnostic(report) -> bytes:
    """Serialize only the immutable diagnostic schema, without provenance claims."""
    try:
        _validate_report(report)
        wire = _canonical(report)
        if not 1 <= len(wire) <= MAX_DIAGNOSTIC_BYTES:
            _invalid()
        return wire
    except Exception:
        _invalid()


def validate_linux_admission_diagnostic(wire) -> LinuxAdmissionDiagnostic:
    """Validate format only; this does not authenticate the source or admit work."""
    try:
        if type(wire) is not bytes or not 1 <= len(wire) <= MAX_DIAGNOSTIC_BYTES:
            _invalid()
        def unique(pairs):
            result = {}
            for key, value in pairs:
                if key in result:
                    _invalid()
                result[key] = value
            return result
        value = json.loads(wire.decode("ascii"), object_pairs_hook=unique)
        if type(value) is not dict or set(value) != set(LinuxAdmissionDiagnostic.__dataclass_fields__):
            _invalid()
        obs = value["observations"]
        if type(obs) is not dict or set(obs) != {"minimal_probe", "protected_path_probe"}:
            _invalid()
        value["observations"] = LinuxDiagnosticObservations(**obs)
        report = LinuxAdmissionDiagnostic(**value)
        _validate_report(report)
        if _canonical(report) != wire:
            _invalid()
        return report
    except Exception:
        _invalid()


def _policy_version():
    try:
        value = sandbox_policy.POLICY_SCHEMA_VERSION
        if _positive_int(value):
            return value
    except Exception:
        pass
    raise ValueError("linux_admission_unavailable") from None


def _host_identity():
    try:
        os_build = platform.release() + " " + platform.version()
        if not _os_build_valid(os_build):
            os_build = None
    except Exception:
        os_build = None
    try:
        architecture = {"x86_64": "x86_64", "amd64": "x86_64",
                        "aarch64": "arm64", "arm64": "arm64"}.get(platform.machine().lower())
    except Exception:
        architecture = None
    return os_build, architecture


def _helper_identity():
    """Check local bundle consistency, without authenticating a launch object."""
    try:
        helper = native_helper.bundled_linux_helper()
        if helper is None:
            return None
        manifest = helper.parent / "icode-landlock.sha256"
        if native_helper.verify_native_helper(helper, manifest) is not True:
            return None
        with helper.open("rb") as stream:
            digest = hashlib.file_digest(stream, "sha256").hexdigest()
        expected = manifest.read_text(encoding="ascii")
        if re.fullmatch(r"[0-9a-f]{64}\n?", expected) is None or expected.rstrip("\n") != digest:
            return None
        if native_helper.verify_native_helper(helper, manifest) is not True:
            return None
        return helper, digest
    except Exception:
        return None


def collect_linux_admission_diagnostic() -> LinuxAdmissionDiagnostic:
    """Collect legacy summaries; no result grants execution or R2 readiness."""
    if sys.platform != "linux":
        raise ValueError("linux_admission_unavailable") from None
    policy = _policy_version()
    try:
        checked_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    except Exception:
        raise ValueError("linux_admission_unavailable") from None
    host = _host_identity()

    def result(reason, current_host, digest=None, first=None, second=None):
        # Every return is gated, including early unsupported/missing paths.
        if _policy_version() != policy:
            raise ValueError("linux_admission_unavailable") from None
        value = LinuxAdmissionDiagnostic(
            "linux_admission_diagnostic", 1, "linux", *current_host, digest,
            policy, checked_at, "incomplete", reason,
            LinuxDiagnosticObservations(first, second), "legacy_probe_summary_only", "unknown",
        )
        return validate_linux_admission_diagnostic(serialize_linux_admission_diagnostic(value))

    if None in host:
        return result("unsupported_environment", host)
    before = _helper_identity()
    if before is None:
        return result("helper_unavailable", host)
    first = second = None
    try:
        sandbox = isolation.LandlockSandbox(
            helper=str(before[0]), manifest=str(before[0].parent / "icode-landlock.sha256"),
        )
        summary = isolation.probe_native_sandbox(sandbox).ready
        first = summary if type(summary) is bool else None
        # The probes own cleanup. Read neither detail/checks nor executed.
        try:
            summary = isolation.probe_linux_protected_paths(sandbox).passed
            second = summary if type(summary) is bool else None
        except Exception:
            pass
    except Exception:
        pass
    after = _helper_identity()
    current_host = _host_identity()
    # Policy must be checked before either drift can produce an early return.
    if _policy_version() != policy:
        raise ValueError("linux_admission_unavailable") from None
    if current_host != host or None in current_host:
        return result("unsupported_environment", (None, current_host[1]))
    if after != before:
        return result("helper_changed", current_host)
    reason = "invalid_observation" if first is None or second is None else "observation_incomplete"
    return result(reason, current_host, before[1], first, second)


def linux_diagnostic_binding_current(report) -> bool:
    """Compare current diagnostic identity only; never run probes or admit work.

    A -> B -> A changes and the actual execution FD are not authenticated here;
    checked_at is diagnostic metadata, not a freshness or execution grant.
    """
    try:
        _validate_report(report)
        if report.reason != "observation_incomplete" or sys.platform != "linux":
            return False
        if _policy_version() != report.policy_schema_version:
            return False
        if _host_identity() != (report.os_build, report.architecture):
            return False
        current = _helper_identity()
        return current is not None and current[1] == report.helper_sha256
    except Exception:
        return False
