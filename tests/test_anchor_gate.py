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


DIGESTS = None


def digests():
    from stargate import experiment
    return [certificate.checker_id(), lab.runtime_digest(lab.runtime_sources()),
            experiment.controller_id(), transport.replay_digest()]


def gate(anchors, *arguments):
    result = subprocess.run([sys.executable, '-I', str(GATE), '--anchors', str(anchors), *arguments],
                            capture_output=True, text=True)
    return result.returncode, result.stdout


def membership(text):
    """The predicate the repository had before this gate: every digest appears."""
    return all('`' + pin + '`' in text for pin in digests())


def current():
    """The label the committed table must give the snapshot of this source."""
    return 'checker-' + certificate.checker_id()[:12]


class Refusals(unittest.TestCase):
    def setUp(self):
        self.directory = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.directory)
        self.table = self.directory / 'ANCHORS.md'
        self.table.write_text((ROOT / 'ANCHORS.md').read_text())

    def test_the_committed_table_is_accepted(self):
        self.assertEqual(gate(self.table)[0], 2)      # no mode chosen is invalid input
        code, out = gate(self.table, '--check')
        self.assertEqual(code, 0)
        self.assertIn('"snapshot": "{}"'.format(current()), out)

    def test_one_changed_digit_is_refused(self):
        checker = certificate.checker_id()
        wrong = checker[:-1] + ('0' if checker[-1] != '0' else '1')
        self.table.write_text(self.table.read_text().replace(checker, wrong))
        code, out = gate(self.table, '--check')
        self.assertEqual(code, 4)
        self.assertIn('no_snapshot_describes_this_source', out)

    def test_digests_scattered_across_two_snapshots_are_refused(self):
        """The hole: the old membership predicate accepts exactly this table."""
        text = self.table.read_text()
        runtime = lab.runtime_digest(lab.runtime_sources())
        stale = [line for line in text.splitlines()
                 if '`build-37`' in line and 'Boolean lab runtime' in line][0]
        stale_digest = stale.split('`')[5]
        swapped = text.replace(runtime, '<HERE>').replace(stale_digest, runtime).replace('<HERE>', stale_digest)
        self.table.write_text(swapped)
        self.assertTrue(membership(swapped), 'the old predicate must still accept this table')
        code, out = gate(self.table, '--check')
        self.assertEqual(code, 4)
        self.assertIn('no_snapshot_describes_this_source', out)

    def test_a_tag_that_does_not_follow_the_checker_is_refused(self):
        code, out = gate(self.table, '--check-tag', 'checker-000000000000')
        self.assertEqual(code, 4)
        self.assertIn('tag_not_derived_from_checker', out)
        self.assertEqual(gate(self.table, '--check-tag',
                              'checker-' + certificate.checker_id()[:12])[0], 0)

    def test_a_snapshot_label_claiming_a_different_checker_is_refused(self):
        self.table.write_text(self.table.read_text().replace('`' + current() + '`', '`checker-000000000000`'))
        code, out = gate(self.table, '--check')
        self.assertEqual(code, 4)
        self.assertIn('snapshot_label_not_derived_from_checker', out)

    def test_a_missing_table_is_invalid_input(self):
        self.assertEqual(gate(self.directory / 'nowhere.md', '--check')[0], 2)

    def test_a_duplicated_closure_row_is_invalid_input(self):
        text = self.table.read_text()
        row = [line for line in text.splitlines()
               if '`build-38`' in line and 'Experiment controller' in line][0]
        self.table.write_text(text.replace(row, row + '\n' + row))
        code, out = gate(self.table, '--check')
        self.assertEqual(code, 2)
        self.assertIn('twice', out)


if __name__ == '__main__':
    unittest.main()
