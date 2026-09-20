"""The zoo table is a measurement: it must regenerate, and its declared
mismatches with the pre-registration must be exactly the real ones."""
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
        real = sorted(row['name'] for row in self.committed['rows']
                      if row['registered'] is not None and row['registered'] != row['measured'])
        self.assertEqual(sorted(self.committed['mismatches']), real)


if __name__ == '__main__':
    unittest.main()
