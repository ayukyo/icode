"""Native helper quota wiring only: real scope/namespace, no readiness credit."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
import uuid
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
UNIT_FLAG = "--task-quota-unit"
LIMIT_FLAG = "--task-quota-limit"


class TestLinuxHelperQuotaDistribution(unittest.TestCase):
    def test_source_distribution_contains_quota_header(self) -> None:
        self.assertIn("include native/linux/icode_task_quota.h",
                      (ROOT / "MANIFEST.in").read_text(encoding="utf-8"))


@unittest.skipUnless(sys.platform.startswith("linux") and shutil.which("cc"),
                     "requires Linux/C compiler; conformance_credit=none")
class TestLinuxHelperTaskQuota(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._temporary = tempfile.TemporaryDirectory(prefix="icode-helper-quota-")
        cls.addClassCleanup(cls._temporary.cleanup)
        cls._root = Path(cls._temporary.name)
        source = ROOT / "native/linux/icode_landlock.c"
        driver = cls._root / "driver.c"
        # Same process as the helper: no extra process in the exclusive root.
        driver.write_text(
            '#define _GNU_SOURCE\n#define main icode_original_main\n'
            f'#include "{source}"\n#undef main\n'
            r'''
static int scope_prerequisite(void) {
    FILE *stream = fopen("/proc/self/cgroup", "re");
    if (!stream) return 0;
    char line[4096], path[4096];
    int found = 0;
    while (fgets(line, sizeof(line), stream)) {
        if (!strncmp(line, "0::/", 4)) {
            line[strcspn(line, "\n")] = '\0';
            if (snprintf(path, sizeof(path), "/sys/fs/cgroup%s", line + 3) >= (int)sizeof(path)) {
                fclose(stream); return 0;
            }
            found++;
        }
    }
    fclose(stream);
    if (found != 1) return 0;
    int root = open(path, O_RDONLY | O_DIRECTORY | O_CLOEXEC | O_NOFOLLOW);
    struct stat status;
    if (root < 0) return 0;
    char controllers[512];
    int file = openat(root, "cgroup.controllers", O_RDONLY | O_CLOEXEC | O_NOFOLLOW);
    ssize_t size = file >= 0 ? read(file, controllers, sizeof(controllers) - 1) : -1;
    if (file >= 0) close(file);
    int available = !fstat(root, &status) && status.st_uid == geteuid() &&
        !faccessat(root, "cgroup.procs", W_OK, 0) &&
        !faccessat(root, "cgroup.subtree_control", W_OK, 0) && size >= 0;
    close(root);
    if (!available) return 0;
    controllers[size] = '\0';
    if (!strstr(controllers, "pids")) return 0;
#ifdef SYS_clone3
    errno = 0;
    (void)syscall(SYS_clone3, NULL, 0);
    return errno != ENOSYS && errno != EPERM;
#else
    return 0;
#endif
}
static int deny_test_syscall(int number) {
    struct sock_filter filter[] = {
        BPF_STMT(BPF_LD | BPF_W | BPF_ABS, offsetof(struct seccomp_data, nr)),
        BPF_JUMP(BPF_JMP | BPF_JEQ | BPF_K, (unsigned int)number, 0, 1),
        BPF_STMT(BPF_RET | BPF_K, SECCOMP_RET_ERRNO | EPERM),
        BPF_STMT(BPF_RET | BPF_K, SECCOMP_RET_ALLOW),
    };
    struct sock_fprog program = {.len = 4, .filter = filter};
    return prctl(PR_SET_NO_NEW_PRIVS, 1, 0, 0, 0) ||
           prctl(PR_SET_SECCOMP, SECCOMP_MODE_FILTER, &program);
}
int main(int argc, char **argv) {
    alarm(10);
    if (argc == 2 && !strcmp(argv[1], "--namespace-prerequisite")) {
        if (syscall(SYS_unshare, CLONE_NEWUSER | CLONE_NEWPID)) {
            if (errno == EPERM || errno == EACCES || errno == ENOSYS) return 77;
            return 1;
        }
        int abi = (int)syscall(SYS_landlock_create_ruleset, NULL, 0,
                              LANDLOCK_CREATE_RULESET_VERSION);
        return abi >= 3 ? 0 : 77;
    }
    if (getenv("ICODE_TEST_SCOPE") && !scope_prerequisite()) return 77;
    if (getenv("ICODE_TEST_DENY_UNSHARE") && deny_test_syscall(SYS_unshare)) return 1;
#ifdef SYS_clone3
    if (getenv("ICODE_TEST_DENY_CLONE3") && deny_test_syscall(SYS_clone3)) return 1;
#endif
    char parent[64];
    snprintf(parent, sizeof(parent), "%ld", (long)getppid());
    if (argc >= 5) argv[4] = parent;
    const char *uid = getenv("ICODE_TEST_UID_MAP_PATH");
    return run_helper(argc, argv, "/proc/self/setgroups",
                      uid ? uid : "/proc/self/uid_map");
}
''',
            encoding="ascii",
        )
        cls._driver = cls._root / "driver"
        result = subprocess.run(
            [shutil.which("cc") or "cc", "-std=c11", "-O2", "-Wall", "-Wextra",
             "-Werror", str(driver), "-o", str(cls._driver)],
            capture_output=True, text=True, timeout=15, check=False,
        )
        if result.returncode:
            raise AssertionError(f"native quota driver compile failed: {result.stderr[-1200:]}")

    def _namespace_available(self) -> None:
        result = subprocess.run([str(self._driver), "--namespace-prerequisite"],
                                capture_output=True, timeout=15, check=False)
        if result.returncode == 77:
            self.skipTest("user/PID namespace or Landlock unavailable; conformance_credit=none")
        self.assertEqual(result.returncode, 0)

    def _user_manager(self) -> tuple[dict[str, str], Path]:
        uid = os.getuid()
        bus = Path(f"/run/user/{uid}/bus")
        if uid == 0 or not bus.is_socket():
            self.skipTest("nonroot user bus unavailable; conformance_credit=none")
        if not all(Path(path).is_file() for path in ("/usr/bin/systemd-run", "/usr/bin/systemctl")):
            self.skipTest("user manager tools unavailable; conformance_credit=none")
        environment = {"PATH": "/usr/bin:/bin", "LANG": "C", "LC_ALL": "C",
                       "XDG_RUNTIME_DIR": f"/run/user/{uid}",
                       "DBUS_SESSION_BUS_ADDRESS": f"unix:path={bus}"}
        result = subprocess.run(
            ["/usr/bin/systemctl", "--user", "show", "app.slice",
             "--property=ControlGroup", "--value"],
            capture_output=True, text=True, timeout=10, check=False, env=environment,
        )
        if result.returncode or not result.stdout.strip():
            self.skipTest("active user manager app.slice unavailable; conformance_credit=none")
        path = result.stdout.strip()
        self.assertTrue(path.startswith("/") and ".." not in Path(path).parts)
        return environment, Path("/sys/fs/cgroup") / path.lstrip("/")

    def _command(self, workspace: Path, options: list[str], code: str) -> list[str]:
        return [str(self._driver), "--workspace", str(workspace), "--parent-pid", "PARENT",
                *options, "--", "/usr/bin/python3", "-I", "-c", code]

    def _assert_collected(self, unit: str, scope: Path, environment: dict[str, str]) -> None:
        deadline = time.monotonic() + 3
        while time.monotonic() < deadline:
            result = subprocess.run(
                ["/usr/bin/systemctl", "--user", "show", unit,
                 "--property=LoadState", "--property=ActiveState"],
                capture_output=True, text=True, timeout=10, check=False, env=environment,
            )
            fields = dict(line.split("=", 1) for line in result.stdout.splitlines() if "=" in line)
            if fields.get("LoadState") == "not-found" and not scope.exists():
                return
            time.sleep(0.02)
        self.fail("own transient scope/unit not collected; conformance_credit=none")

    def _scope(self, workspace: Path, options: list[str], code: str,
               *, extra_environment: dict[str, str] | None = None) -> tuple[subprocess.Popen[str], str, Path, dict[str, str]]:
        environment, parent = self._user_manager()
        unit = f"icode-task-{uuid.uuid4().hex}.scope"
        options = [unit if value == "UNIT" else value for value in options]
        environment["ICODE_TEST_SCOPE"] = "1"
        environment.update(extra_environment or {})
        command = ["/usr/bin/systemd-run", "--user", "--scope", "--quiet", "--collect",
                   "--description=ICODE native quota test", f"--unit={unit}",
                   "--property=Delegate=pids", *self._command(workspace, options, code)]
        process = subprocess.Popen(command, env=environment, stdout=subprocess.PIPE,
                                   stderr=subprocess.PIPE, text=True)
        return process, unit, parent / unit, environment

    def _complete(self, process: subprocess.Popen[str], unit: str, scope: Path,
                  environment: dict[str, str], *, expected: int) -> tuple[str, str]:
        stdout, stderr = process.communicate(timeout=15)
        self._assert_collected(unit, scope, environment)
        if process.returncode == 77:
            self.skipTest("delegated cgroup2/clone3 unavailable; conformance_credit=none")
        self.assertEqual(process.returncode, expected, stderr)
        return stdout, stderr

    @staticmethod
    def _payload_prefix() -> str:
        return (
            "import ctypes, errno, fcntl, os, signal, time\nfrom pathlib import Path\n"
            "signal.alarm(8)\n"
            "assert os.getpid() == 2 and os.getppid() == 1\n"
            "for fd in range(3, 256):\n"
            "    try: fcntl.fcntl(fd, fcntl.F_GETFD)\n"
            "    except OSError as error: assert error.errno == errno.EBADF\n"
            "    else: raise AssertionError('management descriptor leaked')\n"
            "try: os.open('/sys/fs/cgroup', os.O_RDONLY | os.O_DIRECTORY)\n"
            "except PermissionError: pass\n"
            "else: raise AssertionError('sys granted')\n"
        )

    def _run_payload(self, mode: str, limit: int, *, mapless: bool = False,
                     exit_code: int = 0) -> str:
        self._namespace_available()
        with tempfile.TemporaryDirectory(prefix="icode-quota-payload-") as temporary:
            root = Path(temporary)
            workspace = root / "code"
            workspace.mkdir()
            environment = {}
            if mapless:
                denied = root / "uid-map-denied"
                denied.write_text("unmapped", encoding="ascii")
                denied.chmod(0o444)
                environment["ICODE_TEST_UID_MAP_PATH"] = str(denied)
            code = self._payload_prefix()
            if mapless:
                code += "assert os.getuid() == 65534 and os.getgid() == 65534\n"
            else:
                code += "assert os.getuid() in (0, 65534)\n"
            if mode == "cap2":
                code += (
                    "child = os.fork()\n"
                    "if child == 0:\n"
                    "    os.setsid()\n"
                    "    try: extra = os.fork()\n"
                    "    except OSError as error: assert error.errno == errno.EAGAIN\n"
                    "    else:\n"
                    "        if extra == 0: Path('forbidden-marker').write_text('bad'); os._exit(3)\n"
                    "        os.waitpid(extra, 0); raise AssertionError('third task allowed')\n"
                    "    Path('descendant-marker').write_text('detached')\n"
                    "    while not Path('release').exists(): time.sleep(0.01)\n"
                    "    os._exit(0)\n"
                    "while not Path('descendant-marker').exists(): time.sleep(0.01)\n"
                )
            elif mode == "fork1":
                code += (
                    "try: child = os.fork()\n"
                    "except OSError as error: assert error.errno == errno.EAGAIN\n"
                    "else:\n"
                    "    if child == 0: Path('forbidden-marker').write_text('bad'); os._exit(3)\n"
                    "    os.waitpid(child, 0); raise AssertionError('quota fork allowed')\n"
                )
            elif mode == "thread1":
                code += (
                    "libc = ctypes.CDLL(None, use_errno=True)\n"
                    "callback_type = ctypes.CFUNCTYPE(ctypes.c_void_p, ctypes.c_void_p)\n"
                    "def forbidden_thread(argument):\n"
                    "    Path('forbidden-marker').write_text('bad'); return None\n"
                    "callback = callback_type(forbidden_thread)\n"
                    "thread = ctypes.c_ulong()\n"
                    "assert libc.pthread_create(ctypes.byref(thread), None, callback, None) == errno.EAGAIN\n"
                )
            code += (
                "Path('ready').write_text('ready')\n"
                "while not Path('release').exists(): time.sleep(0.01)\n"
            )
            if mode == "cap2":
                code += "assert os.waitpid(child, 0)[1] == 0\n"
            code += f"print('probe:payload_uid=' + str(os.getuid()))\nprint('probe:conformance_credit=none')\nraise SystemExit({exit_code})\n"
            process, unit, scope, manager_environment = self._scope(
                workspace, [UNIT_FLAG, "UNIT", LIMIT_FLAG, str(limit)], code,
                extra_environment=environment,
            )
            try:
                deadline = time.monotonic() + 3
                while not (workspace / "ready").exists() and process.poll() is None and time.monotonic() < deadline:
                    time.sleep(0.01)
                if not (workspace / "ready").exists():
                    stdout, stderr = self._complete(process, unit, scope, manager_environment, expected=exit_code)
                    self.fail(f"quota payload did not run: {stdout!r} {stderr!r}")
                self.assertEqual((scope / "payload/pids.max").read_text().strip(), str(limit))
                self.assertEqual((scope / "payload/pids.current").read_text().strip(), str(limit))
                payload_members = set((scope / "payload/cgroup.procs").read_text().split())
                supervisor_members = set((scope / "supervisor/cgroup.procs").read_text().split())
                self.assertEqual(len(payload_members), limit)
                self.assertEqual(len(supervisor_members), 2)
                self.assertTrue(payload_members.isdisjoint(supervisor_members))
                events = dict(line.split() for line in (scope / "payload/pids.events").read_text().splitlines())
                if mode != "normal":
                    self.assertGreater(int(events["max"]), 0)
                self.assertFalse((workspace / "forbidden-marker").exists())
                (workspace / "release").write_text("go", encoding="ascii")
                stdout, stderr = self._complete(process, unit, scope, manager_environment, expected=exit_code)
                if exit_code == 0:
                    self.assertEqual(stderr, "")
                return stdout
            finally:
                if process.poll() is None:
                    (workspace / "release").write_text("go", encoding="ascii")
                    process.communicate(timeout=15)

    def test_cap_two_root_and_detached_descendant_inherit_exact_quota(self) -> None:
        self.assertIn("probe:conformance_credit=none", self._run_payload("cap2", 2))

    def test_cap_one_fork_denial_has_no_marker_and_kernel_event(self) -> None:
        self.assertIn("probe:conformance_credit=none", self._run_payload("fork1", 1))

    def test_cap_one_thread_denial_has_no_marker_and_kernel_event(self) -> None:
        self.assertIn("probe:conformance_credit=none", self._run_payload("thread1", 1))

    def test_mapless_namespace_quota_keeps_fd_and_sys_boundaries(self) -> None:
        self.assertIn("probe:payload_uid=65534", self._run_payload("cap2", 2, mapless=True))

    def test_mapless_cap_one_fork_denial_has_no_marker_and_kernel_event(self) -> None:
        self.assertIn("probe:payload_uid=65534", self._run_payload("fork1", 1, mapless=True))

    def test_mapless_cap_one_thread_denial_has_no_marker_and_kernel_event(self) -> None:
        self.assertIn("probe:payload_uid=65534", self._run_payload("thread1", 1, mapless=True))

    def test_nonzero_exit_is_preserved_and_failed_scope_collected(self) -> None:
        self.assertIn("probe:conformance_credit=none", self._run_payload("normal", 1, exit_code=13))

    def test_no_scope_rejects_before_payload(self) -> None:
        with tempfile.TemporaryDirectory(prefix="icode-quota-no-scope-") as temporary:
            workspace = Path(temporary)
            marker = workspace / "must-not-run"
            unit = f"icode-task-{uuid.uuid4().hex}.scope"
            result = subprocess.run(
                self._command(workspace, [UNIT_FLAG, unit, LIMIT_FLAG, "1"],
                              "from pathlib import Path; Path('must-not-run').write_text('bad')"),
                capture_output=True, text=True, timeout=15, check=False,
            )
            self.assertEqual(result.returncode, 1, result.stderr)
            self.assertFalse(marker.exists())
            self.assertEqual(result.stderr, "task quota setup failed\n")

    def test_invalid_or_unpaired_quota_flags_reject_before_payload(self) -> None:
        unit = f"icode-task-{uuid.uuid4().hex}.scope"
        cases = [[UNIT_FLAG, unit], [LIMIT_FLAG, "1"],
                 [UNIT_FLAG, unit, UNIT_FLAG, unit, LIMIT_FLAG, "1"],
                 [UNIT_FLAG, unit, LIMIT_FLAG, "1", LIMIT_FLAG, "1"],
                 [UNIT_FLAG, "app.scope", LIMIT_FLAG, "1"]]
        cases += [[UNIT_FLAG, unit, LIMIT_FLAG, value]
                  for value in ("0", "-1", "+1", "1.0", " 1", "2147483648", "18446744073709551616")]
        with tempfile.TemporaryDirectory(prefix="icode-quota-flags-") as temporary:
            workspace = Path(temporary)
            for options in cases:
                with self.subTest(options=options):
                    result = subprocess.run(
                        self._command(workspace, options,
                                      "from pathlib import Path; Path('must-not-run').write_text('bad')"),
                        capture_output=True, text=True, timeout=15, check=False,
                    )
                    self.assertEqual(result.returncode, 2)
                    self.assertEqual(result.stderr, "invalid task quota options\n")
                    self.assertFalse((workspace / "must-not-run").exists())

    def _setup_failure(self, extra_environment: dict[str, str], *, limit: str = "1") -> None:
        self._namespace_available()
        with tempfile.TemporaryDirectory(prefix="icode-quota-setup-") as temporary:
            workspace = Path(temporary)
            if extra_environment.get("ICODE_TEST_UID_MAP_PATH") == "MISSING":
                extra_environment = {"ICODE_TEST_UID_MAP_PATH": str(workspace / "absent-uid-map")}
            process, unit, scope, environment = self._scope(
                workspace, [UNIT_FLAG, "UNIT", LIMIT_FLAG, limit],
                "from pathlib import Path; Path('must-not-run').write_text('bad')",
                extra_environment=extra_environment,
            )
            stdout, stderr = self._complete(process, unit, scope, environment, expected=1)
            self.assertEqual(stdout, "")
            self.assertNotIn("task quota cleanup failed", stderr)
            self.assertFalse((workspace / "must-not-run").exists())

    def test_namespace_failure_reclaims_empty_quota_without_fallback(self) -> None:
        self._setup_failure({"ICODE_TEST_DENY_UNSHARE": "1"})

    def test_namespace_mapping_error_reclaims_empty_quota(self) -> None:
        self._setup_failure({"ICODE_TEST_UID_MAP_PATH": "MISSING"})

    def test_clone3_failure_reclaims_empty_quota_without_plain_fork(self) -> None:
        self._setup_failure({"ICODE_TEST_DENY_CLONE3": "1"})

    def test_kernel_rejected_large_limit_never_starts_payload(self) -> None:
        self._setup_failure({}, limit=str(2**31 - 1))


if __name__ == "__main__":
    unittest.main()
