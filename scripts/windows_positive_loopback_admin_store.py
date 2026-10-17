from __future__ import annotations

import ctypes as c
import hashlib
import json
import os
from pathlib import Path
import re
import time
import sys

from scripts.windows_positive_loopback_admin_win32 import Win32, Failure, _release_owned


PRIVATE = "O:BAD:P(A;OICI;FA;;;BA)(A;OICI;FA;;;SY)"
# Kernel objects have no inheritance, so the job descriptor omits OICI flags.
# Storing a DACL on a Job (SE_KERNEL_OBJECT) also maps every ACE mask through
# the Job generic mapping: the file-oriented "FA" mask (0x001F01FF) is stored
# as the Job-specific mask 0x001F003F (JOB_OBJECT_ALL_ACCESS). The expected
# descriptor therefore names that already-mapped mask explicitly, so the DACL
# bytes read back from a live Job match these bytes regardless of whether the
# creation descriptor or SetSecurityInfo carried them.
KERNEL_PRIVATE = "O:BAD:P(A;;0x1F003F;;;BA)(A;;0x1F003F;;;SY)"
LEDGER_LIMIT = 8388608


def wire(value):
    return json.dumps(value, ensure_ascii=True, sort_keys=True,
                      separators=(",", ":"), allow_nan=False).encode("ascii")


def unique(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise Failure("duplicate_key")
        result[key] = value
    return result


def decode(value, limit):
    if type(value) is not bytes or not value or len(value) > limit:
        raise Failure("file_size")
    try:
        return json.loads(value.decode("utf-8"), object_pairs_hook=unique,
                          parse_constant=lambda x: (_ for _ in ()).throw(Failure("json_constant")))
    except (ValueError, UnicodeError, RecursionError) as exc:
        raise Failure("file_json") from exc


class Store:
    def __init__(self, root):
        if type(root) is not Path and not isinstance(root, Path):
            raise Failure("root_type")
        if not root.is_absolute() or root.resolve(strict=True) != root or re.fullmatch(r"icode-positive-admin-[0-9a-f]{32}", root.name) is None:
            raise Failure("root_namespace")
        self.w = Win32()
        self.w.assert_admin()
        self.root, self.handles, self.pins = root, [], []
        try:
            self.route_records = []
            for parent in reversed(root.parents):
                handle = self.w.pin_ancestor(parent, observe_only=True)
                self.pins.append(handle)
                self.route_records.append(dict(path=str(parent),
                    identity=list(self.w.info(handle, directory=True)),
                    security=self.w.observe_security(handle)))
            self.root_handle = self.w.pin_ancestor(root)
            self.pins.append(self.root_handle)
            self.root_identity = self.w.info(self.root_handle, directory=True)
            self.lock, _identity = self.w.open_file(root / "lock", PRIVATE, write=True)
            self.handles.append(self.lock)
            self.data = decode(self.read("ledger.json", PRIVATE, LEDGER_LIMIT), LEDGER_LIMIT)
            if type(self.data) is not dict or self.data.get("schema") != 1:
                raise Failure("ledger_schema")
            if self.data.get("root_identity") != list(self.root_identity):
                raise Failure("root_identity")
        except BaseException:
            _release_owned(sys.exception(), self.close)
            raise

    @classmethod
    def create(cls, root, data):
        w = Win32()
        w.assert_admin()
        pins = []
        try:
            for parent in reversed(root.parents):
                pins.append(w.pin_ancestor(parent, observe_only=True))
            w.create_directory(root, PRIVATE)
            root_handle, identity = w.open_file(root, PRIVATE, directory=True)
            pins.append(root_handle)
            data["root_identity"] = list(identity)
            for name in ("lock", "ledger.json"):
                handle, identity = w.open_file(root / name, PRIVATE, create=True, write=True)
                try:
                    data["file_identities"][name] = list(identity)
                    w.write(handle, wire(data) if name == "ledger.json" else b"")
                finally:
                    _release_owned(sys.exception(),
                        lambda: w.close(handle),
                    )
        finally:
            _release_owned(sys.exception(),
                *(lambda handle=handle: w.close(handle) for handle in reversed(pins)),
            )
        return cls(root)

    def flush(self):
        # A torn/truncated write is never replayed as an earlier successful
        # transaction: reopening malformed JSON fails closed and does not guess.
        encoded = wire(self.data)
        if len(encoded) > LEDGER_LIMIT:
            raise Failure("ledger_limit")
        handle, identity = self.w.open_file(self.root / "ledger.json", PRIVATE, write=True)
        try:
            if self.data["file_identities"].get("ledger.json") != list(identity):
                raise Failure("ledger_replaced")
            self.w.write(handle, encoded)
            if self.w.info(handle) != identity:
                raise Failure("ledger_replaced")
        finally:
            _release_owned(sys.exception(),
                lambda: self.w.close(handle),
            )

    def file_descriptor(self, role):
        if role == "private":
            return PRIVATE
        sid = self.data["account_sid"]
        if type(sid) is not str or re.fullmatch(r"S-1-5-21-(?:[0-9]+-){3}[0-9]+", sid) is None:
            raise Failure("account_sid")
        if role == "public":
            return PRIVATE + "(A;;FR;;;" + sid + ")"
        if role == "request":
            # Write data/read data only, no delete/owner/DACL/parent mutation.
            return PRIVATE + "(A;;0x120003;;;" + sid + ")"
        raise Failure("file_role")

    def read(self, name, descriptor, limit):
        self._leaf(name)
        handle, identity = self.w.open_file(self.root / name, descriptor)
        try:
            expected = self.data.get("file_identities", {}).get(name) if hasattr(self, "data") else None
            if expected is not None and list(identity) != expected:
                raise Failure("file_replaced")
            result = self.w.read(handle, limit)
            if self.w.info(handle) != identity:
                raise Failure("file_replaced")
            return result
        finally:
            _release_owned(sys.exception(),
                lambda: self.w.close(handle),
            )

    def write(self, name, data, role="private", *, create=False):
        self._leaf(name)
        descriptor = self.file_descriptor(role)
        handle, identity = self.w.open_file(self.root / name, descriptor, create=create, write=True)
        try:
            identities = self.data["file_identities"]
            if not create and identities.get(name) != list(identity):
                raise Failure("file_replaced")
            self.w.write(handle, data)
            if create:
                identities[name] = list(identity)
        finally:
            _release_owned(sys.exception(),
                lambda: self.w.close(handle),
            )

    def create_directory(self, relative):
        parts = Path(relative).parts
        if not parts or Path(relative).is_absolute() or any(part in (".", "..") for part in parts):
            raise Failure("directory_name")
        path = self.root
        held = []
        try:
            for number, part in enumerate(parts):
                path /= part
                leaf = number == len(parts) - 1
                exists = path.exists()
                if leaf and exists:
                    raise Failure("directory_exists")
                if not exists:
                    # CreateDirectory is CREATE_NEW; a race cannot silently
                    # replace a component or admit a pre-existing leaf.
                    self.w.create_directory(path, PRIVATE)
                handle, identity = self.w.open_file(path, PRIVATE, directory=True)
                held.append((handle, identity))
            for handle, identity in held:
                if self.w.info(handle, directory=True) != identity:
                    raise Failure("directory_changed")
            # Existing prefixes are admitted only after exact protected SD,
            # canonical namespace and no-reparse identity checks, then pinned
            # for the Store lifetime; exists() by itself is never authority.
            self.pins.extend(handle for handle, _identity in held)
            held.clear()
        finally:
            _release_owned(sys.exception(),
                *(lambda handle=handle: self.w.close(handle) for handle, _identity in reversed(held)),
            )

    @staticmethod
    def _leaf(name):
        if type(name) is not str or re.fullmatch(r"[A-Za-z0-9_.-]{1,100}", name) is None or name in (".", ".."):
            raise Failure("file_name")

    def close(self):
        # Pop only means this instance attempted release, not OS confirmation.
        actions = []
        for collection in (getattr(self, "handles", []), getattr(self, "pins", [])):
            while collection:
                handle = collection.pop()
                actions.append(lambda handle=handle: self.w.close(handle))
        _release_owned(sys.exception(), *actions)


def copy_private_tree(store, source, destination, *, deadline):
    # Called only after Native proved the intended temporary account absent.
    # Source handles deny write/delete; every destination gets an explicit
    # protected descriptor, not a copied user ACL or a symlink/reparse object.
    # Inspect the supplied namespace before resolve: resolving first would
    # erase evidence that the input root itself was a link/reparse object.
    source = Path(source).absolute()
    for entry in reversed((source, *source.parents)):
        if entry.is_symlink() or getattr(entry.lstat(), "st_file_attributes", 0) & 0x400:
            raise Failure("freeze_reparse")
    if source.resolve(strict=True) != source:
        raise Failure("freeze_source_namespace")
    destination = store.root / destination
    store.w.create_directory(destination, PRIVATE)
    records, total = [], 0
    def enumeration_failed(error):
        raise Failure("freeze_enumeration") from error

    for current, directories, files in os.walk(
            source, topdown=True, followlinks=False, onerror=enumeration_failed):
        if time.monotonic() > deadline:
            raise Failure("freeze_deadline")
        relative = Path(current).relative_to(source)
        directories[:] = [name for name in directories if name.casefold() not in
                          {"site-packages", "__pycache__", "test", "tests", "idlelib", "tkinter", "ensurepip"}]
        for name in directories + files:
            path = Path(current) / name
            if name.casefold() == "pyvenv.cfg" or name.casefold().endswith("._pth"):
                raise Failure("unsupported_runtime_layout")
            if path.is_symlink() or getattr(path.lstat(), "st_file_attributes", 0) & 0x400:
                raise Failure("freeze_reparse")
            target = destination / path.relative_to(source)
            if name in directories:
                store.w.create_directory(target, PRIVATE)
                continue
            if len(records) >= 100000:
                raise Failure("freeze_count")
            raw_handle = store.w.k.CreateFileW(str(path), 0x80020080, 1, None, 3, 0x00200000, None)
            if raw_handle in (None, c.c_void_p(-1).value):
                raise Failure("freeze_source_open")
            out = None
            try:
                source_identity = store.w.info(raw_handle)
                info = path.lstat()
                size = int(info.st_size)
                if size < 0 or size > 268435456:
                    raise Failure("freeze_file_limit")
                total += size
                if total > 2147483648:
                    raise Failure("freeze_total_limit")
                data = store.w.read(raw_handle, size)
                if len(data) != size or store.w.info(raw_handle) != source_identity:
                    raise Failure("freeze_source_changed")
                out, target_identity = store.w.open_file(target, PRIVATE, create=True, write=True)
                store.w.write(out, data)
                # The frozen bytes are trusted through this protected copy,
                # not the origin DACL: hosted toolcaches inherit write access
                # for Authenticated Users from the drive root.
                store.w.verify_ancestor(out)
                records.append(dict(path=target.relative_to(store.root).as_posix(),
                                    identity=list(target_identity), size=size,
                                    sha256=hashlib.sha256(data).hexdigest()))
            finally:
                _release_owned(sys.exception(),
                    lambda: store.w.close(out) if out else None,
                    lambda: store.w.close(raw_handle),
                )
            if time.monotonic() > deadline:
                raise Failure("freeze_deadline")
    return records
