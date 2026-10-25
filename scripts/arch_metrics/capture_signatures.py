"""生成对外编排函数签名的基线快照。

用法：python scripts/arch_metrics/capture_signatures.py [输出路径]

SPEC A0.1 要求：P0 实施前后，`run_contract_step` / `resume_contract_step` /
`run_task` / `run_chain` 的对外签名**逐字段不变**。本脚本在改动前生成基线，
改动后由 tests/test_orchestration_context.py 比对。

签名快照是「重构不得削弱公开契约」的机器可读凭据。
"""
from __future__ import annotations

import inspect
import json
import os
import sys

BASE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(BASE, "src"))

TARGETS = [
    ("icode.runner", "run_contract_step"),
    ("icode.runner", "resume_contract_step"),
    ("icode.runner", "run_task"),
    ("icode.chain", "run_chain"),
]


def snapshot() -> dict:
    import importlib

    out: dict = {}
    for module_name, func_name in TARGETS:
        module = importlib.import_module(module_name)
        func = getattr(module, func_name)
        sig = inspect.signature(func)
        params = []
        for name, param in sig.parameters.items():
            default = None if param.default is inspect.Parameter.empty else repr(param.default)
            params.append({
                "name": name,
                "kind": str(param.kind),
                "default": default,
                "has_default": param.default is not inspect.Parameter.empty,
            })
        out[f"{module_name}.{func_name}"] = {
            "param_count": len(params),
            "params": params,
        }
    return out


def main() -> None:
    default_out = os.path.join(BASE, "docs", "nbl", "specs", "baseline_signatures.json")
    out_path = sys.argv[1] if len(sys.argv) > 1 else default_out
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    data = {
        "note": "对外编排函数签名的基线快照。P0 实施后必须逐字段不变（SPEC A0.1）。",
        "baseline_sha": os.popen("git rev-parse --short HEAD").read().strip(),
        "signatures": snapshot(),
    }
    with open(out_path, "w", encoding="utf-8") as handle:
        json.dump(data, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
    print(f"已写入 {out_path}")
    for key, body in data["signatures"].items():
        print(f"  {key}: {body['param_count']} params")


if __name__ == "__main__":
    main()
