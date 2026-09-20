"""The zoo table is a measurement: it must regenerate, its declared mismatches
with the pre-registration must be exactly the real ones, and both checks must be
able to fail."""
import copy
import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parent.parent
ZOO = ROOT / 'examples' / 'zoo'


def harness():
    if str(ZOO) not in sys.path:
        sys.path.insert(0, str(ZOO))
    import harness as module
    return module


def mismatched(rows):
    """Registered cells only; a cell nobody registered cannot disagree."""
    names = []
    for row in rows:
        want = row['registered'] or dict(evidence={}, search={})
        if (any(row['measured']['evidence'][key] != value for key, value in want['evidence'].items())
                or any(row['measured']['search'][key] != value for key, value in want['search'].items())):
            names.append(row['name'])
    return sorted(names)


class Zoo(unittest.TestCase):
    def setUp(self):
        self.module = harness()
        self.systems = self.module.load(ZOO / 'systems')
        self.committed = json.loads((ZOO / 'results.json').read_text())

    def test_systems_are_pairs_that_differ_only_in_next(self):
        self.assertGreaterEqual(len(self.systems), 8)
        for system in self.systems:
            correct = self.module.model(system, 'correct')
            broken = self.module.model(system, 'broken')
            self.assertNotEqual(correct['next'], broken['next'], system['name'])
            for field in ('state', 'events', 'initial', 'invariant', 'goals'):
                self.assertEqual(correct[field], broken[field], (system['name'], field))

    def test_table_regenerates(self):
        self.assertEqual(self.module.measure(self.systems), self.committed['rows'])

    def test_declared_mismatches_are_exactly_the_real_ones(self):
        self.assertEqual(sorted(self.committed['mismatches']), mismatched(self.committed['rows']))

    def test_the_mismatch_check_can_fail(self):
        for row in self.committed['rows']:
            if row['registered'] and row['registered']['evidence']:
                tampered = copy.deepcopy(row)
                key = sorted(tampered['registered']['evidence'])[0]
                tampered['measured']['evidence'][key] = 'something_else'
                self.assertEqual(mismatched([tampered]), [row['name']])
                return
        self.fail('no registered evidence cell to mutate')

    def test_the_table_reads_the_rules_it_claims_to_read(self):
        system = copy.deepcopy(next(s for s in self.systems if s['name'] == 'token-ring-onestep'))
        system['broken'] = system['correct']
        row = self.module.measure([system])[0]
        self.assertEqual(row['measured']['evidence']['broken'], 'verified_certificate')
        self.assertEqual(row['measured']['search']['one-edit']['status'], 'not_needed')


if __name__ == '__main__':
    unittest.main()
