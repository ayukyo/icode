"""Private same-FD verification/ownership; never executes a helper payload."""
from __future__ import annotations

import copy
import errno
import hashlib
import os
from pathlib import Path
import pickle
import socket
import struct
import subprocess
import sys
import unittest
from unittest.mock import patch

from tests._support import REPO_ROOT, temp_workspace
import icode.linux_helper_object as subject

REAL_OPEN, REAL_CLOSE = os.open, os.close
REAL_FSTAT, REAL_READ, REAL_LSEEK = os.fstat, os.read, os.lseek
ERROR = "Linux helper object is unavailable"


def image(machine: int = 62, tail: bytes = b"private fixture") -> bytes:
    header = bytearray(64)
    header[:7] = b"\x7fELF\x02\x01\x01"
    struct.pack_into("<HHI", header, 16, 2, machine, 1)
    struct.pack_into("<H", header, 52, 64)
    return bytes(header) + tail


def pair(root: Path, data: bytes | None = None, name: str = "helper"):
    data = image() if data is None else data
    binary, manifest = root / name, root / (name + ".sha256")
    binary.write_bytes(data)
    binary.chmod(0o700)
    manifest.write_bytes(hashlib.sha256(data).hexdigest().encode() + b"\n")
    return binary, manifest


class PortablePlatformTests(unittest.TestCase):
    def test_non_linux_rejects_before_host_or_open(self):
        for platform in ("win32", "darwin", "freebsd"):
            with self.subTest(platform=platform), patch.object(
                subject.sys, "platform", platform
            ), patch.object(subject.platform, "machine") as host, patch.object(
                subject.os, "open"
            ) as opened:
                with self.assertRaises(subject.LinuxHelperObjectError) as caught:
                    subject.open_linux_helper_object(Path("secret-path"), Path("manifest"))
                self.assertEqual(str(caught.exception), ERROR)
                self.assertIsNone(caught.exception.__cause__)
                host.assert_not_called()
                opened.assert_not_called()

    def test_bad_host_and_host_faults_reject_before_open(self):
        for answer in ("i686", "riscv64", "", None, OSError("private-host")):
            with self.subTest(answer=type(answer).__name__), patch.object(
                subject.sys, "platform", "linux"
            ), patch.object(subject.platform, "machine", **(
                {"side_effect": answer} if isinstance(answer, Exception)
                else {"return_value": answer}
            )), patch.object(subject.os, "open") as opened:
                with self.assertRaises(subject.LinuxHelperObjectError) as caught:
                    subject.open_linux_helper_object(Path("private"), Path("private"))
                self.assertEqual(str(caught.exception), ERROR)
                self.assertIsNone(caught.exception.__cause__)
                opened.assert_not_called()

    def test_host_interrupts_keep_identity(self):
        for signal in (KeyboardInterrupt("host"), SystemExit(17)):
            with self.subTest(signal=type(signal).__name__), patch.object(
                subject.sys, "platform", "linux"
            ), patch.object(subject.platform, "machine", side_effect=signal), patch.object(
                subject.os, "open"
            ) as opened:
                with self.assertRaises(type(signal)) as caught:
                    subject.open_linux_helper_object(Path("private"), Path("private"))
                self.assertIs(caught.exception, signal)
                opened.assert_not_called()


@unittest.skipUnless(sys.platform.startswith("linux"), "real Linux FD cases")
class LinuxHelperObjectTests(unittest.TestCase):
    def setUp(self):
        self.host = patch.object(subject.platform, "machine", return_value="x86_64")
        self.host.start()
        self.addCleanup(self.host.stop)

    def assert_closed(self, descriptor):
        with self.assertRaises(OSError) as caught:
            REAL_FSTAT(descriptor)
        self.assertEqual(caught.exception.errno, errno.EBADF)

    def reject(self, binary, manifest):
        with self.assertRaises(subject.LinuxHelperObjectError) as caught:
            subject.open_linux_helper_object(binary, manifest)
        self.assertEqual(str(caught.exception), ERROR)
        self.assertIsNone(caught.exception.__cause__)
        self.assertTrue(caught.exception.__suppress_context__)

    def test_real_regular_same_fd_metadata_offset_and_context(self):
        with temp_workspace() as root:
            binary, manifest = pair(root)
            reads, opens = [], []
            def opened(path, flags):
                fd = REAL_OPEN(path, flags)
                opens.append((Path(path), fd, flags))
                return fd
            def read(fd, size):
                reads.append((fd, REAL_LSEEK(fd, 0, os.SEEK_CUR), size))
                return REAL_READ(fd, size)
            with patch.object(subject.os, "open", side_effect=opened), patch.object(
                subject.os, "read", side_effect=read
            ):
                owner = subject.open_linux_helper_object(binary, manifest)
            self.assertIsInstance(owner, subject.LinuxHelperObject)
            with owner as entered:
                self.assertIs(entered, owner)
                fd = owner.fileno()
                self.assertFalse(os.get_inheritable(fd))
                self.assertEqual(owner.architecture, "x86_64")
                self.assertEqual(owner.sha256, hashlib.sha256(binary.read_bytes()).hexdigest())
                self.assertEqual([path for path, _, _ in opens], [binary, manifest])
                required = os.O_NOFOLLOW | os.O_CLOEXEC | os.O_NONBLOCK
                self.assertTrue(all(flags & required == required for _, _, flags in opens))
                binary_reads = [entry for entry in reads if entry[0] == fd]
                self.assertEqual(binary_reads[0][1:], (0, 64))
                self.assertEqual(binary_reads[1][1], 0)
                self.assertLessEqual(max(size for _, _, size in binary_reads), 64 * 1024)
                self.assert_closed(opens[1][1])
            self.assert_closed(fd)
            owner.close()
            with self.assertRaises(subject.LinuxHelperObjectError):
                owner.fileno()

    def test_supported_host_aliases_and_architecture_mismatch(self):
        for host, machine, architecture in (("x86_64", 62, "x86_64"),
                                             ("aarch64", 183, "arm64"),
                                             ("arm64", 183, "arm64")):
            with self.subTest(host=host), temp_workspace() as root, patch.object(
                subject.platform, "machine", return_value=host
            ):
                binary, manifest = pair(root, image(machine))
                with subject.open_linux_helper_object(binary, manifest) as owner:
                    self.assertEqual(owner.architecture, architecture)
                binary, manifest = pair(root, image(183 if machine == 62 else 62))
                self.reject(binary, manifest)

    def test_missing_required_flags_reject_before_open(self):
        for flag in ("O_NOFOLLOW", "O_CLOEXEC", "O_NONBLOCK"):
            with self.subTest(flag=flag), temp_workspace() as root:
                binary, manifest = pair(root)
                value = getattr(subject.os, flag)
                try:
                    delattr(subject.os, flag)
                    with patch.object(subject.os, "open") as opened:
                        self.reject(binary, manifest)
                        opened.assert_not_called()
                finally:
                    setattr(subject.os, flag, value)
                with patch.object(subject.os, flag, 0), patch.object(subject.os, "open") as opened:
                    self.reject(binary, manifest)
                    opened.assert_not_called()

    def test_manifest_grammar_limit_and_short_reads(self):
        with temp_workspace() as root:
            binary, manifest = pair(root)
            digest = hashlib.sha256(binary.read_bytes()).hexdigest().encode()
            for text in (digest, digest + b"\n"):
                manifest.write_bytes(text)
                with patch.object(subject.os, "read", side_effect=lambda fd, count:
                                  REAL_READ(fd, min(count, 3))):
                    with subject.open_linux_helper_object(binary, manifest) as owner:
                        self.assertGreaterEqual(owner.fileno(), 0)
            for text in (b"", digest.upper(), digest + b"\r\n", digest + b"\n\n",
                         digest + b"x", b" " + digest, b"\xff" * 64, b"a" * 4096):
                with self.subTest(length=len(text)):
                    manifest.write_bytes(text)
                    seen = []
                    def read(fd, count):
                        result = REAL_READ(fd, count)
                        seen.append((fd, len(result), count))
                        return result
                    with patch.object(subject.os, "read", side_effect=read):
                        self.reject(binary, manifest)
                    self.assertLessEqual(sum(size for _, size, _ in seen), 66)

    def test_missing_paths_wrong_header_digest_and_execute_mode(self):
        with temp_workspace() as root:
            binary, manifest = pair(root)
            self.reject(root / "absent", manifest)
            self.reject(binary, root / "absent")
            manifest.write_bytes(b"0" * 64 + b"\n")
            self.reject(binary, manifest)
            for data in (b"\x7fELF", image(3), b"not-elf" + b"x" * 80):
                binary, manifest = pair(root, data)
                self.reject(binary, manifest)
            binary, manifest = pair(root)
            binary.chmod(0o600)
            self.reject(binary, manifest)

    def test_directories_sockets_soft_and_hard_links_in_both_roles(self):
        for role in (0, 1):
            for kind in ("directory", "socket", "symlink", "hardlink"):
                with self.subTest(role=role, kind=kind), temp_workspace() as root:
                    paths = list(pair(root))
                    target = paths[role]
                    saved = root / "saved"
                    target.rename(saved)
                    endpoint = None
                    try:
                        if kind == "directory":
                            target.mkdir()
                        elif kind == "socket":
                            endpoint = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
                            endpoint.bind(str(target))
                        elif kind == "symlink":
                            target.symlink_to(saved)
                        else:
                            os.link(saved, target)
                        self.reject(*paths)
                    finally:
                        if endpoint is not None:
                            endpoint.close()

    def _fifo_child(self, binary, manifest, remove_nonblock):
        script = r'''
import os, platform, sys
from pathlib import Path
from unittest.mock import patch
import icode.linux_helper_object as subject
real_open = os.open
def opened(path, flags):
    return real_open(path, flags & ~os.O_NONBLOCK if sys.argv[3] == "strip" else flags)
with patch.object(subject.platform, "machine", return_value="x86_64"), patch.object(subject.os, "open", side_effect=opened):
    try:
        subject.open_linux_helper_object(Path(sys.argv[1]), Path(sys.argv[2]))
    except subject.LinuxHelperObjectError:
        print("rejected", flush=True)
    else:
        raise AssertionError("FIFO accepted")
'''
        environment = dict(os.environ)
        environment["PYTHONPATH"] = str(REPO_ROOT / "src")
        process = subprocess.Popen(
            [sys.executable, "-c", script, str(binary), str(manifest),
             "strip" if remove_nonblock else "keep"],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, env=environment,
        )
        try:
            output, errors = process.communicate(timeout=2)
        except subprocess.TimeoutExpired:
            process.kill()
            process.communicate(timeout=2)
            self.assertIsNotNone(process.returncode)
            raise
        finally:
            if process.poll() is None:
                process.kill()
                process.communicate(timeout=2)
        return process.returncode, output, errors

    def test_real_fifo_without_writer_and_timeout_negative_control(self):
        for role in (0, 1):
            with self.subTest(role=role), temp_workspace() as root:
                paths = list(pair(root))
                paths[role].unlink()
                os.mkfifo(paths[role], 0o600)
                code, output, errors = self._fifo_child(*paths, False)
                self.assertEqual((code, output, errors), (0, "rejected\n", ""))
                with self.assertRaises(subprocess.TimeoutExpired):
                    self._fifo_child(*paths, True)

    def test_size_limit_exact_boundary_and_continuous_growth_are_bounded(self):
        self.assertEqual(subject._BINARY_LIMIT, 64 * 1024 * 1024)
        self.assertEqual(subject._READ_CHUNK, 64 * 1024)
        with temp_workspace() as root:
            binary, manifest = pair(root, image(tail=b"x" * 16))
            with patch.object(subject, "_BINARY_LIMIT", 80), patch.object(subject, "_READ_CHUNK", 7):
                with subject.open_linux_helper_object(binary, manifest) as owner:
                    self.assertGreaterEqual(owner.fileno(), 0)
                binary, manifest = pair(root, image(tail=b"x" * 17))
                self.reject(binary, manifest)
                binary, manifest = pair(root, image(tail=b"x" * 16))
                calls, total = [], []
                def growing(fd, count):
                    calls.append(count)
                    if REAL_FSTAT(fd).st_ino == binary.stat().st_ino:
                        with binary.open("ab") as stream:
                            stream.write(b"z" * 7)
                    result = REAL_READ(fd, count)
                    total.append(len(result))
                    return result
                with patch.object(subject.os, "read", side_effect=growing):
                    self.reject(binary, manifest)
                self.assertLessEqual(len(calls), 30)
                self.assertLessEqual(max(calls), 66)
                self.assertLessEqual(sum(total), 65 + 64 + 81)

    def test_visible_fstat_drift_rejects_even_with_matching_digest(self):
        for field in ("st_dev", "st_ino", "st_size", "st_mtime_ns", "st_ctime_ns"):
            with self.subTest(field=field), temp_workspace() as root:
                binary, manifest = pair(root)
                binary_calls = 0
                inode = binary.stat().st_ino
                def status(fd):
                    nonlocal binary_calls
                    actual = REAL_FSTAT(fd)
                    if actual.st_ino == inode:
                        binary_calls += 1
                        if binary_calls == 2:
                            class Changed:
                                def __getattr__(self, name):
                                    value = getattr(actual, name)
                                    return value + 1 if name == field else value
                            return Changed()
                    return actual
                with patch.object(subject.os, "fstat", side_effect=status):
                    self.reject(binary, manifest)

    def test_pathname_replacement_after_open_does_not_change_held_reads(self):
        with temp_workspace() as root:
            binary, manifest = pair(root)
            expected = binary.read_bytes()
            saved = root / "old"
            # Replacement before binary's initial fstat avoids claiming ctime stability across rename.
            def opened(path, flags):
                fd = REAL_OPEN(path, flags)
                if Path(path) == binary:
                    binary.rename(saved)
                    binary.write_bytes(b"untrusted pathname replacement")
                return fd
            with patch.object(subject.os, "open", side_effect=opened):
                owner = subject.open_linux_helper_object(binary, manifest)
            with owner:
                fd = owner.fileno()
                self.assertEqual(owner.sha256, hashlib.sha256(expected).hexdigest())
                saved.unlink()
                REAL_LSEEK(fd, 0, os.SEEK_SET)
                self.assertEqual(REAL_READ(fd, 4096), expected)
                self.assertEqual(owner.fileno(), fd)
                self.assertEqual(REAL_FSTAT(fd).st_nlink, 0)

    def test_two_owners_are_independent(self):
        with temp_workspace() as root:
            binary, manifest = pair(root)
            first = subject.open_linux_helper_object(binary, manifest)
            second = subject.open_linux_helper_object(binary, manifest)
            try:
                a, b = first.fileno(), second.fileno()
                self.assertNotEqual(a, b)
                first.close()
                self.assert_closed(a)
                self.assertEqual(second.fileno(), b)
            finally:
                first.close()
                second.close()

    def test_copy_deepcopy_pickle_do_not_transfer_close_responsibility(self):
        with temp_workspace() as root:
            binary, manifest = pair(root)
            with subject.open_linux_helper_object(binary, manifest) as owner:
                fd = owner.fileno()
                for operation in (copy.copy, copy.deepcopy, pickle.dumps):
                    with self.subTest(operation=operation.__name__):
                        with self.assertRaises(subject.LinuxHelperObjectError) as caught:
                            operation(owner)
                        self.assertEqual(str(caught.exception), ERROR)
                        self.assertEqual(owner.fileno(), fd)

    def test_external_different_object_reuse_is_not_closed(self):
        with temp_workspace() as root:
            binary, manifest = pair(root)
            owner = subject.open_linux_helper_object(binary, manifest)
            fd = owner.fileno()
            other = root / "other"
            other.write_bytes(b"unrelated")
            replacement = REAL_OPEN(other, os.O_RDONLY)
            try:
                os.dup2(replacement, fd)
                with self.assertRaises(subject.LinuxHelperObjectError):
                    owner.fileno()
                with patch.object(subject.os, "close") as closed:
                    with self.assertRaises(subject.LinuxHelperObjectError):
                        owner.close()
                    with self.assertRaises(subject.LinuxHelperObjectError):
                        owner.close()
                    closed.assert_not_called()
                self.assertEqual(REAL_READ(fd, 64), b"unrelated")
            finally:
                REAL_CLOSE(fd)
                REAL_CLOSE(replacement)

    def test_close_failure_unknown_never_retries_even_if_fd_still_open(self):
        for error in (OSError("private-close"), KeyboardInterrupt("close"), SystemExit(19)):
            with self.subTest(error=type(error).__name__), temp_workspace() as root:
                binary, manifest = pair(root)
                owner = subject.open_linux_helper_object(binary, manifest)
                fd = owner.fileno()
                try:
                    with patch.object(subject.os, "close", side_effect=error) as closed:
                        with self.assertRaises(type(error) if not isinstance(error, Exception)
                                               else subject.LinuxHelperObjectError) as caught:
                            owner.close()
                        if not isinstance(error, Exception):
                            self.assertIs(caught.exception, error)
                        else:
                            self.assertEqual(str(caught.exception), ERROR)
                        with self.assertRaises(subject.LinuxHelperObjectError):
                            owner.close()
                        closed.assert_called_once_with(fd)
                    self.assertEqual(REAL_FSTAT(fd).st_ino, binary.stat().st_ino)
                    with self.assertRaises(subject.LinuxHelperObjectError):
                        owner.fileno()
                finally:
                    REAL_CLOSE(fd)

    def test_close_fstat_failure_does_not_guess_or_retry(self):
        with temp_workspace() as root:
            binary, manifest = pair(root)
            owner = subject.open_linux_helper_object(binary, manifest)
            fd = owner.fileno()
            try:
                with patch.object(subject.os, "fstat", side_effect=OSError("private")), patch.object(
                    subject.os, "close"
                ) as closed:
                    with self.assertRaises(subject.LinuxHelperObjectError):
                        owner.close()
                    with self.assertRaises(subject.LinuxHelperObjectError):
                        owner.close()
                    closed.assert_not_called()
                self.assertGreaterEqual(REAL_FSTAT(fd).st_ino, 0)
            finally:
                REAL_CLOSE(fd)

    def test_confirmed_close_and_enter_are_closed_under_context_errors(self):
        for error in (ValueError("body"), KeyboardInterrupt("body"), SystemExit(20)):
            with self.subTest(error=type(error).__name__), temp_workspace() as root:
                binary, manifest = pair(root)
                owner = subject.open_linux_helper_object(binary, manifest)
                fd = owner.fileno()
                with self.assertRaises(type(error)) as caught:
                    with owner:
                        raise error
                self.assertIs(caught.exception, error)
                self.assert_closed(fd)
                with patch.object(subject.os, "close") as closed:
                    owner.close()
                    owner.close()
                    closed.assert_not_called()
                with self.assertRaises(subject.LinuxHelperObjectError):
                    owner.__enter__()

    def test_context_cleanup_interrupt_priority(self):
        for body, cleanup in ((ValueError("body"), OSError("cleanup")),
                              (KeyboardInterrupt("body"), OSError("cleanup")),
                              (SystemExit(21), KeyboardInterrupt("cleanup")),
                              (ValueError("body"), KeyboardInterrupt("cleanup")),
                              (ValueError("body"), SystemExit(22))):
            with self.subTest(body=type(body).__name__, cleanup=type(cleanup).__name__), temp_workspace() as root:
                binary, manifest = pair(root)
                owner = subject.open_linux_helper_object(binary, manifest)
                fd = owner.fileno()
                def closing(descriptor):
                    REAL_CLOSE(descriptor)
                    raise cleanup
                selected = (body if not isinstance(body, Exception)
                            or isinstance(cleanup, Exception) else cleanup)
                with patch.object(subject.os, "close", side_effect=closing):
                    with self.assertRaises(type(selected)) as caught:
                        with owner:
                            raise body
                self.assertIs(caught.exception, selected)
                self.assert_closed(fd)
                with self.assertRaises(subject.LinuxHelperObjectError):
                    owner.close()

    def _factory_trace(self, binary, manifest, inject=None):
        originals = {"open": REAL_OPEN, "fstat": REAL_FSTAT, "read": REAL_READ,
                     "lseek": REAL_LSEEK, "close": REAL_CLOSE}
        events, owned, closes = [], [], []
        from contextlib import ExitStack
        def wrap(name):
            def operation(*args):
                event = (name, sum(old[0] == name for old in events) + 1)
                events.append(event)
                if name == "close":
                    closes.append(args[0])
                if inject is not None and event == inject[0]:
                    if name == "close":
                        originals[name](*args)
                    raise inject[1]
                answer = originals[name](*args)
                if name == "open":
                    owned.append(answer)
                return answer
            return operation
        with ExitStack() as stack:
            for name in originals:
                stack.enter_context(patch.object(subject.os, name, side_effect=wrap(name)))
            try:
                owner = subject.open_linux_helper_object(binary, manifest)
            except BaseException as error:
                return events, owned, closes, error
        owner.close()
        return events, owned, closes, None

    def test_every_factory_os_stage_fault_and_signal_cleans_actual_fds(self):
        with temp_workspace() as root:
            binary, manifest = pair(root)
            healthy, descriptors, _, error = self._factory_trace(binary, manifest)
            self.assertIsNone(error)
            self.assertEqual(set(name for name, _ in healthy), {"open", "fstat", "read", "lseek", "close"})
            for descriptor in descriptors:
                self.assert_closed(descriptor)
            for event in healthy:
                for fault in (OSError("private-os-stage"), KeyboardInterrupt("stage"), SystemExit(23)):
                    with self.subTest(event=event, fault=type(fault).__name__):
                        _, descriptors, closes, error = self._factory_trace(binary, manifest, (event, fault))
                        if isinstance(fault, Exception):
                            self.assertIsInstance(error, subject.LinuxHelperObjectError)
                            self.assertEqual(str(error), ERROR)
                            self.assertIsNone(error.__cause__)
                            self.assertTrue(error.__suppress_context__)
                        else:
                            self.assertIs(error, fault)
                        self.assertEqual(len(closes), len(set(closes)))
                        for descriptor in descriptors:
                            self.assert_closed(descriptor)

    def test_factory_cleanup_priority_and_all_resources_attempted(self):
        for primary, cleanup in ((OSError("read-private"), KeyboardInterrupt("cleanup")),
                                 (OSError("read-private"), SystemExit(24)),
                                 (KeyboardInterrupt("read"), OSError("close-private")),
                                 (SystemExit(25), KeyboardInterrupt("cleanup"))):
            with self.subTest(primary=type(primary).__name__, cleanup=type(cleanup).__name__), temp_workspace() as root:
                binary, manifest = pair(root)
                acquired, closed = [], []
                def opened(path, flags):
                    fd = REAL_OPEN(path, flags)
                    acquired.append(fd)
                    return fd
                def closing(fd):
                    closed.append(fd)
                    REAL_CLOSE(fd)
                    raise cleanup
                selected = primary if not isinstance(primary, Exception) else cleanup
                with patch.object(subject.os, "open", side_effect=opened), patch.object(
                    subject.os, "read", side_effect=primary
                ), patch.object(subject.os, "close", side_effect=closing):
                    with self.assertRaises(type(selected)) as caught:
                        subject.open_linux_helper_object(binary, manifest)
                self.assertIs(caught.exception, selected)
                self.assertEqual(set(closed), set(acquired))
                self.assertEqual(len(closed), len(acquired))
                for fd in acquired:
                    self.assert_closed(fd)


if __name__ == "__main__":
    unittest.main()
