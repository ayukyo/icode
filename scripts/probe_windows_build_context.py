"""Report selected Windows CI build metadata, without product execution authority."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path, PureWindowsPath
import re
import stat
import subprocess
import sys
import xml.etree.ElementTree as ET

_REPOSITORY = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPOSITORY))
sys.path.insert(0, str(_REPOSITORY / "src"))

from icode.runner import (  # noqa: E402
    VerificationOutputCaptureError,
    VerificationOutputLimitError,
    _run_unittest_with_bounded_output,
)

_CONTEXT_LIMIT = 4096
_PROJECT_LIMIT = 1024 * 1024
_OUTPUT_LIMIT = 16384
_CONTEXT_FIELDS = {"schema_version", "generator", "platform", "toolset", "sdk_version", "msbuild"}
_PROPERTY_FIELDS = (
    "Configuration", "Platform", "PlatformToolset", "WindowsTargetPlatformVersion",
    "VCToolsInstallDir", "WindowsSdkDir", "MSBuildToolsPath",
)
_NS = "{http://schemas.microsoft.com/developer/msbuild/2003}"
_UNSAFE_TEXT = re.compile(r"[\x00-\x1f\x7f-\x9f\ud800-\udfff]")

_STAGES = frozenset((
    "input", "context_read", "context_validate", "msbuild_identity",
    "project_read", "project_validate", "query", "query_result", "output_json",
    "properties_validate", "tool_directory", "unavailable",
))
_FAILURE_KINDS = frozenset((
    "timeout", "output_capture", "output_limit", "unicode_error", "xml_parse",
    "os_error", "validation_value", "validation_runtime", "subprocess_error", "unavailable",
))
_REJECTION_PREFIX = "windows-build-context rejection="


class _ProbeDiagnostic:
    __slots__ = ("stage",)

    def __init__(self):
        self.stage = "unavailable"


def _new_diagnostic() -> _ProbeDiagnostic:
    return _ProbeDiagnostic()


def _set_diagnostic_stage(diagnostic: _ProbeDiagnostic, stage: str) -> None:
    diagnostic.stage = stage


def _mark_diagnostic_stage(diagnostic: object, stage: object) -> None:
    if type(diagnostic) is not _ProbeDiagnostic:
        return
    try:
        selected = stage if type(stage) is str and stage in _STAGES else "unavailable"
        _set_diagnostic_stage(diagnostic, selected)
    except MemoryError:
        raise
    except Exception:
        # A failed new marker cannot leave the previous operation as evidence.
        try:
            object.__setattr__(diagnostic, "stage", "unavailable")
        except MemoryError:
            raise
        except Exception:
            try:
                object.__delattr__(diagnostic, "stage")
            except MemoryError:
                raise
            except Exception:
                pass


def _get_diagnostic_stage(diagnostic: object) -> str:
    if type(diagnostic) is not _ProbeDiagnostic:
        return "unavailable"
    try:
        stage = diagnostic.stage
        return stage if type(stage) is str and stage in _STAGES else "unavailable"
    except MemoryError:
        raise
    except Exception:
        return "unavailable"


def _failure_kind(error: BaseException) -> str:
    # Type-only matching; specific runner/subprocess types precede their bases.
    for error_type, label in (
        (subprocess.TimeoutExpired, "timeout"),
        (VerificationOutputCaptureError, "output_capture"),
        (VerificationOutputLimitError, "output_limit"),
        (UnicodeError, "unicode_error"),
        (ET.ParseError, "xml_parse"),
        (OSError, "os_error"),
        (ValueError, "validation_value"),
        (RuntimeError, "validation_runtime"),
        (subprocess.SubprocessError, "subprocess_error"),
    ):
        if isinstance(error, error_type):
            return label
    return "unavailable"


def _rejection_line(diagnostic: object, error: BaseException) -> str | None:
    stage = _get_diagnostic_stage(diagnostic)
    try:
        kind = _failure_kind(error)
    except MemoryError:
        raise
    except Exception:
        kind = "unavailable"
    if type(kind) is not str or kind not in _FAILURE_KINDS:
        kind = "unavailable"
    payload = {"schema_version": 1, "stage": stage, "failure_kind": kind,
               "production_authority": "none"}
    serialized = json.dumps(payload, separators=(",", ":"), ensure_ascii=True)
    if type(serialized) is not str:
        return None
    line = _REJECTION_PREFIX + serialized + "\n"
    if len(line.encode("ascii")) > 256:
        return None
    # Closed keys and labels have no whitespace; require one compact JSON line.
    if any(character.isspace() for character in serialized):
        return None
    decoded = json.loads(serialized, object_pairs_hook=_unique_object, parse_constant=_reject_constant)
    if (type(decoded) is not dict or decoded != payload
            or type(decoded.get("schema_version")) is not int):
        return None
    return line


def _emit_rejection(diagnostic: object, error: BaseException) -> None:
    line = _rejection_line(diagnostic, error)
    if line is not None:
        # One write only after the complete bounded ASCII line is ready.
        sys.stdout.write(line)


def _string(value: object) -> str:
    if type(value) is not str or not value or _UNSAFE_TEXT.search(value):
        raise ValueError("invalid metadata string")
    return value


def _read_regular(path: Path, limit: int) -> bytes:
    # A trusted CI build directory is assumed; this is not an atomic/reparse lock.
    info = path.lstat()
    if not stat.S_ISREG(info.st_mode) or not 0 < info.st_size <= limit:
        raise RuntimeError("invalid metadata file")
    with path.open("rb") as stream:
        raw = stream.read(limit + 1)
    if len(raw) != info.st_size or len(raw) > limit:
        raise RuntimeError("metadata file length changed")
    return raw


def _unique_object(pairs: list[tuple[str, object]]) -> dict:
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate metadata key")
        result[key] = value
    return result


def _reject_constant(value: str) -> None:
    raise ValueError("non-JSON numeric constant")


def _json(raw: bytes) -> object:
    # Decode the entire raw document. JSON BOM, trailing mixed output, constants
    # and excessive nesting must fail rather than producing a partial receipt.
    return json.loads(raw.decode("utf-8", errors="strict"),
                      object_pairs_hook=_unique_object, parse_constant=_reject_constant)


def _windows_path(value: str, *, directory: bool) -> None:
    if not PureWindowsPath(value).is_absolute():
        raise ValueError("Windows path must be absolute")
    info = Path(value).lstat()
    expected = stat.S_ISDIR if directory else stat.S_ISREG
    if not expected(info.st_mode):
        raise ValueError("Windows path kind mismatch")


def _project_selection(raw: bytes, platform: str) -> tuple[str, str]:
    text = raw.decode("utf-8", errors="strict")
    # CMake's real vcxproj includes a UTF-8 BOM. ElementTree accepts it, while
    # DTD/entity declarations are forbidden even when no entity is referenced.
    if re.search(r"<!\s*(?:DOCTYPE|ENTITY)\b", text, flags=re.IGNORECASE):
        raise ValueError("project declarations are forbidden")
    root = ET.fromstring(text)
    if root.tag != _NS + "Project":
        raise ValueError("project namespace or root mismatch")
    groups = root.findall(_NS + "PropertyGroup")
    sdks = [node for group in groups for node in group.findall(_NS + "WindowsTargetPlatformVersion")]
    condition = re.compile(
        r"'\$\(Configuration\)\|\$\(Platform\)'\s*==\s*'Release\|" + re.escape(platform) + "'"
    )
    selected = [group for group in groups
                if condition.fullmatch(group.get("Condition", "").strip())]
    if len(sdks) != 1 or len(selected) != 1:
        raise ValueError("project selected properties are missing or ambiguous")
    toolsets = selected[0].findall(_NS + "PlatformToolset")
    if len(toolsets) != 1 or len(sdks[0]) or len(toolsets[0]):
        raise ValueError("project selected property shape mismatch")
    return _string(sdks[0].text), _string(toolsets[0].text)


def probe(build_directory: Path, architecture: str, *, _diagnostic=None) -> dict:
    """One bounded, property-only query of an explicitly selected CI MSBuild."""
    _mark_diagnostic_stage(_diagnostic, "input")
    if sys.platform != "win32" or architecture not in ("x64", "arm64"):
        raise ValueError("unsupported platform or architecture")
    if not build_directory.is_absolute() or not stat.S_ISDIR(build_directory.lstat().st_mode):
        raise ValueError("build directory must exist and be absolute")
    _mark_diagnostic_stage(_diagnostic, "context_read")
    context_raw = _read_regular(build_directory / "icode-windows-build-context.json", _CONTEXT_LIMIT)
    _mark_diagnostic_stage(_diagnostic, "context_validate")
    context = _json(context_raw)
    if type(context) is not dict or set(context) != _CONTEXT_FIELDS:
        raise ValueError("context field set mismatch")
    if type(context["schema_version"]) is not int or context["schema_version"] != 1:
        raise ValueError("context schema mismatch")
    for field in _CONTEXT_FIELDS - {"schema_version"}:
        _string(context[field])
    platform = {"x64": "x64", "arm64": "ARM64"}[architecture]
    if (re.fullmatch(r"Visual Studio [0-9]+ [0-9]{4}", context["generator"]) is None
            or context["platform"] != platform):
        raise ValueError("generator or platform mismatch")
    msbuild = context["msbuild"]
    _mark_diagnostic_stage(_diagnostic, "msbuild_identity")
    if PureWindowsPath(msbuild).name.casefold() != "msbuild.exe":
        raise ValueError("explicit MSBuild executable required")
    _windows_path(msbuild, directory=False)
    project = build_directory / "icode_windows_bootstrap.vcxproj"
    _mark_diagnostic_stage(_diagnostic, "project_read")
    project_raw = _read_regular(project, _PROJECT_LIMIT)
    _mark_diagnostic_stage(_diagnostic, "project_validate")
    sdk, toolset = _project_selection(project_raw, platform)
    if sdk != context["sdk_version"] or toolset != context["toolset"]:
        raise ValueError("project and context selected properties disagree")
    argv = [
        msbuild, str(project), "-nologo", "-noAutoResponse", "-nodeReuse:false", "-maxCpuCount:1",
        "-property:Configuration=Release", f"-property:Platform={platform}",
        "-getProperty:" + ",".join(_PROPERTY_FIELDS),
    ]
    _mark_diagnostic_stage(_diagnostic, "query")
    result = _run_unittest_with_bounded_output(
        argv, workspace=build_directory, timeout=30, output_limit_bytes=_OUTPUT_LIMIT,
        environment=os.environ.copy(),
    )
    _mark_diagnostic_stage(_diagnostic, "query_result")
    if type(result) is not tuple or len(result) != 3:
        raise RuntimeError("invalid MSBuild runner result")
    code, stdout, stderr = result
    if (type(code) is not int or code != 0 or type(stdout) is not bytes
            or not 0 < len(stdout) <= _OUTPUT_LIMIT or type(stderr) is not bytes or stderr):
        raise RuntimeError("MSBuild property query failed")
    _mark_diagnostic_stage(_diagnostic, "output_json")
    output = _json(stdout)
    _mark_diagnostic_stage(_diagnostic, "properties_validate")
    if type(output) is not dict or set(output) != {"Properties"}:
        raise ValueError("MSBuild output root mismatch")
    properties = output["Properties"]
    if type(properties) is not dict or set(properties) != set(_PROPERTY_FIELDS):
        raise ValueError("MSBuild property field set mismatch")
    for field in _PROPERTY_FIELDS:
        _string(properties[field])
    for field, expected in (
        ("Configuration", "Release"), ("Platform", platform),
        ("PlatformToolset", toolset), ("WindowsTargetPlatformVersion", sdk),
    ):
        if properties[field] != expected:
            raise ValueError("MSBuild evaluated selection mismatch")
    _mark_diagnostic_stage(_diagnostic, "tool_directory")
    for field in _PROPERTY_FIELDS[4:]:
        _windows_path(properties[field], directory=True)
    return {
        "schema_version": 1, "architecture": architecture, "generator": context["generator"],
        "toolset": toolset, "sdk_version": sdk, "msbuild": msbuild,
        **{field: properties[field] for field in _PROPERTY_FIELDS[4:]},
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument("--build-directory", required=True, type=Path)
    parser.add_argument("--architecture", required=True, choices=("x64", "arm64"))
    args = parser.parse_args()
    try:
        diagnostic = _new_diagnostic()
    except MemoryError:
        raise
    except Exception:
        diagnostic = None
    try:
        receipt = probe(args.build_directory, args.architecture, _diagnostic=diagnostic)
    except (OSError, UnicodeError, ValueError, RuntimeError, ET.ParseError, subprocess.SubprocessError) as error:
        print("::error::windows_build_context_probe_failed")
        try:
            _emit_rejection(diagnostic, error)
        except MemoryError:
            raise
        except Exception:
            pass
        return 1
    print("windows-build-context status=PASS production_authority=none")
    print("windows-build-context receipt=" + json.dumps(receipt, separators=(",", ":"), ensure_ascii=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
