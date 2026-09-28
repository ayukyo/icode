"""真实 AF_UNIX/SCM_RIGHTS loopback listener handoff 回归。"""

from __future__ import annotations

import array
import importlib.util
import os
import signal
import socket
import subprocess
import sys
import textwrap
import threading
import time
import unittest
from pathlib import Path
from unittest import mock

_HANDOFF_PREFIX = b"ICODE_PROXY_LISTENER_V1"
_HANDOFF_NONCE = bytes.fromhex("00112233445566778899aabbccddeeff")
_HANDOFF_PACKET = _HANDOFF_PREFIX + _HANDOFF_NONCE
_HANDOFF_ACK = b"ICODE_PROXY_LISTENER_ACK_V1" + _HANDOFF_NONCE


@unittest.skipUnless(sys.platform.startswith("linux"), "仅 Linux 支持 SCM_RIGHTS receiver")
class TestLinuxProxyHandoff(unittest.TestCase):
    @staticmethod
    def _send_fds(
        sender: socket.socket,
        descriptors: list[int],
        *,
        payload: bytes = _HANDOFF_PACKET,
    ) -> None:
        ancillary = []
        if descriptors:
            rights = array.array("i", descriptors)
            ancillary.append((socket.SOL_SOCKET, socket.SCM_RIGHTS, rights))
        sender.sendmsg([payload], ancillary)

    @staticmethod
    def _descriptor_alias_count(sock: socket.socket) -> int:
        target = os.readlink(f"/proc/self/fd/{sock.fileno()}")
        count = 0
        for descriptor in os.listdir("/proc/self/fd"):
            try:
                if os.readlink(f"/proc/self/fd/{descriptor}") == target:
                    count += 1
            except FileNotFoundError:
                continue
        return count

    def test_接收并验证真实loopback_tcp_listener_fd(self) -> None:
        self.assertIsNotNone(
            importlib.util.find_spec("icode.linux_proxy_handoff"),
            "Linux proxy listener handoff receiver is not implemented",
        )
        from icode.linux_proxy_handoff import (
            acknowledge_loopback_listener_handoff,
            create_loopback_listener_handoff_channel,
            receive_loopback_listener,
        )

        host_control, sender_control = create_loopback_listener_handoff_channel()
        source = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        received: socket.socket | None = None
        client: socket.socket | None = None
        accepted: socket.socket | None = None
        try:
            source.bind(("127.0.0.1", 0))
            source.listen(1)
            rights = array.array("i", [source.fileno()])
            sender_control.sendmsg(
                [_HANDOFF_PACKET],
                [(socket.SOL_SOCKET, socket.SCM_RIGHTS, rights)],
            )

            received = receive_loopback_listener(
                host_control, expected_pid=os.getpid(), timeout_seconds=1.0,
            )
            sender_control.settimeout(1.0)
            acknowledge_loopback_listener_handoff(host_control, received)
            self.assertEqual(
                sender_control.recv(64), _HANDOFF_ACK,
            )

            source.close()
            self.assertFalse(received.get_inheritable())
            self.assertEqual(received.getsockname()[0], "127.0.0.1")
            self.assertGreater(received.getsockname()[1], 0)
            client = socket.create_connection(received.getsockname(), timeout=1.0)
            accepted, _ = received.accept()
            client.sendall(b"fd-handoff")
            self.assertEqual(accepted.recv(10), b"fd-handoff")
        finally:
            for sock in (accepted, client, received, source,
                         sender_control, host_control):
                if sock is not None:
                    sock.close()

    def test_ACK必须绑定已接收listener和原控制通道且只能成功一次(self) -> None:
        from icode.linux_proxy_handoff import (
            ProxyHandoffError,
            acknowledge_loopback_listener_handoff,
            create_loopback_listener_handoff_channel,
            receive_loopback_listener,
        )

        host_control, sender_control = create_loopback_listener_handoff_channel()
        other_host, other_sender = create_loopback_listener_handoff_channel()
        source = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        received: socket.socket | None = None
        try:
            source.bind(("127.0.0.1", 0))
            source.listen(1)
            with self.assertRaises(ProxyHandoffError):
                acknowledge_loopback_listener_handoff(host_control, source)
            sender_control.settimeout(0.05)
            with self.assertRaises(socket.timeout):
                sender_control.recv(64)

            self._send_fds(sender_control, [source.fileno()])
            received = receive_loopback_listener(
                host_control, expected_pid=os.getpid(), timeout_seconds=1.0,
            )
            with self.assertRaises(ProxyHandoffError):
                acknowledge_loopback_listener_handoff(other_host, received)
            acknowledge_loopback_listener_handoff(host_control, received)
            sender_control.settimeout(1.0)
            self.assertEqual(sender_control.recv(64), _HANDOFF_ACK)
            with self.assertRaises(ProxyHandoffError):
                acknowledge_loopback_listener_handoff(host_control, received)
        finally:
            for sock in (
                received, source, other_sender, other_host,
                sender_control, host_control,
            ):
                if sock is not None:
                    sock.close()

    def test调用方处理其它异常时仍可成功接收并返回listener(self) -> None:
        from icode.linux_proxy_handoff import (
            create_loopback_listener_handoff_channel,
            receive_loopback_listener,
        )

        host_control, sender_control = create_loopback_listener_handoff_channel()
        source = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        received: socket.socket | None = None
        client: socket.socket | None = None
        accepted: socket.socket | None = None
        try:
            source.bind(("127.0.0.1", 0))
            source.listen(1)
            self._send_fds(sender_control, [source.fileno()])

            try:
                raise ValueError("caller-owned exception context")
            except ValueError:
                received = receive_loopback_listener(
                    host_control,
                    expected_pid=os.getpid(),
                    timeout_seconds=1.0,
                )

            self.assertIsInstance(received, socket.socket)
            self.assertGreater(received.fileno(), -1)
            client = socket.create_connection(received.getsockname(), timeout=1.0)
            accepted, _ = received.accept()
            client.sendall(b"returned-listener-is-open")
            self.assertEqual(accepted.recv(32), b"returned-listener-is-open")
        finally:
            for sock in (accepted, client, received, source,
                         sender_control, host_control):
                if sock is not None:
                    sock.close()

    def test_超大timeout在等待前以稳定错误拒绝(self) -> None:
        from icode.linux_proxy_handoff import (
            ProxyHandoffError,
            create_loopback_listener_handoff_channel,
            receive_loopback_listener,
        )

        host_control, sender_control = create_loopback_listener_handoff_channel()
        try:
            with self.assertRaises(ProxyHandoffError):
                receive_loopback_listener(
                    host_control,
                    expected_pid=os.getpid(),
                    timeout_seconds=10 ** 1000,
                )
        finally:
            sender_control.close()
            host_control.close()

    def test_无消息时按有限timeout退出(self) -> None:
        from icode.linux_proxy_handoff import (
            ProxyHandoffError,
            create_loopback_listener_handoff_channel,
            receive_loopback_listener,
        )

        host_control, sender_control = create_loopback_listener_handoff_channel()
        started = time.monotonic()
        try:
            with self.assertRaises(ProxyHandoffError):
                receive_loopback_listener(
                    host_control,
                    expected_pid=os.getpid(),
                    timeout_seconds=0.05,
                )
            self.assertLess(time.monotonic() - started, 0.5)
        finally:
            sender_control.close()
            host_control.close()

    def test_高编号控制fd仍可接收有效handoff(self) -> None:
        import fcntl

        from icode.linux_proxy_handoff import (
            create_loopback_listener_handoff_channel,
            receive_loopback_listener,
        )

        host_control, sender_control = create_loopback_listener_handoff_channel()
        high_control = socket.socket(
            socket.AF_UNIX,
            socket.SOCK_SEQPACKET,
            fileno=fcntl.fcntl(
                host_control.fileno(), fcntl.F_DUPFD_CLOEXEC, 1100,
            ),
        )
        source = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        received: socket.socket | None = None
        try:
            source.bind(("127.0.0.1", 0))
            source.listen(1)
            self._send_fds(sender_control, [source.fileno()])
            received = receive_loopback_listener(
                high_control,
                expected_pid=os.getpid(),
                timeout_seconds=1.0,
            )
            self.assertEqual(received.getsockname()[0], "127.0.0.1")
        finally:
            if received is not None:
                received.close()
            source.close()
            high_control.close()
            sender_control.close()
            host_control.close()

    def test_并发接收只消费一条消息且第二个接收者不会无限阻塞(self) -> None:
        child_script = textwrap.dedent("""\
            import array
            import os
            import socket
            import threading
            import sys

            from icode.linux_proxy_handoff import (
                ProxyHandoffError,
                create_loopback_listener_handoff_channel,
                receive_loopback_listener,
            )

            host, sender = create_loopback_listener_handoff_channel()
            listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            listener.bind(('127.0.0.1', 0))
            listener.listen(1)
            rights = array.array('i', [listener.fileno()])
            sender.sendmsg(
                [b'ICODE_PROXY_LISTENER_V1' + bytes.fromhex(
                    '00112233445566778899aabbccddeeff')],
                [(socket.SOL_SOCKET, socket.SCM_RIGHTS, rights)],
            )

            gate = threading.Barrier(2)
            class GatedSocket(socket.socket):
                def recvmsg(self, *args):
                    gate.wait(timeout=1)
                    return super().recvmsg(*args)

            control = GatedSocket(
                socket.AF_UNIX, socket.SOCK_SEQPACKET,
                fileno=os.dup(host.fileno()),
            )
            outcomes = []
            def receive_one():
                try:
                    received = receive_loopback_listener(
                        control, expected_pid=os.getpid(), timeout_seconds=0.2,
                    )
                except ProxyHandoffError:
                    outcomes.append('timeout')
                else:
                    outcomes.append('received')
                    received.close()

            readers = [threading.Thread(target=receive_one, daemon=True)
                       for _ in range(2)]
            for reader in readers:
                reader.start()
            for reader in readers:
                reader.join(timeout=0.8)
            if any(reader.is_alive() for reader in readers):
                sys.exit(1)
            if sorted(outcomes) != ['received', 'timeout']:
                sys.exit(2)
            control.close()
            listener.close()
            sender.close()
            host.close()
        """)
        environment = os.environ.copy()
        source_root = str(Path(__file__).resolve().parents[1] / "src")
        environment["PYTHONPATH"] = os.pathsep.join(
            part for part in (source_root, environment.get("PYTHONPATH", "")) if part
        )
        result = subprocess.run(
            [sys.executable, "-c", child_script],
            capture_output=True,
            text=True,
            env=environment,
            timeout=3,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_只接受目标子进程发送的listener_fd(self) -> None:
        from icode.linux_proxy_handoff import (
            create_loopback_listener_handoff_channel,
            receive_loopback_listener,
        )

        host_control, sender_control = create_loopback_listener_handoff_channel()
        script = (
            "import array, socket, sys\n"
            "sender = socket.socket(fileno=int(sys.argv[1]))\n"
            "listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)\n"
            "listener.bind(('127.0.0.1', 0)); listener.listen(1)\n"
            "fds = array.array('i', [listener.fileno()])\n"
            "sender.sendmsg([b'ICODE_PROXY_LISTENER_V1' + bytes.fromhex('00112233445566778899aabbccddeeff')], [(socket.SOL_SOCKET, "
            "socket.SCM_RIGHTS, fds)])\n"
            "print(listener.getsockname()[1], flush=True)\n"
            "listener.close(); sender.close()\n"
        )
        child = subprocess.Popen(
            [sys.executable, "-c", script, str(sender_control.fileno())],
            pass_fds=(sender_control.fileno(),),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        sender_control.close()
        received: socket.socket | None = None
        client: socket.socket | None = None
        accepted: socket.socket | None = None
        try:
            received = receive_loopback_listener(
                host_control, expected_pid=child.pid, timeout_seconds=2.0,
            )
            stdout, stderr = child.communicate(timeout=2.0)
            self.assertEqual(child.returncode, 0, stderr)
            self.assertEqual(
                int(stdout.strip()), received.getsockname()[1],
            )
            client = socket.create_connection(received.getsockname(), timeout=1.0)
            accepted, _ = received.accept()
            client.sendall(b"child-fd")
            self.assertEqual(accepted.recv(8), b"child-fd")
        finally:
            if child.poll() is None:
                child.kill()
                child.wait(timeout=2.0)
            for sock in (accepted, client, received, host_control):
                if sock is not None:
                    sock.close()

    def test_拒绝无fd多fd和错误payload并清理已接收fd(self) -> None:
        from icode.linux_proxy_handoff import (
            ProxyHandoffError,
            create_loopback_listener_handoff_channel,
            receive_loopback_listener,
        )

        for descriptor_count, payload in (
            (0, _HANDOFF_PACKET),
            (2, _HANDOFF_PACKET),
            (5, _HANDOFF_PACKET),
            (1, b"NOT_A_LISTENER"),
        ):
            with self.subTest(descriptor_count=descriptor_count, payload=payload):
                host_control, sender_control = (
                    create_loopback_listener_handoff_channel()
                )
                source = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                try:
                    source.bind(("127.0.0.1", 0))
                    source.listen(1)
                    raw_fds = [source.fileno()] * descriptor_count
                    self._send_fds(sender_control, raw_fds, payload=payload)
                    before = self._descriptor_alias_count(source)
                    with self.assertRaises(ProxyHandoffError):
                        receive_loopback_listener(
                            host_control,
                            expected_pid=os.getpid(),
                            timeout_seconds=1.0,
                        )
                    self.assertEqual(
                        self._descriptor_alias_count(source), before,
                    )
                finally:
                    source.close()
                    sender_control.close()
                    host_control.close()

    def test_拒绝未启用凭据的控制socket(self) -> None:
        from icode.linux_proxy_handoff import (
            ProxyHandoffError,
            receive_loopback_listener,
        )

        host_control, sender_control = socket.socketpair(
            socket.AF_UNIX, socket.SOCK_SEQPACKET,
        )
        try:
            with self.assertRaises(ProxyHandoffError):
                receive_loopback_listener(
                    host_control,
                    expected_pid=os.getpid(),
                    timeout_seconds=0,
                )
        finally:
            sender_control.close()
            host_control.close()

    def test_拒绝非loopback和非TCP监听socket并清理fd(self) -> None:
        from icode.linux_proxy_handoff import (
            ProxyHandoffError,
            create_loopback_listener_handoff_channel,
            receive_loopback_listener,
        )

        for address, socket_type, should_listen in (
            ("127.0.0.1", socket.SOCK_DGRAM, False),
            ("127.0.0.1", socket.SOCK_STREAM, False),
            ("0.0.0.0", socket.SOCK_STREAM, True),
        ):
            with self.subTest(address=address, socket_type=socket_type,
                              should_listen=should_listen):
                host_control, sender_control = (
                    create_loopback_listener_handoff_channel()
                )
                source = socket.socket(socket.AF_INET, socket_type)
                try:
                    source.bind((address, 0))
                    if should_listen:
                        source.listen(1)
                    self._send_fds(sender_control, [source.fileno()])
                    before = self._descriptor_alias_count(source)
                    with self.assertRaises(ProxyHandoffError):
                        receive_loopback_listener(
                            host_control,
                            expected_pid=os.getpid(),
                            timeout_seconds=1.0,
                        )
                    self.assertEqual(
                        self._descriptor_alias_count(source), before,
                    )
                finally:
                    source.close()
                    sender_control.close()
                    host_control.close()

    def test_拒绝错误发送者PID并关闭收到的fd(self) -> None:
        from icode.linux_proxy_handoff import (
            ProxyHandoffError,
            create_loopback_listener_handoff_channel,
            receive_loopback_listener,
        )

        host_control, sender_control = create_loopback_listener_handoff_channel()
        source = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            source.bind(("127.0.0.1", 0))
            source.listen(1)
            self._send_fds(sender_control, [source.fileno()])
            before = self._descriptor_alias_count(source)
            with self.assertRaises(ProxyHandoffError):
                receive_loopback_listener(
                    host_control,
                    expected_pid=os.getpid() + 1,
                    timeout_seconds=1.0,
                )
            self.assertEqual(self._descriptor_alias_count(source), before)
        finally:
            source.close()
            sender_control.close()
            host_control.close()

    def test_ancillary解析被中断时关闭已收到的fd(self) -> None:
        from icode import linux_proxy_handoff

        host_control, sender_control = (
            linux_proxy_handoff.create_loopback_listener_handoff_channel()
        )
        source = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            source.bind(("127.0.0.1", 0))
            source.listen(1)
            self._send_fds(sender_control, [source.fileno()])
            before = self._descriptor_alias_count(source)
            original_parser = linux_proxy_handoff._parse_ancillary_data

            def interrupt_after_parse(*args, **kwargs):
                original_parser(*args, **kwargs)
                raise KeyboardInterrupt

            with mock.patch.object(
                linux_proxy_handoff,
                "_parse_ancillary_data",
                side_effect=interrupt_after_parse,
            ):
                with self.assertRaises(KeyboardInterrupt):
                    linux_proxy_handoff.receive_loopback_listener(
                        host_control,
                        expected_pid=os.getpid(),
                        timeout_seconds=1.0,
                    )
            self.assertEqual(self._descriptor_alias_count(source), before)
        finally:
            source.close()
            sender_control.close()
            host_control.close()

    def test_recvmsg返回后信号中断时关闭尚未登记的fd(self) -> None:
        from icode.linux_proxy_handoff import (
            create_loopback_listener_handoff_channel,
            receive_loopback_listener,
        )

        host_control, sender_control = create_loopback_listener_handoff_channel()
        source = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        old_handler = signal.getsignal(signal.SIGINT)
        signal_observed = threading.Event()

        def interrupt_handler(_signum: int, _frame: object) -> None:
            signal_observed.set()
            raise KeyboardInterrupt

        class InterruptAfterRecvmsgSocket(socket.socket):
            def recvmsg(self, *args):
                message = super().recvmsg(*args)
                os.kill(os.getpid(), signal.SIGINT)
                if not signal_observed.wait(timeout=1.0):
                    raise AssertionError("main thread did not observe SIGINT")
                return message

        interrupt_control = InterruptAfterRecvmsgSocket(
            socket.AF_UNIX,
            socket.SOCK_SEQPACKET,
            fileno=os.dup(host_control.fileno()),
        )
        try:
            signal.signal(signal.SIGINT, interrupt_handler)
            source.bind(("127.0.0.1", 0))
            source.listen(1)
            self._send_fds(sender_control, [source.fileno()])
            before = self._descriptor_alias_count(source)

            with self.assertRaises(KeyboardInterrupt):
                receive_loopback_listener(
                    interrupt_control,
                    expected_pid=os.getpid(),
                    timeout_seconds=1.0,
                )

            self.assertEqual(self._descriptor_alias_count(source), before)
        finally:
            signal.signal(signal.SIGINT, old_handler)
            source.close()
            interrupt_control.close()
            sender_control.close()
            host_control.close()

    def test_dup成功但返回前SIGINT仍关闭未接管的副本(self) -> None:
        from icode import linux_proxy_handoff

        host_control, sender_control = (
            linux_proxy_handoff.create_loopback_listener_handoff_channel()
        )
        source = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        old_handler = signal.getsignal(signal.SIGINT)
        real_dup = os.dup
        signal_observed = threading.Event()

        def interrupt_handler(_signum: int, _frame: object) -> None:
            signal_observed.set()
            raise KeyboardInterrupt

        def duplicate_then_interrupt(descriptor: int) -> int:
            duplicate = real_dup(descriptor)
            os.kill(os.getpid(), signal.SIGINT)
            if not signal_observed.wait(timeout=1.0):
                raise AssertionError("main thread did not observe SIGINT")
            return duplicate

        try:
            signal.signal(signal.SIGINT, interrupt_handler)
            source.bind(("127.0.0.1", 0))
            source.listen(1)
            self._send_fds(sender_control, [source.fileno()])
            before = self._descriptor_alias_count(source)

            with mock.patch.object(
                linux_proxy_handoff.os,
                "dup",
                side_effect=duplicate_then_interrupt,
            ):
                with self.assertRaises(KeyboardInterrupt):
                    linux_proxy_handoff.receive_loopback_listener(
                        host_control,
                        expected_pid=os.getpid(),
                        timeout_seconds=1.0,
                    )

            self.assertFalse(
                any(
                    thread.name == "icode-proxy-fd-receiver"
                    for thread in threading.enumerate()
                ),
                "receiver worker must finish before re-raising SIGINT",
            )
            aliases = self._descriptor_alias_count(source)
            self.assertEqual(aliases, before)
        finally:
            signal.signal(signal.SIGINT, old_handler)
            source.close()
            sender_control.close()
            host_control.close()

    def test其他线程投递SIGINT时接收主线程仍清理fd(self) -> None:
        from icode.linux_proxy_handoff import (
            create_loopback_listener_handoff_channel,
            receive_loopback_listener,
        )

        host_control, sender_control = create_loopback_listener_handoff_channel()
        source = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        old_handler = signal.getsignal(signal.SIGINT)
        request_signal = threading.Event()
        signal_observed = threading.Event()

        def interrupt_handler(_signum: int, _frame: object) -> None:
            signal_observed.set()
            raise KeyboardInterrupt

        class SignalAfterRecvmsgSocket(socket.socket):
            def recvmsg(self, *args):
                message = super().recvmsg(*args)
                request_signal.set()
                if not signal_observed.wait(timeout=1.0):
                    raise AssertionError("main thread did not observe SIGINT")
                return message

        def send_process_signal() -> None:
            if not request_signal.wait(timeout=1.0):
                return
            os.kill(os.getpid(), signal.SIGINT)

        sender_thread = threading.Thread(
            target=send_process_signal,
            name="handoff-sigint-sender",
            daemon=True,
        )
        sender_thread.start()
        interrupt_control = SignalAfterRecvmsgSocket(
            socket.AF_UNIX,
            socket.SOCK_SEQPACKET,
            fileno=os.dup(host_control.fileno()),
        )
        try:
            signal.signal(signal.SIGINT, interrupt_handler)
            source.bind(("127.0.0.1", 0))
            source.listen(1)
            self._send_fds(sender_control, [source.fileno()])
            before = self._descriptor_alias_count(source)

            with self.assertRaises(KeyboardInterrupt):
                receive_loopback_listener(
                    interrupt_control,
                    expected_pid=os.getpid(),
                    timeout_seconds=1.0,
                )

            sender_thread.join(timeout=1.0)
            self.assertFalse(sender_thread.is_alive())
            self.assertIs(
                signal.getsignal(signal.SIGINT),
                interrupt_handler,
            )
            self.assertEqual(self._descriptor_alias_count(source), before)
        finally:
            signal.signal(signal.SIGINT, old_handler)
            sender_thread.join(timeout=1.0)
            source.close()
            interrupt_control.close()
            sender_control.close()
            host_control.close()

    def test自定义信号处理器保留原语义并取消时清理fd(self) -> None:
        from icode.linux_proxy_handoff import (
            create_loopback_listener_handoff_channel,
            receive_loopback_listener,
        )

        host_control, sender_control = create_loopback_listener_handoff_channel()
        source = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        old_handler = signal.getsignal(signal.SIGUSR1)
        request_signal = threading.Event()
        signal_observed = threading.Event()
        handler_fd_counts: list[int] = []
        handler_still_installed: list[bool] = []

        def custom_handler(_signum: int, _frame: object) -> None:
            handler_fd_counts.append(self._descriptor_alias_count(source))
            handler_still_installed.append(
                signal.getsignal(signal.SIGUSR1) is custom_handler,
            )
            signal_observed.set()
            raise RuntimeError("custom-handler-raised")

        class SignalAfterRecvmsgSocket(socket.socket):
            def recvmsg(self, *args):
                message = super().recvmsg(*args)
                request_signal.set()
                if not signal_observed.wait(timeout=1.0):
                    raise AssertionError("main thread did not observe SIGUSR1")
                return message

        def send_process_signal() -> None:
            if request_signal.wait(timeout=1.0):
                os.kill(os.getpid(), signal.SIGUSR1)

        sender_thread = threading.Thread(
            target=send_process_signal,
            name="handoff-custom-signal-sender",
            daemon=True,
        )
        sender_thread.start()
        interrupt_control = SignalAfterRecvmsgSocket(
            socket.AF_UNIX,
            socket.SOCK_SEQPACKET,
            fileno=os.dup(host_control.fileno()),
        )
        try:
            signal.signal(signal.SIGUSR1, custom_handler)
            source.bind(("127.0.0.1", 0))
            source.listen(1)
            self._send_fds(sender_control, [source.fileno()])
            before = self._descriptor_alias_count(source)
            with self.assertRaisesRegex(RuntimeError, "custom-handler-raised"):
                receive_loopback_listener(
                    interrupt_control,
                    expected_pid=os.getpid(),
                    timeout_seconds=1.0,
                )

            sender_thread.join(timeout=1.0)
            self.assertFalse(sender_thread.is_alive())
            self.assertEqual(len(handler_fd_counts), 1)
            self.assertEqual(handler_still_installed, [True])
            self.assertIs(signal.getsignal(signal.SIGUSR1), custom_handler)
            self.assertEqual(self._descriptor_alias_count(source), before)
        finally:
            signal.signal(signal.SIGUSR1, old_handler)
            sender_thread.join(timeout=1.0)
            source.close()
            interrupt_control.close()
            sender_control.close()
            host_control.close()

    def test清理阶段取消操作被信号打断后仍关闭未交付socket(self) -> None:
        from icode import linux_proxy_handoff

        listener, peer = socket.socketpair()

        class InterruptOnceEvent:
            def __init__(self) -> None:
                self.interrupted = False
                self.is_cancelled = False

            def set(self) -> None:
                if not self.interrupted:
                    self.interrupted = True
                    raise KeyboardInterrupt
                self.is_cancelled = True

            def is_set(self) -> bool:
                return self.is_cancelled

        class ImmediateThread:
            def __init__(self, *, target, **_kwargs) -> None:
                self._target = target
                self.ident = None

            def start(self) -> None:
                self.ident = 1
                self._target()

            def is_alive(self) -> bool:
                return False

            def join(self, timeout=None) -> None:
                del timeout

        try:
            with (
                mock.patch.object(
                    linux_proxy_handoff.threading,
                    "Event",
                    InterruptOnceEvent,
                ),
                mock.patch.object(
                    linux_proxy_handoff.threading,
                    "Thread",
                    ImmediateThread,
                ),
                mock.patch.object(
                    linux_proxy_handoff,
                    "_receive_loopback_listener_impl",
                    return_value=(listener, _HANDOFF_NONCE),
                ),
            ):
                with self.assertRaises(KeyboardInterrupt):
                    linux_proxy_handoff.receive_loopback_listener(
                        peer,
                        expected_pid=os.getpid(),
                        timeout_seconds=1.0,
                    )

            self.assertEqual(listener.fileno(), -1)
        finally:
            listener.close()
            peer.close()

    def test清理循环中捕获的信号异常不会被吞掉(self) -> None:
        from icode import linux_proxy_handoff

        listener, peer = socket.socketpair()

        class InterruptDuringFinalizerThread:
            def __init__(self, *, target, **_kwargs) -> None:
                self._target = target
                self.ident = None
                self.join_calls = 0

            def start(self) -> None:
                self.ident = 1
                self._target()

            def join(self, timeout=None) -> None:
                del timeout
                self.join_calls += 1
                if self.join_calls == 1:
                    raise KeyboardInterrupt

        try:
            with (
                mock.patch.object(
                    linux_proxy_handoff.threading,
                    "Thread",
                    InterruptDuringFinalizerThread,
                ),
                mock.patch.object(
                    linux_proxy_handoff,
                    "_receive_loopback_listener_impl",
                    return_value=(listener, _HANDOFF_NONCE),
                ),
            ):
                with self.assertRaises(KeyboardInterrupt):
                    linux_proxy_handoff.receive_loopback_listener(
                        peer,
                        expected_pid=os.getpid(),
                        timeout_seconds=1.0,
                    )

            self.assertEqual(listener.fileno(), -1)
        finally:
            listener.close()
            peer.close()

    def test未交付wrapper关闭抛错仍释放原始rights_fd(self) -> None:
        from icode import linux_proxy_handoff

        host_control, sender_control = (
            linux_proxy_handoff.create_loopback_listener_handoff_channel()
        )
        source = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        received_descriptors: list[int] = []

        class CancelAfterAdoption:
            cancelled = False

            def is_set(self) -> bool:
                return self.cancelled

        class CloseRaises:
            def close(self) -> None:
                raise RuntimeError("wrapper close failed")

        cancellation = CancelAfterAdoption()
        parse_ancillary = linux_proxy_handoff._parse_ancillary_data

        def record_received_descriptors(ancillary, descriptors):
            result = parse_ancillary(ancillary, descriptors)
            received_descriptors.extend(descriptors)
            return result

        def adopt_then_cancel(_descriptor: int) -> CloseRaises:
            cancellation.cancelled = True
            return CloseRaises()

        try:
            source.bind(("127.0.0.1", 0))
            source.listen(1)
            self._send_fds(sender_control, [source.fileno()])
            before = self._descriptor_alias_count(source)

            with (
                mock.patch.object(
                    linux_proxy_handoff,
                    "_parse_ancillary_data",
                    side_effect=record_received_descriptors,
                ),
                mock.patch.object(
                    linux_proxy_handoff,
                    "_wrap_received_listener",
                    side_effect=adopt_then_cancel,
                ),
            ):
                with self.assertRaisesRegex(RuntimeError, "wrapper close failed"):
                    linux_proxy_handoff._receive_loopback_listener_impl(
                        host_control,
                        expected_pid=os.getpid(),
                        timeout_seconds=1.0,
                        cancellation=cancellation,
                    )

            self.assertEqual(self._descriptor_alias_count(source), before)
        finally:
            for descriptor in received_descriptors:
                try:
                    os.close(descriptor)
                except OSError:
                    pass
            source.close()
            sender_control.close()
            host_control.close()

    def testThread启动中断且ident未就绪时延迟worker不再访问控制socket(self) -> None:
        from icode import linux_proxy_handoff

        host_control, sender_control = (
            linux_proxy_handoff.create_loopback_listener_handoff_channel()
        )
        source = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        receiver_control = None
        delayed_threads = []

        class DeferredStartThread:
            def __init__(self, *, target, **_kwargs) -> None:
                self._target = target
                self.ident = None

            def start(self) -> None:
                delayed_threads.append(self)
                raise KeyboardInterrupt

            def is_alive(self) -> bool:
                return False

            def join(self, timeout=None) -> None:
                del timeout

        class CountControlSocket(socket.socket):
            getsockopt_calls = 0
            recvmsg_calls = 0

            def getsockopt(self, *args):
                self.getsockopt_calls += 1
                return super().getsockopt(*args)

            def recvmsg(self, *args):
                self.recvmsg_calls += 1
                return super().recvmsg(*args)

        try:
            source.bind(("127.0.0.1", 0))
            source.listen(1)
            self._send_fds(sender_control, [source.fileno()])
            receiver_control = CountControlSocket(
                socket.AF_UNIX,
                socket.SOCK_SEQPACKET,
                fileno=os.dup(host_control.fileno()),
            )

            with mock.patch.object(
                linux_proxy_handoff.threading,
                "Thread",
                DeferredStartThread,
            ):
                with self.assertRaises(KeyboardInterrupt):
                    linux_proxy_handoff.receive_loopback_listener(
                        receiver_control,
                        expected_pid=os.getpid(),
                        timeout_seconds=1.0,
                    )

            before = self._descriptor_alias_count(source)
            delayed_threads[0]._target()
            self.assertEqual(receiver_control.getsockopt_calls, 0)
            self.assertEqual(receiver_control.recvmsg_calls, 0)
            self.assertEqual(self._descriptor_alias_count(source), before)
        finally:
            source.close()
            sender_control.close()
            if receiver_control is not None:
                receiver_control.close()
            host_control.close()

    def test工作线程接收无消息时按时失败关闭(self) -> None:
        from icode.linux_proxy_handoff import (
            ProxyHandoffError,
            create_loopback_listener_handoff_channel,
            receive_loopback_listener,
        )

        host_control, sender_control = create_loopback_listener_handoff_channel()
        outcomes: list[str] = []

        def receive_from_worker() -> None:
            try:
                receive_loopback_listener(
                    host_control,
                    expected_pid=os.getpid(),
                    timeout_seconds=0,
                )
            except ProxyHandoffError:
                outcomes.append("rejected")
            else:
                outcomes.append("received")

        worker = threading.Thread(target=receive_from_worker)
        try:
            worker.start()
            worker.join(timeout=1.0)
            self.assertFalse(worker.is_alive())
            self.assertEqual(outcomes, ["rejected"])
        finally:
            sender_control.close()
            host_control.close()

    def test_解析rights字节被中断时关闭刚解析的fd(self) -> None:
        from icode import linux_proxy_handoff

        host_control, sender_control = (
            linux_proxy_handoff.create_loopback_listener_handoff_channel()
        )
        source = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        real_array_module = linux_proxy_handoff.array

        class InterruptingIntArray:
            def __init__(self) -> None:
                self._values = real_array_module.array("i")

            @property
            def itemsize(self) -> int:
                return self._values.itemsize

            def frombytes(self, payload: bytes) -> None:
                self._values.frombytes(payload)
                raise KeyboardInterrupt

            def __iter__(self):
                return iter(self._values)

        class InterruptingArrayModule:
            @staticmethod
            def array(typecode: str) -> InterruptingIntArray:
                assert typecode == "i"
                return InterruptingIntArray()

        try:
            source.bind(("127.0.0.1", 0))
            source.listen(1)
            self._send_fds(sender_control, [source.fileno()])
            before = self._descriptor_alias_count(source)
            with mock.patch.object(
                linux_proxy_handoff, "array", InterruptingArrayModule(),
            ):
                with self.assertRaises(KeyboardInterrupt):
                    linux_proxy_handoff.receive_loopback_listener(
                        host_control,
                        expected_pid=os.getpid(),
                        timeout_seconds=1.0,
                    )
            self.assertEqual(self._descriptor_alias_count(source), before)
        finally:
            source.close()
            sender_control.close()
            host_control.close()

    def test_创建控制通道被异步中断时关闭两端(self) -> None:
        from icode import linux_proxy_handoff

        created: list[socket.socket] = []
        socketpair = socket.socketpair

        def record_socketpair(*args, **kwargs):
            endpoints = socketpair(*args, **kwargs)
            created.extend(endpoints)
            return endpoints

        with mock.patch.object(
            linux_proxy_handoff.socket, "socketpair", side_effect=record_socketpair,
        ), mock.patch.object(
            linux_proxy_handoff.os,
            "set_inheritable",
            side_effect=KeyboardInterrupt,
        ):
            with self.assertRaises(KeyboardInterrupt):
                linux_proxy_handoff.create_loopback_listener_handoff_channel()

        try:
            self.assertEqual([endpoint.fileno() for endpoint in created], [-1, -1])
        finally:
            for endpoint in created:
                endpoint.close()


if __name__ == "__main__":
    unittest.main()
