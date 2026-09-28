"""Test-only Seatbelt profile composition for AF_UNIX policy probes.

This module is deliberately outside the production sandbox path. Its profile
grant is limited to connecting to AF_UNIX sockets below one approved root.
"""

from __future__ import annotations

from pathlib import Path


def build_test_profile(base_profile: str, approved_socket_root: Path) -> str:
    """Append one path-scoped AF_UNIX connect grant to a deny-default profile."""

    if not isinstance(base_profile, str) or not base_profile:
        raise ValueError("base Seatbelt profile must be non-empty text")

    root = Path(approved_socket_root)
    raw_path = str(root)
    if not root.is_absolute():
        raise ValueError("approved AF_UNIX socket root must be absolute")
    if any(ord(char) < 32 or ord(char) == 127 for char in raw_path):
        raise ValueError("approved AF_UNIX socket root contains a control character")
    if any(part in {".", ".."} for part in root.parts):
        raise ValueError("approved AF_UNIX socket root must be normalized")

    quoted_path = raw_path.replace("\\", "\\\\").replace('"', '\\"')
    return (
        base_profile
        + '(allow file-read-metadata file-test-existence (subpath "'
        + quoted_path
        + '"))'
        + "(allow system-socket (socket-domain AF_UNIX))"
        + '(allow network-outbound (remote unix-socket (subpath "'
        + quoted_path
        + '")))'
    )
