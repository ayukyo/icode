"""Private trusted-host lifecycle, not CP/runner or isolation authorization."""
from __future__ import annotations
from contextlib import contextmanager
import os
import stat
import sys
import threading
from .isolation import LandlockSandbox
from .linux_helper_object import open_linux_helper_object
from .linux_static_helper import validate_static_linux_helper
from .linux_helper_source import observe_linux_helper_source, _source_paths
from .sandbox_policy import SandboxPolicy
from .workspace import WorkspaceSession, TicketLease, _WorkspaceObject

_ERROR = 'Linux prepared step is unavailable'

class LinuxPreparedStepError(RuntimeError):
    def __init__(self):
        super().__init__(_ERROR)

def _raise(error):
    if not isinstance(error, Exception):
        raise error
    raise LinuxPreparedStepError() from None

def _cleanup_choice(body, cleanup):
    # First signal survives; ordinary body cannot conceal unknown cleanup.
    return body if body is not None and not isinstance(body, Exception) else cleanup

def _names(session):
    return session.project_id, session.ticket_id, session.run_id

def _directory_binding(session, policy):
    if not isinstance(session, WorkspaceSession) or not isinstance(policy, SandboxPolicy):
        raise LinuxPreparedStepError()
    policy.validate()
    if (session.ticket_id != policy.ticket_id or session.run_id != policy.run_id
            or session.workspace_root != policy.workspace_root):
        raise LinuxPreparedStepError()
    lease = session.lease
    if not isinstance(lease, TicketLease) or _names(lease) != _names(session):
        raise LinuxPreparedStepError()
    lease._validate_active()
    obj = session._workspace_object
    if not isinstance(obj, _WorkspaceObject):
        raise LinuxPreparedStepError()
    fd, expected = session.workspace_fd, session.workspace_fd_identity
    if type(fd) is not int or fd < 3 or type(expected) is not tuple or len(expected) != 2:
        raise LinuxPreparedStepError()
    if any(type(value) is not int for value in expected):
        raise LinuxPreparedStepError()
    held, path = os.fstat(fd), os.lstat(session.workspace_root)
    if (not stat.S_ISDIR(held.st_mode) or not stat.S_ISDIR(path.st_mode)
            or (held.st_dev, held.st_ino) != expected
            or (path.st_dev, path.st_ino) != expected):
        raise LinuxPreparedStepError()
    return lease, obj, fd, expected

class LinuxPreparedStep:
    def __init__(self, sandbox, *, policy, workspace_session):
        owner = None
        try:
            if not sys.platform.startswith('linux') or not isinstance(sandbox, LandlockSandbox):
                raise LinuxPreparedStepError()
            lease, obj, fd, identity = _directory_binding(workspace_session, policy)
            sandbox.prepare_policy(policy)
            _, _, binary, manifest = _source_paths(sandbox)
            self._sandbox, self._policy, self._session = sandbox, policy, workspace_session
            self._lease, self._workspace_object = lease, obj
            self._workspace_fd, self._workspace_identity = fd, identity
            self._workspace_root = workspace_session.workspace_root
            self._session_names = _names(workspace_session)
            self._policy_names = (policy.ticket_id, policy.run_id, policy.step)
            self._policy_hash = policy.policy_hash
            self._sandbox_paths = (sandbox.helper, sandbox.manifest)
            self._gate = threading.RLock()
            self._attachment, self._inflight = None, False
            self._consume_state, self._owner_state = 'prepared', 'active'
            # One owning factory; resolver has no owner creation/fallback.
            owner = open_linux_helper_object(binary, manifest)
            self._owner = owner
            self._helper_fd = owner.fileno()
            held = os.fstat(self._helper_fd)
            self._helper_identity = held.st_dev, held.st_ino
            self._helper_metadata = owner.architecture, owner.sha256
            validate_static_linux_helper(owner)
            source = observe_linux_helper_source(sandbox, policy=policy, owner=owner)
            self._source_binding = (source.helper_path, source.manifest_path, source.directory_identities)
            self._check(policy=policy, workspace_session=workspace_session)
        except BaseException as body:
            selected = body
            if owner is not None:
                try:
                    owner.close()
                except BaseException as cleanup:
                    selected = _cleanup_choice(body, cleanup)
            _raise(selected)

    def _check(self, *, policy, workspace_session):
        try:
            if policy is not self._policy or workspace_session is not self._session:
                raise LinuxPreparedStepError()
            if self._owner_state != 'active':
                raise LinuxPreparedStepError()
            lease, obj, fd, identity = _directory_binding(workspace_session, policy)
            if (lease is not self._lease or obj is not self._workspace_object
                    or fd != self._workspace_fd or identity != self._workspace_identity
                    or workspace_session.workspace_root != self._workspace_root
                    or _names(workspace_session) != self._session_names
                    or (policy.ticket_id, policy.run_id, policy.step) != self._policy_names
                    or policy.policy_hash != self._policy_hash
                    or (self._sandbox.helper, self._sandbox.manifest) != self._sandbox_paths):
                raise LinuxPreparedStepError()
            helper_fd = self._owner.fileno()
            held = os.fstat(helper_fd)
            if (helper_fd != self._helper_fd
                    or (held.st_dev, held.st_ino) != self._helper_identity
                    or (self._owner.architecture, self._owner.sha256) != self._helper_metadata):
                raise LinuxPreparedStepError()
            validate_static_linux_helper(self._owner)
            try:
                source = observe_linux_helper_source(self._sandbox, policy=policy, owner=self._owner)
            except BaseException:
                # Source uses one fixed error for body/temporary cleanup unknown.
                # Conservatively block all further consumption; creator still owns helper.
                self._consume_state = 'faulted'
                raise
            if (source.helper_path, source.manifest_path, source.directory_identities) != self._source_binding:
                raise LinuxPreparedStepError()
        except BaseException as error:
            _raise(error)

    def _attach(self, *, policy, workspace_session):
        try:
            with self._gate:
                if self._consume_state != 'prepared':
                    raise LinuxPreparedStepError()
                self._check(policy=policy, workspace_session=workspace_session)
                view = object.__new__(_LinuxStepAttachment)
                view._scope, view._attempt, view._validator = self, None, None
                self._attachment, self._consume_state = view, 'attached_pending'
                return view
        except BaseException as error:
            _raise(error)

    def close(self):
        try:
            with self._gate:
                if self._inflight:
                    raise LinuxPreparedStepError()
                if self._owner_state == 'closed':
                    return
                if self._owner_state != 'active':
                    raise LinuxPreparedStepError()
                if self._consume_state != 'faulted':
                    self._consume_state = 'spent'
                self._owner_state = 'unknown'
                self._owner.close()
                self._owner_state = 'closed'
        except BaseException as error:
            _raise(error)

    def __enter__(self):
        try:
            with self._gate:
                # Cleanup convenience only; attach/borrow perform admission.
                # Do not re-observe source or retry unknown on context entry.
                if self._owner_state != 'active' or self._inflight:
                    raise LinuxPreparedStepError()
                return self
        except BaseException as error:
            _raise(error)

    def __exit__(self, kind, body, traceback):
        try:
            self.close()
        except BaseException as cleanup:
            if _cleanup_choice(body, cleanup) is cleanup:
                raise
        return False

    def __copy__(self):
        raise LinuxPreparedStepError() from None

    def __deepcopy__(self, memo):
        raise LinuxPreparedStepError() from None

    def __reduce_ex__(self, protocol):
        raise LinuxPreparedStepError() from None

class _LinuxStepAttachment:
    def __init__(self):
        raise LinuxPreparedStepError() from None

    def _current(self):
        scope = self._scope
        if scope._attachment is not self:
            raise LinuxPreparedStepError()
        return scope

    def _validate_attempt(self, attempt):
        if (type(attempt) is not str or not attempt.strip()
                or any(ord(c) < 32 or ord(c) == 127 for c in attempt)
                or not callable(self._validator) or attempt != self._attempt):
            raise LinuxPreparedStepError()
        # Trusted runner-owned CP observer in S2; callback alone grants nothing.
        if self._validator(attempt) is not None:
            raise LinuxPreparedStepError()

    def _bind_attempt(self, attempt, *, validate_attempt):
        try:
            scope = self._current()
            with scope._gate:
                if scope._consume_state != 'attached_pending' or scope._inflight:
                    raise LinuxPreparedStepError()
                scope._check(policy=scope._policy, workspace_session=scope._session)
                previous = self._attempt, self._validator
                self._attempt, self._validator = attempt, validate_attempt
                try:
                    self._validate_attempt(attempt)
                except BaseException:
                    self._attempt, self._validator = previous
                    raise
                scope._consume_state = 'attached_bound'
        except BaseException as error:
            _raise(error)

    @contextmanager
    def borrow(self, *, policy, workspace_session, attempt):
        try:
            scope = self._current()
            with scope._gate:
                if scope._consume_state != 'attached_bound' or scope._inflight:
                    raise LinuxPreparedStepError()
                scope._check(policy=policy, workspace_session=workspace_session)
                self._validate_attempt(attempt)
                scope._inflight = True
        except BaseException as error:
            _raise(error)
        try:
            yield scope._owner
        finally:
            # The body and command cleanup have ended; this sole borrower's
            # final single-field return performs no fallible lock operation.
            # No subsequent state writes can overwrite a new borrower.
            # No helper/session/lease close; do not clear sticky faulted.
            scope._inflight = False

    def _mark_faulted(self):
        try:
            scope = self._current()
            with scope._gate:
                if not scope._inflight or scope._consume_state not in ('attached_bound', 'faulted'):
                    raise LinuxPreparedStepError()
                scope._consume_state = 'faulted'
        except BaseException as error:
            _raise(error)

    def finish(self):
        try:
            scope = self._current()
            with scope._gate:
                if scope._inflight or scope._consume_state == 'prepared':
                    raise LinuxPreparedStepError()
                if scope._consume_state != 'faulted':
                    scope._consume_state = 'spent'
        except BaseException as error:
            _raise(error)

    def __copy__(self):
        raise LinuxPreparedStepError() from None

    def __deepcopy__(self, memo):
        raise LinuxPreparedStepError() from None

    def __reduce_ex__(self, protocol):
        raise LinuxPreparedStepError() from None

def prepare_linux_step(sandbox, *, policy, workspace_session):
    return LinuxPreparedStep(sandbox, policy=policy, workspace_session=workspace_session)
