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
from typing import Iterable, Mapping, cast


POLICY_SCHEMA_VERSION = 1


class PolicyValidationError(ValueError):
    """Raised when a sandbox policy violates its versioned contract."""


class NetworkMode(str, Enum):
    DENY = "deny"
    PROXY_ALLOWLIST = "proxy_allowlist"


def _require_utf8_scalar(value: str, location: str) -> None:
    try:
        value.encode("utf-8")
    except UnicodeEncodeError as error:
        raise PolicyValidationError(
            f"{location} must contain only UTF-8 encodable Unicode scalars"
        ) from error


def _normalize_path(path: Path, location: str) -> Path:
    _require_utf8_scalar(str(path), location)
    try:
        return path.expanduser().resolve(strict=False)
    except (OSError, RuntimeError, UnicodeError, ValueError) as error:
        raise PolicyValidationError(f"unable to normalize {location}") from error


def _normalize_paths(
    paths: Iterable[Path],
    location: str,
) -> tuple[Path, ...]:
    normalized = {
        _normalize_path(path, f"{location} item")
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
_DECIMAL_IPV4_PART_PATTERN = re.compile(r"[0-9]+")
_HEX_IPV4_PART_PATTERN = re.compile(r"0x[0-9a-f]+", re.IGNORECASE)


def _is_legacy_ipv4_text(domain: str) -> bool:
    """Recognize legacy numeric IPv4 text without DNS or platform parsing."""

    parts = domain.split(".")
    return 1 <= len(parts) <= 4 and all(
        _DECIMAL_IPV4_PART_PATTERN.fullmatch(part) is not None
        or _HEX_IPV4_PART_PATTERN.fullmatch(part) is not None
        for part in parts
    )


def _is_exact_dns_hostname(domain: str) -> bool:
    if not domain or len(domain) > 253:
        return False
    try:
        domain.encode("ascii")
    except UnicodeEncodeError:
        return False
    if _is_legacy_ipv4_text(domain):
        return False
    try:
        ipaddress.ip_address(domain)
    except ValueError:
        pass
    else:
        return False

    labels = domain.split(".")
    if len(labels) < 2:
        return False
    return all(
        len(label) <= 63 and _DNS_LABEL_PATTERN.fullmatch(label) is not None
        for label in labels
    )


def is_exact_dns_hostname(domain: str) -> bool:
    """Return whether *domain* is a canonicalizable exact ASCII DNS hostname."""

    return _is_exact_dns_hostname(domain)


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
        self._validate_declared_types()
        self._validate_unicode_scalars()
        object.__setattr__(
            self,
            "workspace_root",
            _normalize_path(self.workspace_root, "workspace_root"),
        )
        for name in (
            "read_roots",
            "write_roots",
            "deny_read_roots",
            "deny_write_roots",
            "protected_paths",
        ):
            object.__setattr__(
                self,
                name,
                _normalize_paths(getattr(self, name), name),
            )
        object.__setattr__(
            self,
            "allowed_domains",
            tuple(sorted({domain.lower() for domain in self.allowed_domains})),
        )
        self.validate()

    def _validate_declared_types(self) -> None:
        if type(self.schema_version) is not int:
            raise PolicyValidationError("schema_version must be integer 1")

        for name in ("run_id", "ticket_id", "step"):
            if type(getattr(self, name)) is not str:
                raise PolicyValidationError(f"{name} must be a string")

        if not isinstance(self.workspace_root, Path):
            raise PolicyValidationError("workspace_root must be a Path")

        for name in (
            "read_roots",
            "write_roots",
            "deny_read_roots",
            "deny_write_roots",
            "protected_paths",
        ):
            value = getattr(self, name)
            if type(value) is not tuple:
                raise PolicyValidationError(f"{name} must be a tuple")
            if any(not isinstance(path, Path) for path in value):
                raise PolicyValidationError(f"{name} items must be Path instances")

        if not isinstance(self.network_mode, NetworkMode):
            raise PolicyValidationError("network_mode must be a NetworkMode")

        if type(self.allowed_domains) is not tuple:
            raise PolicyValidationError("allowed_domains must be a tuple")
        if any(type(domain) is not str for domain in self.allowed_domains):
            raise PolicyValidationError("allowed_domains items must be strings")

        for name in (
            "process_limit",
            "wall_timeout_seconds",
            "output_limit_bytes",
        ):
            if type(getattr(self, name)) is not int:
                raise PolicyValidationError(
                    f"{name} must be a strictly positive integer"
                )

    def _validate_unicode_scalars(self) -> None:
        for name in ("run_id", "ticket_id", "step"):
            _require_utf8_scalar(getattr(self, name), name)
        _require_utf8_scalar(str(self.workspace_root), "workspace_root")
        for name in (
            "read_roots",
            "write_roots",
            "deny_read_roots",
            "deny_write_roots",
            "protected_paths",
        ):
            for path in getattr(self, name):
                _require_utf8_scalar(str(path), f"{name} item")
        for domain in self.allowed_domains:
            _require_utf8_scalar(domain, "allowed_domains item")

    def validate(self) -> None:
        self._validate_declared_types()
        self._validate_unicode_scalars()

        if self.schema_version != POLICY_SCHEMA_VERSION:
            raise PolicyValidationError(
                f"unsupported sandbox policy schema_version: {self.schema_version!r}"
            )

        for name in ("run_id", "ticket_id", "step"):
            value = getattr(self, name)
            if (
                not value.strip()
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
            if value <= 0:
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
                "allowed domain must be an exact ASCII DNS hostname: "
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

        for protected_path in self.protected_paths:
            if not any(
                _is_within(protected_path, deny_root)
                for deny_root in self.deny_write_roots
            ):
                raise PolicyValidationError(
                    "protected path is not covered by a deny-write root: "
                    f"{protected_path}"
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
        if not isinstance(data, Mapping):
            raise PolicyValidationError("sandbox policy wire must be a mapping")

        expected = {field.name for field in fields(cls)}
        supplied = set(data)
        missing = expected - supplied
        unknown = supplied - expected
        if missing or unknown:
            details = []
            if missing:
                details.append(f"missing fields: {sorted(missing)}")
            if unknown:
                details.append(f"unknown={sorted(unknown, key=repr)}")
            raise PolicyValidationError("; ".join(details))

        schema_version = data["schema_version"]
        if type(schema_version) is not int or schema_version != POLICY_SCHEMA_VERSION:
            raise PolicyValidationError("schema_version must be integer 1")

        for name in ("run_id", "ticket_id", "step", "workspace_root"):
            if type(data[name]) is not str:
                raise PolicyValidationError(f"{name} must be a string")

        path_list_names = (
            "read_roots",
            "write_roots",
            "deny_read_roots",
            "deny_write_roots",
            "protected_paths",
        )
        for name in path_list_names:
            value = data[name]
            if type(value) is not list:
                raise PolicyValidationError(f"{name} must be a list")
            if any(type(item) is not str for item in value):
                raise PolicyValidationError(f"{name} items must be strings")

        allowed_domains = data["allowed_domains"]
        if type(allowed_domains) is not list:
            raise PolicyValidationError("allowed_domains must be a list")
        if any(type(domain) is not str for domain in allowed_domains):
            raise PolicyValidationError("allowed_domains items must be strings")

        for name in (
            "process_limit",
            "wall_timeout_seconds",
            "output_limit_bytes",
        ):
            if type(data[name]) is not int:
                raise PolicyValidationError(f"{name} must be an integer")

        network_mode = data["network_mode"]
        if type(network_mode) is not str:
            raise PolicyValidationError("network_mode must be a string")
        if network_mode not in {mode.value for mode in NetworkMode}:
            raise PolicyValidationError(
                f"unsupported network_mode: {network_mode!r}"
            )

        workspace_root_value = cast(str, data["workspace_root"])
        if not Path(workspace_root_value).is_absolute():
            raise PolicyValidationError("workspace_root must be an absolute path")
        for name in path_list_names:
            value = cast(list[str], data[name])
            for path_value in value:
                if not Path(path_value).is_absolute():
                    raise PolicyValidationError(
                        f"{name} items must be absolute paths"
                    )

        try:
            return cls(
                schema_version=schema_version,
                run_id=cast(str, data["run_id"]),
                ticket_id=cast(str, data["ticket_id"]),
                step=cast(str, data["step"]),
                workspace_root=Path(workspace_root_value),
                read_roots=tuple(
                    Path(path) for path in cast(list[str], data["read_roots"])
                ),
                write_roots=tuple(
                    Path(path) for path in cast(list[str], data["write_roots"])
                ),
                deny_read_roots=tuple(
                    Path(path)
                    for path in cast(list[str], data["deny_read_roots"])
                ),
                deny_write_roots=tuple(
                    Path(path)
                    for path in cast(list[str], data["deny_write_roots"])
                ),
                network_mode=NetworkMode(network_mode),
                allowed_domains=tuple(cast(list[str], allowed_domains)),
                process_limit=cast(int, data["process_limit"]),
                wall_timeout_seconds=cast(int, data["wall_timeout_seconds"]),
                output_limit_bytes=cast(int, data["output_limit_bytes"]),
                protected_paths=tuple(
                    Path(path)
                    for path in cast(list[str], data["protected_paths"])
                ),
            )
        except PolicyValidationError:
            raise
        except (OSError, RuntimeError, TypeError, UnicodeError, ValueError) as error:
            raise PolicyValidationError("invalid sandbox policy wire value") from error

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

    try:
        base.validate()
    except PolicyValidationError as error:
        raise PolicyValidationError(
            "base invalid; candidate policy broadens or cannot be proven narrower"
        ) from error

    try:
        candidate.validate()
    except PolicyValidationError as error:
        raise PolicyValidationError(
            "candidate invalid; candidate policy broadens or cannot be proven narrower"
        ) from error

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
