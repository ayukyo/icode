"""Fixed trusted-workflow entry; no user-controlled privileged command."""
from __future__ import annotations
import argparse
import json
import os
from pathlib import Path
import re
import sys


def emit(value):
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("ascii")
    if len(encoded) > 500:
        raise RuntimeError("entry_receipt_limit")
    sys.stdout.buffer.write(encoded + b"\n")
    sys.stdout.buffer.flush()


STAGE = re.compile(r"[a-z][a-z0-9_]{0,47}")
TYPE = re.compile(r"[A-Za-z][A-Za-z0-9_]{0,47}")


def bounded_stage(error):
    """Bounded failure category for the receipt; never a secret, SID, path or command."""
    text = "" if error is None else str(error)
    if text != "unknown" and ("_" not in text or not STAGE.fullmatch(text)):
        return "unknown"
    return text


def bounded_type(error):
    """Bounded exception class name; never message content."""
    name = type(error).__name__
    return name if TYPE.fullmatch(name) else "unknown"


def failure_receipt(error):
    value = dict(schema=1, stage="failed", state="unknown", error=bounded_stage(error),
                 type=bounded_type(error))
    code = getattr(error, "winerror", None)
    if code is None:
        code = getattr(getattr(error, "__cause__", None), "winerror", None)
    if type(code) is int and 0 < code < 65536:
        value["winerror"] = code
    return value


def main(argv=None):
    parser = argparse.ArgumentParser(allow_abbrev=False)
    parser.add_argument("operation", choices=("freeze", "serve", "readonly", "recover"))
    parser.add_argument("--account")
    parser.add_argument("--root")
    parser.add_argument("--account-sid")
    parser.add_argument("--parent", type=int)
    args = parser.parse_args(argv)
    if sys.platform != "win32" or sys.version_info < (3, 12):
        raise RuntimeError("entry_windows312")
    if not (sys.flags.isolated and sys.flags.no_site and sys.flags.dont_write_bytecode):
        raise RuntimeError("entry_flags")
    script = Path(__file__).absolute()
    private = script.parent.parent.name == "trusted" and script.parent.name == "scripts"
    if args.operation == "freeze":
        if private or args.account is None or any(value is not None for value in (args.root, args.account_sid, args.parent)):
            raise RuntimeError("entry_freeze_arguments")
        checkout = script.parents[1]
        # This branch is reached only before the temporary account exists.
        sys.path.insert(0, str(checkout))
        sys.path.insert(0, str(checkout / "src"))
    else:
        if not private or args.root is None or args.account is not None:
            raise RuntimeError("entry_private_arguments")
        root = Path(args.root)
        if not root.is_absolute() or root.resolve(strict=True) != root or root != script.parents[2]:
            raise RuntimeError("entry_private_root")
        runtime = root / "runtime"
        if Path(sys.executable).absolute() != runtime / "python.exe":
            raise RuntimeError("entry_private_python")
        # Preserve exactly the approved private stdlib/extension slots and two
        # explicit candidate package roots, never checkout/cwd/site-packages.
        sys.path[:] = [str(runtime / "python312.zip"), str(runtime / "DLLs"), str(runtime / "Lib"),
                       str(runtime), str(root / "trusted"), str(root / "trusted/src")]
    from scripts.windows_positive_loopback_admin import Admin, _mapping
    from scripts.windows_positive_loopback_admin_native import Native, context
    from scripts.windows_positive_loopback_admin_win32 import _release_owned
    binding = context(dict(repository=os.environ.get("GITHUB_REPOSITORY"), source_sha=os.environ.get("GITHUB_SHA"),
        run_id=os.environ.get("GITHUB_RUN_ID"), run_attempt=int(os.environ.get("GITHUB_RUN_ATTEMPT", "0")),
        job=os.environ.get("GITHUB_JOB"), matrix={"X64": "x64", "ARM64": "ARM64"}.get(os.environ.get("RUNNER_ARCH"))))
    if args.operation == "freeze":
        root = Admin.freeze_before_user(binding, args.account)
        emit(dict(schema=1, stage="frozen", root=str(root)))
        return 0
    if args.operation == "recover":
        if args.account_sid is not None or args.parent is not None:
            raise RuntimeError("entry_recover_arguments")
        receipt = Admin.recover(root)
        emit(dict(schema=1, stage="recovery", cleanup_state=receipt["stage"], binding=receipt["binding"],
                  native_restoration_verified=receipt.get("native_restoration_verified")))
        return 0 if receipt.get("native_restoration_verified") is True else 4
    if args.account_sid is None or args.parent is None:
        raise RuntimeError("entry_parent_arguments")
    admin = Admin.prepare(root, args.account_sid)
    try:
        admin.attach_parent(args.parent)
        if args.operation == "readonly":
            before = _mapping(admin.native.full_get(admin.store))
            admin.native.stop_parent_job(admin.store)
            after = _mapping(admin.native.full_get(admin.store))
            if before != after:
                raise RuntimeError("readonly_configuration_changed")
            emit(dict(schema=1, stage="readonly_ready", sdk=True, loader=True, storage=True,
                      standard_token=True, configuration_unchanged=True))
            return 0
        receipt = admin.serve()
        # The client receives the receipt before deleting its profile. Keep the
        # outer Job alive until its real parent exits or bounded recovery fails.
        parent = admin.native._process(admin.store, admin.data["parent"], allow_gone=True)
        if parent:
            try:
                if admin.store.w.k.WaitForSingleObject(parent, 30000) != 0:
                    admin._failure("parent_failed")
                    admin.native.stop_parent_job(admin.store)
                    raise RuntimeError("parent_finally_not_reaped")
            finally:
                _release_owned(sys.exception(),
                    lambda: admin.store.w.close(parent),
                )
        admin.native.reap_commands(admin.store)
        emit(dict(schema=1, stage="completed", cleanup_state=receipt["stage"], binding=receipt["binding"],
                  native_restoration_verified=receipt.get("native_restoration_verified")))
        return 0 if receipt.get("native_restoration_verified") is True else 4
    finally:
        # Failure before serve() also owns a suspended/started parent. Cleanup
        # precedes closing the last owned Job handle; errors never grant ready.
        _release_owned(sys.exception(),
            lambda: admin.cleanup(abnormal=True) if admin.data["phase"] != "cleaned" else None,
            lambda: admin.store.close(),
        )


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as error:
        emit(failure_receipt(error))
        raise SystemExit(4)
