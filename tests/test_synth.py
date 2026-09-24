"""Ownership-safe safety synthesis for repair (PR-85, docs/SYNTH_REGISTRY.md).

Small machines only; the two live verticals are the registered run, not these tests.
"""
import hashlib
from pathlib import Path
import types
import unittest

from stargate import certificate, evidence, machine
from stargate.canonical import decode

ROOT = Path(__file__).resolve().parent.parent


def rule(names, expression):
    return ''.join('fact ' + n + ': bool\n' for n in sorted(names)) + 'check ' + expression + '\n'


def build(state, events, rules, invariant, world=None, goals=(), live_goals=None):
    names = list(state) + list(events)
    doc = dict(state=sorted(state), events=sorted(events),
               initial=[{s: False for s in state}], invariant=rule(state, invariant),
               next={n: rule(names, rules[n]) for n in state}, goals=list(goals), max_atp=1000)
    if world is not None:
        doc['world'] = sorted(world)
    if live_goals is not None:
        doc['live_goals'] = list(live_goals)
    return machine.create(doc)


def synth(raw):
    return evidence.repair_search(raw, hashlib.sha256(raw).hexdigest(), strategy='synth')


# K: an event forces the world into the unsafe region whatever the owned bit does.
K = dict(state=['o', 'w'], events=['x'], rules={'w': 'x', 'o': 'o'}, invariant='!w', world=['w'])
# R: the owned bit must follow the world; the parent never sets it.
R = dict(state=['o', 'w'], events=['x'], rules={'w': 'x', 'o': 'false'}, invariant='!w || o', world=['w'])


class Applicability(unittest.TestCase):
    def test_a_certified_parent_is_not_needed(self):
        report, packet = synth(build(**dict(R, rules={'w': 'x', 'o': 'x'})))
        self.assertEqual((report['status'], packet), ('not_needed', None))

    def test_no_declared_world_is_not_applicable(self):
        report, packet = synth(build(**dict(R, world=None)))
        self.assertEqual((report['status'], packet), ('not_applicable', None))

    def test_no_owned_bit_is_not_applicable(self):
        report, packet = synth(build(**dict(R, world=['o', 'w'])))
        self.assertEqual((report['status'], packet), ('not_applicable', None))

    def test_an_unreachable_goal_is_not_applicable(self):
        goal = {'o': True, 'w': False}
        report, packet = synth(build(**dict(R, rules={'w': 'false', 'o': 'false'}, goals=[goal])))
        self.assertEqual((report['status'], packet), ('not_applicable', None))


class Synthesis(unittest.TestCase):
    def test_K_is_unrealizable_with_an_empty_winning_region(self):
        report, packet = synth(build(**K))
        self.assertEqual((report['status'], report.get('synthesis', {}).get('winning_states'), packet),
                         ('unrealizable', 0, None))

    def test_R_is_repaired_and_the_checker_says_so(self):
        raw = build(**R)
        report, packet = synth(raw)
        s = report.get('synthesis', {})
        self.assertEqual((report['status'], s.get('winning_states'), s.get('changed_rows'),
                          s.get('changed_owned_rules'), s.get('total_owned_hamming_delta'),
                          s.get('final_checker_status')),
                         ('found', 3, 3, ['o'], 3, 'verified_repair'))
        verdict, _ = certificate.verify_repair(packet, certificate.identity(certificate.model_from_machine(
            machine.inspect(raw))), certificate.checker_id())
        self.assertEqual(verdict['status'], 'verified_repair')
        self.assertEqual(decode(packet)['candidate']['model']['next']['w'], machine.inspect(raw)['next']['w'])

    def test_a_safe_candidate_the_checker_refuses_is_reported_not_hidden(self):
        # The owned bit only holds (warrant's shape): the minimal fix sets it and never clears
        # it, so the live goal cannot be reached again: safety holds, liveness does not.
        idle = {'o': False, 'w': False}
        raw = build(**dict(R, rules={'w': 'x', 'o': 'o'}, goals=[idle], live_goals=[idle]))
        report, packet = synth(raw)
        self.assertEqual((report['status'], report.get('synthesis', {}).get('final_checker_status'),
                          report.get('synthesis', {}).get('candidate_claim'), packet),
                         ('not_certified', 'verified_refutation', 'trap', None))


class Emitter(unittest.TestCase):
    def test_emitted_rules_equal_the_table_on_every_row(self):
        from stargate import synth as module
        inputs = ['a', 'b', 'c']
        for bits in range(256):
            table = [bool(bits >> (7 - i) & 1) for i in range(8)]
            source = module.emit(table, inputs)
            self.assertEqual(module.table_of(source, inputs), table, source)

    def test_a_rule_over_the_byte_ceiling_is_refused_by_the_compiler(self):
        from stargate import synth as module
        inputs = ['observed_input_' + str(n) for n in range(8)]   # 8 inputs is the machine maximum
        parity = [bin(row).count('1') % 2 == 1 for row in range(256)]
        with self.assertRaises(module.Unrepresentable) as caught:
            module.represent(parity, inputs, rule(inputs, inputs[0]), 1000)
        self.assertEqual(caught.exception.reason, 'rule_wpl')      # the compiler's own ceiling
        self.assertIn('8192 bytes', caught.exception.detail)


class Representation(unittest.TestCase):
    """Codex's pre-run review of #85: the compiler's token ceiling, unchanged rules, delta."""

    def test_short_names_parity_is_under_the_byte_ceiling_but_refused_cleanly_by_tokens(self):
        from stargate import synth as module
        inputs = [chr(ord('a') + n) for n in range(8)]
        parity = [bin(row).count('1') % 2 == 1 for row in range(256)]
        parent = rule(inputs, 'a')
        self.assertLess(len(module.emit(parity, inputs).encode('utf-8')), 8192)
        with self.assertRaises(module.Unrepresentable) as caught:
            module.represent(parity, inputs, parent, 1000)
        self.assertEqual(caught.exception.reason, 'rule_wpl')
        self.assertIn('256 tokens', str(caught.exception.detail))

    def test_an_owned_rule_the_strategy_does_not_change_keeps_its_parent_bytes(self):
        # Two owned bits; the fix needs only o. p's parent rule must come back byte for byte.
        raw = build(state=['o', 'p', 'w'], events=['x'], rules={'w': 'x', 'o': 'false', 'p': 'p || x'},
                    invariant='!w || o', world=['w'])
        report, packet = synth(raw)
        self.assertEqual(report['status'], 'found')
        candidate = decode(packet)['candidate']['model']['next']
        self.assertEqual(candidate['p'], machine.inspect(raw)['next']['p'])
        self.assertEqual(report['synthesis']['changed_owned_rules'], ['o'])

    def test_the_delta_over_the_parent_is_exact_and_chosen_when_shorter(self):
        from stargate import synth as module
        inputs = ['a', 'b', 'c', 'd', 'e', 'f']
        parent = rule(inputs, '(a && b) || (c && !d) || (e && f)')
        table = module.table_of(parent, inputs)
        table[5], table[40] = not table[5], not table[40]
        source = module.represent(table, inputs, parent, 1000)
        self.assertIn('(a && b) || (c && !d) || (e && f)', source)
        self.assertEqual(module.table_of(source, inputs), table)


def mutant(site, replacement):
    from stargate import synth as module
    source = (ROOT / 'src' / 'synth.py').read_text()
    if site not in source:
        raise AssertionError('mutation site not found: the control would prove nothing: ' + site)
    copy = types.ModuleType('stargate.synth_mutant'); copy.__package__ = 'stargate'
    exec(compile(source.replace(site, replacement), 'synth_mutant', 'exec'), copy.__dict__)
    return copy


class Controls(unittest.TestCase):
    def run_with(self, module, raw):
        import stargate
        original = stargate.synth if hasattr(stargate, 'synth') else None
        import sys
        saved = sys.modules.get('stargate.synth')
        sys.modules['stargate.synth'] = module; stargate.synth = module
        try:
            return synth(raw)
        finally:
            sys.modules['stargate.synth'] = saved; stargate.synth = original

    def test_G1_forall_to_exists_reports_K_realizable_and_the_checker_refutes(self):
        report, packet = self.run_with(mutant('all(any(', 'any(any('), build(**K))
        self.assertEqual((report['status'], report.get('synthesis', {}).get('candidate_claim'), packet),
                         ('not_certified', 'unsafe', None))

    def test_G2_choosing_world_bits_repairs_K_and_the_checker_refuses(self):
        report, packet = self.run_with(mutant("choosable = owned", "choosable = list(doc['state'])"), build(**K))
        self.assertEqual((report['status'], packet), ('repair_refused', None))
        self.assertIn('repair alters world rule: w', report.get('reason', ''))

    def test_G3_a_flipped_emitted_row_is_caught_before_the_checker(self):
        site = "        source = declarations + 'check ' + expression + '\\n'\n"
        flipped = mutant(site, "        source = declarations + 'check !(' + expression + ')\\n'\n")
        report, packet = self.run_with(flipped, build(**R))
        self.assertEqual((report['status'], report.get('producer_calls'), packet), ('producer_error', 1, None))


if __name__ == '__main__':
    unittest.main()
