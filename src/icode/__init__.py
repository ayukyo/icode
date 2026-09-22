"""ICODE 自主 Agent 运行时。

定位：**过程可审计** —— 证据在每一步执行中原生产出，而不是事后从日志里抽。
与治理 sidecar 阵营的切割点：它们审"产物"，我们审"过程"。

本包单向只读消费 icode-skill 的流程真源：
  - steps/*.md              流程合同（给模型看）
  - mcp/workflow-gate/gates.json   门禁真源（机器读）
  - tools/icode_control.py  控制面（唯一写入口）
"""

__version__ = "0.1.0"

__all__ = ["__version__"]
