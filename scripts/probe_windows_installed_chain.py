"""Bounded installed-source observations, never launch or compatibility authority."""
import argparse
import json
import re
import sys
import sysconfig
from pathlib import PureWindowsPath

import icode
from icode.native_helper import windows_arch_from_platform
from icode.windows_startup_host_identity import WindowsStartupHostIdentity
from icode.windows_startup_native import WindowsStartupPinBackend
from icode.windows_startup_pin import MAX_STARTUP_BYTES, _local_components, _metadata, pin_startup_file
from icode.windows_startup_security import (
    StartupSecurityError, _MUTATION_ACCESS_MASK, _DELETE_CHILD,
    check_startup_security, parse_startup_security,
)


_MAX_CHAIN_NODES = 32
_MAX_OBSERVED_ACES = 512  # Count both successful snapshots, even if equal.
_WIRE_LIMIT = 256 * 1024  # Includes the one final LF or CRLF.


def _installed_resources():
    # PureWindowsPath is lexical: never resolve reparse ancestors before pinning.
    package = icode.__file__
    purelib = sysconfig.get_path("purelib")
    _local_components(package)
    _local_components(purelib)
    root = PureWindowsPath(purelib)
    if PureWindowsPath(package) != root / "icode" / "__init__.py":
        raise ValueError("invalid_installed_source")
    arch = windows_arch_from_platform(sysconfig.get_platform())
    resources = tuple((resource, root / "icode" / "native" / f"icode-{name}-windows-{arch}.exe")
                      for resource, name in (("helper", "sandbox"), ("verifier", "provenance")))
    for _, path in resources:
        if 1 + len(_local_components(str(path))[1]) > _MAX_CHAIN_NODES:
            raise ValueError("invalid_installed_source")
    return arch, resources


def _owner_category(sid, host_sid):
    if sid == "S-1-5-32-544":
        return "admin"
    if sid == "S-1-5-18":
        return "system"
    return "host" if sid == host_sid else "other"


def _trustee_category(sid, host_sid):
    category = _owner_category(sid, host_sid)
    if category != "other":
        return category
    return {"S-1-1-0": "everyone", "S-1-5-11": "authenticated_users",
            "S-1-5-32-545": "builtin_users", "S-1-3-0": "creator_owner",
            "S-1-3-4": "owner_rights"}.get(sid, "other")


def _policy_result(raw, host_sid, directory):
    try:
        check_startup_security(raw, role="source", host_sid=host_sid, directory=directory)
    except StartupSecurityError as exc:
        messages = {"startup security owner is not trusted for role": "owner_untrusted",
                    "untrusted ACE permits startup mutation": "mutation_untrusted",
                    "empty DACL cannot establish usable startup security": "empty_dacl"}
        # This handler surrounds only the independent pure policy invocation.
        if len(exc.args) == 1 and type(exc.args[0]) is str and exc.args[0] in messages:
            return messages[exc.args[0]]
        raise
    return "pass"


def _observe_resource(resource, path, host_sid, budget):
    # Bound the lexical chain before acquiring any native object.
    if not 2 <= 1 + len(_local_components(str(path))[1]) <= _MAX_CHAIN_NODES:
        raise ValueError("installed_chain_budget")
    backend = WindowsStartupPinBackend()
    owner = pin_startup_file(str(path), _backend=backend)
    try:
        owner.revalidate()
        count = len(owner._handles)
        if not 2 <= count <= _MAX_CHAIN_NODES or len(owner._baseline) != count:
            raise ValueError("installed_chain_budget")
        if type(budget) is not list or len(budget) != 1 or type(budget[0]) is not int or not 0 <= budget[0] <= _MAX_OBSERVED_ACES:
            raise ValueError("installed_chain_budget")
        chain = []
        for index, (handle, baseline) in enumerate(zip(owner._handles, owner._baseline)):
            before = _metadata(backend.query(handle), directory=baseline.directory, max_bytes=MAX_STARTUP_BYTES)
            raw_before = backend.query_security(handle)
            raw_after = backend.query_security(handle)
            after = _metadata(backend.query(handle), directory=baseline.directory, max_bytes=MAX_STARTUP_BYTES)
            if before != baseline or after != baseline:
                raise ValueError("installed_metadata_drift")
            if type(raw_before) is not bytes or type(raw_after) is not bytes or raw_before != raw_after:
                raise ValueError("installed_descriptor_drift")
            first = parse_startup_security(raw_before)
            second = parse_startup_security(raw_after)
            budget[0] += len(first.entries) + len(second.entries)
            if budget[0] > _MAX_OBSERVED_ACES:
                raise ValueError("installed_chain_budget")
            mask = _MUTATION_ACCESS_MASK | (_DELETE_CHILD if baseline.directory else 0)
            policy = _policy_result(raw_before, host_sid, baseline.directory)
            _finite_string(policy, {"pass", "owner_untrusted", "mutation_untrusted", "empty_dacl"})
            chain.append({"index": index, "kind": "root" if index == 0 else "file" if index == count - 1 else "ancestor",
                          "directory": baseline.directory, "metadata_observed_equal": True,
                          "descriptor_observed_equal": True, "parser_result": "supported",
                          "policy_result": policy,
                          "owner": _owner_category(first.owner_sid, host_sid),
                          "entries": [{"allowed": entry.allowed, "flags": entry.flags,
                                       "mutation": entry.mask & mask,
                                       "trustee": _trustee_category(entry.sid, host_sid)} for entry in first.entries]})
        owner.revalidate()
        result = {"resource": resource, "role": "source", "image_sha256": owner.sha256,
                  "chain": chain, "owned_handles": count, "confirmed_closes": count,
                  "unconfirmed_closes": 0}
    except BaseException as original:
        owner._close_preserving_exception(original)
        raise
    # Outside the body handler: an ambiguous close must never be retried.
    owner.close()
    if not owner.close_confirmed:
        raise ValueError("installed_close_unconfirmed")
    return result


def probe(source_sha):
    if sys.platform != "win32" or type(source_sha) is not str or re.fullmatch("[0-9a-f]{40}", source_sha) is None:
        raise ValueError("invalid_installed_observation_input")
    if (sys.version_info.major, sys.version_info.minor) not in ((3, 11), (3, 12)):
        raise ValueError("invalid_installed_observation_input")
    arch, resources = _installed_resources()
    identity = WindowsStartupHostIdentity()
    host_sid = identity.capture()
    if identity.cleanup_unconfirmed is not False:
        raise ValueError("installed_identity_close_unconfirmed")
    budget = [0]
    observed = [_observe_resource(resource, path, host_sid, budget) for resource, path in resources]
    version = sys.getwindowsversion()
    return {"schema_version": 1, "scope": "installed_source_chain_observation", "source_sha": source_sha,
            "architecture": arch, "python": [sys.version_info.major, sys.version_info.minor],
            "windows": [version.major, version.minor, version.build], "observation_complete": True,
            "source_policy_all_passed": all(node["policy_result"] == "pass" for resource in observed for node in resource["chain"]),
            "protected_observed": False, "compatibility_accepted": False, "launch_authorized": False,
            "resources": observed}


_TOP_KEYS = {"schema_version", "scope", "source_sha", "architecture", "python", "windows",
             "observation_complete", "source_policy_all_passed", "protected_observed",
             "compatibility_accepted", "launch_authorized", "resources"}
_RESOURCE_KEYS = {"resource", "role", "image_sha256", "chain", "owned_handles", "confirmed_closes", "unconfirmed_closes"}
_NODE_KEYS = {"index", "kind", "directory", "metadata_observed_equal", "descriptor_observed_equal",
              "parser_result", "policy_result", "owner", "entries"}
_ENTRY_KEYS = {"allowed", "flags", "mutation", "trustee"}
_OWNERS = {"admin", "system", "host", "other"}
_TRUSTEES = _OWNERS | {"everyone", "authenticated_users", "builtin_users", "creator_owner", "owner_rights"}


def _require(condition):
    if not condition:
        raise ValueError("invalid_installed_chain_receipt")


def _object(value, keys):
    _require(type(value) is dict and value.keys() == keys)


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        _require(key not in result)
        result[key] = value
    return result


def _finite_string(value, choices):
    _require(type(value) is str and value in choices)


def _exact_int(value, minimum, maximum):
    _require(type(value) is int and minimum <= value <= maximum)


def _receipt_policy(node):
    if node["owner"] == "other":
        return "owner_untrusted"
    if not node["entries"]:
        return "empty_dacl"
    if any(entry["allowed"] and entry["mutation"] and entry["trustee"] not in {"admin", "system", "host", "owner_rights"}
           for entry in node["entries"]):
        return "mutation_untrusted"
    return "pass"


def validate_wire(wire, source_sha, arch):
    """Check the finite receipt contract; this is not independent OS evidence."""
    try:
        _require(type(source_sha) is str and re.fullmatch("[0-9a-f]{40}", source_sha) is not None)
        _finite_string(arch, {"x64", "arm64"})
        _require(type(wire) is bytes and 1 <= len(wire) <= _WIRE_LIMIT)
        ending = b"\r\n" if wire.endswith(b"\r\n") else b"\n"
        _require(wire.endswith(ending))
        data = json.loads(wire.decode("utf-8", "strict"), object_pairs_hook=_unique_object)
        _require(json.dumps(data, separators=(",", ":")).encode("ascii") + ending == wire)
        _object(data, _TOP_KEYS)
        _exact_int(data["schema_version"], 1, 1)
        _finite_string(data["scope"], {"installed_source_chain_observation"})
        _require(type(data["source_sha"]) is str and data["source_sha"] == source_sha)
        _require(type(data["architecture"]) is str and data["architecture"] == arch)
        for key, expected in (("observation_complete", True), ("protected_observed", False),
                              ("compatibility_accepted", False), ("launch_authorized", False)):
            _require(data[key] is expected)
        python = data["python"]
        _require(type(python) is list and len(python) == 2)
        _exact_int(python[0], 3, 3)
        _exact_int(python[1], 11, 12)
        windows = data["windows"]
        _require(type(windows) is list and len(windows) == 3)
        for value in windows:
            _exact_int(value, 0, 2**32 - 1)
        resources = data["resources"]
        _require(type(resources) is list and len(resources) == 2)
        ace_count = 0
        all_passed = True
        for resource, expected in zip(resources, ("helper", "verifier")):
            _object(resource, _RESOURCE_KEYS)
            _finite_string(resource["resource"], {expected})
            _finite_string(resource["role"], {"source"})
            digest = resource["image_sha256"]
            _require(type(digest) is str and re.fullmatch("[0-9a-f]{64}", digest) is not None)
            chain = resource["chain"]
            _require(type(chain) is list and 2 <= len(chain) <= _MAX_CHAIN_NODES)
            for key in ("owned_handles", "confirmed_closes"):
                _exact_int(resource[key], len(chain), len(chain))
            _exact_int(resource["unconfirmed_closes"], 0, 0)
            for index, node in enumerate(chain):
                _object(node, _NODE_KEYS)
                _exact_int(node["index"], index, index)
                _finite_string(node["kind"], {"root" if index == 0 else "file" if index == len(chain) - 1 else "ancestor"})
                _require(node["directory"] is (index != len(chain) - 1))
                _require(node["metadata_observed_equal"] is True and node["descriptor_observed_equal"] is True)
                _finite_string(node["parser_result"], {"supported"})
                _finite_string(node["owner"], _OWNERS)
                entries = node["entries"]
                _require(type(entries) is list)
                ace_count += 2 * len(entries)
                _require(ace_count <= _MAX_OBSERVED_ACES)
                mask = _MUTATION_ACCESS_MASK | (_DELETE_CHILD if node["directory"] else 0)
                for entry in entries:
                    _object(entry, _ENTRY_KEYS)
                    _require(type(entry["allowed"]) is bool)
                    _exact_int(entry["flags"], 0, 0x1f)
                    mutation = entry["mutation"]
                    _require(type(mutation) is int and mutation >= 0 and mutation & ~mask == 0)
                    _finite_string(entry["trustee"], _TRUSTEES)
                expected_policy = _receipt_policy(node)
                _finite_string(node["policy_result"], {expected_policy})
                all_passed = all_passed and expected_policy == "pass"
        _require(data["source_policy_all_passed"] is all_passed)
        return data
    except Exception:
        # Never expose wire content, JSON parser diagnostics, or exception causes.
        raise ValueError("invalid_installed_chain_receipt") from None


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-sha", required=True)
    args = parser.parse_args(argv)
    try:
        data = probe(args.source_sha)
        wire = json.dumps(data, separators=(",", ":")).encode("ascii") + b"\n"
        validate_wire(wire, args.source_sha, data["architecture"])
        # Probe has confirmed every token and file HANDLE close before output.
        sys.stdout.write(wire.decode("ascii"))
        return 0
    except KeyboardInterrupt:
        code = 130
    except (Exception, SystemExit):
        code = 1
    sys.stderr.write("windows_installed_chain_observation_failed\n")
    return code


if __name__ == "__main__":
    raise SystemExit(main())
