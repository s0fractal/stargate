"""Does the truncated two-phase commit need a third event bit?

Registered in examples/two-phase-commit/REGISTRY.md. The decisive claim is the
last one: whether three independent inputs reach a state two cannot.
"""
from pathlib import Path
import sys
import unittest

from stargate import evidence, lab, machine
from stargate.canonical import InvalidRecord

ROOT = Path(__file__).resolve().parent.parent
MODELS = ROOT / 'examples' / 'two-phase-commit'


def module():
    if not (MODELS / 'two_phase_commit.py').exists():
        return None
    if str(MODELS) not in sys.path:
        sys.path.insert(0, str(MODELS))
    import two_phase_commit
    return two_phase_commit


class TwoPhaseCommit(unittest.TestCase):
    def setUp(self):
        self.model = module()

    def refusal(self, spec):
        try:
            machine.create(spec)
        except InvalidRecord as exc:
            return str(exc)
        return 'accepted'

    def test_three_event_bits_are_refused_today(self):
        spec = self.model.simultaneous() if self.model else None
        self.assertIsNotNone(spec, 'no model to submit')
        self.assertEqual(self.refusal(spec),
                         'machine requires 1..6 state bits and 0..2 disjoint event bits')

    def test_the_serialized_model_certifies(self):
        spec = self.model.serialized() if self.model else None
        self.assertIsNotNone(spec, 'no serialized model')
        raw = machine.create(spec)
        self.assertEqual(evidence.produce(raw, lab.identity(raw))[0]['status'],
                         'verified_certificate')

    def test_the_serialized_model_catches_the_planted_defect(self):
        spec = self.model.serialized(broken=True) if self.model else None
        self.assertIsNotNone(spec, 'no broken model')
        raw = machine.create(spec)
        self.assertEqual(evidence.produce(raw, lab.identity(raw))[0]['status'],
                         'verified_refutation')

    def test_the_third_bit_reaches_no_state_the_second_pair_cannot(self):
        """The decisive measurement, registered before it was run."""
        simultaneous = self.model.reachable(self.model.simultaneous()) if self.model else set()
        serialized = self.model.reachable(self.model.serialized()) if self.model else {'nothing'}
        self.assertEqual(simultaneous, serialized)


if __name__ == '__main__':
    unittest.main()
