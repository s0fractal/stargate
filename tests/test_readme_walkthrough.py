"""The README runner itself. Registered in docs/README_REGISTRY.md (outcome 3)."""
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parent.parent
RUNNER = ROOT / 'tools' / 'readme_walkthrough.py'


def run(readme_text):
    with tempfile.NamedTemporaryFile('w', suffix='.md', delete=False) as handle:
        handle.write(readme_text)
    try:
        result = subprocess.run([sys.executable, str(RUNNER), '--readme', handle.name],
                                capture_output=True, text=True, cwd=ROOT)
        return result.returncode, result.stderr
    finally:
        Path(handle.name).unlink()


class Runner(unittest.TestCase):
    def test_no_sh_block_is_invalid_input(self):
        self.assertEqual(run('# nothing\n```text\necho hi\n```\n')[0], 2)

    def test_a_failing_command_fails_with_its_status(self):
        self.assertEqual(run('```sh\ntrue\n(exit 4)\n```\n')[0], 4)

    def test_writing_into_the_checkout_fails_even_when_every_command_succeeds(self):
        name = 'readme-walkthrough-probe.txt'
        try:
            code, err = run('```sh\necho x > ' + name + '\n```\n')
        finally:
            (ROOT / name).unlink(missing_ok=True)
        self.assertEqual(code, 1, err)
        self.assertIn('changed the checkout', err)

    def test_text_blocks_are_not_run(self):
        self.assertEqual(run('```text\nexit 9\n```\n```sh\ntrue\n```\n')[0], 0)

    def test_blocks_share_one_shell(self):
        self.assertEqual(run('```sh\nX=5\n```\nprose\n```sh\ntest "$X" = 5\n```\n')[0], 0)
