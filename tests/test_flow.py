"""Bootstrap CLI checks; these are not evaluator conformance tests."""
import subprocess
import sys
import unittest

from stargate import CONTRACT_STATUS, KELVIN, __version__


class BootstrapCLI(unittest.TestCase):
    def run_cli(self, *args):
        return subprocess.run([sys.executable, "-m", "stargate", *args],
                              text=True, capture_output=True)

    def test_version_identifies_draft(self):
        result = self.run_cli("--version")
        self.assertEqual(result.returncode, 0)
        self.assertIn(f"build {__version__}", result.stdout)
        self.assertIn(f"{KELVIN}K ({CONTRACT_STATUS})", result.stdout)

    def test_unimplemented_verify_is_rejected(self):
        result = self.run_cli("verify", "record.json")
        self.assertEqual(result.returncode, 2)
        self.assertIn("unrecognized arguments", result.stderr)

    def test_help_states_actual_scope(self):
        result = self.run_cli("--help")
        self.assertEqual(result.returncode, 0)
        self.assertIn("not implemented", result.stdout)


if __name__ == "__main__":
    unittest.main()
