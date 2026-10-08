"""Build-time license closure for the packages actually linked by Go."""


import argparse
import hashlib
import json
import re
import stat
import subprocess
from pathlib import Path

MAX_NOTICE_BYTES = 1 << 20
NOTICE_NAME = re.compile(r"^(LICENSE|LICENCE|COPYING|NOTICE|PATENTS)(?:[._-].*)?$", re.I)


def read_notice(path):
    info = path.lstat()
    if not stat.S_ISREG(info.st_mode) or not 0 < info.st_size <= MAX_NOTICE_BYTES:
        raise ValueError("license file must be a bounded regular file")
    with path.open("rb") as stream:
        data = stream.read(MAX_NOTICE_BYTES + 1)
    if not data or len(data) > MAX_NOTICE_BYTES:
        raise ValueError("license file size changed or exceeded the limit")
    return data.decode("utf-8")


def validate_review(modules, review, linked_ancestors=None):
    approved = {(item["path"], item["version"]): item for item in review["modules"]}
    for key, (module_root, files) in modules.items():
        item = approved.get(key)
        if item is None:
            raise ValueError(f"unreviewed linked module: {key[0]}")
        observed = {path.relative_to(module_root).as_posix() for path in files}
        ancestors = {module_root} if linked_ancestors is None else linked_ancestors[key]
        # Required notices may disappear while LICENSE remains. Check reviewed
        # module-root files and the ancestry of actually linked packages; do not
        # demand unrelated nested packages or modules on another platform.
        required = {relative for relative in item["licenses"]
                    if (module_root / relative).parent in ancestors}
        if not required.issubset(observed):
            raise ValueError(f"missing reviewed linked module notice: {key[0]}")
        for path in files:
            relative = path.relative_to(module_root).as_posix()
            actual = hashlib.sha256(read_notice(path).encode("utf-8")).hexdigest()
            if item["licenses"].get(relative) != actual:
                raise ValueError(f"unreviewed linked module notice: {key[0]} {relative}")


def collect_notices(packages, go_root, project_root, review=None):
    sections = ["ICODE provenance verifier: original linked dependency notices\n"]
    for title, path in (
        ("Go runtime and standard library", go_root / "LICENSE"),
        ("Compiled Sigstore trust anchor (root-signing, Apache-2.0)", project_root / "LICENSE.sigstore"),
    ):
        text = read_notice(path)
        if review is not None:
            field = "go_license_sha256" if path.parent == go_root else "trust_anchor_license_sha256"
            if hashlib.sha256(text.encode("utf-8")).hexdigest() != review[field]:
                raise ValueError("unreviewed runtime or trust anchor license")
        sections.append(f"\n===== {title} =====\n{text}")

    modules = {}
    linked_ancestors = {}
    for package in packages:
        module = package.get("Module")
        if not module or module.get("Main"):
            continue
        if module.get("Replace"):
            raise ValueError("replaced modules require a separate license review")
        key = (module["Path"], module["Version"])
        module_root = Path(module["Dir"])
        directory = Path(package["Dir"])
        directory.relative_to(module_root)
        item = modules.setdefault(key, (module_root, set()))
        ancestors = linked_ancestors.setdefault(key, set())
        if item[0] != module_root:
            raise ValueError("inconsistent module directory")
        # Include package-level notices along each linked package's ancestry,
        # not only module-root licenses and not unrelated test dependencies.
        while True:
            ancestors.add(directory)
            for candidate in directory.iterdir():
                if NOTICE_NAME.fullmatch(candidate.name):
                    item[1].add(candidate)
            if directory == module_root:
                break
            directory = directory.parent

    if review is not None:
        validate_review(modules, review, linked_ancestors)
    for (name, version), (module_root, files) in sorted(modules.items()):
        if not any(re.match(r"^(LICENSE|LICENCE|COPYING)(?:[._-].*)?$", path.name, re.I) for path in files):
            raise ValueError(f"missing original license for linked module: {name}")
        sections.append(f"\n===== {name} {version} =====\n")
        for path in sorted(files):
            sections.append(f"\n--- {path.relative_to(module_root).as_posix()} ---\n{read_notice(path)}")
    return "\n".join(sections)


def decode_package_stream(text):
    decoder = json.JSONDecoder()
    packages = []
    offset = 0
    while offset < len(text):
        while offset < len(text) and text[offset].isspace():
            offset += 1
        if offset == len(text):
            break
        package, offset = decoder.raw_decode(text, offset)
        if not isinstance(package, dict) or package.get("Error") or package.get("DepsErrors"):
            raise ValueError("invalid or incomplete Go package list")
        packages.append(package)
    if not packages:
        raise ValueError("empty Go package list")
    return packages


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--go", default="go", help="build-time Go executable")
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    project = Path(__file__).resolve().parents[1]
    # Go emits UTF-8; Windows locale decoding can reject valid JSON/docs/paths.
    # Decode strictly: do not silently replace bytes or relax notice hashes.
    listed = subprocess.run([args.go, "list", "-mod=readonly", "-deps", "-json", "."], cwd=project, check=True, capture_output=True, text=True, encoding="utf-8", timeout=60)
    goroot = subprocess.run([args.go, "env", "GOROOT"], cwd=project, check=True, capture_output=True, text=True, encoding="utf-8", timeout=30)
    review = json.loads((project / "license-review.json").read_text(encoding="utf-8"))
    if review.get("schema_version") != 1:
        raise ValueError("unsupported license review schema")
    notice = collect_notices(decode_package_stream(listed.stdout), Path(goroot.stdout.strip()), project, review)
    # Build outputs are generated artifacts. Refuse an accidental overwrite.
    with args.output.open("x", encoding="utf-8", newline="\n") as stream:
        stream.write(notice)


if __name__ == "__main__":
    main()
