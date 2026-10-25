"""Deeper metrics: platform mixing, duplication, coupling instability, API surface."""
from __future__ import annotations

import ast
import os
import re
from collections import defaultdict

BASE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
ROOT = os.path.join(BASE, "src", "icode")
TESTS = os.path.join(BASE, "tests")


def module_name(path, root):
    rel = os.path.relpath(path, root).replace(os.sep, ".")
    if rel.endswith(".__init__.py"):
        rel = rel[: -len(".__init__.py")]
    elif rel.endswith(".py"):
        rel = rel[:-3]
    return rel


files = {}
pkgs = set()
for dp, dn, fns in os.walk(ROOT):
    dn[:] = [d for d in dn if d != "__pycache__"]
    if "__init__.py" in fns:
        pkgs.add(module_name(os.path.join(dp, "__init__.py"), ROOT))
for dp, dn, fns in os.walk(ROOT):
    dn[:] = [d for d in dn if d != "__pycache__"]
    for fn in fns:
        if fn.endswith(".py"):
            p = os.path.join(dp, fn)
            files[module_name(p, ROOT)] = p

print("=" * 78)
print("A. PLATFORM CODE MIXING (same file holds both win32 and posix logic)")
print("=" * 78)
WIN_PAT = re.compile(r"sys\.platform|win32|Windows|Win32|ctypes\.windll|CREATE_", re.I)
POSIX_PAT = re.compile(r"posix|os\.fork|killpg|setpgid|waitid|kqueue|SIGKILL|Landlock|seccomp", re.I)

mixed = []
for name, p in sorted(files.items()):
    src = open(p, encoding="utf-8").read()
    if name.startswith("windows_") or name.startswith("linux_"):
        continue  # platform-dedicated modules are fine
    w = len(WIN_PAT.findall(src))
    po = len(POSIX_PAT.findall(src))
    if w >= 3 and po >= 3:
        mixed.append((name, w, po, len(src.splitlines())))
print(f"  mixed-platform modules (>=3 win refs and >=3 posix refs): {len(mixed)}")
for n, w, po, loc in sorted(mixed, key=lambda x: -(x[1] + x[2]))[:15]:
    print(f"    {n:36s} win={w:3d} posix={po:3d} loc={loc:5d}")

print()
print("=" * 78)
print("B. DUPLICATION: repeated function bodies (exact AST-normalized)")
print("=" * 78)
sigs = defaultdict(list)
for name, p in files.items():
    tree = ast.parse(open(p, encoding="utf-8").read(), filename=p)
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            try:
                key = ast.dump(ast.parse(ast.unparse(node)))
            except Exception:
                continue
            # normalize away the function name
            key = re.sub(r"name='[^']*'", "name='<fn>'", key)
            if len(key) < 400:  # skip tiny/boring
                continue
            sigs[key].append((name, node.name, node.lineno,
                              node.end_lineno - node.lineno + 1))
dups = [v for v in sigs.values() if len(v) > 1]
dup_lines = 0
for grp in sorted(dups, key=lambda g: -sum(x[3] for x in g)):
    tot = sum(x[3] for x in grp)
    if tot < 40:
        continue
    dup_lines += tot
    print(f"  [{len(grp)} copies, {tot} total lines]")
    for m, fn, ln, sz in grp:
        print(f"      {m}:{ln}  {fn}()  ({sz} lines)")
print(f"  --> duplicate groups: {len(dups)}, duplicated lines ~{dup_lines}")

print()
print("=" * 78)
print("C. LONG PARAMETER LISTS / BIG SIGNATURES (>8 params)")
print("=" * 78)
big = []
for name, p in files.items():
    tree = ast.parse(open(p, encoding="utf-8").read(), filename=p)
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            n = len(node.args.args) + len(node.args.kwonlyargs)
            if n >= 8:
                big.append((name, node.name, node.lineno, n))
for m, fn, ln, n in sorted(big, key=lambda x: -x[3])[:15]:
    print(f"    {n:2d} params  {m}:{ln}  {fn}()")
print(f"  --> functions with >=8 params: {len(big)}")

print()
print("=" * 78)
print("D. GLOBAL / MUTABLE MODULE STATE")
print("=" * 78)
globals_ = []
for name, p in files.items():
    tree = ast.parse(open(p, encoding="utf-8").read(), filename=p)
    for node in tree.body:
        val = None
        tgt = None
        if isinstance(node, ast.Assign):
            val = node.value
            tgt = ast.unparse(node.targets[0])
        elif isinstance(node, ast.AnnAssign):
            val = node.value
            tgt = ast.unparse(node.target)
        if isinstance(val, (ast.List, ast.Dict, ast.Set)):
            sz = len(val.elts) if hasattr(val, "elts") else len(val.keys)
            globals_.append((name, node.lineno, tgt, sz))
for m, ln, t, sz in sorted(globals_, key=lambda x: -x[3])[:15]:
    print(f"    {sz:3d} entries  {m}:{ln}  {t}")
print(f"  --> module-level mutable globals: {len(globals_)}")

print()
print("=" * 78)
print("E. TEST FILE ORGANIZATION vs SOURCE")
print("=" * 78)
tfiles = defaultdict(int)
for dp, dn, fns in os.walk(TESTS):
    dn[:] = [d for d in dn if d != "__pycache__"]
    for fn in fns:
        if fn.startswith("test_"):
            tfiles[fn] += 1
print(f"  test files: {len(tfiles)}")
print(f"  test files naming a src module pattern (test_<module>.py): "
      f"{len([f for f in tfiles if f[5:-3] in files])}")
srcs = set(files)
matched = {f for f in tfiles if f[5:-3] in srcs}
print(f"  --> direct 1:1 test files for src modules: {len(matched)}/{len(srcs)}")
