"""The anchor gate: all four digests must describe one snapshot, and a tag name
must follow the checker digest. Registered in tools/REGISTRY-ANCHORS.md."""
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

from stargate import certificate, lab, transport

ROOT = Path(__file__).resolve().parent.parent
GATE = ROOT / 'tools' / 'anchors.py'


def run(*arguments):
    """The gate's exit code, or None while the gate does not exist."""
    if not GATE.exists():
        return None
    return subprocess.run([sys.executable, '-I', str(GATE), *arguments],
                          capture_output=True, text=True).returncode


def output(*arguments):
    if not GATE.exists():
        return ''
    return subprocess.run([sys.executable, '-I', str(GATE), *arguments],
                          capture_output=True, text=True).stdout.strip()


class AnchorGate(unittest.TestCase):
    def test_this_source_matches_one_snapshot(self):
        self.assertEqual(run('--check'), 0)

    def test_the_tag_name_follows_the_checker_digest(self):
        self.assertEqual(output('--tag'), 'checker-' + certificate.checker_id()[:12])


if __name__ == '__main__':
    unittest.main()
