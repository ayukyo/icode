"""Reproduce Darwin fixture hazards on POSIX; never grants native quota credit."""
from contextlib import contextmanager
import io
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest import mock

from tests import test_macos_m0a2_vectors as vectors


@unittest.skipUnless(os.name == "posix", "portable C/symlink fixture requires POSIX")
class TestVectorsFixturePortability(unittest.TestCase):
    def test_collector_fixture_handles_an_aliased_temporary_root(self):
        original_directory = tempfile.TemporaryDirectory

        @contextmanager
        def aliased_directory(*args, **kwargs):
            with original_directory(*args, **kwargs) as actual:
                with original_directory(prefix="m0a2-fixture-alias-") as links:
                    alias = Path(links) / "alias"
                    alias.symlink_to(Path(actual), target_is_directory=True)
                    self.assertNotEqual(alias, alias.resolve(strict=True))
                    yield str(alias)

        case = vectors.TestVectorsCollectorPortable(
            "test_actual_collector_success_and_rejection_boundaries")
        output = io.StringIO()
        with mock.patch.object(tempfile, "TemporaryDirectory", aliased_directory):
            result = unittest.TextTestRunner(stream=output, verbosity=2).run(
                unittest.TestSuite([case]))
        self.assertEqual(result.testsRun, 1)
        self.assertFalse(result.skipped, output.getvalue())
        self.assertTrue(result.wasSuccessful(), output.getvalue())

    def test_quota_fixture_compiles_with_the_legacy_stdio_gets_declaration(self):
        original_run = subprocess.run
        injected = []

        def run(command, *args, **kwargs):
            source = kwargs.get("input")
            if isinstance(source, str) and "#include <sys/resource.h>" in source:
                marker = "#include <stdio.h>\n"
                self.assertEqual(source.count(marker), 1)
                kwargs["input"] = source.replace(
                    marker, marker + "char *gets(char *);\n", 1)
                injected.append(tuple(command))
            return original_run(command, *args, **kwargs)

        # Invoke the existing software-only method directly: its class opt-in
        # controls discovery, not any native operation. Actual quota calls in
        # the compiled probe are already replaced by that method's fake APIs.
        case = vectors.TestVectorsLimitPortable(
            "test_actual_quota_source_cap2_and_exact_readback")
        with mock.patch.object(subprocess, "run", side_effect=run):
            case.test_actual_quota_source_cap2_and_exact_readback()
        self.assertEqual(len(injected), 1)

    def test_quota_fixture_selects_darwin_extensions_before_system_headers(self):
        original_run = subprocess.run
        injected = []

        def run(command, *args, **kwargs):
            source = kwargs.get("input")
            if isinstance(source, str) and "#include <sys/resource.h>" in source:
                # Model the feature-selection prerequisite on any POSIX host.
                # This is not a substitute for compiling the actual Darwin SDK.
                marker = "#include <errno.h>\n"
                self.assertIn(marker, source)
                guard = ("#ifndef _DARWIN_C_SOURCE\n"
                         '#error "quota fixture must select Darwin extensions before headers"\n'
                         "#endif\n")
                kwargs["input"] = source.replace(marker, guard + marker, 1)
                injected.append(tuple(command))
            return original_run(command, *args, **kwargs)

        case = vectors.TestVectorsLimitPortable(
            "test_actual_quota_source_cap2_and_exact_readback")
        with mock.patch.object(subprocess, "run", side_effect=run):
            case.test_actual_quota_source_cap2_and_exact_readback()
        self.assertEqual(len(injected), 1)


if __name__ == "__main__":
    unittest.main()
