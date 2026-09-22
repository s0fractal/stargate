"""The inventory in SURFACE.md must describe the commands that exist today."""
from pathlib import Path
import subprocess
import sys
import unittest

ROOT = Path(__file__).resolve().parent.parent
TOOL = ROOT / 'tools' / 'surface.py'
SURFACE = ROOT / 'SURFACE.md'


def run(*arguments):
    if not TOOL.exists():
        return None
    return subprocess.run([sys.executable, '-I', str(TOOL), *arguments],
                          capture_output=True, text=True)


class Surface(unittest.TestCase):
    def test_the_committed_inventory_is_current(self):
        result = run('--check')
        self.assertIsNotNone(result, 'no inventory tool')
        self.assertEqual((result.returncode, 'established' in result.stdout), (0, True))

    def test_every_command_has_a_row(self):
        from stargate import cli
        names = sorted(choice for action in cli.parser()._subparsers._group_actions
                       for choice in action.choices)
        text = SURFACE.read_text() if SURFACE.exists() else ''
        missing = [name for name in names if '| `' + name + '` |' not in text]
        self.assertEqual(missing, [])

    def test_a_stale_inventory_is_refused(self):
        """The control: the check must be able to fail."""
        original = SURFACE.read_text()
        self.addCleanup(SURFACE.write_text, original)
        SURFACE.write_text(original.replace('| `machine-check` |', '| `machine-checkx` |', 1))
        result = run('--check')
        self.assertEqual(result.returncode, 4)
        self.assertIn('does not match', result.stdout)


if __name__ == '__main__':
    unittest.main()
