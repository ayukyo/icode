from __future__ import annotations

import json
import stat
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import scripts.run_windows_appcontainer_read_probe as probe_module
from scripts.run_windows_appcontainer_read_probe import (
    _DaclSnapshot,
    _dacl_state_equal,
    _format_network_error,
    _normalize_inherited_ace_flag,
    _normalize_disposable_workspace_dacl_baseline,
    _safe_diagnostics,
    _stat_is_reparse_point,
    _workspace_dacl_baseline_normalization_valid,
    _workspace_dacl_entries_equivalent,
)


class TestWindowsAppContainerReadProbe(unittest.TestCase):
    def test_network_isolation_denial_requires_exact_native_and_host_evidence(self) -> None:
        verify = getattr(
            probe_module, "_network_isolation_denial_verified", None,
        )
        self.assertTrue(callable(verify), "network isolation denial verifier is missing")
        private_network_error = getattr(
            probe_module, "_NETISO_ERROR_TYPE_PRIVATE_NETWORK", 1,
        )
        receipt = {
            "token_is_appcontainer": True,
            "network_connect_attempted": True,
            "network_connected": False,
            "network_error": 10060,
            "network_isolation_diagnostic_ok": True,
            "network_isolation_status": 0,
            "network_isolation_error_type": private_network_error,
        }

        self.assertTrue(
            verify(
                receipt,
                network_target_is_private=True,
                host_listener_control=True,
                no_network_connection=True,
            ),
        )

        invalid_receipts = (
            {**receipt, "token_is_appcontainer": False},
            {**receipt, "network_connect_attempted": False},
            {**receipt, "network_connected": True},
            {**receipt, "network_error": 10061},
            {**receipt, "network_isolation_diagnostic_ok": False},
            {**receipt, "network_isolation_status": 5},
            {**receipt, "network_isolation_status": True},
            {**receipt, "network_isolation_error_type": 0},
            {**receipt, "network_isolation_error_type": True},
        )
        for invalid in invalid_receipts:
            with self.subTest(receipt=invalid):
                self.assertFalse(
                    verify(
                        invalid,
                        network_target_is_private=True,
                        host_listener_control=True,
                        no_network_connection=True,
                    ),
                )

        self.assertFalse(
            verify(
                receipt,
                network_target_is_private=True,
                host_listener_control=False,
                no_network_connection=True,
            ),
        )
        self.assertFalse(
            verify(
                receipt,
                network_target_is_private=True,
                host_listener_control=True,
                no_network_connection=False,
            ),
        )
        self.assertFalse(
            verify(
                receipt,
                network_target_is_private=False,
                host_listener_control=True,
                no_network_connection=True,
            ),
        )
        self.assertTrue(
            verify(
                {**receipt, "network_error": 10013},
                network_target_is_private=True,
                host_listener_control=True,
                no_network_connection=True,
            ),
        )

    def test_private_network_probe_address_uses_local_adapter_enumeration(self) -> None:
        select = getattr(probe_module, "_select_private_network_probe_address", None)
        self.assertTrue(callable(select), "private-network target selector is missing")
        probe_path = Path("probe.exe")
        with patch.object(
            probe_module.subprocess,
            "run",
            return_value=SimpleNamespace(returncode=0, stdout="10.12.34.56\n"),
        ) as run, patch.object(probe_module.socket, "socket") as socket_factory:
            address = select(probe_path)

        self.assertEqual(address, "10.12.34.56")
        run.assert_called_once_with(
            [str(probe_path), "--select-private-network-target"],
            check=False,
            capture_output=True,
            text=True,
            timeout=5,
        )
        socket_factory.assert_not_called()

    def test_private_network_probe_address_rejects_bad_native_enumeration(self) -> None:
        select = getattr(probe_module, "_select_private_network_probe_address", None)
        self.assertTrue(callable(select), "private-network target selector is missing")

        invalid_results = (
            SimpleNamespace(returncode=0, stdout="8.8.8.8\n"),
            SimpleNamespace(returncode=0, stdout="127.0.0.1\n"),
            SimpleNamespace(returncode=0, stdout="169.254.1.2\n"),
            SimpleNamespace(returncode=0, stdout="192.0.2.8\n"),
            SimpleNamespace(returncode=0, stdout="10.0.0.1\n192.168.0.1\n"),
            SimpleNamespace(returncode=0, stdout=""),
            SimpleNamespace(returncode=1, stdout="10.0.0.1\n"),
        )
        for native_result in invalid_results:
            with self.subTest(native_result=native_result), patch.object(
                probe_module.subprocess, "run", return_value=native_result,
            ):
                with self.assertRaisesRegex(
                    OSError, "private_network_probe_address_unavailable",
                ):
                    select(Path("probe.exe"))

        launch_failures = (
            OSError("native helper path must not leak"),
            probe_module.subprocess.TimeoutExpired("native helper", 5),
        )
        for failure in launch_failures:
            with self.subTest(failure=type(failure).__name__), patch.object(
                probe_module.subprocess, "run", side_effect=failure,
            ):
                with self.assertRaisesRegex(
                    OSError, "private_network_probe_address_unavailable",
                ):
                    select(Path("probe.exe"))

    def test_rfc1918_address_gate_uses_exact_private_ranges(self) -> None:
        is_private = getattr(probe_module, "_is_rfc1918_ipv4", None)
        self.assertTrue(callable(is_private), "RFC1918 address gate is missing")
        for address in (
            "10.0.0.1", "10.255.255.254", "172.16.0.1", "172.31.255.254",
            "192.168.0.1", "192.168.255.254",
        ):
            with self.subTest(address=address):
                self.assertTrue(is_private(address))
        for address in (
            "9.255.255.255", "172.15.255.254", "172.32.0.1", "192.167.255.254",
            "127.0.0.1", "169.254.1.2", "192.0.2.1", "8.8.8.8", "010.0.0.1",
        ):
            with self.subTest(address=address):
                self.assertFalse(is_private(address))
        self.assertFalse(is_private(True))

    def test_network_error_diagnostic_accepts_only_bounded_integer_codes(self) -> None:
        self.assertEqual(_format_network_error(10013), "10013")
        self.assertEqual(_format_network_error(10051), "10051")

        for value in (None, "10013", True, -1, 65536):
            with self.subTest(value=value):
                self.assertEqual(_format_network_error(value), "unknown")

    def test_safe_diagnostics_rejects_sid_shaped_values(self) -> None:
        self.assertEqual(
            _safe_diagnostics("stage=5; package_sid=S-1-15-2-123"),
            "stage=5",
        )
        self.assertEqual(_safe_diagnostics("S-1-15-2-123"), "none")

    def test_inherited_ace_normalization_changes_only_the_inherited_marker(self) -> None:
        ace = b"\x00\x13\x08\x00ABCD"
        self.assertEqual(
            _normalize_inherited_ace_flag(ace),
            b"\x00\x03\x08\x00ABCD",
        )
        with self.assertRaises(ValueError):
            _normalize_inherited_ace_flag(b"\x00\x10\x08\x00")

    def test_dacl_equivalence_allows_only_auto_inheritance_metadata_delta(self) -> None:
        original = _DaclSnapshot(
            descriptor_digest="before",
            acl_digest="raw-before",
            acl_bytes=b"raw-before",
            acl_capacity_bytes=b"raw-before-capacity",
            normalized_acl_digest="normalized",
            control=0x8004,
            revision=1,
            present=True,
            defaulted=False,
            file_identity=(1, 2),
            ace_count=3,
            inherited_ace_count=1,
            acl_bytes_in_use=88,
        )
        auto_inherited = replace(
            original,
            descriptor_digest="after",
            acl_digest="raw-after",
            control=0x8404,
        )

        self.assertTrue(
            _workspace_dacl_entries_equivalent(original, auto_inherited),
        )
        self.assertFalse(
            _workspace_dacl_entries_equivalent(
                original, replace(auto_inherited, control=0x8804),
            ),
        )
        self.assertFalse(
            _workspace_dacl_entries_equivalent(auto_inherited, original),
        )
        self.assertFalse(
            _workspace_dacl_entries_equivalent(
                original, replace(auto_inherited, normalized_acl_digest="different"),
            ),
        )

    def test_baseline_normalization_allows_only_inherited_marker_transition(self) -> None:
        original = _DaclSnapshot(
            descriptor_digest="before",
            acl_digest="raw-before",
            acl_bytes=b"ace-without-inherited-marker",
            acl_capacity_bytes=b"capacity-before-normalization",
            normalized_acl_digest="normalized",
            control=0x8004,
            revision=1,
            present=True,
            defaulted=False,
            file_identity=(1, 2),
            ace_count=3,
            inherited_ace_count=0,
            acl_bytes_in_use=88,
        )
        normalized = replace(
            original,
            descriptor_digest="after",
            acl_digest="raw-after",
            acl_bytes=b"ace-with-inherited-marker",
            control=0x8404,
            inherited_ace_count=3,
        )

        self.assertTrue(
            _workspace_dacl_baseline_normalization_valid(original, normalized),
        )
        self.assertFalse(
            _workspace_dacl_baseline_normalization_valid(normalized, original),
        )
        self.assertFalse(
            _workspace_dacl_baseline_normalization_valid(
                original, replace(normalized, control=0x8804),
            ),
        )
        self.assertFalse(
            _workspace_dacl_baseline_normalization_valid(
                original, replace(normalized, file_identity=(1, 3)),
            ),
        )
        self.assertFalse(
            _workspace_dacl_baseline_normalization_valid(
                original, replace(normalized, explicit_aces=(b"changed",)),
            ),
        )

    def test_baseline_normalization_failure_codes_identify_only_mismatched_contracts(self) -> None:
        failure_codes = getattr(
            probe_module, "_workspace_dacl_baseline_normalization_failure_codes", None,
        )
        self.assertTrue(callable(failure_codes), "normalization failure classifier is missing")

        original = _DaclSnapshot(
            descriptor_digest="before",
            acl_digest="raw-before",
            acl_bytes=b"acl-before",
            acl_capacity_bytes=b"acl-capacity",
            normalized_acl_digest="normalized",
            control=0x8004,
            revision=1,
            present=True,
            defaulted=False,
            file_identity=(1, 2),
            ace_count=3,
            inherited_ace_count=0,
            acl_bytes_in_use=88,
        )
        normalized = replace(original, control=0x8404)

        self.assertEqual(failure_codes(original, normalized), ())
        cases = (
            (replace(normalized, control=0x8804), ("control",)),
            (replace(normalized, control=0x9404), ("control", "protected")),
            (replace(normalized, explicit_aces=(b"changed",)), ("explicit_aces",)),
            (replace(normalized, revision=2), ("revision",)),
            (replace(normalized, present=False), ("dacl_presence",)),
            (replace(normalized, defaulted=True), ("dacl_defaulted",)),
            (replace(normalized, file_identity=(1, 3)), ("file_identity",)),
            (replace(normalized, ace_count=4), ("ace_count",)),
            (replace(normalized, acl_bytes_in_use=96), ("acl_length",)),
        )
        for changed, expected in cases:
            with self.subTest(expected=expected):
                self.assertEqual(failure_codes(original, changed), expected)

    def test_baseline_normalization_allows_only_inherited_ace_additions(self) -> None:
        failure_codes = getattr(
            probe_module, "_workspace_dacl_baseline_normalization_failure_codes", None,
        )
        self.assertTrue(callable(failure_codes), "normalization failure classifier is missing")
        before = SimpleNamespace(
            control=0x8004,
            normalized_acl_digest="before-whole-dacl",
            explicit_aces=(b"explicit-a", b"explicit-b"),
            inherited_aces=(b"i" * 20,),
            revision=1,
            present=True,
            defaulted=False,
            file_identity=(1, 2),
            ace_count=3,
            acl_bytes_in_use=88,
        )
        after = SimpleNamespace(
            control=0x8404,
            normalized_acl_digest="after-whole-dacl",
            explicit_aces=(b"explicit-a", b"explicit-b"),
            inherited_aces=(b"a" * 20, b"i" * 20, b"b" * 20),
            revision=1,
            present=True,
            defaulted=False,
            file_identity=(1, 2),
            ace_count=5,
            acl_bytes_in_use=128,
        )

        self.assertEqual(failure_codes(before, after), ())
        self.assertEqual(
            failure_codes(
                before,
                SimpleNamespace(**{
                    **vars(after),
                    "explicit_aces": (b"changed-explicit", b"explicit-b"),
                }),
            ),
            ("explicit_aces",),
        )
        self.assertEqual(
            failure_codes(
                before,
                SimpleNamespace(**{
                    **vars(after),
                    "inherited_aces": (b"c" * 20, b"b" * 20),
                }),
            ),
            ("inherited_aces",),
        )
        reordered_before = SimpleNamespace(**{
            **vars(before),
            "inherited_aces": (b"i" * 20, b"j" * 20),
            "ace_count": 4,
            "acl_bytes_in_use": 128,
        })
        reordered_after = SimpleNamespace(**{
            **vars(after),
            "inherited_aces": (b"j" * 20, b"i" * 20, b"c" * 20),
            "ace_count": 5,
            "acl_bytes_in_use": 148,
        })
        self.assertEqual(
            failure_codes(reordered_before, reordered_after),
            ("inherited_aces",),
        )

    def test_baseline_normalization_compares_raw_ace_bytes_not_digest_surrogates(self) -> None:
        failure_codes = probe_module._workspace_dacl_baseline_normalization_failure_codes
        before = SimpleNamespace(
            control=0x8004,
            explicit_ace_digests=("same-explicit-digest",),
            inherited_ace_digests=(("same-inherited-digest", 20),),
            explicit_aces=(b"explicit-before",),
            inherited_aces=(b"inherited-before",),
            revision=1,
            present=True,
            defaulted=False,
            file_identity=(1, 2),
            ace_count=2,
            acl_bytes_in_use=48,
        )
        after = SimpleNamespace(
            control=0x8404,
            explicit_ace_digests=("same-explicit-digest",),
            inherited_ace_digests=(("same-inherited-digest", 20),),
            explicit_aces=(b"explicit-after",),
            inherited_aces=(b"inherited-after",),
            revision=1,
            present=True,
            defaulted=False,
            file_identity=(1, 2),
            ace_count=2,
            acl_bytes_in_use=48,
        )

        self.assertEqual(
            failure_codes(before, after),
            ("explicit_aces", "inherited_aces"),
        )

    def test_wfp_receipt_attributes_only_completed_exact_native_subscription(self) -> None:
        classify = getattr(
            probe_module, "_classify_wfp_target_drop_receipt", None,
        )
        self.assertTrue(callable(classify), "WFP target-drop receipt classifier is missing")

        receipt = {
            "schema_version": 5,
            "subscription_ok": True,
            "unsubscribe_ok": True,
            "network_events_collected": True,
            "event_callback_count": 1,
            "capability_drop_event_count": 1,
            "classify_drop_event_count": 0,
            "matched_capability_drop_count": 1,
            "matched_classify_drop_count": 0,
            "matched_network_capability_id": 2,
            "network_capability_id_consistent": True,
        }
        self.assertEqual(
            classify(receipt, collector_exit_code=0),
            "capability_drop_private_network_attributed",
        )

    def test_wfp_receipt_identifies_private_network_capability_drop(self) -> None:
        classify = probe_module._classify_wfp_target_drop_receipt
        receipt = {
            "schema_version": 5,
            "subscription_ok": True,
            "unsubscribe_ok": True,
            "network_events_collected": True,
            "event_callback_count": 1,
            "capability_drop_event_count": 1,
            "classify_drop_event_count": 0,
            "matched_capability_drop_count": 1,
            "matched_classify_drop_count": 0,
            "matched_network_capability_id": 2,
            "network_capability_id_consistent": True,
        }
        self.assertEqual(
            classify(receipt, collector_exit_code=0),
            "capability_drop_private_network_attributed",
        )
        for capability_id, label in (
            (0, "internet_client"),
            (1, "internet_client_server"),
            (2, "private_network"),
        ):
            with self.subTest(capability_id=capability_id):
                self.assertEqual(
                    classify(
                        {**receipt, "matched_network_capability_id": capability_id},
                        collector_exit_code=0,
                    ),
                    f"capability_drop_{label}_attributed",
                )

    def test_wfp_receipt_can_attribute_an_exact_classify_drop(self) -> None:
        classify = getattr(
            probe_module, "_classify_wfp_target_drop_receipt", None,
        )
        self.assertTrue(callable(classify), "WFP target-drop receipt classifier is missing")

        receipt = {
            "schema_version": 5,
            "subscription_ok": True,
            "unsubscribe_ok": True,
            "network_events_collected": True,
            "event_callback_count": 1,
            "capability_drop_event_count": 0,
            "classify_drop_event_count": 1,
            "matched_capability_drop_count": 0,
            "matched_classify_drop_count": 1,
            "matched_network_capability_id": None,
            "network_capability_id_consistent": True,
        }
        self.assertEqual(
            classify(receipt, collector_exit_code=0),
            "classify_drop_attributed",
        )

    def test_wfp_receipt_without_callbacks_or_matching_events_is_unavailable(self) -> None:
        classify = getattr(
            probe_module, "_classify_wfp_target_drop_receipt", None,
        )
        self.assertTrue(callable(classify), "WFP target-drop receipt classifier is missing")
        receipt = {
            "schema_version": 5,
            "subscription_ok": True,
            "unsubscribe_ok": True,
            "network_events_collected": True,
            "event_callback_count": 0,
            "capability_drop_event_count": 0,
            "classify_drop_event_count": 0,
            "matched_capability_drop_count": 0,
            "matched_classify_drop_count": 0,
            "matched_network_capability_id": None,
            "network_capability_id_consistent": True,
        }
        self.assertEqual(
            classify(receipt, collector_exit_code=0),
            "evidence_unavailable",
        )

    def test_wfp_receipt_without_complete_match_remains_evidence_unavailable(self) -> None:
        classify = getattr(
            probe_module, "_classify_wfp_target_drop_receipt", None,
        )
        self.assertTrue(callable(classify), "WFP target-drop receipt classifier is missing")

        valid_receipt = {
            "schema_version": 5,
            "subscription_ok": True,
            "unsubscribe_ok": True,
            "network_events_collected": True,
            "event_callback_count": 1,
            "capability_drop_event_count": 1,
            "classify_drop_event_count": 0,
            "matched_capability_drop_count": 1,
            "matched_classify_drop_count": 0,
            "matched_network_capability_id": 2,
            "network_capability_id_consistent": True,
        }
        unavailable_cases = (
            (None, 0),
            ({**valid_receipt, "subscription_ok": False}, 0),
            ({**valid_receipt, "unsubscribe_ok": False}, 0),
            ({**valid_receipt, "network_events_collected": False}, 0),
            ({**valid_receipt, "schema_version": 4}, 0),
            ({**valid_receipt, "schema_version": 5.0}, 0),
            ({**valid_receipt, "matched_capability_drop_count": True}, 0),
            ({**valid_receipt, "matched_network_capability_id": None}, 0),
            ({**valid_receipt, "matched_network_capability_id": True}, 0),
            ({**valid_receipt, "matched_network_capability_id": 3}, 0),
            ({**valid_receipt, "network_capability_id_consistent": False}, 0),
            ({**valid_receipt, "network_capability_id_consistent": 1}, 0),
            ({**valid_receipt, "capability_drop_event_count": 0}, 0),
            ({**valid_receipt, "event_callback_count": 0}, 0),
            ({**valid_receipt, "classify_drop_event_count": "private"}, 0),
            ({**valid_receipt, "classify_drop_event_count": 1}, 0),
            ({**valid_receipt, "matched_classify_drop_count": 1}, 0),
            ({**valid_receipt, "event_callback_count": 0x10000}, 0),
            (valid_receipt, 1),
        )
        for receipt, collector_exit_code in unavailable_cases:
            with self.subTest(receipt=receipt, exit_code=collector_exit_code):
                self.assertEqual(
                    classify(receipt, collector_exit_code=collector_exit_code),
                    "evidence_unavailable",
                )

    def test_wfp_observer_diagnostics_show_only_bounded_phase_fields(self) -> None:
        summarize = getattr(
            probe_module, "_wfp_observer_diagnostic_summary", None,
        )
        self.assertTrue(callable(summarize), "WFP observer diagnostic summary is missing")

        with tempfile.TemporaryDirectory(prefix="icode-wfp-diagnostic-summary-") as raw:
            root = Path(raw)
            ready = root / "wfp-token.ready"
            stop = root / "wfp-token.stop"
            result = root / "wfp-token.json"
            ready.write_text("ready\n", encoding="ascii")
            safe_receipt = {
                "schema_version": 5,
                "subscription_ok": True,
                "unsubscribe_ok": True,
                "network_events_collected": True,
                "event_callback_count": 6,
                "capability_drop_event_count": 2,
                "classify_drop_event_count": 3,
                "matched_capability_drop_count": 1,
                "matched_classify_drop_count": 0,
                "matched_network_capability_id": 2,
                "network_capability_id_consistent": True,
            }

            summary = summarize(
                process_started=True,
                paths=(ready, stop, result),
                receipt=safe_receipt,
                collector_exit_code=0,
            )
            self.assertEqual(
                summary,
                {
                    "started": True,
                    "ready_state": "ready",
                    "collector_exit_code": 0,
                    "subscription_ok": True,
                    "unsubscribe_ok": True,
                    "network_events_collected": True,
                    "event_callback_count": 6,
                    "capability_drop_event_count": 2,
                    "classify_drop_event_count": 3,
                    "matched_capability_drop_count": 1,
                    "matched_classify_drop_count": 0,
                    "matched_network_capability_id": 2,
                    "network_capability_id_consistent": True,
                },
            )

            ready.write_text("C:\\private\\runner path\n", encoding="ascii")
            unsafe_summary = summarize(
                process_started=False,
                paths=(ready, stop, result),
                receipt={"network_events_collected": "C:\\private\\SID"},
                collector_exit_code=0,
            )
            self.assertEqual(unsafe_summary["ready_state"], "invalid")
            self.assertIsNone(unsafe_summary["network_events_collected"])
            self.assertNotIn(str(root), json.dumps(unsafe_summary))

    def test_wfp_observer_stop_collects_receipt_and_reaps_its_process(self) -> None:
        start = getattr(probe_module, "_start_wfp_event_probe", None)
        stop = getattr(probe_module, "_stop_wfp_event_probe", None)
        classify = probe_module._classify_wfp_target_drop_receipt
        self.assertTrue(callable(start), "WFP observer launcher is missing")
        self.assertTrue(callable(stop), "WFP observer cleanup is missing")

        with tempfile.TemporaryDirectory(prefix="icode-wfp-observer-test-") as raw:
            root = Path(raw)
            fake_observer = root / "fake-wfp-observer"
            fake_observer.write_text(
                "#!/usr/bin/env python3\n"
                "import json, pathlib, sys, time\n"
                "profile, target, port, ready, stop, result = sys.argv[1:]\n"
                "if profile != 'icode-0123456789abcdef0123456789abcdef' or target != '192.168.56.17' or port != '54321':\n"
                "    raise SystemExit(7)\n"
                "pathlib.Path(ready).write_text('ready\\n', encoding='ascii')\n"
                "deadline = time.monotonic() + 4\n"
                "while time.monotonic() < deadline and not pathlib.Path(stop).exists():\n"
                "    time.sleep(0.01)\n"
                "pathlib.Path(result).write_text(json.dumps({\n"
                "    'schema_version': 5, 'subscription_ok': True,\n"
                "    'network_events_collected': True,\n"
                "    'unsubscribe_ok': True, 'event_callback_count': 1,\n"
                "    'capability_drop_event_count': 1,\n"
                "    'classify_drop_event_count': 0,\n"
                "    'matched_capability_drop_count': 1,\n"
                "    'matched_classify_drop_count': 0,\n"
                "    'matched_network_capability_id': 2,\n"
                "    'network_capability_id_consistent': True,\n"
                "}), encoding='ascii')\n",
                encoding="utf-8",
            )
            fake_observer.chmod(0o755)

            invalid_process, invalid_paths = start(
                fake_observer,
                "icode-0123456789abcdef0123456789abcdef",
                "127.0.0.1",
                54321,
                root,
            )
            self.assertIsNone(invalid_process)
            self.assertIsNone(invalid_paths)
            invalid_port_process, invalid_port_paths = start(
                fake_observer,
                "icode-0123456789abcdef0123456789abcdef",
                "192.168.56.17",
                0,
                root,
            )
            self.assertIsNone(invalid_port_process)
            self.assertIsNone(invalid_port_paths)

            process, paths = start(
                fake_observer,
                "icode-0123456789abcdef0123456789abcdef",
                "192.168.56.17",
                54321,
                root,
            )
            self.assertIsNotNone(process)
            self.assertIsNotNone(paths)
            ready_path, stop_path, result_path = paths
            token = "0123456789abcdef0123456789abcdef"
            self.assertEqual(ready_path.parent, root)
            self.assertEqual(stop_path.parent, root)
            self.assertEqual(result_path.parent, root)
            self.assertEqual(ready_path.name, f"wfp-{token}.ready")
            self.assertEqual(stop_path.name, f"wfp-{token}.stop")
            self.assertEqual(result_path.name, f"wfp-{token}.json")
            receipt, exit_code = stop(process, paths)

        self.assertEqual(exit_code, 0)
        self.assertEqual(
            classify(receipt, collector_exit_code=exit_code),
            "capability_drop_private_network_attributed",
        )

    def test_dacl_state_requires_exact_acl_bytes_and_security_control(self) -> None:
        before = _DaclSnapshot(
            descriptor_digest="layout-before",
            acl_digest="digest",
            acl_bytes=b"full-acl",
            acl_capacity_bytes=b"full-acl-capacity",
            normalized_acl_digest="normalized",
            control=0x8404,
            revision=1,
            present=True,
            defaulted=False,
            file_identity=(1, 2),
            ace_count=3,
            inherited_ace_count=3,
            acl_bytes_in_use=88,
        )

        self.assertTrue(
            _dacl_state_equal(before, replace(before, descriptor_digest="new-layout")),
        )
        for changed in (
            replace(before, acl_bytes=b"changed-acl"),
            replace(before, control=0x8004),
            replace(before, file_identity=(1, 3)),
            replace(before, present=False),
        ):
            with self.subTest(changed=changed):
                self.assertFalse(_dacl_state_equal(before, changed))

    def test_baseline_normalization_rejects_reparse_disposable_root(self) -> None:
        snapshot = _DaclSnapshot(
            descriptor_digest="baseline",
            acl_digest="acl",
            acl_bytes=b"acl",
            acl_capacity_bytes=b"capacity",
            normalized_acl_digest="normalized",
            control=0x8404,
            revision=1,
            present=True,
            defaulted=False,
            file_identity=(1, 2),
            ace_count=3,
            inherited_ace_count=3,
            acl_bytes_in_use=88,
        )
        with tempfile.TemporaryDirectory() as temporary:
            parent = Path(temporary)
            actual_root = parent / "icode-appcontainer-read-handle-actual"
            actual_root.mkdir()
            (actual_root / "execution").mkdir()
            linked_root = parent / "icode-appcontainer-read-handle-linked"
            try:
                linked_root.symlink_to(actual_root, target_is_directory=True)
            except (NotImplementedError, OSError) as exc:
                self.skipTest(f"directory symlink is unavailable: {type(exc).__name__}")

            with patch(
                "scripts.run_windows_appcontainer_read_probe._dacl_snapshot",
                return_value=snapshot,
            ):
                with self.assertRaises(OSError):
                    _normalize_disposable_workspace_dacl_baseline(
                        linked_root / "execution",
                    )

    def test_baseline_normalization_reports_path_free_snapshot_failure_code(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "icode-appcontainer-read-handle-diagnostic"
            root.mkdir()
            workspace = root / "execution"
            workspace.mkdir()
            with patch(
                "scripts.run_windows_appcontainer_read_probe._dacl_snapshot",
                side_effect=OSError(5, "access denied", "sensitive-path"),
            ):
                with self.assertRaises(OSError) as raised:
                    _normalize_disposable_workspace_dacl_baseline(workspace)

        self.assertEqual(raised.exception.args, ("dacl_baseline_before_snapshot_errno_5",))

    def test_stat_reparse_detection_includes_windows_junction_attribute(self) -> None:
        regular_directory = SimpleNamespace(
            st_mode=stat.S_IFDIR | 0o755,
            st_file_attributes=0,
        )
        junction = SimpleNamespace(
            st_mode=stat.S_IFDIR | 0o755,
            st_file_attributes=0x0400,
        )
        symbolic_link = SimpleNamespace(
            st_mode=stat.S_IFLNK | 0o777,
            st_file_attributes=0,
        )

        self.assertFalse(_stat_is_reparse_point(regular_directory))
        self.assertTrue(_stat_is_reparse_point(junction))
        self.assertTrue(_stat_is_reparse_point(symbolic_link))


if __name__ == "__main__":
    unittest.main()
