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


LIGHT = dict(
    enums={'light': ['red', 'green', 'yellow']}, flags=[], events=['c'],
    initial={'light': 'red'},
    invariant='true',
    goals=[{'light': 'red'}, {'light': 'green'}],
    transitions={'light': [('c && light:red', 'green'), ('c && light:green', 'yellow'),
                           ('c && light:yellow', 'red')]},
    flag_rules={}, max_atp=1000)

ESCAPE = {'light_0': 'c || light_0', 'light_1': 'c || light_1'}   # red --c--> the unused code


class UnusedCodes(unittest.TestCase):
    """Three values take two bits; the fourth code names nothing."""

    def setUp(self):
        self.tool = frontend()
        self.assertIsNotNone(self.tool)

    def escaping(self, spec):
        declared = 'fact c: bool\nfact light_0: bool\nfact light_1: bool\n'
        compiled = dict(spec)
        compiled['next'] = {bit: declared + 'check ' + source + '\n'
                            for bit, source in ESCAPE.items()}
        return machine.create(compiled)

    def test_the_generated_invariant_excludes_the_code_that_names_nothing(self):
        self.assertEqual(self.tool.unused(LIGHT['enums']), ['!(light_0 && light_1)'])
        compiled = self.tool.compile_spec(LIGHT)
        self.assertIn('!(light_0 && light_1)', compiled['invariant'])

    def test_a_model_that_enters_the_unused_code_is_refuted(self):
        raw = self.escaping(self.tool.compile_spec(LIGHT))
        report, packet = evidence.produce(raw, lab.identity(raw))
        self.assertEqual(report['status'], 'verified_refutation')
        steps = self.tool.decode_trace(decode(packet)['claim']['trace'], LIGHT)
        self.assertEqual(steps[0]['state'], {'light': 'red'})
        self.assertIn('unused_code', steps[-1]['state'])

    def test_without_the_exclusion_the_same_model_certifies(self):
        """The control: an obligation nothing can violate would prove nothing."""
        spec = self.tool.compile_spec(LIGHT)
        spec['invariant'] = spec['invariant'].split('check ')[0] + 'check true\n'
        spec['goals'] = [self.tool.flatten(LIGHT, {'light': 'red'})]
        raw = self.escaping(spec)
        report, _ = evidence.produce(raw, lab.identity(raw))
        self.assertEqual(report['status'], 'verified_certificate')

    def test_the_exclusion_is_what_gives_repair_search_something_to_repair(self):
        """Measured, not predicted: with the clause there is a defect, without it none."""
        with_clause = self.escaping(self.tool.compile_spec(LIGHT))
        report, _ = evidence.repair_search(with_clause, lab.identity(with_clause),
                                           max_candidates=64)
        self.assertIn(report['status'], ('found', 'neighborhood_exhausted', 'search_incomplete'))
        self.assertNotEqual(report['status'], 'not_needed')
        spec = self.tool.compile_spec(LIGHT)
        spec['invariant'] = spec['invariant'].split('check ')[0] + 'check true\n'
        spec['goals'] = [self.tool.flatten(LIGHT, {'light': 'red'})]
        without = self.escaping(spec)
        quiet, _ = evidence.repair_search(without, lab.identity(without), max_candidates=64)
        self.assertEqual(quiet['status'], 'not_needed')


if __name__ == '__main__':
    unittest.main()
