"""Versioned, platform-neutral sandbox policy wire contract.

This module describes policy data only. It does not apply or enable sandboxing.
"""

from __future__ import annotations

import hashlib
import ipaddress
import json
import re
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


def _is_within(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return True


def _roots_are_no_broader(
    candidate: Iterable[Path],
    base: Iterable[Path],
) -> bool:
    base_roots = tuple(base)
    return all(
        any(_is_within(candidate_root, base_root) for base_root in base_roots)
        for candidate_root in candidate
    )


def _denies_preserved(
    candidate: Iterable[Path],
    base: Iterable[Path],
) -> bool:
    candidate_roots = tuple(candidate)
    return all(
        any(_is_within(base_root, candidate_root) for candidate_root in candidate_roots)
        for base_root in base
    )


_DNS_LABEL_PATTERN = re.compile(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?")


def _is_exact_dns_hostname(domain: str) -> bool:
    if not domain or len(domain) > 253:
        return False
    try:
        domain.encode("ascii")
        ipaddress.ip_address(domain)
    except UnicodeEncodeError:
        return False
    except ValueError:
        pass
    else:
        return False

    labels = domain.split(".")
    return all(
        len(label) <= 63 and _DNS_LABEL_PATTERN.fullmatch(label) is not None
        for label in labels
    )


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

        for name in ("run_id", "ticket_id", "step"):
            value = getattr(self, name)
            if (
                not isinstance(value, str)
                or not value.strip()
                or any(
                    ord(character) < 32 or ord(character) == 127
                    for character in value
                )
            ):
                raise PolicyValidationError(
                    f"{name} must be non-blank and contain no ASCII control characters"
                )

        for name in (
            "process_limit",
            "wall_timeout_seconds",
            "output_limit_bytes",
        ):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
                raise PolicyValidationError(
                    f"{name} must be a strictly positive integer"
                )

        if self.network_mode is NetworkMode.DENY and self.allowed_domains:
            raise PolicyValidationError(
                "deny network mode cannot include allowed domains"
            )
        if (
            self.network_mode is NetworkMode.PROXY_ALLOWLIST
            and not self.allowed_domains
        ):
            raise PolicyValidationError(
                "proxy allowlist network mode requires at least one domain"
            )

        invalid_domains = [
            domain
            for domain in self.allowed_domains
            if not _is_exact_dns_hostname(domain)
        ]
        if invalid_domains:
            raise PolicyValidationError(
                "allowed domain must be an exact lowercase DNS hostname: "
                f"{invalid_domains!r}"
            )

        for write_root in self.write_roots:
            if not _is_within(write_root, self.workspace_root):
                raise PolicyValidationError(
                    f"write root must be within workspace_root: {write_root}"
                )

        for kind, allow_roots, deny_roots in (
            ("read", self.read_roots, self.deny_read_roots),
            ("write", self.write_roots, self.deny_write_roots),
        ):
            for allow_root in allow_roots:
                if any(_is_within(allow_root, deny_root) for deny_root in deny_roots):
                    raise PolicyValidationError(
                        f"{kind} root is fully covered by a deny root: {allow_root}"
                    )

        deny_roots = self.deny_read_roots + self.deny_write_roots
        for protected_path in self.protected_paths:
            if not any(
                _is_within(protected_path, deny_root) for deny_root in deny_roots
            ):
                raise PolicyValidationError(
                    f"protected path is not covered by a deny root: {protected_path}"
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
                details.append(f"unknown={sorted(unknown)}")
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


def tighten_policy(base: SandboxPolicy, candidate: SandboxPolicy) -> SandboxPolicy:
    """Return *candidate* when it can only reduce the authority in *base*."""

    identity_fields = (
        "schema_version",
        "run_id",
        "ticket_id",
        "step",
        "workspace_root",
    )
    if any(
        getattr(candidate, name) != getattr(base, name) for name in identity_fields
    ):
        raise PolicyValidationError(
            "candidate policy broadens by changing its identity"
        )

    for name in ("read_roots", "write_roots"):
        if not _roots_are_no_broader(getattr(candidate, name), getattr(base, name)):
            raise PolicyValidationError(f"candidate policy broadens {name}")

    for name in ("deny_read_roots", "deny_write_roots"):
        if not _denies_preserved(getattr(candidate, name), getattr(base, name)):
            raise PolicyValidationError(
                f"candidate policy broadens by weakening {name}"
            )

    if not set(base.protected_paths).issubset(candidate.protected_paths):
        raise PolicyValidationError(
            "candidate policy broadens by removing a protected path"
        )

    for name in (
        "process_limit",
        "wall_timeout_seconds",
        "output_limit_bytes",
    ):
        if getattr(candidate, name) > getattr(base, name):
            raise PolicyValidationError(f"candidate policy broadens {name}")

    if base.network_mode is NetworkMode.DENY:
        if candidate.network_mode is not NetworkMode.DENY:
            raise PolicyValidationError("candidate policy broadens network access")
    elif candidate.network_mode is NetworkMode.PROXY_ALLOWLIST:
        if not set(candidate.allowed_domains).issubset(base.allowed_domains):
            raise PolicyValidationError("candidate policy broadens allowed domains")

    return candidate
