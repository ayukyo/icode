"""Private resource transcript tests; no product/conformance credit."""
from __future__ import annotations

import array
import importlib.util
import os
from pathlib import Path
import socket
import shutil
import struct
import subprocess
import sys
import tempfile
import time
import unittest
from unittest import mock
import uuid

ROOT = Path(__file__).resolve().parents[1]
UNIT = "icode-task-0123456789abcdef0123456789abcdef.scope"
NONCE = bytes.fromhex(UNIT[11:43])


def frame(phase: int, *, nonce: bytes = NONCE, limit: int = 2) -> bytes:
    return b"ICQR1" + bytes([phase]) + nonce + struct.pack("!I", limit)


class TestTaskResourceInterface(unittest.TestCase):
    def test_private_receiver_component_exists(self) -> None:
        self.assertTrue((ROOT / "src/icode/linux_task_resource.py").is_file(),
                        "private receiver is not implemented")

    @unittest.skipUnless(sys.platform.startswith("linux"), "Linux-only channel; conformance_credit=none")
    def test_channel_creation_does_not_swallow_caller_interrupt(self) -> None:
        from icode.linux_task_resource import create_task_resource_channel
        with mock.patch("icode.linux_task_resource.socket.socketpair", side_effect=KeyboardInterrupt):
            try:
                create_task_resource_channel()
            except BaseException as error:
                self.assertIsInstance(error, KeyboardInterrupt)
            else:
                self.fail("caller interrupt was swallowed")


@unittest.skipUnless(sys.platform.startswith("linux") and importlib.util.find_spec("icode.linux_task_resource"),
                     "Linux-only resource channel; conformance_credit=none")
class TestTaskResourceTranscript(unittest.TestCase):
    def setUp(self) -> None:
        from icode.linux_task_resource import (
            LinuxTaskResourceReceiver, create_task_resource_channel,
        )
        self.host, self.sender = create_task_resource_channel()
        self.addCleanup(self.host.close)
        self.addCleanup(self.sender.close)
        self.receiver = LinuxTaskResourceReceiver(self.host, unit=UNIT, limit=2)
        self.receiver.bind(expected_pid=os.getpid(), expected_uid=os.getuid(),
                           expected_gid=os.getgid())
        self.addCleanup(self.receiver.close)

    def start(self) -> None:
        self.receiver.start(deadline_monotonic=time.monotonic() + 1)

    def configured(self) -> None:
        self.sender.send(frame(1))
        self.sender.settimeout(1)
        self.assertEqual(self.sender.recv(64), b"ICQA1" + NONCE + struct.pack("!I", 2))

    def complete(self, terminal: int) -> dict[str, object]:
        self.sender.send(frame(terminal))
        self.sender.close()
        self.assertTrue(self.receiver.wait(timeout_seconds=2))
        return self.receiver.receipt()

    def test_configured_finished_never_means_successful_exec(self) -> None:
        self.start()
        self.configured()
        receipt = self.complete(3)
        self.assertTrue(receipt["configured"])
        self.assertEqual(receipt["terminal"], "finished")
        self.assertIsNone(receipt["payload_started"])
        self.assertEqual(receipt["channel_status"], "complete")

    def test_initial_explicit_failure_proves_not_started_only(self) -> None:
        self.start()
        receipt = self.complete(2)
        self.assertFalse(receipt["configured"])
        self.assertIs(receipt["payload_started"], False)
        self.assertEqual(receipt["terminal"], "preexec_failed")
        self.assertNotIn("scope_cleanup_ok", receipt)

    def test_cleanup_failure_has_unknown_start(self) -> None:
        self.start()
        self.configured()
        receipt = self.complete(4)
        self.assertIsNone(receipt["payload_started"])
        self.assertEqual(receipt["terminal"], "cleanup_failed")

    def test_configured_explicit_failure_is_false(self) -> None:
        self.start()
        self.configured()
        self.assertIs(self.complete(2)["payload_started"], False)

    def test_initial_cleanup_failure_keeps_unknown(self) -> None:
        self.start()
        receipt = self.complete(4)
        self.assertFalse(receipt["configured"])
        self.assertIsNone(receipt["payload_started"])

    def test_eof_without_terminal_keeps_unknown(self) -> None:
        self.start()
        self.configured()
        self.sender.close()
        self.assertTrue(self.receiver.wait(timeout_seconds=2))
        self.assertEqual(self.receiver.receipt()["channel_status"], "incomplete")
        self.assertIsNone(self.receiver.receipt()["payload_started"])

    def test_protocol_matrix_rejects_wrong_order_and_extra_frames(self) -> None:
        sequences = [(3,), (1, 1), (2, 1), (1, 2, 3), (1, 3, 2), (5,)]
        for sequence in sequences:
            with self.subTest(sequence=sequence):
                self.tearDown_pair()
                self.setUp()
                self.start()
                for phase in sequence:
                    try:
                        if phase == 1:
                            self.sender.send(frame(phase))
                            self.sender.settimeout(0.2)
                            self.sender.recv(64)
                        else:
                            self.sender.send(frame(phase))
                    except (OSError, TimeoutError):
                        break
                self.sender.close()
                self.assertTrue(self.receiver.wait(timeout_seconds=2))
                self.assertEqual(self.receiver.receipt()["channel_status"], "incomplete")
                self.assertIsNone(self.receiver.receipt()["payload_started"])

    def tearDown_pair(self) -> None:
        self.receiver.close()
        self.host.close()
        self.sender.close()

    def test_malformed_nonce_cap_length_and_truncation_reject(self) -> None:
        messages = [frame(1, nonce=b"x" * 16), frame(1, limit=1), frame(1)[:-1],
                    frame(1) + b"x", b"x" * 65536]
        for message in messages:
            with self.subTest(length=len(message)):
                self.tearDown_pair()
                self.setUp()
                self.start()
                self.sender.send(message)
                self.sender.close()
                self.assertTrue(self.receiver.wait(timeout_seconds=2))
                self.assertEqual(self.receiver.receipt()["channel_status"], "incomplete")

    def test_unexpected_credentials_reject(self) -> None:
        self.receiver.close()
        from icode.linux_task_resource import LinuxTaskResourceReceiver
        self.receiver = LinuxTaskResourceReceiver(self.host, unit=UNIT, limit=2)
        for pid, uid, gid in ((os.getpid() + 1000000, os.getuid(), os.getgid()),
                              (os.getpid(), os.getuid() + 1, os.getgid()),
                              (os.getpid(), os.getuid(), os.getgid() + 1)):
            with self.subTest(pid=pid, uid=uid, gid=gid):
                self.tearDown_pair()
                self.setUp()
                self.receiver.close()
                self.receiver = LinuxTaskResourceReceiver(self.host, unit=UNIT, limit=2)
                self.receiver.bind(expected_pid=pid, expected_uid=uid, expected_gid=gid)
                self.start()
                self.sender.send(frame(1))
                self.sender.close()
                self.assertTrue(self.receiver.wait(timeout_seconds=2))
                self.assertEqual(self.receiver.receipt()["channel_status"], "incomplete")

    def test_received_rights_are_rejected_and_closed(self) -> None:
        for count in (1, 7, 24, 40, 253):
            with self.subTest(count=count):
                self.tearDown_pair()
                self.setUp()
                before = set(os.listdir("/proc/self/fd"))
                self.start()
                descriptors = array.array("i", [self.sender.fileno()] * count)
                self.sender.sendmsg([frame(1)], [(socket.SOL_SOCKET, socket.SCM_RIGHTS, descriptors)])
                self.assertTrue(self.receiver.wait(timeout_seconds=2))
                self.assertEqual(self.receiver.receipt()["channel_status"], "incomplete")
                self.assertEqual(set(os.listdir("/proc/self/fd")), before)

    def test_closed_receiver_cannot_start_again(self) -> None:
        from icode.linux_task_resource import LinuxTaskResourceError
        self.receiver.close()
        with self.assertRaises(LinuxTaskResourceError):
            self.start()

    def test_worker_creation_failure_terminates_bound_child(self) -> None:
        # OS thread creation failure cannot be safely induced by exhausting the
        # host. Only that failure boundary is injected; termination is observed.
        from icode.linux_task_resource import LinuxTaskResourceReceiver
        self.receiver.close()
        self.receiver = LinuxTaskResourceReceiver(self.host, unit=UNIT, limit=2)
        child = subprocess.Popen([sys.executable, "-I", "-c", "import time; time.sleep(10)"],
                                 stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                                 stderr=subprocess.DEVNULL, env={"PATH": "/usr/bin:/bin"})
        try:
            self.receiver.bind_process(child, expected_uid=os.getuid(), expected_gid=os.getgid())
            with mock.patch("icode.linux_task_resource.threading.Thread.start", side_effect=RuntimeError):
                try:
                    self.start()
                except RuntimeError:
                    pass
            self.assertEqual(child.wait(timeout=3), -9)
        finally:
            if child.poll() is None:
                child.kill()
            child.wait(timeout=3)

    def test_receiver_on_nonlinux_is_fixed_unsupported(self) -> None:
        from icode.linux_task_resource import LinuxTaskResourceError, LinuxTaskResourceReceiver
        with mock.patch("icode.linux_task_resource.sys.platform", "darwin"):
            with self.assertRaises(LinuxTaskResourceError):
                LinuxTaskResourceReceiver(self.host, unit=UNIT, limit=2)

    def test_ancillary_parse_exception_closes_already_delivered_rights(self) -> None:
        # Only the parser failure is injected; delivery and FD ownership are
        # real recvmsg/SCM_RIGHTS, including rights after the credential cmsg.
        before = set(os.listdir("/proc/self/fd"))
        parser = mock.Mock(size=12, unpack=mock.Mock(side_effect=RuntimeError))
        try:
            with mock.patch("icode.linux_task_resource._CREDENTIALS", parser):
                self.start()
                self.sender.sendmsg([frame(1)], [(socket.SOL_SOCKET, socket.SCM_RIGHTS,
                                                 array.array("i", [self.sender.fileno()]))])
                self.assertTrue(self.receiver.wait(timeout_seconds=2))
            after = set(os.listdir("/proc/self/fd"))
            self.assertEqual(after, before)
        finally:
            # If RED strands a delivered duplicate, this test owns that exact
            # new socket descriptor and closes it; no host-wide FD cleanup.
            own_socket = os.readlink(f"/proc/self/fd/{self.sender.fileno()}")
            for descriptor in set(os.listdir("/proc/self/fd")) - before:
                try:
                    if os.readlink(f"/proc/self/fd/{descriptor}") == own_socket:
                        os.close(int(descriptor))
                except OSError:
                    pass

    def test_empty_packet_cannot_complete_and_hide_a_later_bad_frame(self) -> None:
        self.start()
        self.configured()
        self.sender.send(frame(2))
        self.sender.send(b"")  # A seqpacket, not peer EOF.
        self.sender.send(b"bad frame after empty packet")
        self.sender.close()
        self.assertTrue(self.receiver.wait(timeout_seconds=2))
        receipt = self.receiver.receipt()
        self.assertEqual(receipt["channel_status"], "incomplete")
        self.assertIsNone(receipt["payload_started"])

    def test_wrong_writer_empty_packet_is_not_accepted_as_eof(self) -> None:
        self.start()
        self.sender.send(frame(2))
        writer = subprocess.run(
            [sys.executable, "-I", "-c", "import socket; socket.socket(fileno=" +
             str(self.sender.fileno()) + ").send(b'')"],
            pass_fds=(self.sender.fileno(),), capture_output=True, timeout=10,
        )
        self.assertEqual(writer.returncode, 0)
        self.sender.close()
        self.assertTrue(self.receiver.wait(timeout_seconds=2))
        self.assertEqual(self.receiver.receipt()["channel_status"], "incomplete")
        self.assertIsNone(self.receiver.receipt()["payload_started"])


@unittest.skipUnless(sys.platform.startswith("linux") and shutil.which("cc"),
                     "Linux C compiler required; conformance_credit=none")
class TestNativeResourceInterface(unittest.TestCase):
    def test_native_resource_fd_flag_failures_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory(prefix="icode-resource-fcntl-") as temporary:
            root = Path(temporary)
            source = root / "fcntl_probe.c"
            source.write_text(
                '#define _GNU_SOURCE\n#include <fcntl.h>\n#include <stdarg.h>\n'
                '#include <stdlib.h>\n#include <string.h>\n#include <errno.h>\n'
                'static int target=-1,reads=0;static const char *mode;\n'
                'static int fault_fcntl(int fd,int command,...) {\n'
                'if(fd==target && command==F_GETFD) { reads++;\n'
                'if(!strcmp(mode,"get") || (!strcmp(mode,"readback") && reads==2)){errno=EPERM;return -1;}\n'
                'return fcntl(fd,command);}\n'
                'va_list values;va_start(values,command);int value=va_arg(values,int);va_end(values);\n'
                'if(fd==target && !strcmp(mode,"set")){errno=EPERM;return -1;}\n'
                'return fcntl(fd,command,value);}\n'
                '#define fcntl fault_fcntl\n'
                f'#include "{ROOT / "native/linux/icode_task_resource.h"}"\n'
                '#undef fcntl\n'
                'int main(int argc,char **argv) {if(argc!=3)return 3;mode=argv[1];target=atoi(argv[2]);\n'
                'struct icode_task_resource resource;\n'
                f'return icode_resource_init(&resource,target,"{UNIT}",2)==-1?0:1;}}\n',
                encoding="ascii",
            )
            executable = root / "probe"
            build = subprocess.run(["cc", "-std=c11", "-O2", "-Wall", "-Wextra", "-Werror",
                                    str(source), "-o", str(executable)], capture_output=True, timeout=15)
            self.assertEqual(build.returncode, 0, build.stderr)
            host, sender = socket.socketpair(socket.AF_UNIX, socket.SOCK_SEQPACKET)
            try:
                for mode in ("get", "set", "readback"):
                    with self.subTest(mode=mode):
                        result = subprocess.run([str(executable), mode, str(sender.fileno())],
                                                pass_fds=(sender.fileno(),), capture_output=True, timeout=15)
                        self.assertEqual(result.returncode, 0, "native swallowed FD flag failure")
            finally:
                host.close()
                sender.close()

    def test_native_accepts_authenticated_resource_fd_before_scope_failure(self) -> None:
        with tempfile.TemporaryDirectory(prefix="icode-resource-red-") as temporary:
            root = Path(temporary)
            helper = root / "helper"
            build = subprocess.run(["cc", "-std=c11", "-O2", "-Wall", "-Wextra", "-Werror",
                                    str(ROOT / "native/linux/icode_landlock.c"), "-o", str(helper)],
                                   capture_output=True, timeout=15)
            self.assertEqual(build.returncode, 0, build.stderr)
            host, sender = socket.socketpair(socket.AF_UNIX, socket.SOCK_SEQPACKET)
            try:
                result = subprocess.run([str(helper), "--workspace", str(root),
                                         "--parent-pid", str(os.getpid()),
                                         "--task-quota-unit", UNIT, "--task-quota-limit", "2",
                                         "--resource-control-fd", str(sender.fileno()),
                                         "--", "/bin/true"], pass_fds=(sender.fileno(),),
                                        capture_output=True, timeout=15)
                self.assertEqual(result.returncode, 1, result.stderr)
                host.settimeout(1)
                self.assertEqual(host.recv(64), frame(2))
            finally:
                sender.close()
                host.close()


@unittest.skipUnless(sys.platform.startswith("linux") and shutil.which("cc"),
                     "Linux C compiler required; conformance_credit=none")
class TestNativeTaskResource(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        from tests.test_linux_helper_task_quota import TestLinuxHelperTaskQuota
        TestLinuxHelperTaskQuota.setUpClass()
        cls.addClassCleanup(TestLinuxHelperTaskQuota.doClassCleanups)
        cls._harness = TestLinuxHelperTaskQuota()
        cls._temporary = tempfile.TemporaryDirectory(prefix="icode-resource-native-")
        cls.addClassCleanup(cls._temporary.cleanup)
        cls._root = Path(cls._temporary.name)
        source = cls._root / "driver.c"
        source.write_text(
            '#define _GNU_SOURCE\n#include <stdlib.h>\n#include <string.h>\n#include <errno.h>\n'
            'static int fault_unsetenv(const char *name){\n'
            'const char *failure=getenv("ICODE_TEST_UNSETENV_FAILURE");\n'
            'if(failure && !strcmp(failure,name)){errno=ENOMEM;return -1;}\n'
            'return unsetenv(name);}\n#define unsetenv fault_unsetenv\n'
            f'#include "{ROOT / "native/linux/icode_task_quota.h"}"\n'
            '#include <sys/prctl.h>\n#include <sys/wait.h>\n'
            'static int close_inherited_descriptors(int first,int second);\n'
            'static pid_t owned_cleanup_child=-1;\n'
            'static int occupied_quota_prepare(const char *unit,uint64_t limit,struct icode_task_quota *state){\n'
            'int result=icode_task_quota_prepare(unit,limit,state);\n'
            'if(result || !getenv("ICODE_TEST_OCCUPY_OWN_PAYLOAD"))return result;\n'
            'int readiness[2];if(pipe2(readiness,O_CLOEXEC)){\n'
            'icode_task_quota_finish(state);icode_task_quota_close(state);return -1;}\n'
            'pid_t creator=getpid(); owned_cleanup_child=icode_task_quota_fork(state);\n'
            'if(owned_cleanup_child==0){\n'
            'alarm(5);\n'
            'if(prctl(PR_SET_PDEATHSIG,SIGKILL,0,0,0) || getppid()!=creator ||\n'
            'close_inherited_descriptors(-1,-1))_exit(4);\n'
            'for(;;)pause();}\n'
            'close(readiness[1]);\n'
            'if(owned_cleanup_child<0){close(readiness[0]);icode_task_quota_finish(state);icode_task_quota_close(state);return -1;}\n'
            'char marker;ssize_t count;do{count=read(readiness[0],&marker,1);}while(count<0 && errno==EINTR);\n'
            'close(readiness[0]);if(count!=0)return -1;\n'
            'return 0;}\n#define icode_task_quota_prepare occupied_quota_prepare\n'
            '#define main icode_original_main\n'
            f'#include "{ROOT / "native/linux/icode_landlock.c"}"\n#undef main\n'
            'int main(int argc, char **argv) {\n'
            'alarm(10);\n'
            'if(argc==3 && !strcmp(argv[1],"--init-fd-audit")){\n'
            'int fd=atoi(argv[2]);struct icode_task_resource resource;\n'
            f'int result=icode_resource_init(&resource,fd,"{UNIT}",2);\n'
            'printf("probe:init_ok=%d cloexec=%d\\n",result==0,(fcntl(fd,F_GETFD)&FD_CLOEXEC)!=0);\n'
            'return 0;}\n'
            'if(getenv("ICODE_TEST_DENY_PAYLOAD_DUP")){\n'
            '#ifdef SYS_dup2\nint denied_dup=SYS_dup2;\n'
            '#else\nint denied_dup=SYS_dup3;\n#endif\n'
            'struct sock_filter filter[]={\n'
            'BPF_STMT(BPF_LD | BPF_W | BPF_ABS,offsetof(struct seccomp_data,nr)),\n'
            'BPF_JUMP(BPF_JMP | BPF_JEQ | BPF_K,(unsigned int)denied_dup,0,5),\n'
            'BPF_STMT(BPF_LD | BPF_W | BPF_ABS,offsetof(struct seccomp_data,args[0])),\n'
            'BPF_JUMP(BPF_JMP | BPF_JEQ | BPF_K,1,0,3),\n'
            'BPF_STMT(BPF_LD | BPF_W | BPF_ABS,offsetof(struct seccomp_data,args[1])),\n'
            'BPF_JUMP(BPF_JMP | BPF_JEQ | BPF_K,2,0,1),\n'
            'BPF_STMT(BPF_RET | BPF_K,SECCOMP_RET_ERRNO | EPERM),\n'
            'BPF_STMT(BPF_RET | BPF_K,SECCOMP_RET_ALLOW)};\n'
            'struct sock_fprog program={.len=8,.filter=filter};\n'
            'if(prctl(PR_SET_NO_NEW_PRIVS,1,0,0,0)||prctl(PR_SET_SECCOMP,SECCOMP_MODE_FILTER,&program))return 4;}\n'
            'if(getenv("ICODE_TEST_DENY_RESOURCE_CLOSE")){\n'
            'int target=-1; for(int i=1;i+1<argc;i++)\n'
            'if(!strcmp(argv[i],"--resource-control-fd"))target=atoi(argv[i+1]);\n'
            'struct sock_filter filter[]={\n'
            'BPF_STMT(BPF_LD | BPF_W | BPF_ABS,offsetof(struct seccomp_data,nr)),\n'
            'BPF_JUMP(BPF_JMP | BPF_JEQ | BPF_K,SYS_close,0,3),\n'
            'BPF_STMT(BPF_LD | BPF_W | BPF_ABS,offsetof(struct seccomp_data,args[0])),\n'
            'BPF_JUMP(BPF_JMP | BPF_JEQ | BPF_K,(unsigned int)target,0,1),\n'
            'BPF_STMT(BPF_RET | BPF_K,SECCOMP_RET_ERRNO | EPERM),\n'
            'BPF_STMT(BPF_RET | BPF_K,SECCOMP_RET_ALLOW)};\n'
            'struct sock_fprog program={.len=6,.filter=filter};\n'
            'if(prctl(PR_SET_NO_NEW_PRIVS,1,0,0,0)||prctl(PR_SET_SECCOMP,SECCOMP_MODE_FILTER,&program))return 4;}\n'
            'int denied=getenv("ICODE_TEST_DENY_UNSHARE")?SYS_unshare:\n'
            'getenv("ICODE_TEST_DENY_CLONE3")?SYS_clone3:-1;\n'
            'if(denied>=0){struct sock_filter filter[]={\n'
            'BPF_STMT(BPF_LD | BPF_W | BPF_ABS, offsetof(struct seccomp_data,nr)),\n'
            'BPF_JUMP(BPF_JMP | BPF_JEQ | BPF_K,(unsigned int)denied,0,1),\n'
            'BPF_STMT(BPF_RET | BPF_K,SECCOMP_RET_ERRNO | EPERM),\n'
            'BPF_STMT(BPF_RET | BPF_K,SECCOMP_RET_ALLOW)};\n'
            'struct sock_fprog program={.len=4,.filter=filter};\n'
            'if(prctl(PR_SET_NO_NEW_PRIVS,1,0,0,0)||prctl(PR_SET_SECCOMP,SECCOMP_MODE_FILTER,&program))return 1;}\n'
            'if(argc==3 && !strcmp(argv[1],"--ack-fd-audit")) {\n'
            'int fd=atoi(argv[2]),before=0,after=0;\n'
            'if(validate_violation_control_descriptor(fd))return 3;\n'
            'for(int i=3;i<1024;i++)if(fcntl(i,F_GETFD)>=0)before++;\n'
            'struct icode_task_resource resource;\n'
            f'icode_resource_init(&resource,fd,"{UNIT}",2);\n'
            'int result=icode_resource_ack(&resource);\n'
            'for(int i=3;i<1024;i++)if(fcntl(i,F_GETFD)>=0)after++;\n'
            'printf("probe:ack_denied=%d fds_equal=%d\\n",result==-1,before==after);\n'
            'return result==-1 && before==after?0:1; }\n'
            'if (getenv("ICODE_TEST_KILL_EXEC")) {\n'
            'struct sock_filter filter[] = {\n'
            'BPF_STMT(BPF_LD | BPF_W | BPF_ABS, offsetof(struct seccomp_data, nr)),\n'
            'BPF_JUMP(BPF_JMP | BPF_JEQ | BPF_K, SYS_execve, 0, 1),\n'
            'BPF_STMT(BPF_RET | BPF_K, SECCOMP_RET_KILL_PROCESS),\n'
            'BPF_STMT(BPF_RET | BPF_K, SECCOMP_RET_ALLOW)};\n'
            'struct sock_fprog program = {.len=4,.filter=filter};\n'
            'if(prctl(PR_SET_NO_NEW_PRIVS,1,0,0,0)||prctl(PR_SET_SECCOMP,SECCOMP_MODE_FILTER,&program))return 1;\n'
            '}\n'
            'const char *uid=getenv("ICODE_TEST_UID_MAP_PATH");\n'
            'int result=run_helper(argc,argv,"/proc/self/setgroups",uid?uid:"/proc/self/uid_map");\n'
            'if(owned_cleanup_child>0){\n'
            'if(kill(owned_cleanup_child,SIGKILL) && errno!=ESRCH)return 4;\n'
            'int status;pid_t waited;do{waited=waitpid(owned_cleanup_child,&status,0);}while(waited<0 && errno==EINTR);\n'
            'if(waited!=owned_cleanup_child)return 4;\n'
            'puts("probe:owned_cleanup_child_reaped");}\n'
            'return result;}\n',
            encoding="ascii",
        )
        cls._driver = cls._root / "driver"
        build = subprocess.run(["cc", "-std=c11", "-O2", "-Wall", "-Wextra", "-Werror",
                                str(source), "-o", str(cls._driver)],
                               capture_output=True, timeout=15)
        if build.returncode:
            raise AssertionError(build.stderr)

    def run_resource(self, *, limit: int = 2, mapless: bool = False,
                     default_fallback: bool = False,
                     missing_exec: bool = False, kill_exec: bool = False,
                     violation: bool = False, thread_probe: bool = False,
                     management_boundary: bool = False,
                     unset_failure: str | None = None,
                     setup_failure: str | None = None) -> tuple[dict[str, object], str]:
        from icode.linux_task_resource import (
            LinuxTaskResourceReceiver, create_task_resource_channel,
        )
        self._harness._namespace_available()
        environment, parent = self._harness._user_manager()
        if management_boundary:
            # Keep the real manager bus/runtime values, not simulated values.
            self.assertTrue(environment["DBUS_SESSION_BUS_ADDRESS"])
            self.assertTrue(environment["XDG_RUNTIME_DIR"])
            environment["INVOCATION_ID"] = "icode-test-management-invocation"
        with tempfile.TemporaryDirectory(prefix="icode-resource-payload-") as temporary:
            workspace = Path(temporary) / "code"
            workspace.mkdir()
            if mapless or default_fallback:
                uid_map = Path(temporary) / "uid_map"
                uid_map.write_text("", encoding="ascii")
                uid_map.chmod(0o444)
                environment["ICODE_TEST_UID_MAP_PATH"] = str(uid_map)
            if kill_exec:
                environment["ICODE_TEST_KILL_EXEC"] = "1"
            if setup_failure == "namespace":
                environment["ICODE_TEST_DENY_UNSHARE"] = "1"
            elif setup_failure == "clone":
                environment["ICODE_TEST_DENY_CLONE3"] = "1"
            elif setup_failure == "mapping":
                environment["ICODE_TEST_UID_MAP_PATH"] = str(Path(temporary) / "missing_uid_map")
            elif setup_failure == "resource_close":
                environment["ICODE_TEST_DENY_RESOURCE_CLOSE"] = "1"
            elif setup_failure == "dup":
                environment["ICODE_TEST_DENY_PAYLOAD_DUP"] = "1"
            elif setup_failure == "unset":
                environment["ICODE_TEST_UNSETENV_FAILURE"] = unset_failure
            unit = f"icode-task-{uuid.uuid4().hex}.scope"
            host, sender = create_task_resource_channel()
            monitor = observer_host = observer_sender = None
            receiver = LinuxTaskResourceReceiver(host, unit=unit, limit=limit)
            process = None
            try:
                flags = ["--task-quota-unit", unit, "--task-quota-limit", str(limit),
                         "--resource-control-fd", str(sender.fileno())]
                descriptors = [sender.fileno()]
                if violation:
                    from icode.linux_seccomp_notify import (
                        LinuxSeccompViolationMonitor, create_seccomp_listener_handoff_channel,
                    )
                    observer_host, observer_sender = create_seccomp_listener_handoff_channel()
                    flags += ["--violation-control-fd", str(observer_sender.fileno())]
                    descriptors.append(observer_sender.fileno())
                    monitor = LinuxSeccompViolationMonitor(observer_host)
                code = self._harness._payload_prefix() + (
                    "import sys\n"
                    "assert sys.argv[1:] == ['$X', '${X}', '$$', 'space value', '-leading']\n"
                    # Default may use the helper's verified mapless fallback;
                    # only an explicitly forced mapless run proves that mode.
                    "assert os.getuid() " + ("== 65534" if mapless else "in (0, 65534)") + "\n"
                )
                if thread_probe:
                    code += (
                        "libc=ctypes.CDLL(None,use_errno=True)\n"
                        "callback_type=ctypes.CFUNCTYPE(ctypes.c_void_p,ctypes.c_void_p)\n"
                        "def forbidden(argument): Path('forbidden').write_text('bad'); return None\n"
                        "callback=callback_type(forbidden); thread=ctypes.c_ulong()\n"
                        "assert libc.pthread_create(ctypes.byref(thread),None,callback,None)==errno.EAGAIN\n"
                    )
                elif limit == 1:
                    code += (
                        "try: child=os.fork()\n"
                        "except OSError as error: assert error.errno==errno.EAGAIN\n"
                        "else:\n"
                        "    if child==0: Path('forbidden').write_text('bad'); os._exit(3)\n"
                        "    os.waitpid(child,0); raise AssertionError('fork allowed')\n"
                    )
                else:
                    code += (
                        "child=os.fork()\n"
                        "if child==0:\n"
                        "    os.setsid(); Path('descendant').write_text('ok'); os._exit(0)\n"
                        "assert os.waitpid(child,0)[1]==0\n"
                    )
                if violation:
                    code += (
                        "import socket\n"
                        "try: socket.socket(socket.AF_INET,socket.SOCK_STREAM)\n"
                        "except PermissionError: pass\n"
                        "else: raise AssertionError('network allowed')\n"
                    )
                code += "Path('ready').write_text('ok')\nwhile not Path('release').exists(): time.sleep(.01)\nprint('ICQR1 forged phase2')\n"
                if management_boundary:
                    code += (
                        "print('ICODE_PAYLOAD_STDOUT',flush=True)\n"
                        "print('ICODE_PAYLOAD_STDERR',file=sys.stderr,flush=True)\n"
                        "assert all(name not in os.environ for name in "
                        "('DBUS_SESSION_BUS_ADDRESS','XDG_RUNTIME_DIR','INVOCATION_ID')), "
                        "'management environment reached payload'\n"
                    )
                if setup_failure in ("resource_close", "dup", "unset"):
                    # The old implementation actually executes this marker;
                    # do not let the normal FD assertion hide that violation.
                    code = "from pathlib import Path; Path('forbidden').write_text('payload executed')"
                payload = (["/missing-icode-resource-executable"] if missing_exec else
                           ["/usr/bin/python3", "-I", "-c", code, "$X", "${X}", "$$", "space value", "-leading"])
                command = ["/usr/bin/systemd-run", "--user", "--scope", "--quiet", "--collect",
                           "--no-ask-password", "--description=ICODE private resource test",
                           f"--unit={unit}", "--property=Delegate=pids", str(self._driver),
                           "--workspace", str(workspace), "--parent-pid", str(os.getpid()),
                           *flags, "--runtime-read", "/usr", "--runtime-read", "/lib",
                           *(["--runtime-read", str(Path(temporary) / "missing_runtime")]
                             if setup_failure == "filesystem" else []), "--", *payload]
                process = subprocess.Popen(command, env=environment, pass_fds=tuple(descriptors),
                                           stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
                receiver.bind_process(process, expected_uid=os.getuid(), expected_gid=os.getgid())
                receiver.start(deadline_monotonic=time.monotonic() + 10)
                sender.close()
                if monitor:
                    observer_sender.close()
                    monitor.bind_process(process)
                    monitor.start(deadline_monotonic=time.monotonic() + 5)
                scope = parent / unit
                if not missing_exec and not kill_exec and not setup_failure:
                    deadline = time.monotonic() + 3
                    while not (workspace / "ready").exists() and process.poll() is None and time.monotonic() < deadline:
                        time.sleep(.01)
                    self.assertTrue((workspace / "ready").exists(), "payload did not reach native quota")
                    members = set((scope / "supervisor/cgroup.procs").read_text().split())
                    self.assertIn(str(process.pid), members)  # systemd scope exec preserves Popen PID.
                    self.assertNotIn(str(os.getpid()), members)
                    self.assertEqual((scope / "payload/pids.current").read_text().strip(), "1")
                    self.assertNotIn(str(os.getpid()), (scope / "payload/cgroup.procs").read_text().split())
                    if limit == 1:
                        events = dict(line.split() for line in (scope / "payload/pids.events").read_text().splitlines())
                        self.assertGreater(int(events["max"]), 0)
                    (workspace / "release").write_text("go", encoding="ascii")
                output, error = process.communicate(timeout=15)
                self.assertTrue(receiver.wait(timeout_seconds=2))
                self._harness._assert_collected(unit, scope, environment)
                self.assertFalse((workspace / "forbidden").exists())
                if management_boundary:
                    self.assertNotIn("ICODE_PAYLOAD_STDERR", error)
                    if not missing_exec and not setup_failure:
                        self.assertIn("ICODE_PAYLOAD_STDOUT", output)
                        self.assertIn("ICODE_PAYLOAD_STDERR", output)
                if missing_exec:
                    self.assertNotIn("execvp:", output)
                    self.assertNotIn("execvp:", error)
                self.assertEqual(process.returncode, 1 if setup_failure else 127 if missing_exec else 159 if kill_exec else 0, error)
                if monitor:
                    self.assertTrue(monitor.close())
                    self.assertIsNotNone(monitor.receipt())
                return receiver.receipt(), output
            finally:
                (workspace / "release").write_text("go", encoding="ascii")
                if process is not None:
                    if process.poll() is None:
                        process.kill()
                    process.communicate(timeout=15)
                receiver.close()
                for endpoint in (sender, host, observer_sender, observer_host):
                    if endpoint is not None:
                        endpoint.close()
                if monitor:
                    monitor.close()

    def test_real_scope_cap_two_binds_popen_writer_and_literal_argv(self) -> None:
        receipt, output = self.run_resource()
        self.assertEqual(receipt["terminal"], "finished")
        self.assertIsNone(receipt["payload_started"])
        self.assertIn("forged phase2", output)

    def test_default_fallback_and_mapless_cap_one_and_two(self) -> None:
        for mapless, fallback, limit in ((False, False, 1), (False, True, 1),
                                        (False, True, 2), (True, False, 1), (True, False, 2)):
            with self.subTest(mapless=mapless, default_fallback=fallback, limit=limit):
                receipt, _output = self.run_resource(mapless=mapless, default_fallback=fallback, limit=limit)
                self.assertEqual(receipt["terminal"], "finished")
                self.assertIsNone(receipt["payload_started"])

    def test_explicit_missing_exec_failure_is_false(self) -> None:
        receipt, _output = self.run_resource(missing_exec=True)
        self.assertEqual(receipt["terminal"], "preexec_failed")
        self.assertIs(receipt["payload_started"], False)

    def test_management_boundary_default_payload(self) -> None:
        receipt, _output = self.run_resource(management_boundary=True)
        self.assertEqual(receipt["terminal"], "finished")
        self.assertIsNone(receipt["payload_started"])

    def test_management_boundary_mapless_payload(self) -> None:
        receipt, _output = self.run_resource(management_boundary=True, mapless=True)
        self.assertEqual(receipt["terminal"], "finished")
        self.assertIsNone(receipt["payload_started"])

    def test_management_boundary_dual_user_notif(self) -> None:
        receipt, _output = self.run_resource(management_boundary=True, violation=True)
        self.assertEqual(receipt["terminal"], "finished")
        self.assertIsNone(receipt["payload_started"])

    def test_management_missing_exec_does_not_emit_native_diagnostic(self) -> None:
        receipt, output = self.run_resource(management_boundary=True, missing_exec=True)
        self.assertEqual(output, "")
        self.assertEqual(receipt["terminal"], "preexec_failed")
        self.assertIs(receipt["payload_started"], False)

    def test_management_dup_failure_never_executes_payload(self) -> None:
        receipt, _output = self.run_resource(management_boundary=True, setup_failure="dup")
        self.assertEqual(receipt["terminal"], "preexec_failed")
        self.assertIs(receipt["payload_started"], False)

    def test_management_unset_failure_never_executes_payload(self) -> None:
        # Only the individual libc API failure is injected. Real native setup,
        # execution marker, private receipt and own-scope GC remain observable.
        for variable in ("DBUS_SESSION_BUS_ADDRESS", "XDG_RUNTIME_DIR", "INVOCATION_ID"):
            with self.subTest(variable=variable):
                receipt, _output = self.run_resource(management_boundary=True,
                                                    setup_failure="unset", unset_failure=variable)
                self.assertEqual(receipt["terminal"], "preexec_failed")
                self.assertIs(receipt["payload_started"], False)

    def test_legacy_without_resource_preserves_environment_and_streams(self) -> None:
        self._harness._namespace_available()
        environment = {"PATH": "/usr/bin:/bin", "DBUS_SESSION_BUS_ADDRESS": "test-bus",
                       "XDG_RUNTIME_DIR": "test-runtime", "INVOCATION_ID": "test-invocation"}
        code = ("import os,sys; assert [os.environ[name] for name in "
                "('DBUS_SESSION_BUS_ADDRESS','XDG_RUNTIME_DIR','INVOCATION_ID')] == "
                "['test-bus','test-runtime','test-invocation']; "
                "print('ICODE_LEGACY_STDOUT'); print('ICODE_LEGACY_STDERR',file=sys.stderr)")
        with tempfile.TemporaryDirectory(prefix="icode-resource-legacy-") as workspace:
            result = subprocess.run([str(self._driver), "--workspace", workspace,
                                     "--parent-pid", str(os.getpid()), "--runtime-read", "/usr",
                                     "--runtime-read", "/lib", "--", "/usr/bin/python3", "-I", "-c", code],
                                    env=environment, capture_output=True, text=True, timeout=15)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(result.stdout, "ICODE_LEGACY_STDOUT\n")
            self.assertEqual(result.stderr, "ICODE_LEGACY_STDERR\n")

    def test_preexec_death_without_error_pipe_frame_is_unknown(self) -> None:
        receipt, _output = self.run_resource(kill_exec=True)
        self.assertEqual(receipt["terminal"], "finished")
        self.assertIsNone(receipt["payload_started"])

    def test_two_fd_whitelist_retains_user_notif_handoff(self) -> None:
        receipt, _output = self.run_resource(violation=True)
        self.assertEqual(receipt["terminal"], "finished")
        self.assertIsNone(receipt["payload_started"])

    def test_private_channel_cap_one_threads_are_charged_in_both_mappings(self) -> None:
        for mapless in (False, True):
            with self.subTest(mapless=mapless):
                receipt, _output = self.run_resource(limit=1, thread_probe=True, mapless=mapless)
                self.assertEqual(receipt["terminal"], "finished")
                self.assertIsNone(receipt["payload_started"])

    def test_native_setup_failures_are_explicit_not_started(self) -> None:
        for failure in ("namespace", "mapping", "clone", "filesystem"):
            with self.subTest(failure=failure):
                receipt, _output = self.run_resource(setup_failure=failure)
                self.assertTrue(receipt["configured"])
                self.assertEqual(receipt["terminal"], "preexec_failed")
                self.assertIs(receipt["payload_started"], False)

    def test_resource_fd_close_denial_never_executes_payload(self) -> None:
        receipt, _output = self.run_resource(setup_failure="resource_close")
        self.assertEqual(receipt["terminal"], "preexec_failed")
        self.assertIs(receipt["payload_started"], False)

    def test_native_resource_init_restores_close_on_exec(self) -> None:
        from icode.linux_task_resource import create_task_resource_channel
        host, sender = create_task_resource_channel()
        try:
            result = subprocess.run([str(self._driver), "--init-fd-audit", str(sender.fileno())],
                                    pass_fds=(sender.fileno(),), capture_output=True, text=True, timeout=15)
            self.assertEqual(result.returncode, 0)
            self.assertEqual(result.stdout.strip(), "probe:init_ok=1 cloexec=1")
        finally:
            sender.close()
            host.close()

    def test_native_ack_rights_are_closed_before_rejection(self) -> None:
        from icode.linux_task_resource import create_task_resource_channel
        for count in (1, 7, 40):
            with self.subTest(count=count):
                host, sender = create_task_resource_channel()
                try:
                    process = subprocess.Popen([str(self._driver), "--ack-fd-audit", str(sender.fileno())],
                                               pass_fds=(sender.fileno(),), stdout=subprocess.PIPE,
                                               stderr=subprocess.PIPE, text=True)
                    sender.close()
                    host.sendmsg([b"ICQA1" + NONCE + struct.pack("!I", 2)],
                                 [(socket.SOL_SOCKET, socket.SCM_RIGHTS,
                                   array.array("i", [host.fileno()] * count))])
                    output, error = process.communicate(timeout=15)
                    self.assertEqual(process.returncode, 0, error)
                    self.assertEqual(output.strip(), "probe:ack_denied=1 fds_equal=1")
                finally:
                    sender.close()
                    host.close()

    def raw_handshake(self, mode: str, *, interrupt_before_ack: bool = False) -> None:
        from icode.linux_task_resource import create_task_resource_channel
        self._harness._namespace_available()
        environment, parent = self._harness._user_manager()
        if mode == "cleanup":
            environment["ICODE_TEST_OCCUPY_OWN_PAYLOAD"] = "1"
        with tempfile.TemporaryDirectory(prefix="icode-resource-ack-") as temporary:
            workspace = Path(temporary)
            unit = f"icode-task-{uuid.uuid4().hex}.scope"
            nonce = bytes.fromhex(unit[11:43])
            host, sender = create_task_resource_channel()
            scope = parent / unit
            process = None
            interrupted_child_reaped = False
            try:
                command = ["/usr/bin/systemd-run", "--user", "--scope", "--quiet", "--collect",
                           "--no-ask-password", "--description=ICODE resource ACK test",
                           f"--unit={unit}", "--property=Delegate=pids", str(self._driver),
                           "--workspace", str(workspace), "--parent-pid", str(os.getpid()),
                           "--task-quota-unit", unit, "--task-quota-limit", "2",
                           "--resource-control-fd", str(sender.fileno()), "--runtime-read", "/usr",
                           "--runtime-read", "/lib", "--", "/usr/bin/python3", "-I", "-c",
                           "from pathlib import Path; Path('forbidden').write_text('bad')"]
                process = subprocess.Popen(command, env=environment, pass_fds=(sender.fileno(),),
                                           stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
                sender.close()
                host.settimeout(5)
                payload, ancillary, flags, _address = host.recvmsg(27, socket.CMSG_SPACE(12))
                self.assertEqual(payload, frame(1, nonce=nonce))
                self.assertEqual(flags, 0)
                self.assertEqual(ancillary, [(socket.SOL_SOCKET, socket.SCM_CREDENTIALS,
                                             struct.pack("3i", process.pid, os.getuid(), os.getgid()))])
                if mode == "close":
                    host.close()  # Cannot receive a failure fact; start remains unknown.
                elif mode == "cleanup":
                    # The test driver creates its own charged child atomically
                    # inside this scope. Its pre-notification pipe EOF only
                    # synchronizes closed management FDs, not payload exec.
                    # No external cgroup member is moved.
                    self.assertEqual((scope / "payload/pids.current").read_text().strip(), "1")
                    child_members = (scope / "payload/cgroup.procs").read_text().split()
                    self.assertEqual(len(child_members), 1)
                    self.assertNotIn(str(process.pid), child_members)
                    self.assertNotIn(str(os.getpid()), child_members)
                    for descriptor in (Path("/proc") / child_members[0] / "fd").iterdir():
                        self.assertLess(int(descriptor.name), 3)
                    if interrupt_before_ack:
                        raise KeyboardInterrupt
                    host.send(b"ICQA1" + nonce + struct.pack("!I", 2))
                elif mode == "timeout":
                    pass
                elif mode == "sibling":
                    ack = b"ICQA1" + nonce + struct.pack("!I", 2)
                    impersonator = subprocess.run(
                        ["/usr/bin/python3", "-I", "-c",
                         "import socket; socket.socket(fileno=" + str(host.fileno()) +
                         ").send(bytes.fromhex('" + ack.hex() + "'))"],
                        pass_fds=(host.fileno(),), capture_output=True, timeout=10,
                    )
                    self.assertEqual(impersonator.returncode, 0)
                else:
                    host.send(b"ICQA1" + b"x" * 16 + struct.pack("!I", 2))
                if mode != "close":
                    self.assertEqual(host.recv(27), frame(4 if mode == "cleanup" else 2, nonce=nonce))
                output, _error = process.communicate(timeout=15)
                self.assertEqual(process.returncode, 1)
                self.assertEqual(output, "probe:owned_cleanup_child_reaped\n" if mode == "cleanup" else "")
                self.assertFalse((workspace / "forbidden").exists())
                if mode == "cleanup":
                    self.assertFalse((Path("/proc") / child_members[0]).exists())
                self._harness._assert_collected(unit, scope, environment)
            finally:
                for child in (process,):
                    if child is not None:
                        if mode == "cleanup" and child.poll() is None:
                            # Even an assertion/interrupt before ACK lets the
                            # driver reap its own child through a denied ACK.
                            # A bounded failure fallback is PDEATHSIG + alarm.
                            try:
                                host.send(b"invalid cleanup-test ACK")
                            except OSError:
                                pass
                            try:
                                child.communicate(timeout=4)
                            except subprocess.TimeoutExpired:
                                pass
                        if child.poll() is None:
                            child.kill()
                        cleanup_output, _cleanup_error = child.communicate(timeout=15)
                        if interrupt_before_ack:
                            interrupted_child_reaped = cleanup_output == "probe:owned_cleanup_child_reaped\n"
                host.close()
                sender.close()
                if mode == "cleanup" and process is not None:
                    self._harness._assert_collected(unit, scope, environment)
                    if interrupt_before_ack:
                        self.assertTrue(interrupted_child_reaped, "owned cleanup child was not reaped")

    def test_wrong_ack_denies_before_payload_and_finishes_own_leaf(self) -> None:
        self.raw_handshake("wrong")

    def test_missing_ack_denies_before_payload(self) -> None:
        self.raw_handshake("timeout")

    def test_ack_endpoint_death_does_not_launch_payload(self) -> None:
        self.raw_handshake("close")

    def test_cleanup_failure_takes_precedence_over_preexec_failure(self) -> None:
        self.raw_handshake("cleanup")
        with self.assertRaises(KeyboardInterrupt):
            self.raw_handshake("cleanup", interrupt_before_ack=True)

    def test_inherited_ack_endpoint_cannot_impersonate_host_parent(self) -> None:
        self.raw_handshake("sibling")

    def test_resource_flag_binding_and_distinct_endpoints_are_strict(self) -> None:
        with tempfile.TemporaryDirectory(prefix="icode-resource-flags-") as temporary:
            host, sender = socket.socketpair(socket.AF_UNIX, socket.SOCK_SEQPACKET)
            try:
                fd = str(sender.fileno())
                valid = ["--task-quota-unit", UNIT, "--task-quota-limit", "2"]
                bad = [
                    ["--resource-control-fd", fd],
                    [*valid, "--resource-control-fd"],
                    [*valid, "--resource-control-fd", "2"],
                    [*valid, "--resource-control-fd", "-1"],
                    [*valid, "--resource-control-fd", "x"],
                    [*valid, "--resource-control-fd", fd, "--resource-control-fd", fd],
                    [*valid, "--resource-control-fd", fd, "--violation-control-fd", fd],
                    [*valid, "--resource-control-fd", fd, "--proxy-control-fd", fd],
                ]
                for flags in bad:
                    with self.subTest(flags=flags):
                        result = subprocess.run([str(self._driver), "--workspace", temporary,
                                                 "--parent-pid", str(os.getpid()), *flags,
                                                 "--", "/bin/touch", "forbidden"],
                                                pass_fds=(sender.fileno(),), capture_output=True, timeout=15)
                        self.assertEqual(result.returncode, 2)
                        self.assertFalse((Path(temporary) / "forbidden").exists())
            finally:
                host.close()
                sender.close()
