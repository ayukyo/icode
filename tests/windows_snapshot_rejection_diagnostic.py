"""Test-only observation of the existing Windows snapshot rejection gates."""

from __future__ import annotations

from contextlib import ExitStack, contextmanager
from dataclasses import dataclass
import json
import threading
from unittest.mock import patch

from icode import workspace_snapshot as ws
from icode import windows_worktree as ww


PREFIX = "ICODE_WINDOWS_SNAPSHOT_REJECTION="
MAX_FRAMES = 129
_OWNER = threading.Lock()


def _slot(attempt, status="not_observed"):
    stage = "not_observed" if status == "not_observed" else "none"
    return dict(attempt=attempt, status=status, scope="unavailable",
                reject_stage=stage, changed_entry_class="not_observed",
                listing_difference_mask=None, handle_observation="not_observed",
                handle_difference_mask=None)


def _unavailable(attempt):
    return dict(attempt=attempt, status="diagnostic_unavailable",
                scope="unavailable", reject_stage="unavailable",
                changed_entry_class="unavailable", listing_difference_mask=None,
                handle_observation="unavailable", handle_difference_mask=None)


def _scope(parts):
    if type(parts) is not tuple:
        return "unavailable"
    for part in parts:
        if type(part) is not str or not part or part in (".", ".."):
            return "unavailable"
        if any(char in part for char in ("\0", "/", "\\", ":")):
            return "unavailable"
    if not parts:
        return "root"
    return "git_metadata" if parts[0] == ".git" else "other_descendant"


def _entry_class(name, scope):
    if scope == "unavailable":
        raise ValueError("scope unavailable")
    if scope == "git_metadata" or (scope == "root" and name == ".git"):
        return 1
    if name in (".icode_output", "__pycache__"):
        return 2
    return 4


def _listing_difference(before, after, scope):
    """Merge the already sorted unique-name production signature tuples."""
    i = j = mask = classes = 0
    while i < len(before) or j < len(after):
        if j == len(after) or (i < len(before) and before[i][0] < after[j][0]):
            mask |= 1
            classes |= _entry_class(before[i][0], scope)
            i += 1
        elif i == len(before) or after[j][0] < before[i][0]:
            mask |= 1
            classes |= _entry_class(after[j][0], scope)
            j += 1
        else:
            difference = 0
            for field, bit in ((1, 2), (2, 4), (3, 8), (4, 16), (5, 32)):
                if before[i][field] != after[j][field]:
                    difference |= bit
            if difference:
                mask |= difference
                classes |= _entry_class(before[i][0], scope)
            i += 1
            j += 1
    label = {0: "not_observed", 1: "git_metadata", 2: "ignored_control",
             4: "other"}.get(classes, "mixed")
    return mask, label


def _handle_difference(before, after):
    mask = 0
    for index in range(8):
        if before[index] != after[index]:
            mask |= 1 << index
    return mask


@dataclass(slots=True)
class _Frame:
    slot_index: int
    scope: str
    unavailable: bool = False
    listing_count: int = 0
    listing_before: object = None
    listing_mask: int | None = None
    entry_class: str = "not_observed"
    handle_count: int = 0
    handle_before: object = None
    handle_mask: int | None = None


class _Observer:
    def __init__(self):
        self.thread = threading.get_ident()
        self.frames = []
        self.suspended = 0
        self.root_count = 0
        self.current_slot = 0
        self.records = [_slot(1), _slot(2)]
        self.seen_rejection = False
        self.invalid_context = False
        self.output_failed = False

    def _make_frame(self, slot_index, parts):
        return _Frame(slot_index, _scope(parts))

    def _active(self):
        if (threading.get_ident() != self.thread or self.invalid_context
                or self.suspended or not self.frames):
            return None
        return self.frames[-1]

    def _listing(self, value):
        frame = self._active()
        if frame is None or frame.unavailable:
            return
        frame.listing_count += 1
        if frame.listing_count == 1:
            frame.listing_before = value
        elif frame.listing_count == 2:
            try:
                frame.listing_mask, frame.entry_class = _listing_difference(
                    frame.listing_before, value, frame.scope)
            finally:
                frame.listing_before = None
        else:
            frame.unavailable = True

    def _handle(self, value):
        frame = self._active()
        # File and symlink signatures precede the two final listing signatures.
        if frame is None or frame.unavailable or frame.listing_mask != 0:
            return
        frame.handle_count += 1
        if frame.handle_count == 1:
            frame.handle_before = value
        elif frame.handle_count == 2:
            try:
                frame.handle_mask = _handle_difference(frame.handle_before, value)
            finally:
                frame.handle_before = None
        else:
            frame.unavailable = True

    def signature(self, original, observe):
        def wrapped(*args, **kwargs):
            value = original(*args, **kwargs)
            if threading.get_ident() == self.thread and not self.invalid_context:
                try:
                    observe(value)
                except Exception:
                    try:
                        frame = self._active()
                        if frame is not None:
                            frame.unavailable = True
                    except Exception:
                        self.output_failed = True
            return value
        return wrapped

    def _rejected(self, frame, slot_index):
        self.seen_rejection = True
        if self.records[slot_index]["status"] in (
                "directory_rejected", "diagnostic_unavailable"):
            return  # First unwinding frame is the deepest actual rejection.
        if frame is None or frame.unavailable or frame.scope == "unavailable":
            self.records[slot_index] = _unavailable(slot_index + 1)
            return
        record = _slot(slot_index + 1, "directory_rejected")
        record["scope"] = frame.scope
        if frame.listing_mask:
            record.update(reject_stage="listing", changed_entry_class=frame.entry_class,
                          listing_difference_mask=frame.listing_mask)
        elif frame.listing_mask == 0 and frame.handle_count == 2 and frame.handle_mask:
            record.update(reject_stage="held_handle", listing_difference_mask=0,
                          handle_observation="different",
                          handle_difference_mask=frame.handle_mask)
        else:
            record = _unavailable(slot_index + 1)
        self.records[slot_index] = record

    def _restore(self, length, suspended, slot_index):
        del self.frames[length:]
        self.suspended = suspended
        self.current_slot = slot_index

    def walker(self, original):
        def wrapped(*args, **kwargs):
            if threading.get_ident() != self.thread or self.invalid_context:
                return original(*args, **kwargs)
            prior_length = len(self.frames)
            prior_suspended = self.suspended
            prior_slot = self.current_slot
            frame = None
            root = kwargs.get("is_root") is True and kwargs.get("depth") == 0
            slot_index = self.current_slot
            try:
                if root:
                    self.root_count += 1
                    if self.root_count > 2:
                        self.invalid_context = True
                    else:
                        slot_index = self.root_count - 1
                        self.current_slot = slot_index
                if self.invalid_context:
                    pass
                elif self.suspended or prior_length >= MAX_FRAMES:
                    self.suspended += 1
                else:
                    frame = self._make_frame(slot_index, kwargs.get("snapshot_parts"))
                    self.frames.append(frame)
            except Exception:
                self.suspended = prior_suspended + 1
                frame = None
            if self.invalid_context:
                return original(*args, **kwargs)
            try:
                try:
                    value = original(*args, **kwargs)
                except Exception as error:
                    try:
                        if (isinstance(error, ws.WorktreeTreeUnavailable)
                                and error.reason == "windows_directory_changed"):
                            self._rejected(frame, slot_index)
                        elif root and self.records[slot_index]["status"] == "not_observed":
                            self.records[slot_index] = _slot(slot_index + 1, "other_error")
                    except Exception:
                        if (isinstance(error, ws.WorktreeTreeUnavailable)
                                and error.reason == "windows_directory_changed"):
                            self.seen_rejection = True
                            try:
                                self.records[slot_index] = _unavailable(slot_index + 1)
                            except Exception:
                                self.output_failed = True
                        else:
                            self.output_failed = True
                    raise
                try:
                    if root and self.records[slot_index]["status"] == "not_observed":
                        self.records[slot_index] = _slot(slot_index + 1, "completed")
                except Exception:
                    self.output_failed = True
                return value
            finally:
                # No callbacks or new I/O during frame restoration.
                try:
                    self._restore(prior_length, prior_suspended, prior_slot)
                    if frame is not None:
                        frame.listing_before = frame.handle_before = None
                except Exception:
                    self.invalid_context = True
                    self.frames = []
                    self.suspended = prior_suspended
                    self.current_slot = prior_slot
        return wrapped

    def emit(self, sink, outcome):
        if self.invalid_context or self.output_failed or not self.seen_rejection:
            return
        try:
            payload = dict(schema_version=1, call_outcome=outcome, attempts=self.records)
            line = PREFIX + json.dumps(payload, ensure_ascii=True, separators=(",", ":"))
            sink(line)
        except Exception:
            pass  # Diagnostic serialization/output cannot replace snapshot failure.


def _close_hooks(stack, references):
    failed = False
    try:
        stack.close()
    except Exception:
        failed = True
    finally:
        # Also roll back a partial installation or a failed ExitStack close.
        # Only restore this owner's wrappers; never remove an unrelated hook.
        for module, name, original, replacement in references:
            try:
                if getattr(module, name) is replacement:
                    setattr(module, name, original)
            except Exception:
                failed = True
    return not failed


@contextmanager
def windows_snapshot_rejection_diagnostic(*, enabled=True, sink=print):
    if not enabled or not _OWNER.acquire(blocking=False):
        yield
        return
    stack = None
    observer = None
    installed = False
    owns_lock = True
    returned = False
    references = ()
    try:
        try:
            stack = ExitStack()
            observer = _Observer()
            listing = observer.signature(ws._windows_directory_listing_signature, observer._listing)
            handle = observer.signature(ws._windows_handle_signature, observer._handle)
            recursive = observer.walker(ws._walk_windows_directory)
            top = observer.walker(ww._walk_windows_directory)
            references = (
                (ws, "_windows_directory_listing_signature", ws._windows_directory_listing_signature, listing),
                (ws, "_windows_handle_signature", ws._windows_handle_signature, handle),
                (ws, "_walk_windows_directory", ws._walk_windows_directory, recursive),
                (ww, "_walk_windows_directory", ww._walk_windows_directory, top))
            for module, name, original, replacement in references:
                stack.enter_context(patch.object(module, name, new=replacement))
            installed = True
        except Exception:
            try:
                if observer is not None:
                    observer.thread = None  # Unrestorable wrappers remain transparent.
                _close_hooks(stack, references)  # Roll back before the unobserved body.
            finally:
                _OWNER.release()
                owns_lock = False
        yield
        returned = True
    finally:
        if owns_lock:
            try:
                if observer is not None:
                    # Stop observation without invalidating the collected receipt.
                    observer.thread = None
                if not _close_hooks(stack, references) and observer is not None:
                    observer.output_failed = True
            finally:
                _OWNER.release()
        if installed:
            try:
                observer.emit(sink, "returned" if returned else "raised")
            except Exception:
                pass  # Even an observer entry-point fault preserves the body.
