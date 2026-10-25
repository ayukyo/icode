"""Architecture metrics for ICODE src/icode — import graph, hubs, cycles, unclassified modules."""
from __future__ import annotations

import ast
import json
import os
import sys
from collections import defaultdict

BASE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
ROOT = os.path.join(BASE, "src", "icode")
TESTS = os.path.join(BASE, "tests")


def module_name(path: str, root: str) -> str:
    rel = os.path.relpath(path, root).replace(os.sep, ".")
    if rel.endswith(".__init__.py"):
        rel = rel[: -len(".__init__.py")]
    elif rel.endswith(".py"):
        rel = rel[:-3]
    return rel


def collect(root: str) -> dict[str, dict]:
    mods: dict[str, dict] = {}
    # first pass: know which names are packages
    pkgs: set[str] = set()
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d != "__pycache__"]
        if "__init__.py" in filenames:
            pkgs.add(module_name(os.path.join(dirpath, "__init__.py"), root))
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d != "__pycache__"]
        for fn in filenames:
            if not fn.endswith(".py"):
                continue
            p = os.path.join(dirpath, fn)
            name = module_name(p, root)
            with open(p, "r", encoding="utf-8") as fh:
                src = fh.read()
            tree = ast.parse(src, filename=p)
            deps: set[str] = set()
            classes: list[str] = []
            funcs: list[str] = []
            methods = 0
            for node in ast.walk(tree):
                if isinstance(node, ast.ClassDef):
                    classes.append(node.name)
                    methods += sum(1 for c in node.body if isinstance(c, (ast.FunctionDef, ast.AsyncFunctionDef)))
                elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    funcs.append(node.name)
            pkg = name if name in pkgs else (name.rsplit(".", 1)[0] if "." in name else "")
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for a in node.names:
                        deps.add(a.name)
                elif isinstance(node, ast.ImportFrom):
                    if node.level:  # relative import
                        parts = pkg.split(".") if pkg else []
                        if node.level > 1:
                            parts = parts[: len(parts) - (node.level - 1)]
                        target = ".".join(parts + ([node.module] if node.module else []))
                        if node.module:
                            deps.add(target)
                        else:
                            deps.add(pkg or name)
                        for a in node.names:
                            deps.add(f"{target}.{a.name}" if target else a.name)
                    elif node.module:
                        deps.add(node.module)
                        for a in node.names:
                            deps.add(f"{node.module}.{a.name}")
            mods[name] = {
                "path": p,
                "loc": len(src.splitlines()),
                "code": sum(1 for l in src.splitlines() if l.strip() and not l.strip().startswith("#")),
                "deps": deps,
                "classes": classes,
                "funcs": funcs,
                "methods": methods,
            }
    return mods


def internal_deps(name: str, mods: dict) -> set[str]:
    """Resolve a dep string to an internal module name, or None."""
    parts = name.split(".")
    # exact match, or a package prefix match
    if name in mods:
        return name
    for i in range(len(parts) - 1, 0, -1):
        cand = ".".join(parts[:i])
        if cand in mods:
            return cand
    return None


def find_cycles(mods: dict) -> list[list[str]]:
    graph: dict[str, set[str]] = {}
    for name, m in mods.items():
        out = set()
        for d in m["deps"]:
            t = internal_deps(d, mods)
            if t and t != name:
                out.add(t)
        graph[name] = out
    cycles: list[list[str]] = []
    seen: set[frozenset] = set()
    color: dict[str, int] = {}

    def dfs(u: str, stack: list[str]):
        color[u] = 1
        stack.append(u)
        for v in sorted(graph.get(u, ())):
            if color.get(v, 0) == 0:
                dfs(v, stack)
            elif color.get(v, 0) == 1:
                idx = stack.index(v)
                cyc = stack[idx:] + [v]
                key = frozenset(cyc)
                if key not in seen:
                    seen.add(key)
                    cycles.append(cyc)
        stack.pop()
        color[u] = 2

    for n in sorted(graph):
        if color.get(n, 0) == 0:
            dfs(n, [])
    return cycles


def test_coverage(mods: dict) -> dict[str, list[str]]:
    direct: dict[str, list[str]] = defaultdict(list)
    test_files = []
    for dirpath, dirnames, filenames in os.walk(TESTS):
        dirnames[:] = [d for d in dirnames if d != "__pycache__"]
        for fn in filenames:
            if fn.endswith(".py"):
                test_files.append(os.path.join(dirpath, fn))
    for p in test_files:
        with open(p, "r", encoding="utf-8") as fh:
            try:
                tree = ast.parse(fh.read(), filename=p)
            except SyntaxError:
                continue
        imported: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for a in node.names:
                    imported.add(a.name)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported.add(node.module)
                for a in node.names:
                    imported.add(f"{node.module}.{a.name}")
        for m in mods:
            if m in imported or any(d.endswith("." + m) or d == m for d in imported):
                direct[m].append(os.path.relpath(p, TESTS))
    return direct


def main():
    mods = collect(ROOT)
    fan_in: dict[str, int] = defaultdict(int)
    fan_out: dict[str, int] = defaultdict(int)
    graph: dict[str, set[str]] = {}
    for name, m in mods.items():
        outs = set()
        for d in m["deps"]:
            t = internal_deps(d, mods)
            if t and t != name:
                outs.add(t)
        graph[name] = outs
        fan_out[name] = len(outs)
    for u, outs in graph.items():
        for v in outs:
            fan_in[v] += 1

    cycles = find_cycles(mods)
    cov = test_coverage(mods)

    print("=" * 72)
    print(f"modules={len(mods)}  loc={sum(m['loc'] for m in mods.values())}  "
          f"code={sum(m['code'] for m in mods.values())}")
    print("=" * 72)
    print("\n--- FAN-IN (top 15) ---")
    for n, c in sorted(fan_in.items(), key=lambda x: -x[1])[:15]:
        print(f"  {c:3d}  {n}")
    print("\n--- FAN-OUT (top 15) ---")
    for n, c in sorted(fan_out.items(), key=lambda x: -x[1])[:15]:
        print(f"  {c:3d}  {n}")
    print(f"\n--- CYCLES: {len(cycles)} ---")
    for c in cycles[:20]:
        print("  " + " -> ".join(c))

    print("\n--- UNTESTED (no direct test import) ---")
    untested = []
    for n, m in sorted(mods.items(), key=lambda x: -x[1]["loc"]):
        if not cov.get(n):
            untested.append((n, m["loc"]))
    total_un = sum(l for _, l in untested)
    for n, l in untested:
        print(f"  {l:5d}  {n}")
    print(f"  --> {len(untested)} modules, {total_un} LOC untested directly")

    print("\n--- GOD CLASSES / CLASS METRICS (top 20 by class size) ---")
    for name, m in sorted(mods.items(), key=lambda x: -x[1]["loc"])[:20]:
        print(f"  {m['loc']:5d} loc  {len(m['classes']):2d} cls  {m['methods']:4d} meth  "
              f"{len(m['funcs']):4d} func  {name}")

    out = {
        "modules": len(mods),
        "loc": sum(m["loc"] for m in mods.values()),
        "cycles": len(cycles),
        "fan_in": dict(fan_in),
        "fan_out": dict(fan_out),
        "untested_modules": untested,
    }
    with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "metrics_out.json"), "w") as fh:
        json.dump(out, fh, indent=2)


if __name__ == "__main__":
    main()
