"""Sandbox policy wire contract tests."""

from __future__ import annotations

import json
import re
import unittest
from dataclasses import FrozenInstanceError, replace
from importlib.resources import files
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import ANY

from tests import _support  # noqa: F401  # Add the repository's src/ to sys.path.

from icode.sandbox_policy import (
    NetworkMode,
    PolicyValidationError,
    SandboxPolicy,
    tighten_policy,
)


class SandboxPolicyTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self._temp_dir = TemporaryDirectory()
        self.addCleanup(self._temp_dir.cleanup)
        self.workspace = Path(self._temp_dir.name).resolve()

    def make_policy(self, **overrides: object) -> SandboxPolicy:
        values: dict[str, object] = {
            "schema_version": 1,
            "run_id": "run-001",
            "ticket_id": "ICODE-24",
            "step": "code",
            "workspace_root": self.workspace,
            "read_roots": (self.workspace,),
            "write_roots": (self.workspace,),
            "deny_read_roots": (self.workspace / ".git",),
            "deny_write_roots": (self.workspace / ".git",),
            "network_mode": NetworkMode.DENY,
            "allowed_domains": (),
            "process_limit": 32,
            "wall_timeout_seconds": 600,
            "output_limit_bytes": 4 * 1024 * 1024,
            "protected_paths": (self.workspace / ".git",),
        }
        values.update(overrides)
        return SandboxPolicy(**values)

    def assert_wire_rejected(self, wire: object) -> None:
        try:
            SandboxPolicy.from_dict(wire)  # type: ignore[arg-type]
        except Exception as error:  # Assert the public exception boundary.
            self.assertIsInstance(error, PolicyValidationError)
        else:
            self.fail("wire policy was accepted")

    def assert_direct_rejected(self, **overrides: object) -> None:
        try:
            self.make_policy(**overrides)
        except Exception as error:  # Assert the public exception boundary.
            self.assertIsInstance(error, PolicyValidationError)
        else:
            self.fail("direct policy construction was accepted")

    def test_policy_is_frozen_and_normalizes_duplicate_paths(self) -> None:
        policy = self.make_policy(
            read_roots=(self.workspace / ".", self.workspace, self.workspace)
        )

        with self.assertRaises(FrozenInstanceError):
            policy.run_id = "run-002"  # type: ignore[misc]
        self.assertEqual(policy.read_roots, (self.workspace,))

    def test_canonical_json_round_trip_and_hash_are_stable(self) -> None:
        policy = self.make_policy()
        canonical_json = policy.canonical_json()
        restored = SandboxPolicy.from_dict(json.loads(canonical_json))

        self.assertEqual(restored, policy)
        self.assertEqual(restored.canonical_json(), canonical_json)
        self.assertEqual(policy.canonical_json(), canonical_json)
        self.assertEqual(restored.policy_hash, policy.policy_hash)
        self.assertEqual(policy.policy_hash, policy.policy_hash)
        self.assertEqual(len(policy.policy_hash), 64)

    def test_proxy_allowlist_wire_format_normalizes_domains(self) -> None:
        policy = self.make_policy(
            network_mode=NetworkMode.PROXY_ALLOWLIST,
            allowed_domains=("PYPI.org", "files.pythonhosted.org", "pypi.org"),
        )

        wire = policy.to_dict()
        self.assertEqual(wire["network_mode"], "proxy_allowlist")
        self.assertEqual(
            wire["allowed_domains"],
            ["files.pythonhosted.org", "pypi.org"],
        )
        self.assertIsInstance(wire["workspace_root"], str)

    def test_from_dict_rejects_unknown_fields(self) -> None:
        wire = self.make_policy().to_dict()
        wire["shell"] = True

        with self.assertRaisesRegex(PolicyValidationError, r"unknown=.*shell"):
            SandboxPolicy.from_dict(wire)

    def test_from_dict_rejects_missing_fields_as_policy_error(self) -> None:
        wire = self.make_policy().to_dict()
        del wire["run_id"]

        self.assert_wire_rejected(wire)

    def test_from_dict_requires_strict_integer_schema_version(self) -> None:
        for value in (True, 1.0):
            with self.subTest(value=value):
                wire = self.make_policy().to_dict()
                wire["schema_version"] = value
                self.assert_wire_rejected(wire)

    def test_direct_constructor_and_replace_require_strict_schema_version(self) -> None:
        for value in (True, 1.0):
            with self.subTest(construction="direct", value=value):
                self.assert_direct_rejected(schema_version=value)

            with self.subTest(construction="replace", value=value):
                policy = self.make_policy()
                with self.assertRaises(PolicyValidationError):
                    replace(policy, schema_version=value)

    def test_direct_constructor_requires_annotation_types(self) -> None:
        invalid_values: tuple[tuple[str, object], ...] = (
            ("run_id", 42),
            ("ticket_id", True),
            ("step", b"code"),
            ("workspace_root", str(self.workspace)),
            ("read_roots", [self.workspace]),
            ("write_roots", (str(self.workspace),)),
            ("deny_read_roots", {self.workspace / ".git"}),
            ("deny_write_roots", (42,)),
            ("protected_paths", (str(self.workspace / ".git"),)),
            ("network_mode", "deny"),
            ("allowed_domains", []),
            ("allowed_domains", (42,)),
            ("process_limit", True),
            ("wall_timeout_seconds", 1.0),
            ("output_limit_bytes", False),
        )
        for field_name, value in invalid_values:
            with self.subTest(field_name=field_name, value=value):
                self.assert_direct_rejected(**{field_name: value})

    def test_from_dict_requires_string_identity_fields(self) -> None:
        for field_name in ("run_id", "ticket_id", "step", "workspace_root"):
            with self.subTest(field_name=field_name):
                wire = self.make_policy().to_dict()
                wire[field_name] = 42
                self.assert_wire_rejected(wire)

    def test_from_dict_requires_path_lists_not_other_iterables(self) -> None:
        for field_name in (
            "read_roots",
            "write_roots",
            "deny_read_roots",
            "deny_write_roots",
            "protected_paths",
        ):
            with self.subTest(field_name=field_name):
                wire = self.make_policy().to_dict()
                wire[field_name] = ""
                self.assert_wire_rejected(wire)

    def test_from_dict_requires_string_path_list_items(self) -> None:
        for field_name in (
            "read_roots",
            "write_roots",
            "deny_read_roots",
            "deny_write_roots",
            "protected_paths",
        ):
            with self.subTest(field_name=field_name):
                wire = self.make_policy().to_dict()
                wire[field_name] = [42]
                self.assert_wire_rejected(wire)

    def test_from_dict_requires_allowed_domains_list(self) -> None:
        wire = self.make_policy().to_dict()
        wire["allowed_domains"] = ""

        self.assert_wire_rejected(wire)

    def test_from_dict_requires_string_allowed_domain_items(self) -> None:
        wire = self.make_policy().to_dict()
        wire["network_mode"] = "proxy_allowlist"
        wire["allowed_domains"] = [42]

        self.assert_wire_rejected(wire)

    def test_from_dict_requires_strict_integer_limits(self) -> None:
        for field_name in (
            "process_limit",
            "wall_timeout_seconds",
            "output_limit_bytes",
        ):
            for value in (True, 1.0, "1"):
                with self.subTest(field_name=field_name, value=value):
                    wire = self.make_policy().to_dict()
                    wire[field_name] = value
                    self.assert_wire_rejected(wire)

    def test_from_dict_rejects_relative_workspace_root(self) -> None:
        wire = self.make_policy().to_dict()
        wire["workspace_root"] = "relative/workspace"
        wire["read_roots"] = ["relative/workspace"]
        wire["write_roots"] = ["relative/workspace"]
        wire["deny_read_roots"] = ["relative/workspace/.git"]
        wire["deny_write_roots"] = ["relative/workspace/.git"]
        wire["protected_paths"] = ["relative/workspace/.git"]

        self.assert_wire_rejected(wire)

    def test_from_dict_rejects_relative_paths_in_every_path_list(self) -> None:
        for field_name in (
            "read_roots",
            "write_roots",
            "deny_read_roots",
            "deny_write_roots",
            "protected_paths",
        ):
            with self.subTest(field_name=field_name):
                wire = self.make_policy().to_dict()
                current_workspace = Path.cwd().resolve()
                relative_path = "relative/path"
                absolute_path = str(current_workspace / relative_path)
                protected_path = str(current_workspace / ".git")
                wire["workspace_root"] = str(current_workspace)
                wire["read_roots"] = [str(current_workspace)]
                wire["write_roots"] = [str(current_workspace)]
                wire["deny_read_roots"] = [protected_path]
                wire["deny_write_roots"] = [protected_path]
                wire["protected_paths"] = [protected_path]
                if field_name == "deny_write_roots":
                    wire["protected_paths"] = [absolute_path]
                elif field_name == "protected_paths":
                    wire["deny_write_roots"] = [absolute_path]
                wire[field_name] = ["relative/path"]
                self.assert_wire_rejected(wire)

    def test_from_dict_rejects_invalid_network_mode_as_policy_error(self) -> None:
        for value in (42, "unrestricted"):
            with self.subTest(value=value):
                wire = self.make_policy().to_dict()
                wire["network_mode"] = value
                self.assert_wire_rejected(wire)

    def test_from_dict_canonicalizes_legal_domain_wire(self) -> None:
        wire = self.make_policy(
            network_mode=NetworkMode.PROXY_ALLOWLIST,
            allowed_domains=("pypi.org",),
        ).to_dict()
        wire["allowed_domains"] = ["PYPI.org", "pypi.org"]

        policy = SandboxPolicy.from_dict(wire)
        canonical = SandboxPolicy.from_dict(policy.to_dict())

        self.assertEqual(policy.allowed_domains, ("pypi.org",))
        self.assertEqual(policy.policy_hash, canonical.policy_hash)

    def test_mixed_case_domains_are_canonicalized_without_other_rewriting(self) -> None:
        direct = self.make_policy(
            network_mode=NetworkMode.PROXY_ALLOWLIST,
            allowed_domains=("V1.Example.Com",),
        )
        wire = direct.to_dict()
        wire["allowed_domains"] = ["FILES.PythonHosted.Org"]

        decoded = SandboxPolicy.from_dict(wire)

        self.assertEqual(direct.allowed_domains, ("v1.example.com",))
        self.assertEqual(decoded.allowed_domains, ("files.pythonhosted.org",))

    def test_deny_network_mode_rejects_allowed_domains(self) -> None:
        with self.assertRaisesRegex(
            PolicyValidationError,
            r"(?i)(?=.*deny)(?=.*domains)",
        ):
            self.make_policy(allowed_domains=("pypi.org",))

    def test_proxy_allowlist_requires_a_domain(self) -> None:
        with self.assertRaisesRegex(
            PolicyValidationError,
            r"(?i)(?=.*allowlist)(?=.*domain)",
        ):
            self.make_policy(network_mode=NetworkMode.PROXY_ALLOWLIST)

    def test_domains_must_be_exact_dns_hostnames(self) -> None:
        invalid_domains = (
            "https://pypi.org",
            "*.pypi.org",
            "pypi.org/simple",
            "pypi.org:443",
            "localhost",
            "127.0.0.1",
            "::1",
        )

        for domain in invalid_domains:
            with self.subTest(domain=domain):
                with self.assertRaisesRegex(PolicyValidationError, r"(?i)domain"):
                    wire = self.make_policy(
                        network_mode=NetworkMode.PROXY_ALLOWLIST,
                        allowed_domains=("pypi.org",),
                    ).to_dict()
                    wire["allowed_domains"] = [domain]
                    SandboxPolicy.from_dict(wire)

    def test_domains_reject_legacy_ipv4_and_untrusted_surrounding_text(self) -> None:
        attacks = (
            "127.1",
            "0177.0.0.1",
            "0x7f.0.0.1",
            " pypi.org",
            "pypi.org ",
            "pypi.org.",
            "pypi.org\n",
        )
        for domain in attacks:
            with self.subTest(source="direct", domain=domain):
                self.assert_direct_rejected(
                    network_mode=NetworkMode.PROXY_ALLOWLIST,
                    allowed_domains=(domain,),
                )

            with self.subTest(source="wire", domain=domain):
                wire = self.make_policy(
                    network_mode=NetworkMode.PROXY_ALLOWLIST,
                    allowed_domains=("pypi.org",),
                ).to_dict()
                wire["allowed_domains"] = [domain]
                self.assert_wire_rejected(wire)

    def test_policy_strings_must_be_utf8_encodable_unicode_scalars(self) -> None:
        invalid_text = "bad\ud800"
        with self.subTest(field="identity", source="direct"):
            self.assert_direct_rejected(run_id=invalid_text)
        with self.subTest(field="identity", source="wire"):
            wire = self.make_policy().to_dict()
            wire["run_id"] = invalid_text
            self.assert_wire_rejected(wire)
        with self.subTest(field="path", source="direct"):
            self.assert_direct_rejected(
                read_roots=(self.workspace / invalid_text,),
            )
        with self.subTest(field="path", source="wire"):
            wire = self.make_policy().to_dict()
            wire["read_roots"] = [str(self.workspace / invalid_text)]
            self.assert_wire_rejected(wire)
        with self.subTest(field="domain", source="direct"):
            self.assert_direct_rejected(
                network_mode=NetworkMode.PROXY_ALLOWLIST,
                allowed_domains=(f"{invalid_text}.example",),
            )
        with self.subTest(field="domain", source="wire"):
            wire = self.make_policy(
                network_mode=NetworkMode.PROXY_ALLOWLIST,
                allowed_domains=("pypi.org",),
            ).to_dict()
            wire["allowed_domains"] = [f"{invalid_text}.example"]
            self.assert_wire_rejected(wire)

    def test_path_resolution_errors_are_wrapped_as_policy_validation_errors(
        self,
    ) -> None:
        first = self.workspace / "a"
        second = self.workspace / "b"
        try:
            first.symlink_to(second)
            second.symlink_to(first)
        except (NotImplementedError, OSError) as error:
            if __import__("sys").platform == "win32":
                self.skipTest(f"symlink creation unavailable: {error}")
            raise

        with self.subTest(source="direct"):
            with self.assertRaises(PolicyValidationError) as raised:
                self.make_policy(read_roots=(first,))
            self.assertIsInstance(raised.exception.__cause__, RuntimeError)
        with self.subTest(source="wire"):
            wire = self.make_policy().to_dict()
            wire["read_roots"] = [str(first)]
            with self.assertRaises(PolicyValidationError) as raised:
                SandboxPolicy.from_dict(wire)
            self.assertIsInstance(raised.exception.__cause__, RuntimeError)

    def test_write_root_must_stay_within_workspace(self) -> None:
        with self.assertRaisesRegex(PolicyValidationError, r"(?i)write root"):
            self.make_policy(write_roots=(self.workspace.parent,))

    def test_resource_limits_must_be_strictly_positive_integers(self) -> None:
        for field_name in (
            "process_limit",
            "wall_timeout_seconds",
            "output_limit_bytes",
        ):
            with self.subTest(field_name=field_name):
                with self.assertRaisesRegex(PolicyValidationError, field_name):
                    self.make_policy(**{field_name: 0})

    def test_resource_limits_reject_bool_values(self) -> None:
        for field_name in (
            "process_limit",
            "wall_timeout_seconds",
            "output_limit_bytes",
        ):
            with self.subTest(field_name=field_name):
                with self.assertRaisesRegex(PolicyValidationError, field_name):
                    self.make_policy(**{field_name: True})

    def test_protected_path_must_be_covered_by_deny_write_root(self) -> None:
        with self.assertRaisesRegex(PolicyValidationError, r"(?i)protected path"):
            self.make_policy(
                deny_read_roots=(self.workspace / "secrets",),
                deny_write_roots=(),
                protected_paths=(self.workspace / "secrets",),
            )

    def test_deny_write_coverage_passes_without_deny_read_coverage(self) -> None:
        policy = self.make_policy(deny_read_roots=())

        self.assertEqual(policy.protected_paths, (self.workspace / ".git",))
        self.assertEqual(policy.deny_write_roots, (self.workspace / ".git",))

    def test_identity_fields_reject_blank_and_control_characters(self) -> None:
        for field_name in ("run_id", "ticket_id", "step"):
            for value in ("   ", "valid\x00invalid", "line\nbreak"):
                with self.subTest(field_name=field_name, value=value):
                    with self.assertRaisesRegex(PolicyValidationError, field_name):
                        self.make_policy(**{field_name: value})

    def test_allow_root_fully_denied_is_rejected(self) -> None:
        source_root = self.workspace / "src"

        with self.assertRaisesRegex(PolicyValidationError, r"(?i)write root"):
            self.make_policy(
                write_roots=(source_root,),
                deny_write_roots=(self.workspace,),
            )

    def test_read_root_fully_denied_is_rejected(self) -> None:
        source_root = self.workspace / "src"

        with self.assertRaisesRegex(PolicyValidationError, r"(?i)read root"):
            self.make_policy(
                read_roots=(source_root,),
                deny_read_roots=(self.workspace,),
            )

    def test_deny_subpath_takes_precedence_without_invalidating_allow_root(
        self,
    ) -> None:
        policy = self.make_policy()

        self.assertEqual(policy.write_roots, (self.workspace,))
        self.assertEqual(policy.deny_write_roots, (self.workspace / ".git",))

    def test_tighten_policy_allows_narrower_write_root(self) -> None:
        base = self.make_policy()
        candidate = replace(base, write_roots=(self.workspace / "src",))

        self.assertIs(tighten_policy(base, candidate), candidate)

    def test_tighten_policy_allows_proxy_allowlist_to_become_deny(self) -> None:
        base = self.make_policy(
            network_mode=NetworkMode.PROXY_ALLOWLIST,
            allowed_domains=("pypi.org",),
        )
        candidate = replace(
            base,
            network_mode=NetworkMode.DENY,
            allowed_domains=(),
        )

        self.assertIs(tighten_policy(base, candidate), candidate)

    def test_tighten_policy_allows_lower_process_limit(self) -> None:
        base = self.make_policy(process_limit=32)
        candidate = replace(base, process_limit=8)

        self.assertIs(tighten_policy(base, candidate), candidate)

    def test_tighten_policy_rejects_wider_write_root(self) -> None:
        base = self.make_policy(write_roots=(self.workspace / "src",))
        candidate = replace(base, write_roots=(self.workspace,))

        with self.assertRaisesRegex(PolicyValidationError, r"(?i)broadens"):
            tighten_policy(base, candidate)

    def test_tighten_policy_rejects_added_domain(self) -> None:
        base = self.make_policy(
            network_mode=NetworkMode.PROXY_ALLOWLIST,
            allowed_domains=("pypi.org",),
        )
        candidate = replace(
            base,
            allowed_domains=("files.pythonhosted.org", "pypi.org"),
        )

        with self.assertRaisesRegex(PolicyValidationError, r"(?i)broadens"):
            tighten_policy(base, candidate)

    def test_tighten_policy_rejects_higher_limit(self) -> None:
        base = self.make_policy(process_limit=8)
        candidate = replace(base, process_limit=32)

        with self.assertRaisesRegex(PolicyValidationError, r"(?i)broadens"):
            tighten_policy(base, candidate)

    def test_tighten_policy_rejects_removed_deny_rule(self) -> None:
        base = self.make_policy(
            deny_write_roots=(
                self.workspace / ".git",
                self.workspace / "secrets",
            )
        )
        candidate = replace(
            base,
            deny_write_roots=(self.workspace / ".git",),
        )

        with self.assertRaisesRegex(PolicyValidationError, r"(?i)broadens"):
            tighten_policy(base, candidate)

    def test_tighten_policy_rejects_removed_protected_path(self) -> None:
        base = self.make_policy()
        candidate = replace(base, protected_paths=())

        with self.assertRaisesRegex(PolicyValidationError, r"(?i)broadens"):
            tighten_policy(base, candidate)

    def test_tighten_policy_rejects_identity_change(self) -> None:
        base = self.make_policy()
        candidate = replace(base, run_id="run-002")

        with self.assertRaisesRegex(PolicyValidationError, r"(?i)broadens"):
            tighten_policy(base, candidate)

    def test_tighten_policy_revalidates_both_inputs(self) -> None:
        for corrupted_side in ("base", "candidate"):
            with self.subTest(corrupted_side=corrupted_side):
                base = self.make_policy()
                candidate = self.make_policy()
                object.__setattr__(
                    base if corrupted_side == "base" else candidate,
                    "schema_version",
                    True,
                )
                with self.assertRaises(PolicyValidationError):
                    tighten_policy(base, candidate)


class SandboxPolicySchemaTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        resource = files("icode").joinpath(
            "schemas/sandbox-policy-v1.schema.json"
        )
        cls.schema = json.loads(resource.read_text(encoding="utf-8"))

    def assert_pattern_accepts(
        self,
        pattern: str,
        accepted: tuple[str, ...],
        rejected: tuple[str, ...],
    ) -> None:
        for value in accepted:
            with self.subTest(value=value):
                self.assertIsNotNone(re.fullmatch(pattern, value))
        for value in rejected:
            with self.subTest(value=value):
                self.assertIsNone(re.fullmatch(pattern, value))

    def test_schema_documents_shape_and_authoritative_semantic_boundary(self) -> None:
        description = self.schema["description"].lower()

        self.assertIn("wire", description)
        self.assertIn("python", description)
        self.assertIn("semantic", description)
        self.assertIn("authoritative", description)
        self.assertIn("cross", description)

    def test_schema_locks_version_and_identity_shape(self) -> None:
        properties = self.schema["properties"]
        self.assertEqual(
            properties["schema_version"],
            {
                "type": "integer",
                "const": 1,
                "description": ANY,
            },
        )
        self.assertIn("strict", properties["schema_version"]["description"].lower())
        for field_name in ("run_id", "ticket_id", "step"):
            definition = properties[field_name]
            self.assertEqual(definition["type"], "string")
            self.assertEqual(definition["minLength"], 1)
            self.assert_pattern_accepts(
                definition["pattern"],
                ("run-001", " ticket "),
                ("", "   ", "line\nbreak", "nul\x00byte", "delete\x7f"),
            )

    def test_schema_path_and_domain_patterns_reject_attack_shapes(self) -> None:
        definitions = self.schema["$defs"]
        path_pattern = definitions["absolutePath"]["pattern"]
        self.assert_pattern_accepts(
            path_pattern,
            ("/workspace", "C:\\workspace", "\\\\server\\share\\dir"),
            ("relative/path", "./workspace", "C:relative"),
        )
        self.assertEqual(definitions["pathList"]["type"], "array")
        self.assertEqual(
            definitions["pathList"]["items"],
            {"$ref": "#/$defs/absolutePath"},
        )

        domain_pattern = definitions["domain"]["pattern"]
        self.assert_pattern_accepts(
            domain_pattern,
            ("pypi.org", "PYPI.org", "files.pythonhosted.org", "v1.example.com"),
            (
                "localhost",
                "127.0.0.1",
                "127.1",
                "0177.0.0.1",
                "0x7f.0.0.1",
                "::1",
                "https://pypi.org",
                "pypi.org/simple",
                "pypi.org:443",
                "*.pypi.org",
                " pypi.org",
                "pypi.org ",
                "pypi.org.",
                "pypi.org\n",
            ),
        )
        domain_description = definitions["domain"]["description"].lower()
        self.assertIn("legacy", domain_description)

    def test_schema_documents_unicode_scalar_decoder_boundary(self) -> None:
        description = self.schema["description"].lower()

        self.assertIn("unicode scalar", description)
        self.assertIn("strict decoder", description)

    def test_schema_encodes_network_mode_domain_cardinality(self) -> None:
        all_of = self.schema.get("allOf")
        self.assertIsInstance(all_of, list)
        if not isinstance(all_of, list):
            return
        self.assertIn(
            {
                "if": {"properties": {"network_mode": {"const": "deny"}}},
                "then": {"properties": {"allowed_domains": {"maxItems": 0}}},
            },
            all_of,
        )
        self.assertIn(
            {
                "if": {
                    "properties": {
                        "network_mode": {"const": "proxy_allowlist"}
                    }
                },
                "then": {"properties": {"allowed_domains": {"minItems": 1}}},
            },
            all_of,
        )


if __name__ == "__main__":
    unittest.main()
