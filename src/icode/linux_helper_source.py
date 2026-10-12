"""Finite package-source observation; not authentication or execution authority."""
from __future__ import annotations
from dataclasses import dataclass
import os
from pathlib import Path
import re
import stat
import sys
from . import native_helper
from .isolation import LandlockSandbox
from .sandbox_policy import SandboxPolicy
from .linux_helper_object import (
    LinuxHelperObject, LinuxHelperObjectError, _select, _raise_fixed_or_signal,
)

_PATH_BYTES = 4096
_DIRECTORY_LIMIT = 128
_MANIFEST_READ = 67
_DIGEST_LINE = re.compile(rb'[0-9a-f]{64}\n?\Z')

@dataclass(frozen=True)
class LinuxHelperSourceObservation:
    helper_path: Path
    manifest_path: Path
    directory_identities: tuple[tuple[Path, int, int], ...]
    helper_snapshot: tuple[int, int, int, int, int]
    manifest_snapshot: tuple[int, int, int, int, int]
    manifest_digest: str

def _identity(value):
    return value.st_dev, value.st_ino

def _snapshot(value):
    return (*_identity(value), value.st_size, value.st_mtime_ns, value.st_ctime_ns)

def _regular(value):
    if not stat.S_ISREG(value.st_mode) or value.st_nlink != 1:
        raise LinuxHelperObjectError()

def _bounded(path):
    if not path.is_absolute() or len(os.fsencode(path)) > _PATH_BYTES:
        raise LinuxHelperObjectError()

def _source_paths(sandbox):
    module = Path(native_helper.__file__).resolve(strict=True)
    native = module.parent / 'native'
    binary = native / 'icode-landlock'
    manifest = native / 'icode-landlock.sha256'
    for path in (module, native, binary, manifest):
        _bounded(path)
    if (sandbox.manifest is None
            or Path(sandbox.helper).resolve(strict=True) != binary
            or Path(sandbox.manifest).resolve(strict=True) != manifest):
        raise LinuxHelperObjectError()
    return module, native, binary, manifest

def _write_boundary(native, policy):
    # Ancestors are not bidirectional conflicts: a sibling workspace cannot
    # control source entries in the shared /home/user or /tmp ancestor.
    for root in policy.write_roots:
        resolved = root.resolve(strict=True)
        if native.is_relative_to(resolved) or resolved.is_relative_to(native):
            raise LinuxHelperObjectError()

def observe_linux_helper_source(sandbox: LandlockSandbox, *,
        policy: SandboxPolicy, owner: LinuxHelperObject) -> LinuxHelperSourceObservation:
    """Borrow helper; own only temporary directories and one fresh manifest FD."""
    owned = []
    selected = None
    result = None
    try:
        if (not sys.platform.startswith('linux') or not callable(getattr(os, 'pread', None))
                or not isinstance(sandbox, LandlockSandbox)
                or not isinstance(policy, SandboxPolicy)
                or not isinstance(owner, LinuxHelperObject)):
            raise LinuxHelperObjectError()
        directory_flags = os.O_RDONLY
        for name in ('O_CLOEXEC', 'O_NOFOLLOW', 'O_DIRECTORY'):
            flag = getattr(os, name, None)
            if type(flag) is not int or flag <= 0:
                raise LinuxHelperObjectError()
            directory_flags |= flag
        nonblock = getattr(os, 'O_NONBLOCK', None)
        if type(nonblock) is not int or nonblock <= 0:
            raise LinuxHelperObjectError()
        file_flags = (directory_flags & ~os.O_DIRECTORY) | nonblock
        # Preserve the actual existing DENY/single-root/runtime conflict checks.
        sandbox._checked_policy_workspace(policy, strict_runtime=True)
        initial_paths = _source_paths(sandbox)
        module, native, binary, manifest = initial_paths
        _write_boundary(native, policy)
        runtime = sandbox._runtime_read_roots(strict=True)
        if not any(native.is_relative_to(root) for root in runtime):
            raise LinuxHelperObjectError()
        parts = native.parts[1:]
        if len(parts) + 1 > _DIRECTORY_LIMIT:
            raise LinuxHelperObjectError()
        helper_fd = owner.fileno()
        helper_before = os.fstat(helper_fd)
        _regular(helper_before)
        root_fd = os.open('/', directory_flags)
        owned.append(root_fd)
        root_status = os.fstat(root_fd)
        if not stat.S_ISDIR(root_status.st_mode):
            raise LinuxHelperObjectError()
        # Keep each parent and child handle so later ancestor replacement is
        # checked via its original parent entry, not by a fresh trusted pathname.
        nodes = [(Path('/'), root_fd, _identity(root_status))]
        links = []
        parent_fd, parent_path = root_fd, Path('/')
        for part in parts:
            entry = os.stat(part, dir_fd=parent_fd, follow_symlinks=False)
            if not stat.S_ISDIR(entry.st_mode):
                raise LinuxHelperObjectError()
            child_fd = os.open(part, directory_flags, dir_fd=parent_fd)
            owned.append(child_fd)
            held = os.fstat(child_fd)
            if not stat.S_ISDIR(held.st_mode) or _identity(entry) != _identity(held):
                raise LinuxHelperObjectError()
            child_path = parent_path / part
            nodes.append((child_path, child_fd, _identity(held)))
            links.append((parent_fd, part, child_fd, _identity(held)))
            parent_fd, parent_path = child_fd, child_path
        helper_entry = os.stat(binary.name, dir_fd=parent_fd, follow_symlinks=False)
        _regular(helper_entry)
        if _snapshot(helper_entry) != _snapshot(helper_before):
            raise LinuxHelperObjectError()
        manifest_entry = os.stat(manifest.name, dir_fd=parent_fd, follow_symlinks=False)
        _regular(manifest_entry)
        manifest_fd = os.open(manifest.name, file_flags, dir_fd=parent_fd)
        owned.append(manifest_fd)
        manifest_before = os.fstat(manifest_fd)
        _regular(manifest_before)
        if _snapshot(manifest_entry) != _snapshot(manifest_before):
            raise LinuxHelperObjectError()
        if not 64 <= manifest_before.st_size <= 65:
            raise LinuxHelperObjectError()
        contents = os.pread(manifest_fd, _MANIFEST_READ, 0)
        if (type(contents) is not bytes or len(contents) != manifest_before.st_size
                or _DIGEST_LINE.fullmatch(contents) is None
                or contents.rstrip(b'\n').decode('ascii') != owner.sha256):
            raise LinuxHelperObjectError()
        manifest_after = os.fstat(manifest_fd)
        _regular(manifest_after)
        manifest_final_entry = os.stat(manifest.name, dir_fd=parent_fd, follow_symlinks=False)
        _regular(manifest_final_entry)
        if (_snapshot(manifest_before) != _snapshot(manifest_after)
                or _snapshot(manifest_after) != _snapshot(manifest_final_entry)):
            raise LinuxHelperObjectError()
        helper_final_entry = os.stat(binary.name, dir_fd=parent_fd, follow_symlinks=False)
        _regular(helper_final_entry)
        if owner.fileno() != helper_fd:
            raise LinuxHelperObjectError()
        helper_after = os.fstat(helper_fd)
        _regular(helper_after)
        if (_snapshot(helper_before) != _snapshot(helper_after)
                or _snapshot(helper_after) != _snapshot(helper_final_entry)):
            raise LinuxHelperObjectError()
        root_entry = os.stat('/', follow_symlinks=False)
        if not stat.S_ISDIR(root_entry.st_mode) or _identity(root_entry) != nodes[0][2]:
            raise LinuxHelperObjectError()
        for parent, name, child, expected in links:
            entry = os.stat(name, dir_fd=parent, follow_symlinks=False)
            held = os.fstat(child)
            if (not stat.S_ISDIR(entry.st_mode) or not stat.S_ISDIR(held.st_mode)
                    or _identity(entry) != expected or _identity(held) != expected):
                raise LinuxHelperObjectError()
        if initial_paths != _source_paths(sandbox):
            raise LinuxHelperObjectError()
        _write_boundary(native, policy)
        if runtime != sandbox._runtime_read_roots(strict=True):
            raise LinuxHelperObjectError()
        result = LinuxHelperSourceObservation(binary, manifest,
            tuple((path, *identity) for path, _, identity in nodes),
            _snapshot(helper_after), _snapshot(manifest_after), owner.sha256)
    except BaseException as error:
        selected = error
    finally:
        while owned:
            fd = owned.pop()
            try:
                os.close(fd)
            except BaseException as error:
                selected = _select(selected, error)
    if selected is not None:
        _raise_fixed_or_signal(selected)
    return result
