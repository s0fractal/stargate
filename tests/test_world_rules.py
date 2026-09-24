"""Ownership-safe automatic repair. Registered in docs/WORLD_RULES_REGISTRY.md."""
import json
from pathlib import Path
import unittest

from stargate import certificate, evidence, lab, machine
from stargate.canonical import canon, decode, InvalidRecord

ROOT = Path(__file__).resolve().parent.parent
SPECS = ROOT / 'examples' / 'mcp-proxy' / 'specs'
WORLD = ['calls.one', 'calls.two']
SERVER_OWES_NOTHING = ('(((host && !(reply)) || ((!(host) && reply) && calls.two)) && '
                       '((!(host) && !(reply)) && calls.one))')   # what repair-search returned in #64


def spec(variant, world=WORLD, **rules):
    doc = json.loads((SPECS / (variant + '.json')).read_text())
    for name, expression in rules.items():
        head = doc['next'][name].split('check ', 1)[0]
        doc['next'][name] = head + 'check ' + expression + '\n'
    if world is not None:
        doc['world'] = world
    return doc


def proof(doc):
    raw = machine.create(doc)
    return evidence.produce(raw, lab.identity(raw))[1]


def outcome(call):
    """('ok', status) | ('invalid', message) | ('error', type) — never an exception."""
    try:
        result = call()
    except InvalidRecord as exc:
        return 'invalid', str(exc)
    except Exception as exc:  # the red state: the field does not exist yet
        return 'error', type(exc).__name__ + ': ' + str(exc)[:80]
    report = result[0] if isinstance(result, tuple) else result
    return 'ok', report['status']


class Repair(unittest.TestCase):
    def test_1_a_repair_that_edits_a_world_rule_is_invalid(self):
        forged = lambda: certificate.verify_repair(
            certificate.pack_repair(proof(spec('current')), proof(spec('current', **{'calls.one': SERVER_OWES_NOTHING}))),
            certificate.identity(decode(proof(spec('current')))['model']), certificate.checker_id())
        kind, detail = outcome(forged)
        self.assertEqual(kind, 'invalid', detail)
        self.assertIn('world rule', detail)

    def test_1_a_repair_within_the_owned_rules_verifies(self):
        repair = lambda: certificate.verify_repair(
            certificate.pack_repair(proof(spec('current')), proof(spec('fixed'))),
            certificate.identity(decode(proof(spec('current')))['model']), certificate.checker_id())
        self.assertEqual(outcome(repair), ('ok', 'verified_repair'))


class Classification(unittest.TestCase):
    def test_2_a_change_or_repair_cannot_touch_world(self):
        with_world = lambda: proof(spec('fixed'))
        without = lambda: proof(spec('fixed', world=None))
        parent = lambda: certificate.identity(decode(with_world())['model'])
        cases = {
            'change drops world': lambda: certificate.verify_change(
                certificate.pack_change(with_world(), without()), parent(), certificate.checker_id()),
            'change adds world': lambda: certificate.verify_change(
                certificate.pack_change(without(), with_world()),
                certificate.identity(decode(without())['model']), certificate.checker_id()),
            'change alters world': lambda: certificate.verify_change(
                certificate.pack_change(with_world(), proof(spec('fixed', world=['calls.one']))),
                parent(), certificate.checker_id()),
            'repair alters world': lambda: certificate.verify_repair(
                certificate.pack_repair(proof(spec('current')), proof(spec('fixed', world=['calls.one']))),
                certificate.identity(decode(proof(spec('current')))['model']), certificate.checker_id()),
        }
        results = {name: outcome(call)[0] for name, call in cases.items()}
        self.assertEqual(results, {name: 'invalid' for name in cases})

    def test_3_malformed_world_is_invalid(self):
        bad = {'empty': [], 'unsorted': ['calls.two', 'calls.one'], 'duplicate': ['calls.one', 'calls.one'],
               'not a state bit': ['host']}
        results = {name: outcome(lambda w=w: machine.create(spec('fixed', world=w)) and {'status': 'created'})[0]
                   for name, w in bad.items()}
        self.assertEqual(results, {name: 'invalid' for name in bad})

    def test_4_a_plain_change_may_evolve_a_world_rule(self):
        base = lambda: proof(spec('fixed'))
        evolved = lambda: proof(spec('fixed', **{'calls.two': '(!host && !reply && calls.two) || (host && !reply && calls.one)'}))
        change = lambda: certificate.verify_change(certificate.pack_change(base(), evolved()),
                                                   certificate.identity(decode(base())['model']), certificate.checker_id())
        self.assertEqual(outcome(change), ('ok', 'verified_change'))


class Compatibility(unittest.TestCase):
    def test_5_a_model_without_world_keeps_its_model_id(self):
        """examples/mcp-proxy/results.json recorded fixed's certificate ModelID before world existed."""
        recorded = json.loads((ROOT / 'examples' / 'mcp-proxy' / 'results.json').read_text())['successors']['fixed']['model']
        raw = machine.create(spec('fixed', world=None))
        self.assertEqual(certificate.identity(certificate.model_from_machine(machine.inspect(raw))), recorded)

    def test_5_world_travels_from_machine_to_model_only_when_present(self):
        kind, detail = outcome(lambda: {'status': certificate.model_from_machine(
            machine.inspect(machine.create(spec('fixed')))).get('world')})
        self.assertEqual((kind, detail), ('ok', WORLD))


class Control(unittest.TestCase):
    SITE = "            raise InvalidRecord('repair alters world rule: ' + bit)\n"

    def test_without_the_world_rule_equality_the_forged_repair_verifies(self):
        source = (ROOT / 'src' / 'certificate.py').read_text()
        self.assertIn(self.SITE, source, 'mutation site not found: the control would prove nothing')
        import types, stargate
        mutant = types.ModuleType('stargate.certificate_mutant'); mutant.__package__ = 'stargate'
        mutant.__file__ = certificate.__file__; mutant.__loader__ = certificate.__loader__
        exec(compile(source.replace(self.SITE, "            pass\n"), 'certificate_mutant', 'exec'), mutant.__dict__)
        parent = proof(spec('current'))
        forged = certificate.pack_repair(parent, proof(spec('current', **{'calls.one': SERVER_OWES_NOTHING})))
        with self.assertRaises(InvalidRecord):
            certificate.verify_repair(forged, certificate.identity(decode(parent)['model']), certificate.checker_id())
        report, _ = mutant.verify_repair(forged, certificate.identity(decode(parent)['model']), certificate.checker_id())
        self.assertEqual(report['status'], 'verified_repair')


class Producer(unittest.TestCase):
    def test_no_search_candidate_touches_a_world_rule(self):
        from stargate import search
        doc = machine.inspect(machine.create(spec('current')))
        seen = 0
        for rules in list(search.repair_candidates(doc, list(doc['state']))) + list(search.machine_candidates(doc)):
            seen += 1
            self.assertEqual({w: rules[w] for w in WORLD}, {w: doc['next'][w] for w in WORLD})
        self.assertGreater(seen, 0)
