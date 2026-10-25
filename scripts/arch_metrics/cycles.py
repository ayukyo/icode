"""Precise cycle analysis: locate exact import statements, detect TYPE_CHECKING guards."""
from __future__ import annotations

import ast
import os
from collections import defaultdict

BASE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
ROOT = os.path.join(BASE, "src", "icode")


def module_name(path: str, root: str) -> str:
    rel = os.path.relpath(path, root).replace(os.sep, ".")
    if rel.endswith(".__init__.py"):
        rel = rel[: -len(".__init__.py")]
    elif rel.endswith(".py"):
        rel = rel[:-3]
    return rel


def build():
    mods, pkgs, trees = {}, set(), {}
    for dirpath, dirnames, filenames in os.walk(ROOT):
        dirnames[:] = [d for d in dirnames if d != "__pycache__"]
        if "__init__.py" in filenames:
            pkgs.add(module_name(os.path.join(dirpath, "__init__.py"), ROOT))
    for dirpath, dirnames, filenames in os.walk(ROOT):
        dirnames[:] = [d for d in dirnames if d != "__pycache__"]
        for fn in filenames:
            if fn.endswith(".py"):
                p = os.path.join(dirpath, fn)
                n = module_name(p, ROOT)
                mods[n] = p
                trees[n] = ast.parse(open(p, encoding="utf-8").read(), filename=p)
    return mods, pkgs, trees


def resolve_dep(src_mod: str, node, pkgs, mods):
    """Return list of (target_module, kind) for a single import node."""
    out = []
    if isinstance(node, ast.Import):
        for a in node.names:
            out.append((a.name, "import"))
        return out
    pkg = src_mod if src_mod in pkgs else (src_mod.rsplit(".", 1)[0] if "." in src_mod else "")
    if node.level:
        parts = pkg.split(".") if pkg else []
        if node.level > 1:
            parts = parts[: len(parts) - (node.level - 1)]
        target = ".".join(parts + ([node.module] if node.module else []))
        if node.module:
            out.append((target, "rel-from"))
            for a in node.names:
                out.append((f"{target}.{a.name}", "rel-from-name"))
        else:
            out.append((pkg or src_mod, "rel-package"))
            for a in node.names:
                out.append((f"{target}.{a.name}" if target else a.name, "rel-from-name"))
    elif node.module:
        out.append((node.module, "from"))
        for a in node.names:
            out.append((f"{node.module}.{a.name}", "from-name"))
    return out


def in_type_checking(node) -> bool:
    """True if the import node is nested inside an `if TYPE_CHECKING:` block."""
    for parent in ast.walk(node):
        pass
    return False


def main():
    mods, pkgs, trees = build()

    # per-module: resolved internal deps with source info
    edges: dict[str, dict[str, list]] = defaultdict(lambda: defaultdict(list))
    guarded: set[tuple[str, str]] = set()

    for n, tree in trees.items():
        for node in ast.walk(tree):
            if not isinstance(node, (ast.Import, ast.ImportFrom)):
                continue
            # detect TYPE_CHECKING context
            tc = False
            for parent in ast.walk(tree):
                if isinstance(parent, ast.If) and node in ast.walk(parent):
                    test = ast.unparse(parent.test)
                    if "TYPE_CHECKING" in test:
                        tc = True
                        break
            for target, kind in resolve_dep(n, node, pkgs, mods):
                t = target
                if t not in mods:
                    found = None
                    parts = t.split(".")
                    for i in range(len(parts) - 1, 0, -1):
                        cand = ".".join(parts[:i])
                        if cand in mods:
                            found = cand
                            break
                    if not found:
                        continue
                    t = found
                if t == n:
                    continue
                edges[n][t].append((node.lineno, kind, tc))

    # find cycles (Tarjan SCC)
    nodes = set(edges) | {t for n in edges for t in edges[n]}
    index, low, onstack, stack, sccs = {}, {}, set(), [], []
    counter = [0]

    def strongconnect(v):
        index[v] = low[v] = counter[0]
        counter[0] += 1
        stack.append(v)
        onstack.add(v)
        for w in edges.get(v, {}):
            if w not in index:
                strongconnect(w)
                low[v] = min(low[v], low[w])
            elif w in onstack:
                low[v] = min(low[v], index[w])
        if low[v] == index[v]:
            comp = []
            while True:
                w = stack.pop()
                onstack.discard(w)
                comp.append(w)
                if w == v:
                    break
            if len(comp) > 1:
                sccs.append(comp)
            elif comp and comp[0] in edges.get(comp[0], {}):
                sccs.append(comp)

    for v in sorted(nodes):
        if v not in index:
            strongconnect(v)

    print(f"total internal modules: {len(mods)}")
    print(f"SCCs with >1 member: {len(sccs)}\n")

    for comp in sorted(sccs, key=lambda c: -len(c)):
        print("=" * 78)
        print(f"CYCLE GROUP ({len(comp)} modules): {', '.join(sorted(comp))}")
        print("-" * 78)
        for m in sorted(comp):
            for t, srcs in sorted(edges.get(m, {}).items()):
                if t not in comp:
                    continue
                for lineno, kind, tc in srcs:
                    tag = " [TYPE_CHECKING]" if tc else ""
                    print(f"  {m}  ->  {t}   (line {lineno}, {kind}){tag}")
        print()


if __name__ == "__main__":
    main()
