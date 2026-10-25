"""Classify import cycles: hard (module-level both ways) vs deferred (function-local)."""
from __future__ import annotations

import ast
import os
from collections import defaultdict

BASE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
ROOT = os.path.join(BASE, "src", "icode")


def module_name(path, root):
    rel = os.path.relpath(path, root).replace(os.sep, ".")
    if rel.endswith(".__init__.py"):
        rel = rel[: -len(".__init__.py")]
    elif rel.endswith(".py"):
        rel = rel[:-3]
    return rel


def build():
    mods, pkgs, trees = {}, set(), {}
    for dp, dn, fns in os.walk(ROOT):
        dn[:] = [d for d in dn if d != "__pycache__"]
        if "__init__.py" in fns:
            pkgs.add(module_name(os.path.join(dp, "__init__.py"), ROOT))
    for dp, dn, fns in os.walk(ROOT):
        dn[:] = [d for d in dn if d != "__pycache__"]
        for fn in fns:
            if fn.endswith(".py"):
                p = os.path.join(dp, fn)
                n = module_name(p, ROOT)
                mods[n] = p
                trees[n] = ast.parse(open(p, encoding="utf-8").read(), filename=p)
    return mods, pkgs, trees


def collect_edges(mods, pkgs, trees):
    """Return edges[(src,dst)] = list of (lineno, scope) where scope in {module, function, class}."""
    edges = defaultdict(list)

    def visit_module(node, scope):
        for child in ast.iter_child_nodes(node):
            if isinstance(child, (ast.Import, ast.ImportFrom)):
                for target in targets(child, scope_name, pkgs, mods):
                    edges[(scope_name, target)].append((child.lineno, scope))
            elif isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                visit_module(child, "function")
            elif isinstance(child, ast.ClassDef):
                visit_module(child, "class")

    for scope_name, tree in trees.items():
        # only module-level scope matters for cycle severity
        for node in ast.iter_child_nodes(tree):
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                for target in targets(node, scope_name, pkgs, mods):
                    edges[(scope_name, target)].append((node.lineno, "module"))
            elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                for sub in ast.walk(node):
                    if isinstance(sub, (ast.Import, ast.ImportFrom)):
                        for target in targets(sub, scope_name, pkgs, mods):
                            edges[(scope_name, target)].append((sub.lineno, "deferred"))
    return edges


def targets(node, src_mod, pkgs, mods):
    out = []
    if isinstance(node, ast.Import):
        for a in node.names:
            out.append(a.name)
        return out
    pkg = src_mod if src_mod in pkgs else (src_mod.rsplit(".", 1)[0] if "." in src_mod else "")
    if node.level:
        parts = pkg.split(".") if pkg else []
        if node.level > 1:
            parts = parts[: len(parts) - (node.level - 1)]
        target = ".".join(parts + ([node.module] if node.module else []))
        out.append(target if node.module else (pkg or src_mod))
        for a in node.names:
            out.append(f"{target}.{a.name}" if target else a.name)
    elif node.module:
        out.append(node.module)
        for a in node.names:
            out.append(f"{node.module}.{a.name}")
    resolved = []
    for t in out:
        if t in mods:
            resolved.append(t)
            continue
        parts = t.split(".")
        for i in range(len(parts) - 1, 0, -1):
            cand = ".".join(parts[:i])
            if cand in mods:
                resolved.append(cand)
                break
    return resolved


def main():
    mods, pkgs, trees = build()
    edges = collect_edges(mods, pkgs, trees)

    # classify each edge
    scope_of = {}
    for (a, b), srcs in edges.items():
        if any(s == "module" for _, s in srcs):
            scope_of[(a, b)] = "HARD"
        else:
            scope_of[(a, b)] = "DEFERRED"

    # build graph on hard edges
    hard = defaultdict(set)
    soft = defaultdict(set)
    for (a, b), kind in scope_of.items():
        (hard if kind == "HARD" else soft)[a].add(b)

    # SCC on hard graph
    nodes = set(hard) | {b for bs in hard.values() for b in bs}
    index, low, onstack, stack, sccs = {}, {}, set(), [], []
    counter = [0]

    def sc(v):
        index[v] = low[v] = counter[0]; counter[0] += 1
        stack.append(v); onstack.add(v)
        for w in hard.get(v, ()):
            if w not in index:
                sc(w); low[v] = min(low[v], low[w])
            elif w in onstack:
                low[v] = min(low[v], index[w])
        if low[v] == index[v]:
            comp = []
            while True:
                w = stack.pop(); onstack.discard(w); comp.append(w)
                if w == v: break
            if len(comp) > 1: sccs.append(comp)

    for v in sorted(nodes):
        if v not in index: sc(v)

    print("=" * 78)
    print("HARD CYCLES (module-level import in BOTH directions)")
    print("=" * 78)
    if not sccs:
        print("  (none)  -> no import-time cycle; all cycles go through deferred imports")
    for comp in sorted(sccs, key=lambda c: -len(c)):
        print(f"\n  GROUP: {', '.join(sorted(comp))}")
        for m in sorted(comp):
            for t in sorted(hard.get(m, ())):
                if t in comp:
                    lns = [str(l) for l, s in edges[(m, t)] if s == "module"]
                    print(f"    {m:32s} -> {t:28s} lines {','.join(lns)}")

    print("\n" + "=" * 78)
    print("DEFERRED CYCLES (one side is a function-local import -> runtime-safe)")
    print("=" * 78)
    for (a, b), kind in sorted(scope_of.items()):
        if kind != "DEFERRED":
            continue
        # only report if there's a path back b->a
        reach = b in hard.get(a, ()) or b in soft.get(a, ())
        if not reach:
            continue
        lns = [str(l) for l, s in edges[(a, b)] if s == "deferred"]
        back = "HARD" if b in hard.get(a, ()) else "DEFERRED"
        print(f"    {a:32s} -> {b:28s} line {','.join(lns):10s} (back edge: {back})")


if __name__ == "__main__":
    main()
