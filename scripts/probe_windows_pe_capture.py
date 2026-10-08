"""Capture Windows CI PE samples without granting production authority."""

from __future__ import annotations

import base64
import argparse
import hashlib
import json
import os
from pathlib import Path, PureWindowsPath
import re
import subprocess
import sys
import sysconfig
import tempfile
import xml.etree.ElementTree as ET

_REPOSITORY = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPOSITORY))
sys.path.insert(0, str(_REPOSITORY / 'src'))

from icode.runner import _run_unittest_with_bounded_output  # noqa: E402
from icode.native_helper import windows_arch_from_platform, windows_pe_architecture  # noqa: E402
from scripts.probe_windows_build_context import probe as _probe_context, _read_regular  # noqa: E402

_IMAGE_LIMIT = 8 * 1024 * 1024
_OUTPUT_LIMIT = 16384
_MANIFEST_LIMIT = 4096
_RECEIPT_LIMIT = 32768
_CONTEXT_FIELDS = {'schema_version', 'architecture', 'generator', 'toolset', 'sdk_version',
                   'msbuild', 'VCToolsInstallDir', 'WindowsSdkDir', 'MSBuildToolsPath'}


def _image_digest(path: Path, architecture: str) -> str:
    # Trusted CI host/tools are the TCB; this is not a HANDLE/ACL/publisher lock.
    raw = _read_regular(path, _IMAGE_LIMIT)
    if windows_pe_architecture(raw) != architecture:
        raise ValueError('PE machine mismatch')
    return hashlib.sha256(raw).hexdigest()


def _invoke(argv: list[str], workspace: Path, environment: dict[str, str], *, require_stdout: bool) -> bytes:
    result = _run_unittest_with_bounded_output(argv, workspace=workspace, timeout=30,
        output_limit_bytes=_OUTPUT_LIMIT, environment=environment)
    if type(result) is not tuple or len(result) != 3:
        raise RuntimeError('invalid tool runner result')
    code, stdout, stderr = result
    if (type(code) is not int or code != 0 or type(stdout) is not bytes
            or type(stderr) is not bytes or len(stdout) + len(stderr) > _OUTPUT_LIMIT
            or stderr or (require_stdout and not stdout)):
        raise RuntimeError('tool sample capture failed')
    return stdout


def _encode(receipt: dict) -> str:
    encoded = json.dumps(receipt, sort_keys=True, separators=(',', ':'), ensure_ascii=True)
    if len(encoded.encode('ascii')) > _RECEIPT_LIMIT:
        raise RuntimeError('capture receipt exceeds total budget')
    return encoded


def capture(build_directory: Path, architecture: str) -> dict:
    # get_platform identifies the compiled Python target, not the native OS.
    if (sys.platform != 'win32' or architecture not in ('x64', 'arm64')
            or windows_arch_from_platform(sysconfig.get_platform()) != architecture):
        raise ValueError('unsupported platform or process target')
    context = _probe_context(build_directory, architecture)
    if type(context) is not dict or set(context) != _CONTEXT_FIELDS:
        raise ValueError('context field set mismatch')
    if type(context['schema_version']) is not int or context['schema_version'] != 1:
        raise ValueError('context schema mismatch')
    if any(type(context[field]) is not str or not context[field]
           for field in _CONTEXT_FIELDS - {'schema_version'}):
        raise ValueError('invalid context string')
    if context['architecture'] != architecture:
        raise ValueError('context architecture mismatch')
    if re.fullmatch(r'[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+', context['sdk_version']) is None:
        raise ValueError('invalid SDK version component')
    if any(not PureWindowsPath(context[field]).is_absolute()
           for field in ('VCToolsInstallDir', 'WindowsSdkDir')):
        raise ValueError('tool roots must be absolute')
    environment = {key: os.environ.get(key, '') for key in ('SystemRoot', 'WINDIR')}
    if not all(environment.values()):
        raise ValueError('system roots are required')
    dumpbin = Path(str(PureWindowsPath(context['VCToolsInstallDir']) / 'bin' /
                       ('Host' + architecture) / architecture / 'dumpbin.exe'))
    mt = Path(str(PureWindowsPath(context['WindowsSdkDir']) / 'bin' /
                  context['sdk_version'] / architecture / 'mt.exe'))
    helper = build_directory / 'Release' / f'icode-sandbox-windows-{architecture}.exe'
    digests = [_image_digest(path, architecture) for path in (helper, dumpbin, mt)]
    with tempfile.TemporaryDirectory(prefix='icode-pe-capture-', dir=build_directory) as directory:
        workspace = Path(directory)
        output = workspace / 'manifest.xml'
        environment.update(TEMP=directory, TMP=directory)
        imports = _invoke([str(dumpbin), '/nopdb', '/imports', str(helper)],
                          workspace, environment, require_stdout=True)
        # lstat also detects dangling links. Only FileNotFoundError means absent.
        try:
            output.lstat()
        except FileNotFoundError:
            pass
        else:
            raise RuntimeError('manifest output already exists')
        _invoke(
            [str(mt), '-nologo', '-inputresource:' + str(helper) + ';#1', '-out:' + str(output)],
            workspace, environment, require_stdout=False)
        manifest = _read_regular(output, _MANIFEST_LIMIT)
    # Cleanup must complete before a receipt can be constructed. Re-read each
    # original object; size alone cannot detect same-length byte changes.
    for path, expected in zip((helper, dumpbin, mt), digests):
        if _image_digest(path, architecture) != expected:
            raise RuntimeError('PE bytes changed during capture')
    receipt = dict(schema_version=1, architecture=architecture, build_context=context,
        helper_sha256=digests[0], dumpbin=dict(path=str(dumpbin), sha256=digests[1]),
        mt=dict(path=str(mt), sha256=digests[2]),
        dumpbin_stdout_base64=base64.b64encode(imports).decode('ascii'),
        manifest_base64=base64.b64encode(manifest).decode('ascii'),
        parse_complete=False, runtime_load_verified=False, source_launch_verified=False)
    # These public base64 samples are reversible raw bytes, not redaction or a
    # complete PE/manifest parse. Enforce the total budget without truncation.
    _encode(receipt)
    return receipt


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument('--build-directory', required=True, type=Path)
    parser.add_argument('--architecture', required=True, choices=('x64', 'arm64'))
    args = parser.parse_args()
    try:
        receipt = capture(args.build_directory, args.architecture)
        encoded = _encode(receipt)
    except (OSError, UnicodeError, ValueError, RuntimeError, ET.ParseError, subprocess.SubprocessError):
        print('::error::windows_pe_capture_probe_failed')
        return 1
    print('windows-pe-capture status=CAPTURED production_authority=none')
    print('windows-pe-capture receipt=' + encoded)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
