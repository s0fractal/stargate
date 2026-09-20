"""The enum front-end must reproduce the hand-written Peterson model and must
exclude codes that name no value. Registered in tools/REGISTRY.md."""
import importlib.util
import itertools
from pathlib import Path
import sys
import unittest

from stargate import evidence, lab, machine
from stargate.canonical import decode

ROOT = Path(__file__).resolve().parent.parent
TOOLS = ROOT / 'tools'

PETERSON = dict(
    enums={'a': ['idle', 'want', 'wait', 'crit'], 'b': ['idle', 'want', 'wait', 'crit']},
    flags=['t'], events=['s'],
    initial={'a': 'idle', 'b': 'idle', 't': False},
    invariant='!(a:crit && b:crit)',
    goals=[{'a': 'crit', 'b': 'idle', 't': True}, {'a': 'idle', 'b': 'crit', 't': False}],
    transitions={
        'a': [('!s && a:idle', 'want'), ('!s && a:want', 'wait'),
              ('!s && a:wait && (b:idle || !t)', 'crit'), ('!s && a:crit', 'idle')],
        'b': [('s && b:idle', 'want'), ('s && b:want', 'wait'),
              ('s && b:wait && (a:idle || t)', 'crit'), ('s && b:crit', 'idle')]},
    flag_rules={'t': '(!s && a:want) || (t && !(s && b:want))'},
    max_atp=4000)


def frontend():
    if not (TOOLS / 'enum_frontend.py').exists():
        return None
    if str(TOOLS) not in sys.path:
        sys.path.insert(0, str(TOOLS))
    import enum_frontend
    return enum_frontend


def hand_written(yield_turn):
    """The states of examples/peterson_repair.py, as named values."""
    if str(ROOT / 'examples') not in sys.path:
        sys.path.insert(0, str(ROOT / 'examples'))
    import peterson_repair
    raw = machine.create(peterson_repair.model(yield_turn))
    report = machine.verify(raw, lab.identity(raw))
    order = ['idle', 'want', 'wait', 'crit']
    return {(order[2 * state['a1'] + state['a0']], order[2 * state['b1'] + state['b0']], state['t'])
            for state in report['reachable']}, report


def generated(spec):
    tool = frontend()
    if tool is None:
        return set(), None                      # no front-end yet: nothing is reached
    raw = machine.create(tool.compile_spec(spec))
    report = machine.verify(raw, lab.identity(raw))
    states = {tuple(tool.decode_state(state, spec)[name] for name in ('a', 'b', 't'))
              for state in report['reachable']}
    return states, raw


class Peterson(unittest.TestCase):
    def test_the_front_end_reaches_the_hand_written_states(self):
        expected, _ = hand_written(True)
        self.assertEqual(len(expected), 20)
        states, _ = generated(PETERSON)
        self.assertEqual(states, expected)

    def test_the_broken_variant_is_refuted_with_a_six_step_trace(self):
        spec = dict(PETERSON, flag_rules={'t': '(s && b:want) || (t && !(!s && a:want))'})
        _, raw = generated(spec)
        self.assertIsNotNone(raw, 'no front-end to generate the broken variant')
        report, packet = evidence.produce(raw, lab.identity(raw))
        self.assertEqual(report['status'], 'verified_refutation')
        self.assertEqual(len(decode(packet)['claim']['trace']['steps']), 6)


if __name__ == '__main__':
    unittest.main()
