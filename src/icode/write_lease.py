"""区域写租约：并行 Agent 的写冲突检测（R6/W2）。

规则：

- 租约按**区域**（工作区相对路径前缀）授予；两个区域相等或一个是另一个的
  前缀即重叠——重叠的第二个获取者被 ``LeaseBusy`` 拒绝，绝不静默放行。
- 双层保证：进程内区域表（线程互斥）+ 跨进程文件锁（POSIX ``flock`` /
  Windows ``msvcrt.locking``，沿用 `workspace.TicketLease` 的锁纪律：先锁后写、
  锁竞争与平台错误分别收敛为稳定码）。
- 锁文件落在显式 lease 目录（调用方给定，通常在工作区外），命名为区域摘要；
  持锁者异常退出时由 ``finally``/进程退出回收，绝不留“幽灵占用”。
- 只读角色连租约都申请不到：本模块只认调用方传入的持有者身份串，是否可写由
  角色层（`roles.assert_may_write`）先判——编排器保证判定先于租约。
"""

from __future__ import annotations

import hashlib
import os
import re
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import BinaryIO, Iterable

# 控制面/账本产物特征：与 R5 扩展契约同一份黑名单——这些位置不应成为任何
# Agent 的写区域（授权由策略层另行收紧，这里只做冲突检测的输入消毒）。
_CONTROL_PLANE_MARKERS = (
    ".ico_events.jsonl", ".ico_metadata.json", ".icode_output_",
    ".git/AI-HANDOFF", "gates.json",
)

_SEGMENT_RE = re.compile(r"^[A-Za-z0-9._-]+$")


class LeaseError(RuntimeError):
    """租约错误；``code`` 稳定。"""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(f"{code}: {message}")
        self.code = code


class LeaseBusy(LeaseError):
    """区域已被占用（进程内重叠或跨进程锁竞争）。"""

    def __init__(self, region: tuple[str, ...], holder: str) -> None:
        super().__init__("lease_busy", f"区域 {region} 已被占用")
        self.region = region
        self.holder = holder


def normalize_region(region: object) -> tuple[str, ...]:
    """把区域规范化为路径段元组；接受字符串或段元组。

    拒绝绝对路径、父目录逃逸与控制面目标。
    """
    if isinstance(region, (tuple, list)):
        parts = tuple(region)
    elif isinstance(region, str) and region.strip():
        if region.lstrip().startswith(("/", "~")) or re.match(r"^[A-Za-z]:", region.strip()):
            raise LeaseError("invalid_region", "区域必须是工作区相对路径（拒绝绝对路径）")
        text = region.replace("\\", "/").strip().strip("/")
        parts = tuple(text.split("/")) if text else ()
    else:
        raise LeaseError("invalid_region", "区域必须为非空字符串或段元组")
    if not parts:
        raise LeaseError("invalid_region", "区域不能为空")
    for part in parts:
        if not isinstance(part, str) or part in ("", ".", ".."):
            raise LeaseError("invalid_region", "区域拒绝空段与父目录逃逸")
        if _SEGMENT_RE.match(part) is None:
            raise LeaseError("invalid_region", f"区域段含非法字符：{part!r}")
    joined = "/".join(parts)
    if any(marker in joined for marker in _CONTROL_PLANE_MARKERS):
        raise LeaseError("invalid_region", "控制面/账本不是可声明写区域")
    return parts


def regions_overlap(left: tuple[str, ...], right: tuple[str, ...]) -> bool:
    """相等或前缀相关即重叠（前者覆盖后者或被后者覆盖）。"""
    shorter = min(len(left), len(right))
    return left[:shorter] == right[:shorter]


def _digest(region: tuple[str, ...]) -> str:
    return hashlib.sha256("/".join(region).encode("utf-8")).hexdigest()


def _prepare_lease_directory(lease_dir: Path) -> Path:
    try:
        lease_dir.mkdir(parents=True, exist_ok=True)
        info = lease_dir.stat()
        if not lease_dir.is_dir():
            raise LeaseError("invalid_lease_dir", "租约目录不是目录")
        if os.name == "posix":
            os.chmod(lease_dir, 0o700, follow_symlinks=False)
        del info
        return lease_dir
    except LeaseError:
        raise
    except OSError as exc:
        raise LeaseError("invalid_lease_dir", "无法准备租约目录") from exc


def _acquire_file_lock(stream: BinaryIO) -> None:
    if os.name == "posix":
        try:
            import fcntl
        except ImportError as exc:  # pragma: no cover - 异常平台安装
            raise LeaseError("lock_unavailable", "POSIX 平台缺少 fcntl") from exc
        try:
            fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            _raise_lock_error(exc)
        return
    if os.name == "nt":  # pragma: no cover - 在 Windows CI 上执行
        try:
            import msvcrt
        except ImportError as exc:
            raise LeaseError("lock_unavailable", "Windows 平台缺少 msvcrt") from exc
        stream.seek(0)
        try:
            msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
        except OSError as exc:
            _raise_lock_error(exc)
        return
    raise LeaseError("lock_unavailable", f"不支持的平台：{os.name}")


def _release_file_lock(stream: BinaryIO) -> None:
    try:
        if os.name == "posix":
            import fcntl
            fcntl.flock(stream.fileno(), fcntl.LOCK_UN)
            return
        if os.name == "nt":  # pragma: no cover - 在 Windows CI 上执行
            import msvcrt
            stream.seek(0)
            msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
            return
    except OSError:
        pass


def _raise_lock_error(exc: OSError) -> None:
    if os.name == "posix":
        contention = exc.errno in (11, 35, 11 + 0)  # EAGAIN/EWOULDBLOCK
    else:  # pragma: no cover - Windows
        contention = getattr(exc, "winerror", None) in (33, 36)
    if contention:
        raise LeaseBusy((), "") from exc
    raise LeaseError("lock_failed", f"无法获取租约文件锁：{exc}") from exc


@dataclass
class WriteLease:
    """一个已获取的写租约；离开 with 或 release 后区域即释放（含区域表除名）。"""

    region: tuple[str, ...]
    holder: str
    path: Path
    _board: "WriteLeaseBoard | None" = field(default=None, repr=False, compare=False)
    _stream: BinaryIO | None = field(default=None, repr=False, compare=False)
    _released: bool = field(default=False, repr=False, compare=False)

    def release(self) -> None:
        if self._released:
            return
        self._released = True
        stream, self._stream = self._stream, None
        if stream is not None:
            _release_file_lock(stream)
            try:
                stream.close()
            except OSError:
                pass
        board, self._board = self._board, None
        if board is not None:
            board._discard(self.region, self.holder)

    def __enter__(self) -> "WriteLease":
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.release()


class WriteLeaseBoard:
    """进程内区域表 + 跨进程文件锁的组合板。"""

    def __init__(self, lease_dir: Path | str) -> None:
        if not isinstance(lease_dir, (Path, str)) or not str(lease_dir):
            raise LeaseError("invalid_lease_dir", "lease_dir 必须为非空路径")
        self.lease_dir = Path(lease_dir)
        self._guard = threading.Lock()
        self._held: dict[Path, dict[tuple[str, ...], str]] = {}

    def acquire(self, region: object, holder: object) -> WriteLease:
        parts = normalize_region(region)
        if not isinstance(holder, str) or not holder.strip():
            raise LeaseError("invalid_holder", "持有者身份必须为非空字符串")
        holder = holder.strip()
        if len(holder) > 128:
            raise LeaseError("invalid_holder", "持有者身份过长")
        with self._guard:
            held = self._held.setdefault(self.lease_dir, {})
            for existing, owner in held.items():
                if regions_overlap(existing, parts):
                    raise LeaseBusy(existing, owner)
            lease_path = _prepare_lease_directory(self.lease_dir) / _digest(parts)
            stream = self._open_lock_file(lease_path)
            try:
                _acquire_file_lock(stream)
            except LeaseBusy:
                # 跨进程竞争：文件锁拿不到即视为占用（holder 未知，不做猜测）。
                try:
                    stream.close()
                except OSError:
                    pass
                raise LeaseBusy(parts, "unknown-cross-process") from None
            # 先锁后写：零长 inode 也必须先锁住再落持有者字节（TicketLease 纪律）。
            try:
                if os.fstat(stream.fileno()).st_size == 0:
                    stream.seek(0)
                    stream.write(holder.encode("utf-8"))
                    stream.flush()
                    os.fsync(stream.fileno())
            except OSError as exc:
                _release_file_lock(stream)
                try:
                    stream.close()
                except OSError:
                    pass
                raise LeaseError("lock_failed", "无法写入租约标识") from exc
            held[parts] = holder
            return WriteLease(region=parts, holder=holder, path=lease_path,
                              _board=self, _stream=stream)

    def _open_lock_file(self, path: Path) -> BinaryIO:
        try:
            return open(path, "r+b")
        except FileNotFoundError:
            pass
        except OSError as exc:
            raise LeaseError("lock_failed", f"无法打开租约文件：{exc}") from exc
        try:
            return open(path, "w+b")
        except OSError as exc:
            raise LeaseError("lock_failed", f"无法创建租约文件：{exc}") from exc

    def release(self, lease: WriteLease) -> None:
        if not isinstance(lease, WriteLease):
            raise LeaseError("invalid_lease", "需要 WriteLease")
        lease.release()

    def _discard(self, region: tuple[str, ...], holder: str) -> None:
        with self._guard:
            held = self._held.get(self.lease_dir)
            if held is not None and held.get(region) == holder:
                del held[region]

    def holders(self) -> dict[str, list[str]]:
        """当前占用的只读视图（区域串 → 持有者列表），供冲突审计。"""
        with self._guard:
            held = self._held.get(self.lease_dir, {})
            return {"/".join(region): [holder] for region, holder in sorted(held.items())}
