"""The honest philosophers model certifies today although its deadlock is
reachable. Once its goals are declared live, the same rules must be refused.

Expectations are pre-registered in examples/live_goals_REGISTRY.md.
"""
from pathlib import Path
import sys
import unittest

from stargate import evidence, lab, machine
from stargate.canonical import decode, InvalidRecord

ROOT = Path(__file__).resolve().parent.parent
ZOO = ROOT / 'examples' / 'zoo'
DEADLOCK = dict(e0=False, e1=False, h0=True, h1=True)


def build(name, *, live):
    if str(ZOO) not in sys.path:
        sys.path.insert(0, str(ZOO))
    import harness
    system = next(s for s in harness.load(ZOO / 'systems') if s['name'] == name)
    spec = harness.model(system, 'correct')
    if not live:
        return machine.create(spec)
    try:
        return machine.create(dict(spec, live_goals=spec['goals']))
    except InvalidRecord:
        return machine.create(spec)   # the field does not exist yet; this is today's model


class LiveGoals(unittest.TestCase):
    def test_the_model_certifies_while_its_goals_are_ordinary(self):
        raw = build('philosophers', live=False)
        report, _ = produce(raw)
        self.assertEqual(report['status'], 'verified_certificate')

    def test_declaring_the_goals_live_refutes_the_same_rules(self):
        raw = build('philosophers', live=True)
        report, packet = produce(raw)
        self.assertEqual(report['status'], 'verified_refutation')
        claim = decode(packet)['claim']
        self.assertEqual(claim['kind'], 'trap')
        self.assertEqual(claim['states'], [DEADLOCK])


def produce(raw):
    return evidence.produce(raw, lab.identity(raw))


if __name__ == '__main__':
    unittest.main()
