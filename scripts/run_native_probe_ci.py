"""R2.2 开发期原生后端负向探测；未通过则 CI 失败。"""

from __future__ import annotations

import shutil
import sys

from icode.isolation import BubblewrapSandbox, MacSeatbeltSandbox, probe_native_sandbox


def main() -> int:
    if sys.platform.startswith("linux"):
        executable = shutil.which("bwrap")
        backend = BubblewrapSandbox(bwrap=executable or "bwrap")
    elif sys.platform == "darwin":
        executable = shutil.which("sandbox-exec")
        backend = MacSeatbeltSandbox(sandbox_exec=executable or "sandbox-exec")
    else:
        print("::error::R2.2 native probe CI only supports Linux and macOS")
        return 1

    if executable is None:
        print(f"::error::{backend.name} executable is missing")
        return 1

    result = probe_native_sandbox(backend)
    for name, passed in result.checks.items():
        print(f"{backend.name} {name}: {'PASS' if passed else 'FAIL'}")
    if not result.ready:
        print(f"::error::{backend.name} native probe failed: {result.detail}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
