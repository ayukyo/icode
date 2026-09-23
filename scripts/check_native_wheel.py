"""检查 Linux wheel 是否真的随包携带可执行且哈希匹配的原生助手。"""

from __future__ import annotations

import hashlib
import sys
import zipfile
from pathlib import Path


def check(wheel: Path) -> list[str]:
    problems: list[str] = []
    with zipfile.ZipFile(wheel) as archive:
        names = set(archive.namelist())
        binary = "icode/native/icode-landlock"
        manifest = "icode/native/icode-landlock.sha256"
        for name in (binary, manifest):
            if name not in names:
                problems.append(f"wheel 缺少 {name}")
        wheel_metadata = next((name for name in names if name.endswith(".dist-info/WHEEL")), None)
        if wheel_metadata is None:
            problems.append("wheel 缺少 WHEEL 元数据")
        else:
            tags = [
                line.removeprefix("Tag: ")
                for line in archive.read(wheel_metadata).decode("utf-8").splitlines()
                if line.startswith("Tag: ")
            ]
            if tags != [f"py3-none-{wheel.stem.rsplit('-', 1)[-1]}"]:
                problems.append(f"Linux 原生 wheel 应使用 py3-none-平台标签：{tags}")
        if binary in names and manifest in names:
            content = archive.read(binary)
            expected = archive.read(manifest).decode("ascii").strip()
            if hashlib.sha256(content).hexdigest() != expected:
                problems.append("包内助手 SHA-256 与清单不一致")
            mode = archive.getinfo(binary).external_attr >> 16
            if mode & 0o111 == 0:
                problems.append("包内助手缺少可执行权限")
    return problems


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: check_native_wheel.py WHEEL", file=sys.stderr)
        return 2
    problems = check(Path(sys.argv[1]))
    for problem in problems:
        print(f"::error::{problem}")
    if problems:
        return 1
    print("Linux native wheel OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
