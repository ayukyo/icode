# Linux B1 channel 工厂失败收尾 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use nbl.subagent-driven-development (recommended) or nbl.executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 两个 channel 工厂在初始化失败后，独立且各一次收尾已取得的端点；关闭异常后解除 socket 对象 owning，保留原异常合同。

**Architecture:** 复用 `_select_cleanup_error`，在两个局部工厂增加基类 detach 防御；detach 不是 FD 释放确认，返回整数不得重试。成功 tuple、flags、签名、caller owning、broker 与旧 None 调用形状不变；不引入 callback 或资源管理框架。

**Tech Stack:** Python 3.11+、Linux AF_UNIX/SOCK_SEQPACKET、unittest、既有 `.venv` 与 preflight。

---

批准依据：[B1 DESIGN](../specs/2026-10-12-linux-channel-factory-cleanup-design.md)，SHA256 `02847d0856ccdf81b4b89dd7b90645276949c6d158bbda04d69b913a2a5d77b1`；独立 SPEC→不同 QUALITY 正式 C0/I0/M0 后才编写本计划。基线 main `d52ebcc011f4bb9a37627a38d8eb4af18f4f7d25`。计划最初仅 DOCS ONLY，资产本身不授实际实施/正式 RED/GREEN 信用；随后 root 分阶段授权的实际进度见本文实施证据。

三问已确认：seccomp 原清理会因 sender.close 的 RuntimeError 跳过 host 并覆盖原 KI/SE；task 已有独立清理和异常选择机制；两工厂→既有 broker 创建窗口及旧直接 caller。S1c construction_failed 只结束消费，不证明工厂内部回收。本片只处理已取得端点；opaque socketpair、scope 临时 FD、parser/start/listener、receiver opaque selector仍为独立债务，不授 native/CP/installed/R2/R3 信用。

精确七路径及职责：

| 路径 | 允许变化 |
| --- | --- |
| `src/icode/linux_task_resource.py` | 仅 channel 工厂 close 异常后基类 detach |
| `src/icode/linux_seccomp_notify.py` | 仅 channel 工厂逐项清理/选择首异常/基类 detach与私有 helper import |
| `tests/test_linux_channel_factory_cleanup.py` | 新真实 socket/FD 故障边界测试 |
| `tests/test_linux_prepared_broker.py` | 仅唯一真实 seccomp fixture 方法配对卫生调整 |
| `docs/nbl/specs/2026-10-12-linux-channel-factory-cleanup-design.md` | 已批准设计与实际证据 |
| `docs/nbl/plans/2026-10-12-linux-channel-factory-cleanup.md` | 本执行资产与实际证据 |
| `docs/agent-landscape-live.md` | root 记录固定 CPython 研究/取舍与阶段事实 |

所有命令 cwd=`/home/orbbec/git/icode`。main-only，不新增 branch/worktree；broker、S1c其余方法、vendor/native/CI/母设计均只读。下列代码和差分是未来执行资产，不表示已经落盘。各 task fresh 作者、串行；作者不得自行 fullguard/提交/交接。

## Task 1：旧 fixture 配对与新测试先行

**状态**

- [x] 任务完成

**Dependencies:** None（已批准 DESIGN；fresh 测试作者先完整读两工厂与旧 fixture）
**Parallelizable:** No（root 核旧 fixture GREEN与正式新 RED后才放 SOURCE）

- [x] **Step 1：只在旧 fixture 的唯一方法应用以下差分，原 SOURCE下先独立 GREEN。**

~~~diff
--- a/tests/test_linux_prepared_broker.py
+++ b/tests/test_linux_prepared_broker.py
@@ -436,6 +436,6 @@
         view = self.bind(self.attach(scope))
         self.precheck_fixture()
-        held, attempts = [], []
+        held, attempts, host_fds = [], [], []
         actual_pair = seccomp.socket.socketpair
         actual_set_inheritable = seccomp.os.set_inheritable
         class UnknownHost(seccomp.socket.socket):
@@ -446,5 +446,6 @@
             host, sender = actual_pair(*args, **kwargs)
             host = UnknownHost(fileno=host.detach())
+            host_fds.append(host.fileno())
             held.extend((host, sender))
             return host, sender
         def inheritable(descriptor, value):
@@ -462,7 +463,7 @@
             self.assertIsNone(error)
             self.assertEqual(answer.error, 'isolation_unavailable')
             self.assertEqual(len(held), 2)
-            descriptor = held[0].fileno()
+            descriptor = host_fds[0]
             self.assertEqual(attempts, [descriptor])
             self.assertTrue(stat.S_ISSOCK(os.fstat(descriptor).st_mode))
             self.assertFalse(scope._inflight)
@@ -475,5 +476,9 @@
                     pass
         finally:
-            # Test hygiene only; A does not recover this unreturned socket.
-            for endpoint in held:
-                seccomp.socket.socket.close(endpoint)
+            # Before-close injection guarantees this saved FD remains live.
+            # Test hygiene only: detach is not production release credit.
+            if held:
+                seccomp.socket.socket.detach(held[0])
+                os.close(host_fds[0])
+            if len(held) == 2:
+                seccomp.socket.socket.close(held[1])
~~~

~~~sh
.venv/bin/python -B -m unittest tests.test_linux_prepared_broker.PreparedBrokerTests.test_construction_seccomp_real_unreturned_socket_target -v
~~~

期待 1方法、0FAIL/error/skip、exit0；保存真实 host FD仍 live、close恰一次、attachment faulted与下一 borrow拒绝均不变。其余旧方法字节不改；不得在此加 fileno==-1新目标，避免把 SOURCE行为要求混入旧适配。

- [x] **Step 2：仅用 apply_patch 新增以下完整测试文件。**

~~~python
"""Real socket ownership boundaries; Linux software only, no native/CP credit."""
from __future__ import annotations

import os
import socket
import stat
import sys
import types
import unittest
from unittest.mock import patch

REAL_SOCKET = socket.socket
REAL_PAIR = socket.socketpair
REAL_DETACH = REAL_SOCKET.detach
if sys.platform.startswith('linux'):
    from icode import linux_seccomp_notify as seccomp
    from icode import linux_task_resource as resource
    FACTORIES = ((resource, resource.create_task_resource_channel,
                  resource.LinuxTaskResourceError, 'Linux task resource channel is invalid'),
                 (seccomp, seccomp.create_seccomp_listener_handoff_channel,
                  seccomp.LinuxSeccompNotificationError, 'Linux seccomp notifications unavailable'))
else:
    FACTORIES = ()


@unittest.skipUnless(sys.platform.startswith('linux'),
    'Linux real-socket fixture; skip is not acceptance')
class ChannelFactoryCleanupTests(unittest.TestCase):
    def exercise(self, module, factory, body, failures, *, detach_error=None):
        held, descriptors, attempts, replacements = [], [], [], []
        test = self

        class Endpoint(REAL_SOCKET):
            def setsockopt(self, *args):
                if self is held[0]:
                    raise body
                return super().setsockopt(*args)

            def detach(self):
                raise AssertionError('factory used overridable detach')

            def close(self):
                index = held.index(self)
                attempts.append(index)
                failure = failures.get(index)
                if failure is None:
                    return REAL_SOCKET.close(self)
                mode, error = failure
                if mode == 'after':
                    descriptor = self.fileno()
                    REAL_SOCKET.close(self)
                    replacement = os.open('/dev/null', os.O_RDONLY)
                    if replacement != descriptor:
                        os.dup2(replacement, descriptor)
                        os.close(replacement)
                    replacements.append(descriptor)
                raise error

        def pair(*args, **kwargs):
            test.assertEqual(args, (socket.AF_UNIX, socket.SOCK_SEQPACKET))
            test.assertEqual(kwargs, {})
            for endpoint in REAL_PAIR(*args, **kwargs):
                wrapped = Endpoint(fileno=REAL_DETACH(endpoint))
                held.append(wrapped)
                descriptors.append(wrapped.fileno())
            return tuple(held)

        def inheritable(descriptor, value):
            test.assertEqual(value, False)
            raise body

        class DetachBoundary:
            @staticmethod
            def detach(endpoint):
                if endpoint is held[1] and detach_error is not None:
                    raise detach_error
                return REAL_DETACH(endpoint)

        boundary = types.SimpleNamespace(socketpair=pair,
            socket=REAL_SOCKET if detach_error is None else DetachBoundary,
            AF_UNIX=socket.AF_UNIX, SOCK_SEQPACKET=socket.SOCK_SEQPACKET,
            SOL_SOCKET=socket.SOL_SOCKET, SO_PASSCRED=socket.SO_PASSCRED)
        captured = None
        try:
            with patch.object(module, 'socket', boundary), \
                    patch.object(module.os, 'set_inheritable', side_effect=inheritable):
                try:
                    factory()
                except BaseException as error:
                    captured = error
            return captured, held, descriptors, attempts, replacements
        except BaseException:
            self.hygiene(held, descriptors, failures, replacements)
            raise

    def hygiene(self, held, descriptors, failures, replacements):
        # Only the controlled before-close injection guarantees saved FD live.
        for index, endpoint in enumerate(held):
            descriptor = REAL_DETACH(endpoint)
            if descriptor >= 0:
                os.close(descriptor)
            elif failures.get(index, ('', None))[0] == 'before':
                os.close(descriptors[index])
        for descriptor in replacements:
            os.close(descriptor)

    def test_seccomp_original_signal_and_independent_host_close(self):
        for signal in (KeyboardInterrupt('body'), SystemExit(29)):
            with self.subTest(signal=type(signal).__name__):
                failures = {1: ('before', RuntimeError('sender close'))}
                answer = self.exercise(seccomp,
                    seccomp.create_seccomp_listener_handoff_channel, signal, failures)
                error, held, fds, attempts, replacements = answer
                try:
                    self.assertTrue(stat.S_ISSOCK(os.fstat(fds[1]).st_mode))
                    self.assertIs(error, signal)
                    self.assertEqual(attempts, [1, 0])
                    self.assertEqual([endpoint.fileno() for endpoint in held], [-1, -1])
                finally:
                    self.hygiene(held, fds, failures, replacements)

    def test_both_factories_disarm_before_close_without_release_credit(self):
        for module, factory, kind, message in FACTORIES:
            with self.subTest(factory=factory.__name__):
                failures = {0: ('before', OSError('host close')),
                            1: ('before', RuntimeError('sender close'))}
                answer = self.exercise(module, factory, OSError('init'), failures)
                error, held, fds, attempts, replacements = answer
                try:
                    self.assertTrue(all(stat.S_ISSOCK(os.fstat(fd).st_mode) for fd in fds))
                    self.assertIs(type(error), kind)
                    self.assertEqual(str(error), message)
                    self.assertEqual(attempts, [1, 0])
                    self.assertEqual([endpoint.fileno() for endpoint in held], [-1, -1])
                finally:
                    self.hygiene(held, fds, failures, replacements)

    def test_cleanup_signal_selected_and_original_signal_retained(self):
        for module, factory, _kind, _message in FACTORIES:
            for received in (RuntimeError('body'), KeyboardInterrupt('body'), SystemExit(31)):
                for cleanup in (KeyboardInterrupt('close'), SystemExit(32)):
                    with self.subTest(factory=factory.__name__, body=type(received).__name__,
                                      cleanup=type(cleanup).__name__):
                        failures = {1: ('before', cleanup), 0: ('before', SystemExit(33))}
                        answer = self.exercise(module, factory, received, failures)
                        error, held, fds, attempts, replacements = answer
                        try:
                            self.assertIs(error, cleanup if isinstance(received, Exception) else received)
                            self.assertEqual(attempts, [1, 0])
                            self.assertEqual([endpoint.fileno() for endpoint in held], [-1, -1])
                        finally:
                            self.hygiene(held, fds, failures, replacements)

    def test_after_close_reused_integer_is_not_retried(self):
        for module, factory, _kind, _message in FACTORIES:
            with self.subTest(factory=factory.__name__):
                body = RuntimeError('body')
                failures = {1: ('after', OSError('close after release'))}
                answer = self.exercise(module, factory, body, failures)
                error, held, fds, attempts, replacements = answer
                try:
                    self.assertEqual(replacements, [fds[1]])
                    self.assertTrue(stat.S_ISCHR(os.fstat(fds[1]).st_mode))
                    self.assertIs(error, body)
                    self.assertEqual(attempts, [1, 0])
                    self.assertEqual([endpoint.fileno() for endpoint in held], [-1, -1])
                finally:
                    self.hygiene(held, fds, failures, replacements)

    def test_detach_failure_still_attempts_host_and_keeps_first_signal(self):
        for module, factory, _kind, _message in FACTORIES:
            for body in (RuntimeError('body'), KeyboardInterrupt('body'), SystemExit(34)):
                with self.subTest(factory=factory.__name__, body=type(body).__name__):
                    detached = KeyboardInterrupt('detach')
                    failures = {1: ('before', OSError('sender close'))}
                    answer = self.exercise(module, factory, body, failures, detach_error=detached)
                    error, held, fds, attempts, replacements = answer
                    try:
                        self.assertTrue(stat.S_ISSOCK(os.fstat(fds[1]).st_mode))
                        self.assertIs(error, detached if isinstance(body, Exception) else body)
                        self.assertEqual(attempts, [1, 0])
                        self.assertEqual(held[0].fileno(), -1)
                        self.assertEqual(held[1].fileno(), fds[1])
                    finally:
                        self.hygiene(held, fds, failures, replacements)

    def test_ordinary_initialization_contract(self):
        for module, factory, kind, message in FACTORIES:
            for body in (OSError('init'), RuntimeError('init')):
                with self.subTest(factory=factory.__name__, body=type(body).__name__):
                    answer = self.exercise(module, factory, body, {})
                    error, held, fds, attempts, replacements = answer
                    try:
                        if isinstance(body, OSError):
                            self.assertIs(type(error), kind)
                            self.assertEqual(str(error), message)
                        else:
                            self.assertIs(error, body)
                        self.assertEqual(attempts, [1, 0])
                        self.assertEqual([endpoint.fileno() for endpoint in held], [-1, -1])
                    finally:
                        self.hygiene(held, fds, {}, replacements)

    def test_success_tuple_flags_and_caller_ownership(self):
        for module, factory, _kind, _message in FACTORIES:
            with self.subTest(factory=factory.__name__):
                endpoints = factory()
                try:
                    self.assertIs(type(endpoints), tuple)
                    self.assertEqual(len(endpoints), 2)
                    for endpoint in endpoints:
                        self.assertIs(type(endpoint), REAL_SOCKET)
                        self.assertTrue(stat.S_ISSOCK(os.fstat(endpoint.fileno()).st_mode))
                        self.assertFalse(endpoint.get_inheritable())
                        self.assertEqual(endpoint.getsockopt(socket.SOL_SOCKET, socket.SO_TYPE),
                                         socket.SOCK_SEQPACKET)
                    if module is resource:
                        self.assertEqual(endpoints[0].getsockopt(socket.SOL_SOCKET, socket.SO_PASSCRED), 1)
                finally:
                    for endpoint in endpoints:
                        endpoint.close()

    def test_nonlinux_fixed_refusal_before_pair(self):
        for module, factory, kind, message in FACTORIES:
            with self.subTest(factory=factory.__name__):
                with patch.object(module.sys, 'platform', 'win32'), \
                        patch.object(module.socket, 'socketpair') as pair:
                    with self.assertRaises(kind) as raised:
                        factory()
                self.assertEqual(str(raised.exception), message)
                pair.assert_not_called()


if __name__ == '__main__':
    unittest.main()
~~~

该文件以单尾 LF落盘。顶层仅Linux条件导入两组件并建立FACTORIES；其他平台FACTORIES为空，类8方法全部skip，避免seccomp的fcntl在collection前失败。只替换工厂模块的 `socket` 绑定；detach 失败通过可执行边界类注入，不 patch不可写的 C类型属性。真实pair/FD与基类 close/detach预先保存；覆写的 endpoint.detach 是拒绝负控。before-close明确留真实FD，after-close明确实际close且数字复用为新资源；fixture卫生不计生产释放。

- [x] **Step 3：作者与 root 分别在原两源码正式执行 RED并记录真实输出。**

~~~sh
.venv/bin/python -B -m unittest tests.test_linux_channel_factory_cleanup -v
.venv/bin/python -B -m unittest tests.test_linux_channel_factory_cleanup.ChannelFactoryCleanupTests.test_seccomp_original_signal_and_independent_host_close tests.test_linux_channel_factory_cleanup.ChannelFactoryCleanupTests.test_both_factories_disarm_before_close_without_release_credit -v
git diff --check
~~~

期待新模块 exit1，至少上述两个目标出现有效 assertion FAIL，0error/skip：seccomp 原 KI/SE对象被 sender RuntimeError覆盖或 host未尝试；两工厂 before-close对象 fileno仍原FD或 host未尝试。其他信号/detach目标亦可出现 assertion FAIL。成功/普通初始化/nonLinux控制应 GREEN；after-close数字复用负控可旧SOURCE已GREEN，不伪称其RED。不能以缺符号、fixture TypeError、缺属性、卫生异常计RED；先修测试再重复原SOURCE。root全读文件、核真实FD前置和自身独立RED后冻结测试；未获 GO不能写 SOURCE。

## Task 2：不同作者的最小两工厂修复

**状态**

- [x] 任务完成

**Dependencies:** Task 1（root正式有效RED与原SOURCE摘要已记录）
**Parallelizable:** No（fresh SOURCE作者，不修改测试；仅两factory）

- [x] **Step 1：对冻结基线应用以下最小差分。**

~~~diff
--- a/src/icode/linux_task_resource.py
+++ b/src/icode/linux_task_resource.py
@@ -54,6 +54,11 @@
                 try:
                     endpoint.close()
                 except BaseException as cleanup_error:
                     selected = _select_cleanup_error(selected, cleanup_error)
+                    try:
+                        # Disarm automatic owning; an unknown FD must not be retried.
+                        socket.socket.detach(endpoint)
+                    except BaseException as detach_error:
+                        selected = _select_cleanup_error(selected, detach_error)
         if selected is not error:
             raise selected
~~~

~~~diff
--- a/src/icode/linux_seccomp_notify.py
+++ b/src/icode/linux_seccomp_notify.py
@@ -20,4 +20,6 @@
 import threading
 import time
-
+
+from .linux_task_resource import _select_cleanup_error
+
 _HANDOFF_MESSAGE = b"ICODE_SECCOMP_LISTENER_V1"
@@ -59,9 +61,17 @@
     except BaseException as exc:
+        selected = exc
         for endpoint in (sender_control, host_control):
             if endpoint is not None:
                 try:
                     endpoint.close()
-                except OSError:
-                    pass
+                except BaseException as cleanup_error:
+                    selected = _select_cleanup_error(selected, cleanup_error)
+                    try:
+                        # Disarm automatic owning; an unknown FD must not be retried.
+                        socket.socket.detach(endpoint)
+                    except BaseException as detach_error:
+                        selected = _select_cleanup_error(selected, detach_error)
+        if selected is not exc:
+            raise selected
         if isinstance(exc, OSError):
             raise LinuxSeccompNotificationError(
~~~

基类 detach每次失败 close后仅一次；detach自身异常也被记录并继续另一端点，不声称解除成功。普通 body+普通 cleanup保留 body，OSError仍固定公开错误；body KI/SE保留首对象，普通body遇清理KI/SE仍按原 helper选择；不新增排名、整数 retry或公开字段。成功路径不变。

- [x] **Step 2：作者运行新模块与原33/163回归，root独立重复。**

~~~sh
.venv/bin/python -B -m unittest tests.test_linux_channel_factory_cleanup -v
.venv/bin/python -B -m unittest tests.test_linux_prepared_broker tests.test_linux_resource_cleanup -v
.venv/bin/python -B -m unittest tests.test_linux_prepared_step tests.test_linux_helper_dispatch tests.test_execution_broker tests.test_linux_task_resource tests.test_linux_violation_receipt tests.test_linux_helper_object -v
git diff --check
~~~

期待新8方法、原33、旧163均0FAIL/error/skip、exit0；若 native/OS旧skip实际发生必须独立登记，不能宣称零skip或软件fixture供应native信用。root全读完整工厂模块与新test/diff，核旧fixture仅唯一方法改变、broker/S1c其他方法无变化；原None兼容方法在原33内复验。源码再变化使此前冻结失效。

## Task 3：fresh双审、原完整预检与七路径发布

**状态**

- [ ] 任务完成

**Dependencies:** Task 2
**Parallelizable:** No（先SOURCE SPEC再不同QUALITY；root唯一完整preflight）

- [x] **Step 1：fresh SOURCE SPEC全文对照DESIGN/PLAN/实际源码测试，再不同QUALITY独立审查。**

两审分别核真实FD负控、close各一次、原首信号、detach自身异常、override避开、after-close复用未误关、固定普通error与成功/None/签名合同。任一I/C先返修、重新正式目标测试与两审；不拿RAM或旧S1c审查信用替代。两个阶段：PLAN也须先fresh SPEC→不同QUALITY零遗留才派Task1；SOURCE双审在实施后进行。

- [x] **Step 2：source/test冻结后root一次原完整preflight，最多-j1。**

~~~sh
validation_log_dir=$(mktemp -d /tmp/icode-b1-preflight.XXXXXX)
printf '%s\n' "$validation_log_dir/typescript"
script -q -e -f -c 'CMAKE_BUILD_PARALLEL_LEVEL=1 MAKEFLAGS=-j1 .venv/bin/python -B -u scripts/preflight.py' "$validation_log_dir/typescript"
~~~

记录原log、started/done、三guard/exit；不替换原入口、不推测未输出测试总数。等待期间仅DOCS/只读观察。source/test再改撤销本次信用。

- [x] **Step 3：root填写实际证据与live取舍，最终文档改后原scanner连续两遍。**

~~~sh
.venv/bin/python -B /home/orbbec/.agents/skills/doc-contract-consistency-audit/scripts/check_consistency.py docs/nbl/plans/2026-10-12-linux-channel-factory-cleanup.md docs/nbl/specs/2026-10-12-linux-channel-factory-cleanup-design.md docs/agent-landscape-live.md
.venv/bin/python -B /home/orbbec/.agents/skills/doc-contract-consistency-audit/scripts/check_consistency.py docs/nbl/plans/2026-10-12-linux-channel-factory-cleanup.md docs/nbl/specs/2026-10-12-linux-channel-factory-cleanup-design.md docs/agent-landscape-live.md
git diff --check
.venv/bin/python -B scripts/preflight.py --only secrets
.venv/bin/python -B scripts/preflight.py --only submodule
~~~

记录raw finding/exit并逐项人工判定；fence参数/异常误报不可称raw=0，不改scanner。核vendor固定且clean，不读KEY正文/复制/上传。研究采用固定CPython v3.11.15/PSF-2.0已观察close先使sock_fd无效再sysclose、detach只移交整数；Python中断/替换故障另行真实负控，不能把detach或GC授OS回收信用。精确源码锚/日期与采纳/暂缓/不适配在live由root写，不复制上游代码、不新增依赖权限。旧d52ebcc三工作流收齐terminal才下一push。

- [ ] **Step 4：root冻结七路径bytes，精确stage/cached校核后commit/push main。**

~~~sh
git branch --show-current
git add src/icode/linux_task_resource.py src/icode/linux_seccomp_notify.py tests/test_linux_channel_factory_cleanup.py tests/test_linux_prepared_broker.py docs/agent-landscape-live.md
git add -f docs/nbl/specs/2026-10-12-linux-channel-factory-cleanup-design.md docs/nbl/plans/2026-10-12-linux-channel-factory-cleanup.md
git diff --cached --check
.venv/bin/python -B - <<'PY'
from pathlib import Path
import hashlib
import subprocess
paths = ['src/icode/linux_task_resource.py', 'src/icode/linux_seccomp_notify.py',
         'tests/test_linux_channel_factory_cleanup.py', 'tests/test_linux_prepared_broker.py',
         'docs/nbl/specs/2026-10-12-linux-channel-factory-cleanup-design.md',
         'docs/nbl/plans/2026-10-12-linux-channel-factory-cleanup.md',
         'docs/agent-landscape-live.md']
assert subprocess.check_output(['git', 'branch', '--show-current'], text=True).strip() == 'main'
staged = subprocess.check_output(['git', 'diff', '--cached', '--name-only', '-z']).decode().split('\0')[:-1]
assert set(staged) == set(paths) and len(staged) == 7, staged
for path in paths:
    work = Path(path).read_bytes()
    index = subprocess.check_output(['git', 'show', ':' + path])
    assert work == index, path
    print(hashlib.sha256(work).hexdigest(), path)
PY
git commit -m "fix(linux): independently clean acquired channel endpoints"
git push origin main
git ls-remote --heads origin main
~~~

只在全部门通过和七路径精确相等时执行；保存冻结摘要与真实commit/push/remote main。若DESIGN最终补实际证据改变批准SHA，区分批准设计原摘要与证据追加，不冒称原字节不变。随后只读收同SHA三工作流终态；CI不能代替本地正式RED/完整guard或设备验证。不得stage母设计/vendor/CI/unrelated。

## 实际实施证据（2026-10-12，有限软件范围）

批准执行的 PLAN 为 `78356eecc3ad8b885969ae4be787d1bceda708f7fc15ea3e854a39c576418e3c`，经独立 SPEC→不同 QUALITY C0/I0/M0；以下为随后追加的事实，不冒称当前文档仍是批准摘要。此前 Windows collection I1 已用仅新测试条件导入修订；模拟8skip不是原生信用。

Task1 作者仅两测试路径：旧唯一fixture先在原SOURCE单方法GREEN，作者/root分别0.053s/0.054s；新实际模块作者/root随后8方法18有效assertion FAIL、0error/skip、exit1，分别0.009s/0.008s；两目标各2方法4有效assertion FAIL、0error/skip、exit1，均0.002s。root全文实际新文件和旧唯一diff；真实FD留存前置通过，不以卫生或缺模块计RED。原两SOURCE摘要仍为3f2317f3/740eaca9。

不同Task2作者随后仅批准的两源码差分；作者新8/0.006s、原33/2.165s、旧163/21.335s均0F/E/skip。root实际新8/0.008s、原33/2.197s、旧163/21.367s亦全过，compileall-j1、site、governance与diff检查通过。实际task/seccomp与两测试摘要完全等于本计划资产；已停止SOURCE/test编辑。实际SOURCE双审、原完整预检和七路径发布仍待，不授工厂opaque内部、native/CP/installed或R2/R3整体验收。

随后 fresh 实际 SOURCE SPEC C0/I0/M0、独立41/2.366s；不同 QUALITY C0/I0/M0、独立41/2.436s，均0F/E/skip。root 原唯一 fullguard session13290，日志 `/tmp/icode-b1-preflight.QZ6CTH/typescript`，05:45:12 UTC已观察启动，编译并发j1；05:46:09 UTC密钥/子模块已通过，全量测试进行中。四SOURCE/test冻结未变；完整guard返回及七路径发布仍待。

该原完整预检随后真实 exit0，原日志footer2026-10-12 05:55:18 UTC，root05:55:23 UTC取得三门全通过；原入口不输出全量测试数量，不能从远端3163推猜本次数量。当前仅授本片有限软件门，最后文档 scanner、fresh secret/submodule 与七路径 index检查及发布仍在进行。

最终证据补入后三文档原scanner已连续两轮raw0、exit0，fresh secret/submodule各exit0。此次记录后再次运行原scanner两轮与单门，以最终文档字节为准；七路径提交命令仍待root核index/工作相等后执行，本文不预写commit SHA或整体完成。

## 计划自检与执行边界

规格覆盖：Task1旧fixture配对先GREEN、新正式RED；Task2两端点独立收尾、基类detach、原异常/成功合同；Task3两阶段双审、fullguard、scanner两轮及七路径发布。执行顺序纯链、fresh测试作者→root正式RED→不同fresh源码作者；所有RAM投影/compile/诊断仅资产可行性，不能计实际实施。

PLAN QUALITY I1修订：原新test无条件importseccomp，使Windows缺fcntl在skip装饰器前collection失败；仅修正文档资产的条件导入/FACTORIES，8方法保留，未改SOURCE/test磁盘文件。fresh PLAN SPEC→不同QUALITY须重新审查，不沿用旧freeze。

PLAN作者RAM诊断（不计正式执行信用）：严格唯一上下文/行数/位置投影三份差分及完整新test compile通过；旧唯一fixture在原SOURCE投影1方法、0FAIL/error/skip；最终修订新test在Linux原SOURCE RAM为8方法、18有效assertionFAIL、0error/skip，在拟修SOURCE RAM为8方法、0FAIL/error/skip。另在Ubuntu解释器预载标准库unittest.mock后，模拟sys.platform=win32并禁止fcntl import，完整新资产可导入/collection、8方法全skip、0FAIL/error、fcntl import尝试0次。此模拟仅核本资产导入守卫，不供应真实Windows运行信用；不能在Linux强切平台后要求标准库加载不存在的Windows _overlapped扩展。实际正式执行仍须Task1作者与root各自RED、不同Task2作者和root GREEN。

资产SHA256（文件口径单尾LF）：新test `99809b76cf607b4e9fa920b8913ed9b4f9d98b514e5d4ffdc3eed384eac1fa96`；唯一旧fixture投影 `ceb362432fe795afa9c3e1c5d3c81b695d540717ef0f85f9953837a56b51a620`；task SOURCE投影 `f75932afa50ab6bc82af9a4019211d3ec22b535a6594565dd2189cc99e65a217`；seccomp SOURCE投影 `9642ec65260b847705d6447daf02e073f880806c30136632f2931e2bc333fc8f`。执行前核基线与资产，摘要不替测试。

【架构级自检报告】（计划资产，不是实施结果）

- 语法/编译：完整代码及差分RAM compile/严格唯一上下文投影通过；生产未改，不报告生产编译通过。
- 依赖/调用链：复用既有 `_select_cleanup_error`；seccomp→task私有helper，无反向import；broker不改。
- 逻辑/边界：before/after-close分开，detach不释放、数字不retry、成功caller owning保留。
- 异常处理：覆盖原KI/SE、清理KI/SE、普通error及detach失败后另一端点继续；无回收信用冒领。
- 关联模块：七路径明确，旧fixture仅唯一method；原33/163与None兼容必验。
- 兼容安全：签名/flags/tuple/固定消息不变，无callbacks/框架/依赖/权限新增。
- 可运行性：仅计划资产自审，正式RED/GREEN、双审与preflight尚待执行，不报告100%。

**Execution Mode:** serial

原writer交付后已停止。root 的 DOCS ONLY委派与用户main-only要求覆盖skill自动handoff/worktree建议；root完成fresh PLAN SPEC→不同QUALITY后才按上述任务分别授权测试和源码作者。writer无权自动启动实施、凭据读取、完整guard或GIT写操作。
