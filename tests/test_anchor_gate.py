"""The anchor gate: every anchored digest must describe one snapshot, and a tag name
must follow the composite of all of them. Registered in tools/REGISTRY-ANCHORS.md;
the composite rule in vertical/projection_portable_REGISTRY.md (second registration)."""
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

    def test_the_tag_name_follows_the_snapshot_digest(self):
        """Moved from the checker- rule to the composite rule."""
        self.assertEqual(output('--tag'), current())


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
    gate_module = tool()
    return own_composite(gate_module.current(), gate_module.launcher())


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
        # Under the composite rule the edited rows no longer hash to their own label,
        # so the gate refuses one step earlier than it did under the checker- rule.
        self.assertIn('snapshot_label_not_derived_from_its_rows', out)

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
        self.assertIn('snapshot_label_not_derived_from_its_rows', out)

    def test_a_tag_that_does_not_follow_the_snapshot_is_refused(self):
        """Moved from the checker- rule to the composite rule."""
        code, out = gate(self.table, '--check-tag', 'snapshot-000000000000')
        self.assertEqual(code, 4)
        self.assertIn('tag_not_derived_from_snapshot', out)
        self.assertEqual(gate(self.table, '--check-tag', current())[0], 0)

    def test_a_snapshot_label_claiming_other_digests_is_refused(self):
        """Moved from the checker- rule to the composite rule."""
        self.table.write_text(self.table.read_text().replace('`' + current() + '`', '`snapshot-000000000000`'))
        code, out = gate(self.table, '--check')
        self.assertEqual(code, 4)
        self.assertIn('snapshot_label_not_derived', out)

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


def tool():
    import importlib.util
    spec = importlib.util.spec_from_file_location('anchors_tool', GATE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def own_composite(digests, launched):
    """The test's own derivation, not the gate's."""
    import hashlib, json
    body = dict(digests, **{'Offline launcher': launched})
    return 'snapshot-' + hashlib.sha256(json.dumps(body, sort_keys=True, separators=(',', ':'))
                                         .encode()).hexdigest()[:12]


def rows(label, digests, launched):
    return ''.join('| `{}` | {} | `{}` | `{}` |\n'.format(label, closure, digest, launched)
                   for closure, digest in digests.items())


class Composite(unittest.TestCase):
    """Second registration in vertical/projection_portable_REGISTRY.md."""

    def setUp(self):
        self.gate = tool()
        self.current, self.launched = self.gate.current(), self.gate.launcher()
        self.directory = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.directory)
        self.table = self.directory / 'ANCHORS.md'
        self.text = (ROOT / 'ANCHORS.md').read_text()

    def test_the_tag_is_the_composite_of_every_anchored_digest(self):
        expected = own_composite(self.current, self.launched)
        self.assertEqual(self.gate.snapshot_label(self.current, self.launched), expected)
        self.assertEqual(output('--tag'), expected)

    def test_changing_any_one_digest_alone_changes_the_tag(self):
        base = self.gate.snapshot_label(self.current, self.launched)
        unchanged = []
        for closure in self.current:
            changed = dict(self.current, **{closure: 'f' * 64})
            if self.gate.snapshot_label(changed, self.launched) == base:
                unchanged.append(closure)
        if self.gate.snapshot_label(self.current, 'f' * 64) == base:
            unchanged.append('Offline launcher')
        self.assertEqual(unchanged, [])

    def test_two_snapshots_sharing_a_machine_checker_coexist(self):
        other = dict(self.current, **{'Projection checker': '1' * 64})
        extra = rows(own_composite(other, self.launched), other, self.launched)
        self.table.write_text(self.text.replace('\nFor a machine proof', extra + '\nFor a machine proof', 1))
        code, out = gate(self.table, '--check')
        self.assertEqual(code, 0, out)
        self.assertIn('"snapshot": "{}"'.format(own_composite(self.current, self.launched)), out)

    def test_the_legacy_checker_label_is_refused_for_this_source(self):
        label = self.gate.snapshot_label(self.current, self.launched)
        self.table.write_text(self.text.replace('`' + label + '`', '`checker-ab72a8025a56`'))
        code, out = gate(self.table, '--check')
        self.assertEqual(code, 4, out)
        self.assertIn('snapshot_label_not_derived_from_digests', out)

    def test_a_snapshot_label_its_own_rows_do_not_hash_to_is_refused(self):
        other = dict(self.current, **{'Projection checker': '1' * 64})
        extra = rows('snapshot-000000000000', other, self.launched)
        self.table.write_text(self.text.replace('\nFor a machine proof', extra + '\nFor a machine proof', 1))
        code, out = gate(self.table, '--check')
        self.assertEqual(code, 4, out)
        self.assertIn('snapshot_label_not_derived_from_its_rows', out)

    def test_a_legacy_tag_is_refused(self):
        code, out = gate(ROOT / 'ANCHORS.md', '--check-tag', 'checker-ab72a8025a56')
        self.assertEqual(code, 4, out)
        self.assertIn('tag_not_derived_from_snapshot', out)
