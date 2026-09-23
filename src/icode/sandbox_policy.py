"""Versioned, platform-neutral sandbox policy wire contract.

This module describes policy data only. It does not apply or enable sandboxing.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, fields
from enum import Enum
from pathlib import Path
from typing import Iterable, Mapping


POLICY_SCHEMA_VERSION = 1


class PolicyValidationError(ValueError):
    """Raised when a sandbox policy violates its versioned contract."""


class NetworkMode(str, Enum):
    DENY = "deny"
    PROXY_ALLOWLIST = "proxy_allowlist"


def _normalize_paths(paths: Iterable[Path]) -> tuple[Path, ...]:
    normalized = {
        Path(path).expanduser().resolve(strict=False)
        for path in paths
    }
    return tuple(sorted(normalized, key=str))


@dataclass(frozen=True)
class SandboxPolicy:
    schema_version: int
    run_id: str
    ticket_id: str
    step: str
    workspace_root: Path
    read_roots: tuple[Path, ...]
    write_roots: tuple[Path, ...]
    deny_read_roots: tuple[Path, ...]
    deny_write_roots: tuple[Path, ...]
    network_mode: NetworkMode
    allowed_domains: tuple[str, ...]
    process_limit: int
    wall_timeout_seconds: int
    output_limit_bytes: int
    protected_paths: tuple[Path, ...]

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "workspace_root",
            Path(self.workspace_root).expanduser().resolve(strict=False),
        )
        for name in (
            "read_roots",
            "write_roots",
            "deny_read_roots",
            "deny_write_roots",
            "protected_paths",
        ):
            object.__setattr__(self, name, _normalize_paths(getattr(self, name)))
        object.__setattr__(self, "network_mode", NetworkMode(self.network_mode))
        object.__setattr__(
            self,
            "allowed_domains",
            tuple(
                sorted(
                    {
                        domain.strip().lower().rstrip(".")
                        for domain in self.allowed_domains
                    }
                )
            ),
        )
        self.validate()

    def validate(self) -> None:
        if self.schema_version != POLICY_SCHEMA_VERSION:
            raise PolicyValidationError(
                f"unsupported sandbox policy schema_version: {self.schema_version!r}"
            )

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "run_id": self.run_id,
            "ticket_id": self.ticket_id,
            "step": self.step,
            "workspace_root": str(self.workspace_root),
            "read_roots": [str(path) for path in self.read_roots],
            "write_roots": [str(path) for path in self.write_roots],
            "deny_read_roots": [str(path) for path in self.deny_read_roots],
            "deny_write_roots": [str(path) for path in self.deny_write_roots],
            "network_mode": self.network_mode.value,
            "allowed_domains": list(self.allowed_domains),
            "process_limit": self.process_limit,
            "wall_timeout_seconds": self.wall_timeout_seconds,
            "output_limit_bytes": self.output_limit_bytes,
            "protected_paths": [str(path) for path in self.protected_paths],
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, object]) -> SandboxPolicy:
        expected = {field.name for field in fields(cls)}
        supplied = set(data)
        missing = expected - supplied
        unknown = supplied - expected
        if missing or unknown:
            details = []
            if missing:
                details.append(f"missing fields: {sorted(missing)}")
            if unknown:
                details.append(f"unknown fields: {sorted(unknown)}")
            raise PolicyValidationError("; ".join(details))

        return cls(
            schema_version=data["schema_version"],  # type: ignore[arg-type]
            run_id=data["run_id"],  # type: ignore[arg-type]
            ticket_id=data["ticket_id"],  # type: ignore[arg-type]
            step=data["step"],  # type: ignore[arg-type]
            workspace_root=Path(data["workspace_root"]),  # type: ignore[arg-type]
            read_roots=tuple(Path(path) for path in data["read_roots"]),  # type: ignore[union-attr]
            write_roots=tuple(Path(path) for path in data["write_roots"]),  # type: ignore[union-attr]
            deny_read_roots=tuple(Path(path) for path in data["deny_read_roots"]),  # type: ignore[union-attr]
            deny_write_roots=tuple(Path(path) for path in data["deny_write_roots"]),  # type: ignore[union-attr]
            network_mode=NetworkMode(data["network_mode"]),  # type: ignore[arg-type]
            allowed_domains=tuple(data["allowed_domains"]),  # type: ignore[arg-type]
            process_limit=data["process_limit"],  # type: ignore[arg-type]
            wall_timeout_seconds=data["wall_timeout_seconds"],  # type: ignore[arg-type]
            output_limit_bytes=data["output_limit_bytes"],  # type: ignore[arg-type]
            protected_paths=tuple(Path(path) for path in data["protected_paths"]),  # type: ignore[union-attr]
        )

    def canonical_json(self) -> str:
        return json.dumps(
            self.to_dict(),
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        )

    @property
    def policy_hash(self) -> str:
        return hashlib.sha256(self.canonical_json().encode("utf-8")).hexdigest()
