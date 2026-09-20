"""Goals that must stay reachable from every certified state.

The models are the zoo's philosophers and Peterson, with one field added.
Expectations are pre-registered in examples/live_goals_REGISTRY.md.
"""
import copy
import importlib.util
import itertools
from pathlib import Path
import sys
import unittest

from stargate import certificate, evidence, lab, machine
from stargate.canonical import canon, decode, InvalidRecord

ROOT = Path(__file__).resolve().parent.parent
ZOO = ROOT / 'examples' / 'zoo'

DEADLOCK = dict(e0=False, e1=False, h0=True, h1=True)
RELEASE_0 = '(!s && !h0 && !e0) || (h0 && !e0 && !h1)'
RELEASE_1 = '(s && !h1 && !e1) || (h1 && !e1 && !h0)'


def zoo(name):
    if str(ZOO) not in sys.path:
        sys.path.insert(0, str(ZOO))
    import harness
    system = next(s for s in harness.load(ZOO / 'systems') if s['name'] == name)
    return harness, system


def build(name, *, live, rules=None, which='correct'):
    harness, system = zoo(name)
    if rules:
        system = copy.deepcopy(system)
        system[which].update(rules)
    spec = harness.model(system, which)
    if live is not None:
        spec['live_goals'] = live
    return machine.create(spec)


def produce(raw):
    return evidence.produce(raw, lab.identity(raw))


class LiveGoals(unittest.TestCase):
    def test_a_model_without_the_field_is_unchanged(self):
        raw = build('philosophers', live=None)
        self.assertNotIn('live_goals', decode(raw))
        report, packet = produce(raw)
        self.assertEqual(report['status'], 'verified_certificate')
        self.assertNotIn('ranks', decode(packet))

    def test_the_same_model_with_live_goals_is_refuted_by_the_deadlock_trap(self):
        base = build('philosophers', live=None)
        raw = build('philosophers', live=decode(base)['goals'])
        self.assertNotEqual(lab.identity(raw), lab.identity(base))
        report, packet = produce(raw)
        self.assertEqual(report['status'], 'verified_refutation')
        claim = decode(packet)['claim']
        self.assertEqual(claim['kind'], 'trap')
        self.assertEqual(claim['states'], [DEADLOCK])

    def test_the_asymmetric_fix_certifies_against_the_pre_registration(self):
        """Registered expectation: refuted, a trap remains. Measured: it certifies.

        One philosopher releasing its fork is enough in this model, and the
        independent oracle below agrees. The registration is left as written.
        """
        base = build('philosophers', live=None)
        raw = build('philosophers', live=decode(base)['goals'], rules={'h0': RELEASE_0})
        report, _ = produce(raw)
        self.assertEqual(report['status'], 'verified_certificate')

    def test_the_symmetric_fix_certifies_with_ranks(self):
        base = build('philosophers', live=None)
        raw = build('philosophers', live=decode(base)['goals'],
                    rules={'h0': RELEASE_0, 'h1': RELEASE_1})
        report, packet = produce(raw)
        self.assertEqual(report['status'], 'verified_certificate')
        document = decode(packet)
        self.assertEqual(len(document['ranks']), len(document['model']['live_goals']))
        for entry in document['ranks']:
            self.assertEqual(len(entry['ranks']), len(document['states']))

    def test_peterson_certifies_with_live_goals(self):
        base = build('peterson', live=None)
        raw = build('peterson', live=decode(base)['goals'])
        report, _ = produce(raw)
        self.assertEqual(report['status'], 'verified_certificate')

    def test_live_goals_must_be_declared_goals(self):
        base = build('philosophers', live=None)
        stranger = dict(e0=True, e1=True, h0=True, h1=True)
        with self.assertRaises(InvalidRecord):
            build('philosophers', live=[stranger])

    def test_a_repair_candidate_inherits_live_goals(self):
        base = build('philosophers', live=None)
        live = decode(base)['goals']
        raw = build('philosophers', live=live, which='broken')
        report, packet = evidence.repair_search(raw, lab.identity(raw), max_candidates=64)
        self.assertIn(report['status'], ('found', 'neighborhood_exhausted'))
        if report['status'] == 'found':
            candidate = decode(decode(packet)['candidate'])['model'] if isinstance(
                decode(packet)['candidate'], bytes) else decode(packet)['candidate']['model']
            self.assertEqual(candidate['live_goals'], live)


class IndependentOracle(unittest.TestCase):
    """Decide liveness without the checker: own evaluator, own search."""

    @staticmethod
    def evaluate(expression, facts):
        # The expressions come from this repository's own example files.
        return bool(eval(expression.replace('&&', ' and ').replace('||', ' or ').replace('!', ' not '),
                         {'__builtins__': {}}, dict(facts)))

    def traps(self, name, rules=None, which='correct'):
        _, system = zoo(name)
        source = dict(system[which]); source.update(rules or {})
        bits, events = sorted(system['state']), sorted(system['events'])
        start = [tuple(row[bit] for bit in bits) for row in system['initial']]
        seen, queue, edges = set(start), list(start), {}
        while queue:
            state = queue.pop()
            for row in itertools.product([False, True], repeat=len(events)):
                facts = dict(zip(bits, state)); facts.update(zip(events, row))
                target = tuple(self.evaluate(source[bit], facts) for bit in bits)
                edges.setdefault(state, []).append(target)
                if target not in seen:
                    seen.add(target); queue.append(target)
        found = {}
        for goal in ({tuple(g[bit] for bit in bits) for g in system['goals']}):
            backward, frontier = {goal}, [goal]
            while frontier:
                following = []
                for node in frontier:
                    for state, targets in edges.items():
                        if state not in backward and node in targets:
                            backward.add(state); following.append(state)
                frontier = following
            stuck = sorted(seen - backward)
            if stuck:
                found[goal] = [dict(zip(bits, state)) for state in stuck]
        return found

    def test_the_oracle_and_the_checker_agree_on_four_models(self):
        cases = [('philosophers', None, 'verified_refutation'),
                 ('philosophers', {'h0': RELEASE_0}, 'verified_certificate'),
                 ('philosophers', {'h0': RELEASE_0, 'h1': RELEASE_1}, 'verified_certificate'),
                 ('peterson', None, 'verified_certificate')]
        for name, rules, expected in cases:
            with self.subTest(name=name, rules=rules):
                base = build(name, live=None)
                raw = build(name, live=decode(base)['goals'], rules=rules)
                report, packet = produce(raw)
                traps = self.traps(name, rules)
                self.assertEqual(report['status'], expected)
                self.assertEqual(bool(traps), expected == 'verified_refutation')
                if traps:
                    self.assertIn(decode(packet)['claim']['states'], list(traps.values()))


RANK_CHECK = ("            if not any(ranks[transitions[(state_key, bits)]] < rank for bits in events):\n"
              "                raise InvalidRecord('no event lowers the rank of a certified state')\n")
CLOSURE_CHECK = ("            if _assignment(target, names) not in keys:\n"
                 "                raise InvalidRecord('refutation set is not closed under transitions')\n")


def mutant(*replacements):
    """A copy of the checker with one obligation removed, loaded beside the real one."""
    source = Path(certificate.__file__).read_text()
    for old, new in replacements:
        assert source.count(old) == 1, old
        source = source.replace(old, new)
    module = importlib.util.module_from_spec(
        importlib.util.spec_from_loader('stargate._mutated_certificate', loader=None))
    module.__package__ = 'stargate'
    module.__file__ = certificate.__file__       # its checker_id still hashes the real files
    module.__loader__ = certificate.__loader__
    exec(compile(source, 'mutated-certificate', 'exec'), module.__dict__)
    return module


class Controls(unittest.TestCase):
    """Every new obligation gets a mutation that a bad proof survives."""

    def certified(self):
        base = build('philosophers', live=None)
        raw = build('philosophers', live=decode(base)['goals'],
                    rules={'h0': RELEASE_0, 'h1': RELEASE_1})
        report, packet = produce(raw)
        self.assertEqual(report['status'], 'verified_certificate')
        return decode(packet)

    def test_a_rank_map_that_never_decreases_passes_only_without_the_check(self):
        document = self.certified()
        goal = document['model']['live_goals'][0]
        flat = [dict(state=row['state'], rank=0 if row['state'] == goal else 1)
                for row in document['ranks'][0]['ranks']]
        document['ranks'] = [dict(entry, ranks=flat) if entry['goal'] == goal else entry
                             for entry in document['ranks']]
        raw = canon(document)
        model_id = certificate.identity(document['model'])
        with self.assertRaises(InvalidRecord):
            certificate.verify(raw, model_id, certificate.checker_id())
        without = mutant((RANK_CHECK, ''))
        self.assertEqual(without.verify(raw, model_id, without.checker_id())['status'],
                         'verified_certificate')

    def test_a_trap_that_is_not_closed_passes_only_without_the_check(self):
        base = build('philosophers', live=None)
        raw = build('philosophers', live=decode(base)['goals'])
        report, packet = produce(raw)
        self.assertEqual(report['status'], 'verified_refutation')
        document = decode(packet)
        escape = dict(e0=False, e1=False, h0=False, h1=False)  # the initial state leaves the set
        document['claim'] = dict(document['claim'], states=[escape])
        document['claim']['trace'] = dict(initial=escape, steps=[])
        bogus = canon(document)
        model_id = certificate.identity(document['model'])
        with self.assertRaises(InvalidRecord):
            certificate.verify_refutation(bogus, model_id, certificate.checker_id())
        without = mutant((CLOSURE_CHECK, ''))
        self.assertEqual(without.verify_refutation(bogus, model_id, without.checker_id())['status'],
                         'verified_refutation')

    def test_dropping_live_goals_in_a_repair_passes_only_without_the_check(self):
        base = build('philosophers', live=None)
        live = decode(base)['goals']
        broken = build('philosophers', live=live, which='broken')
        refutation_report, refutation = produce(broken)
        self.assertEqual(refutation_report['status'], 'verified_refutation')
        fixed_report, fixed = produce(base)                    # same rules, no live_goals
        self.assertEqual(fixed_report['status'], 'verified_certificate')
        packet = certificate.pack_repair(refutation, fixed)
        parent_id = certificate.identity(decode(refutation)['model'])
        with self.assertRaises(InvalidRecord):
            certificate.verify_repair(packet, parent_id, certificate.checker_id())
        without = mutant(("'goals', 'live_goals'", "'goals'"))
        report, successor = without.verify_repair(packet, parent_id, without.checker_id())
        self.assertEqual(report['status'], 'verified_repair')
        self.assertIsNotNone(successor)


class Attacks(unittest.TestCase):
    """Rank maps that are wrong in one place each. None may be admitted."""

    def setUp(self):
        base = build('philosophers', live=None)
        raw = build('philosophers', live=decode(base)['goals'],
                    rules={'h0': RELEASE_0, 'h1': RELEASE_1})
        report, packet = produce(raw)
        self.assertEqual(report['status'], 'verified_certificate')
        self.document = decode(packet)
        self.model_id = certificate.identity(self.document['model'])

    def refuse(self, mutate):
        document = copy.deepcopy(self.document)
        mutate(document)
        with self.assertRaises(InvalidRecord):
            certificate.verify(canon(document), self.model_id, certificate.checker_id())

    def test_a_plateau_of_equal_ranks_is_not_almost_strict_enough(self):
        def plateau(document):
            rows = document['ranks'][0]['ranks']
            top = max(row['rank'] for row in rows)
            for row in rows:
                if row['rank'] >= top - 1 and row['state'] != document['ranks'][0]['goal']:
                    row['rank'] = top
        self.refuse(plateau)

    def test_a_second_state_may_not_share_rank_zero(self):
        self.refuse(lambda document: document['ranks'][0]['ranks'][0].update(rank=0))

    def test_the_goal_may_not_be_lifted_off_zero(self):
        def lift(document):
            goal = document['ranks'][0]['goal']
            for row in document['ranks'][0]['ranks']:
                if row['state'] == goal: row['rank'] = 1
        self.refuse(lift)

    def test_the_map_must_cover_the_certified_set_exactly(self):
        self.refuse(lambda document: document['ranks'][0]['ranks'].pop())
        self.refuse(lambda document: document['ranks'][0]['ranks'].append(
            dict(state=document['states'][0], rank=1)))

    def test_rank_maps_are_read_in_live_goal_order(self):
        self.refuse(lambda document: document['ranks'].reverse())

    def test_a_rank_must_be_a_bounded_integer(self):
        self.refuse(lambda document: document['ranks'][0]['ranks'][0].update(rank=len(document['states'])))
        self.refuse(lambda document: document['ranks'][0]['ranks'][0].update(rank=True))

    def test_the_maps_may_not_be_dropped(self):
        self.refuse(lambda document: document.pop('ranks'))


if __name__ == '__main__':
    unittest.main()
