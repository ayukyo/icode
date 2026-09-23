"""策略会话的精确工单产物端口；模型进程不直接访问宿主账本。"""

from __future__ import annotations

import fnmatch
import json
import os
import re
import stat
import tempfile
from dataclasses import dataclass
from pathlib import Path

from .contracts import Port, StepContract

_ARTIFACT_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
# review_manifest 由带真实 attempt/哈希的控制面装配，模型正文不可替代。
_MACHINE_OWNED = frozenset({"review_manifest.json"})


class ArtifactAccessError(ValueError):
    """仅返回稳定错误，不包含宿主目录和模型正文。"""


def _reject_nonfinite(_value: str) -> None:
    raise ValueError("non-finite JSON number")


@dataclass(frozen=True)
class ArtifactBroker:
    out_dir: Path
    contract: StepContract
    max_bytes: int

    def __post_init__(self) -> None:
        root = Path(self.out_dir)
        if root.is_symlink() or not root.is_dir():
            raise ArtifactAccessError("工单产物目录不可用")
        if type(self.max_bytes) is not int or self.max_bytes <= 0:
            raise ArtifactAccessError("工单产物限额非法")
        object.__setattr__(self, "out_dir", root.resolve())

    def _target(self, name: str, ports: tuple[Port, ...], *, write: bool) -> Path:
        if type(name) is not str or _ARTIFACT_NAME.fullmatch(name) is None:
            raise ArtifactAccessError("产物名非法")
        if write and name in _MACHINE_OWNED:
            raise ArtifactAccessError("机器装配产物不可由模型提交")
        allowed = any(
            (port.kind == "ticket_file" and port.value == name)
            or (port.kind == "ticket_glob" and fnmatch.fnmatchcase(name, port.value)
                and "/" not in port.value and "\\" not in port.value)
            for port in ports
        )
        if not allowed:
            raise ArtifactAccessError("产物不在当前步骤合同内")
        target = self.out_dir / name
        if target.is_symlink() or (target.exists() and not target.is_file()):
            raise ArtifactAccessError("产物目标不是普通文件")
        return target

    def submit(self, name: str, content: str) -> int:
        """校验后在宿主目录原子替换；登记仍由现有控制面执行。"""
        target = self._target(name, self.contract.outputs, write=True)
        if type(content) is not str:
            raise ArtifactAccessError("产物正文必须是文本")
        try:
            body = content.encode("utf-8")
        except UnicodeError:
            raise ArtifactAccessError("产物正文不是 UTF-8 文本") from None
        if len(body) > self.max_bytes:
            raise ArtifactAccessError("产物正文超过限额")
        if name.endswith(".json"):
            try:
                parsed = json.loads(content, parse_constant=_reject_nonfinite)
            except (ValueError, TypeError):
                raise ArtifactAccessError("产物不是合法 JSON 对象") from None
            if not isinstance(parsed, dict):
                raise ArtifactAccessError("产物不是合法 JSON 对象")

        try:
            descriptor, temporary = tempfile.mkstemp(prefix=".icode-artifact-", dir=self.out_dir)
        except OSError:
            raise ArtifactAccessError("宿主产物写入失败") from None
        try:
            with os.fdopen(descriptor, "wb") as stream:
                stream.write(body)
                stream.flush()
                os.fsync(stream.fileno())
            # 临时文件位于宿主受保护目录，模型命令无法访问。
            if target.is_symlink() or (target.exists() and not target.is_file()):
                raise ArtifactAccessError("产物目标已改变")
            os.replace(temporary, target)
        except OSError:
            raise ArtifactAccessError("宿主产物写入失败") from None
        finally:
            if os.path.exists(temporary):
                try:
                    os.unlink(temporary)
                except OSError:
                    pass
        return len(body)

    def read(self, name: str) -> str:
        """仅返回合同声明的既有输入，禁止读取账本元数据。"""
        target = self._target(name, self.contract.inputs, write=False)
        if not target.is_file():
            raise ArtifactAccessError("声明的输入不存在")
        try:
            descriptor = os.open(
                target, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
            )
            with os.fdopen(descriptor, "rb") as stream:
                if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode):
                    raise ArtifactAccessError("声明的输入不是普通文件")
                body = stream.read(self.max_bytes + 1)
            if len(body) > self.max_bytes:
                raise ArtifactAccessError("输入正文超过限额")
            return body.decode("utf-8")
        except (OSError, UnicodeError):
            raise ArtifactAccessError("声明的输入不可读") from None
