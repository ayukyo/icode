"""Finite static-load subcheck on real factory owners; no execution grant."""
from __future__ import annotations
import hashlib
import os
import struct
import sys
import unittest
from types import SimpleNamespace
from unittest.mock import patch
from tests._support import temp_workspace
import icode.linux_helper_object as factory
import icode.linux_static_helper as subject
REAL_PREAD = getattr(os, 'pread', None)
REAL_FSTAT = os.fstat
ERROR = 'Linux helper object is unavailable'

def image(*, machine=62, kind=2, types=(1,), phoff=64, entsize=56, count=None, tail=b''):
    header = bytearray(64)
    header[:7] = b'\x7fELF\x02\x01\x01'
    struct.pack_into('<HHI', header, 16, kind, machine, 1)
    struct.pack_into('<Q', header, 32, phoff)
    struct.pack_into('<HHH', header, 52, 64, entsize, len(types) if count is None else count)
    table = b''.join(struct.pack('<IIQQQQQQ', ptype, 5, 0, 0, 0, 64 + 56 * len(types), 64 + 56 * len(types), 4096) for ptype in types)
    return bytes(header) + table + tail

def pair(root, data):
    binary, manifest = root / 'helper', root / 'helper.sha256'
    binary.write_bytes(data)
    binary.chmod(0o700)
    manifest.write_bytes(hashlib.sha256(data).hexdigest().encode() + b'\n')
    return binary, manifest

class PortableTests(unittest.TestCase):
    def test_unsupported_platform_refuses_before_owner(self):
        # Typed negative sentinel only: no FD resource, factory provenance or authority.
        # Never close it; the platform gate must precede any owner access.
        owner = factory.LinuxHelperObject(-1, (-1, -1), 'x86_64', '0' * 64)
        for platform in ('win32', 'darwin', 'freebsd'):
            with self.subTest(platform=platform), patch.object(subject.sys, 'platform', platform):
                with patch.object(factory.LinuxHelperObject, 'fileno') as fileno, patch.object(subject.os, 'pread', side_effect=AssertionError('unexpected read'), create=True) as read:
                    with self.assertRaises(factory.LinuxHelperObjectError) as caught:
                        subject.validate_static_linux_helper(owner)
                    self.assertEqual(str(caught.exception), ERROR)
                    fileno.assert_not_called()
                    read.assert_not_called()
    def test_missing_pread_refuses_before_owner(self):
        # Same resource-free type sentinel; construction is not factory verification.
        owner = factory.LinuxHelperObject(-1, (-1, -1), 'x86_64', '0' * 64)
        with patch.object(subject.sys, 'platform', 'linux'), patch.object(subject.os, 'pread', None, create=True), patch.object(factory.LinuxHelperObject, 'fileno') as fileno:
            with self.assertRaises(factory.LinuxHelperObjectError):
                subject.validate_static_linux_helper(owner)
            fileno.assert_not_called()

@unittest.skipUnless(sys.platform.startswith('linux') and REAL_PREAD is not None, 'real Linux pread cases; no installed-package credit')
class StaticTests(unittest.TestCase):
    def setUp(self):
        host = patch.object(factory.platform, 'machine', return_value='x86_64')
        host.start()
        self.addCleanup(host.stop)
    def reject(self, owner):
        with self.assertRaises(factory.LinuxHelperObjectError) as caught:
            subject.validate_static_linux_helper(owner)
        self.assertEqual(str(caught.exception), ERROR)
        self.assertIsNone(caught.exception.__cause__)
        self.assertTrue(caught.exception.__suppress_context__)
    def test_dynamic_targets_old_factory_accepts_new_check_rejects(self):
        for data in (image(kind=3), image(types=(1, 3)), image(types=(1, 2))):
            with self.subTest(data=data[16:18]), temp_workspace() as root:
                with factory.open_linux_helper_object(*pair(root, data)) as owner:
                    fd = owner.fileno()
                    self.reject(owner)
                    self.assertEqual(owner.fileno(), fd)
    def test_static_and_architectures_offset_same_fd_and_no_close(self):
        for machine, host, tail in ((62, 'x86_64', b''), (183, 'aarch64', b''), (62, 'x86_64', b'x' * (65536 + 17))):
            with self.subTest(machine=machine, tail_size=len(tail)), temp_workspace() as root, patch.object(factory.platform, 'machine', return_value=host):
                data = image(machine=machine, tail=tail)
                with factory.open_linux_helper_object(*pair(root, data)) as owner:
                    fd = owner.fileno()
                    os.lseek(fd, 7, os.SEEK_SET)
                    calls = []
                    def pread(descriptor, length, offset):
                        calls.append((descriptor, length, offset))
                        return REAL_PREAD(descriptor, length, offset)
                    with patch.object(subject.os, 'pread', side_effect=pread), patch.object(subject.os, 'open', side_effect=AssertionError('reopened')), patch.object(subject.os, 'close') as closed:
                        self.assertIsNone(subject.validate_static_linux_helper(owner))
                        closed.assert_not_called()
                    self.assertTrue(all(descriptor == fd for descriptor, _, _ in calls))
                    self.assertLessEqual(max(length for _, length, _ in calls), 65536)
                    self.assertLessEqual(sum(length for _, length, _ in calls), 64 + 56 + len(data) + 1)
                    if len(data) > 65536:
                        self.assertEqual(calls[2:], [(fd, 65536, 0), (fd, len(data) - 65536, 65536), (fd, 1, len(data))])
                    self.assertEqual(os.lseek(fd, 0, os.SEEK_CUR), 7)
                    self.assertEqual(owner.fileno(), fd)
    def test_program_table_boundaries_and_extended_counts(self):
        bad = (image(entsize=0), image(entsize=55), image(entsize=57), image(count=0), image(count=1025), image(count=65535), image(phoff=0), image(phoff=63), image(phoff=2**64 - 1), image(phoff=121), image(count=2), image()[:-1])
        for data in bad:
            with self.subTest(length=len(data)), temp_workspace() as root:
                with factory.open_linux_helper_object(*pair(root, data)) as owner:
                    self.reject(owner)
        with temp_workspace() as root:
            with factory.open_linux_helper_object(*pair(root, image(types=(1,) * 1024))) as owner:
                self.assertIsNone(subject.validate_static_linux_helper(owner))
    def test_header_and_architecture_drift_after_factory(self):
        for offset, replacement in ((0, b'BAD!'), (4, b'\x01'), (5, b'\x02'), (6, b'\x00'), (18, b'\xb7\x00'), (20, b'\x00' * 4), (52, b'\x3f\x00')):
            with self.subTest(offset=offset), temp_workspace() as root:
                binary, manifest = pair(root, image())
                with factory.open_linux_helper_object(binary, manifest) as owner:
                    with binary.open('r+b') as stream:
                        stream.seek(offset)
                        stream.write(replacement)
                    self.reject(owner)
    def test_digest_drift_with_valid_header_is_target_rejection(self):
        with temp_workspace() as root:
            binary, manifest = pair(root, image(tail=b'old'))
            with factory.open_linux_helper_object(binary, manifest) as owner:
                binary.write_bytes(image(tail=b'new'))
                self.reject(owner)
                self.assertGreaterEqual(owner.fileno(), 0)
    def test_pre_post_snapshot_drift(self):
        for field in ('st_dev', 'st_ino', 'st_size', 'st_mtime_ns', 'st_ctime_ns'):
            with self.subTest(field=field), temp_workspace() as root:
                with factory.open_linux_helper_object(*pair(root, image())) as owner:
                    reads = []
                    fstat_calls = 0
                    injected = False
                    def pread(fd, length, offset):
                        reads.append((length, offset))
                        return REAL_PREAD(fd, length, offset)
                    def fstat(fd):
                        nonlocal fstat_calls, injected
                        fstat_calls += 1
                        actual = REAL_FSTAT(fd)
                        if fstat_calls == 4:
                            fields = {name: getattr(actual, name) for name in ('st_dev', 'st_ino', 'st_size', 'st_mtime_ns', 'st_ctime_ns', 'st_mode')}
                            fields[field] += 1
                            injected = True
                            return SimpleNamespace(**fields)
                        return actual
                    with patch.object(subject.os, 'pread', side_effect=pread), patch.object(subject.os, 'fstat', side_effect=fstat):
                        self.reject(owner)
                    self.assertEqual(fstat_calls, 4)
                    self.assertTrue(injected)
                    self.assertEqual(reads, [(64, 0), (56, 64), (120, 0), (1, 120)])
                    self.assertGreaterEqual(owner.fileno(), 0)
    def test_short_pread_each_stage_rejects_without_close(self):
        for stage in (1, 2, 3):
            with self.subTest(stage=stage), temp_workspace() as root:
                with factory.open_linux_helper_object(*pair(root, image())) as owner:
                    calls = 0
                    def pread(fd, length, offset):
                        nonlocal calls
                        calls += 1
                        data = REAL_PREAD(fd, length, offset)
                        return data[:-1] if calls == stage else data
                    with patch.object(subject.os, 'pread', side_effect=pread), patch.object(subject.os, 'close') as closed:
                        self.reject(owner)
                        closed.assert_not_called()
    def test_eof_growth_is_rejected_and_bounded(self):
        with temp_workspace() as root:
            data = image()
            with factory.open_linux_helper_object(*pair(root, data)) as owner:
                calls = []
                def pread(fd, length, offset):
                    calls.append((length, offset))
                    return b'x' if offset == len(data) else REAL_PREAD(fd, length, offset)
                with patch.object(subject.os, 'pread', side_effect=pread):
                    self.reject(owner)
                self.assertEqual(calls[-1], (1, len(data)))
                self.assertLessEqual(sum(length for length, _ in calls), 64 + 56 + len(data) + 1)
    def test_size_limit_exact_and_plus_one(self):
        self.assertEqual(subject._BINARY_LIMIT, 64 * 1024 * 1024)
        self.assertEqual(subject._READ_CHUNK, 64 * 1024)
        for tail, accepted in ((b'x' * 8, True), (b'x' * 9, False)):
            with self.subTest(accepted=accepted), temp_workspace() as root:
                with factory.open_linux_helper_object(*pair(root, image(tail=tail))) as owner:
                    with patch.object(subject, '_BINARY_LIMIT', 128):
                        if accepted:
                            self.assertIsNone(subject.validate_static_linux_helper(owner))
                        else:
                            self.reject(owner)
    def test_internal_read_range_types_refuse_before_os(self):
        invalid = ((True, 1, 120), (0, True, 120), (0, 1, True), (-1, 1, 120), (0, -1, 120), (121, 0, 120), (119, 2, 120), (2**64, 1, 120), (0, 65537, 65537))
        with patch.object(subject.os, 'pread') as read:
            for offset, length, size in invalid:
                with self.subTest(offset=offset, length=length, size=size):
                    with self.assertRaises(factory.LinuxHelperObjectError):
                        subject._read_exact(3, offset, length, size)
            read.assert_not_called()
    def test_rename_unlink_replace_uses_held_object(self):
        for operation in ('rename', 'unlink', 'replace'):
            with self.subTest(operation=operation), temp_workspace() as root:
                binary, manifest = pair(root, image())
                with factory.open_linux_helper_object(binary, manifest) as owner:
                    fd = owner.fileno()
                    if operation == 'unlink':
                        binary.unlink()
                    else:
                        binary.rename(root / 'saved')
                        if operation == 'replace':
                            binary.write_bytes(image(types=(2,)))
                    self.assertIsNone(subject.validate_static_linux_helper(owner))
                    self.assertEqual(owner.fileno(), fd)
    def test_wrong_closed_and_reused_owner(self):
        with patch.object(subject.os, 'pread') as read:
            for value in (None, False, object(), SimpleNamespace(fileno=lambda: 0)):
                self.reject(value)
            read.assert_not_called()
        with temp_workspace() as root:
            binary, manifest = pair(root, image())
            owner = factory.open_linux_helper_object(binary, manifest)
            owner.close()
            self.reject(owner)
            owner = factory.open_linux_helper_object(binary, manifest)
            fd = owner.fileno()
            other = root / 'other'
            other.write_bytes(image())
            replacement = os.open(other, os.O_RDONLY)
            try:
                os.dup2(replacement, fd)
                with patch.object(subject.os, 'close') as closed:
                    self.reject(owner)
                    closed.assert_not_called()
                self.assertEqual(REAL_FSTAT(fd).st_ino, other.stat().st_ino)
            finally:
                os.close(fd)
                os.close(replacement)
    def test_every_os_stage_fixed_fault_and_original_signals(self):
        for stage, ordinals in (('fileno', (1, 2)), ('fstat', (1, 2, 3, 4)), ('pread', (1, 2, 3, 4))):
            for ordinal in ordinals:
                for error in (OSError('private-data'), KeyboardInterrupt('private-signal'), SystemExit(17)):
                    with self.subTest(stage=stage, ordinal=ordinal, error=type(error).__name__), temp_workspace() as root:
                        with factory.open_linux_helper_object(*pair(root, image())) as owner:
                            target = owner if stage == 'fileno' else subject.os
                            original = getattr(target, stage)
                            calls = 0
                            def operation(*args):
                                nonlocal calls
                                calls += 1
                                if calls == ordinal:
                                    raise error
                                return original(*args)
                            with patch.object(target, stage, side_effect=operation), patch.object(subject.os, 'close') as closed:
                                if isinstance(error, Exception):
                                    self.reject(owner)
                                else:
                                    with self.assertRaises(type(error)) as caught:
                                        subject.validate_static_linux_helper(owner)
                                    self.assertIs(caught.exception, error)
                                self.assertEqual(calls, ordinal)
                                closed.assert_not_called()
                            self.assertGreaterEqual(owner.fileno(), 0)
if __name__ == '__main__':
    unittest.main()
