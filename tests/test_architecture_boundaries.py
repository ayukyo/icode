"""架构边界回归测试 —— 盒子→模块登记表的强制约束。

唯一真源：docs/architecture/modules.json

强制约束：
  1. 完备性    —— 每个 src/icode 模块都必须登记；新增未登记模块即失败。
  2. 平台隔离  —— 编排层不得**顶层** import 平台专用模块。
                 函数内延迟 import 是本仓既有的刻意解耦机制，只登记不禁止。
  3. hub 反向依赖 —— 平台专用模块不得顶层 import sandbox_policy / isolation。

本文件只做静态检查，不导入 icode 运行时（避免环境依赖）。
登记表用 JSON 而非 YAML：core 零第三方依赖是硬约束，标准库无 YAML 解析器，
自研 YAML 解析器的脆弱性不优于直接用 JSON。
"""
from __future__ import annotations

import ast
import json
import os
import unittest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC_ROOT = os.path.join(REPO_ROOT, "src", "icode")
REGISTRY_PATH = os.path.join(REPO_ROOT, "docs", "architecture", "modules.json")
ARCH_DOC_PATH = os.path.join(REPO_ROOT, "docs", "icode-agent-product-architecture.md")

# 豁免总数上限：超过说明有人在绕过评审扩大豁免面
MAX_EXEMPTIONS = 40


def _registry() -> dict:
    with open(REGISTRY_PATH, "r", encoding="utf-8") as handle:
        return json.load(handle)


def discover_modules(root: str = SRC_ROOT) -> dict[str, str]:
    """返回 {模块名: 文件路径}。口径：src/icode 下所有 .py，含 __init__.py。"""
    found: dict[str, str] = {}
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d != "__pycache__"]
        for filename in filenames:
            if not filename.endswith(".py"):
                continue
            path = os.path.join(dirpath, filename)
            rel = os.path.relpath(path, root).replace(os.sep, ".")
            name = (rel[: -len(".__init__.py")] if rel.endswith(".__init__.py")
                    else rel[: -len(".py")])
            found[name] = path
    return found


def _resolve(raw: str, modules: dict[str, str]) -> str | None:
    if raw in modules:
        return raw
    parts = raw.split(".")
    for i in range(len(parts) - 1, 0, -1):
        candidate = ".".join(parts[:i])
        if candidate in modules:
            return candidate
    return None


def analyze_imports(root: str = SRC_ROOT) -> tuple[dict[str, set[str]], dict[str, set[str]]]:
    """返回 (顶层 import 边, 函数内延迟 import 边)。"""
    modules = discover_modules(root)
    packages: set[str] = set()
    for name, path in modules.items():
        if os.path.basename(path) == "__init__.py":
            packages.add(name)

    top: dict[str, set[str]] = {}
    deferred: dict[str, set[str]] = {}

    for name, path in modules.items():
        with open(path, "r", encoding="utf-8") as handle:
            tree = ast.parse(handle.read(), filename=path)
        package = (name if name in packages
                   else (name.rsplit(".", 1)[0] if "." in name else ""))

        def targets_of(node: ast.Import | ast.ImportFrom) -> list[str]:
            if isinstance(node, ast.Import):
                return [alias.name for alias in node.names]
            if node.level:
                parts = package.split(".") if package else []
                if node.level > 1:
                    parts = parts[: len(parts) - (node.level - 1)]
                base = ".".join(parts + ([node.module] if node.module else []))
                return [base if node.module else (package or name)]
            return [node.module] if node.module else []

        top_set: set[str] = set()
        for node in tree.body:
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                for raw in targets_of(node):
                    resolved = _resolve(raw, modules)
                    if resolved and resolved != name:
                        top_set.add(resolved)
        top[name] = top_set

        deferred_set: set[str] = set()
        for func in ast.walk(tree):
            if not isinstance(func, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            for node in ast.walk(func):
                if isinstance(node, (ast.Import, ast.ImportFrom)):
                    for raw in targets_of(node):
                        resolved = _resolve(raw, modules)
                        if resolved and resolved != name:
                            deferred_set.add(resolved)
        deferred[name] = deferred_set

    return top, deferred


def check_completeness(module_names: set[str], registered: set[str]) -> list[str]:
    """完备性检查：返回未登记的模块名。

    抽成接受「虚拟清单」的纯函数，使负例自测无需向仓库写入任何文件。
    """
    return sorted(module_names - registered)


class ArchitectureBoundaryTests(unittest.TestCase):
    """架构边界的回归防线。新增模块必须登记；边界违反必须显式豁免。"""

    @classmethod
    def setUpClass(cls) -> None:
        cls.registry = _registry()
        cls.modules = discover_modules()
        cls.top, cls.deferred = analyze_imports()
        boxes = cls.registry.get("boxes", {})
        registered: set[str] = set()
        cls.box_of: dict[str, str] = {}
        for box_name, body in boxes.items():
            for module in body.get("modules", []):
                registered.add(module)
                cls.box_of[module] = box_name
        cls.registered = registered

    def _layer_of(self, module: str) -> int:
        box = self.box_of.get(module)
        if box is None:
            return 99
        return int(self.registry["boxes"][box].get("layer", 99))

    # ---------------------------------------------------------------- 完备性
    def test_registry_covers_every_module(self) -> None:
        """每个 src/icode 模块都必须登记（双向相等）。"""
        missing = check_completeness(set(self.modules), self.registered)
        self.assertEqual(
            [], missing,
            "有模块未在 docs/architecture/modules.json 登记："
            f"{missing}。新增模块必须登记其盒子与层级。",
        )

    def test_registry_has_no_phantom_modules(self) -> None:
        """登记表不得包含不存在的模块（防止改名后留下僵尸条目）。"""
        phantom = check_completeness(self.registered, set(self.modules))
        self.assertEqual(
            [], phantom,
            f"登记表中的模块在 src/icode 下不存在：{phantom}",
        )

    def test_completeness_check_detects_unregistered(self) -> None:
        """负例自测：完备性检查必须能发现未登记模块。

        用虚拟清单调用纯函数，**不向仓库写入任何文件**。
        """
        result = check_completeness(
            {"known_module", "brand_new_unregistered_module"},
            {"known_module"},
        )
        self.assertEqual(["brand_new_unregistered_module"], result)

    def test_registry_module_count_matches(self) -> None:
        """登记表声明的模块数必须与实际一致。"""
        declared = self.registry.get("meta", {}).get("module_count")
        self.assertIsNotNone(declared, "modules.json 的 meta.module_count 缺失")
        self.assertEqual(
            int(declared), len(self.modules),
            "modules.json 的 meta.module_count 与实际模块数不符",
        )

    # ------------------------------------------------------------ 豁免清单
    def test_exemptions_are_explicit_and_bounded(self) -> None:
        """豁免必须逐条显式登记，禁止通配符，且总数受上限约束。"""
        exempts = self.registry.get("exempt", [])
        self.assertLessEqual(
            len(exempts), MAX_EXEMPTIONS,
            f"豁免条目数 {len(exempts)} 超过上限 {MAX_EXEMPTIONS}；"
            "新增豁免必须走评审并说明理由",
        )
        for item in exempts:
            self.assertIsInstance(item, dict, f"豁免条目必须是映射：{item!r}")
            for field in ("module", "rule", "reason", "reviewer"):
                self.assertIn(field, item, f"豁免条目缺少 {field} 字段：{item!r}")
                value = item[field]
                self.assertTrue(
                    isinstance(value, str) and value.strip(),
                    f"豁免条目的 {field} 不得为空：{item!r}",
                )
            for wildcard in ("*", "?", "**"):
                self.assertNotIn(
                    wildcard, str(item.get("target", "")),
                    f"豁免禁止通配符：{item!r}",
                )
            self.assertIn(
                item["module"], self.modules,
                f"豁免条目指向不存在的模块：{item['module']}",
            )

    # ------------------------------------------------------------ 规则 2
    def test_orchestration_layers_do_not_top_import_platform_modules(self) -> None:
        """编排层不得顶层 import 平台专用模块（延迟 import 只登记不禁止）。"""
        prefixes = tuple(self.registry.get("platform_module_prefixes", []))
        self.assertTrue(prefixes, "modules.json 未声明 platform_module_prefixes")
        exemptions = {
            (item["module"], item.get("target", ""))
            for item in self.registry.get("exempt", [])
            if item.get("rule") == "no-platform-top-import-in-orch"
        }
        violations: list[str] = []
        for name, deps in self.top.items():
            if self._layer_of(name) > 2:
                continue
            for dep in sorted(deps):
                if not dep.startswith(prefixes):
                    continue
                if (name, dep) in exemptions:
                    continue
                violations.append(f"{name} 顶层 import {dep}")
        self.assertEqual(
            [], violations,
            "编排层顶层 import 平台专用模块（须显式豁免）：\n  " + "\n  ".join(violations),
        )

    def test_deferred_platform_imports_are_registered(self) -> None:
        """编排层的延迟平台 import 必须登记（保持可见性，不禁止）。"""
        prefixes = tuple(self.registry.get("platform_module_prefixes", []))
        registered = {
            item["module"]: set(item.get("targets", []))
            for item in self.registry.get("deferred_platform_imports", [])
        }
        unregistered: list[str] = []
        for name, deps in self.deferred.items():
            if self._layer_of(name) > 2:
                continue
            for dep in sorted(deps):
                if not dep.startswith(prefixes):
                    continue
                if dep in registered.get(name, set()):
                    continue
                unregistered.append(f"{name} 延迟 import {dep}")
        self.assertEqual(
            [], unregistered,
            "编排层的延迟平台 import 未登记：\n  " + "\n  ".join(unregistered),
        )

    # ------------------------------------------------------------ 规则 3
    def test_platform_modules_do_not_top_import_hubs(self) -> None:
        """平台专用模块不得顶层 import sandbox_policy / isolation。"""
        hub_targets = {"sandbox_policy", "isolation"}
        exemptions = {
            item["module"]
            for item in self.registry.get("exempt", [])
            if item.get("rule") == "no-hub-import-from-platform"
        }
        violations: list[str] = []
        for name, deps in self.top.items():
            if not name.startswith(("windows_", "linux_")):
                continue
            if name in exemptions:
                continue
            for dep in sorted(deps & hub_targets):
                violations.append(f"{name} 顶层 import {dep}")
        self.assertEqual(
            [], violations,
            "平台专用模块顶层 import hub（须显式豁免）：\n  " + "\n  ".join(violations),
        )

    # ------------------------------------------------------------ 文档同步
    def test_architecture_doc_points_at_registry(self) -> None:
        """架构文档必须指向登记表，映射关系才有唯一真源。"""
        self.assertTrue(
            os.path.isfile(ARCH_DOC_PATH),
            f"架构文档不存在：{ARCH_DOC_PATH}",
        )
        with open(ARCH_DOC_PATH, "r", encoding="utf-8") as handle:
            text = handle.read()
        self.assertIn(
            "modules.json", text,
            "架构文档未引用 docs/architecture/modules.json；"
            "盒子→模块映射的唯一真源必须被文档指向",
        )


if __name__ == "__main__":
    unittest.main()
