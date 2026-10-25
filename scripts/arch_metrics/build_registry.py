"""生成 docs/architecture/modules.yaml —— 盒子→模块登记表。

数据来源：实测 AST 依赖图（scripts/arch_metrics/ 同族脚本），盒子语义对齐
docs/icode-agent-product-architecture.md §4/§5。生成后可人工微调，但**每次新增模块
必须重新登记**，否则 tests/test_architecture_boundaries.py 的完备性断言会失败。

用法：python scripts/arch_metrics/build_registry.py
"""
from __future__ import annotations

import ast
import os
from collections import defaultdict

BASE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
ROOT = os.path.join(BASE, "src", "icode")

# (box, layer, platform) —— layer 越小越靠近编排/入口
#   layer 1 = 入口/界面      layer 2 = 编排
#   layer 3 = 契约/策略基座   layer 4 = 平台实现
BOXES: dict[str, tuple[str, int, str]] = {}


def reg(names, box, layer, platform="generic"):
    for n in names:
        BOXES[n] = (box, layer, platform)


# ---- 入口与界面层（layer 1）----
reg(["cli", "webui", "workbench", "acp"], "UI", 1)
reg(["__init__"], "UI", 1)

# ---- 编排层（layer 2）----
reg(["runner", "chain", "autonomy", "multi_agent", "sequential", "reasoning",
     "execution_broker", "loop", "agent_scope", "agent_conclusion", "roles",
     "reviewer", "engineering_verification", "verification_presets",
     "recipes", "context_index", "compaction", "handshake"], "ORCH", 2)

# ---- 契约/策略/基座层（layer 3）----
reg(["config", "contracts", "control", "connect_request", "sandbox_policy",
     "approvals", "guard", "budget", "disclosure", "failure_policy",
     "operations", "mcp_gates", "hooks", "extension_contract", "connectors",
     "tickets", "native_helper", "skill_resources", "model_routing"],
    "BASE", 3)
reg(["evidence", "engineering_evidence", "pack_verify", "pack_signing",
     "pack_anchor", "self_verify", "checkpoint", "recovery"],
    "EVIDENCE", 3)

# ---- 隔离执行层（layer 4）----
reg(["isolation", "workspace", "workspace_snapshot", "write_lease",
     "git_broker", "git_status", "artifact_broker", "network_connector",
     "network_destination", "network_lease", "network_proxy_scope",
     "network_proxy_server", "leased_connect"], "SANDBOX", 4)

# ---- 模型后端（layer 3：稳定基座，独立于编排）----
reg(["backends", "backends.base", "backends.anthropic", "backends.gemini",
     "backends.ollama", "backends.openai_compatible", "backends.fake",
     "backends.pricing", "backends.transport"], "MODELS", 3)

# ---- 工具层（layer 3/4）----
reg(["tools", "tools.base"], "TOOLS", 3)
reg(["tools.builtin"], "TOOLS", 4)

# ---- 扩展生态（layer 3/4）----
reg(["extensions", "extensions.mcp_client"], "EXT", 3)

# ---- 评测与合规（layer 3）----
reg(["benchmark", "conformance", "conformance_evidence"], "BENCH", 3)

# ---- 平台专用（layer 5：最底层）----
reg(["windows_appcontainer", "windows_job", "windows_process_tree",
     "windows_runner_pipe", "windows_runner_protocol",
     "windows_startup_host_identity", "windows_startup_native",
     "windows_startup_pin", "windows_startup_security",
     "windows_startup_security_native", "windows_startup_source",
     "windows_worktree", "windows_positive_loopback_policy",
     "windows_provenance"], "PLATFORM", 5, "windows")
reg(["linux_admission_diagnostic", "linux_helper_object",
     "linux_helper_source", "linux_prepared_control", "linux_prepared_step",
     "linux_proxy_handoff", "linux_seccomp_notify", "linux_static_helper",
     "linux_task_resource", "linux_task_scope"], "PLATFORM", 5, "linux")


def main():
    found = set()
    for dp, dn, fns in os.walk(ROOT):
        dn[:] = [d for d in dn if d != "__pycache__"]
        for fn in fns:
            if fn.endswith(".py"):
                p = os.path.join(dp, fn)
                rel = os.path.relpath(p, ROOT).replace(os.sep, ".")
                name = (rel[: -len(".__init__.py")] if rel.endswith(".__init__.py")
                        else rel[:-3])
                found.add(name)

    missing = found - set(BOXES)
    extra = set(BOXES) - found
    if missing:
        print("未登记模块：", sorted(missing))
    if extra:
        print("登记表中有不存在的模块：", sorted(extra))
    print(f"实际 {len(found)} / 登记 {len(BOXES)}")
    return missing, extra


if __name__ == "__main__":
    main()
