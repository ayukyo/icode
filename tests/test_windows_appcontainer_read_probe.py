from __future__ import annotations

import unittest

from scripts.run_windows_appcontainer_read_probe import _format_network_error


class TestWindowsAppContainerReadProbe(unittest.TestCase):
    def test_network_error_diagnostic_accepts_only_bounded_integer_codes(self) -> None:
        self.assertEqual(_format_network_error(10013), "10013")
        self.assertEqual(_format_network_error(10051), "10051")

        for value in (None, "10013", True, -1, 65536):
            with self.subTest(value=value):
                self.assertEqual(_format_network_error(value), "unknown")


if __name__ == "__main__":
    unittest.main()
