"""The projection verifier: a projection is checked against a verified certificate.

Expectations are pre-registered in vertical/projection_check_REGISTRY.md.
"""
import contextlib
import hashlib
import io
import itertools
import json
from pathlib import Path
import random
import shutil
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_projection import F, T, corner, hand_made, rule, two_bit, with_rows  # noqa: E402

from stargate import certificate, cli, evidence, lab, machine, projection, projection_check  # noqa: E402
from stargate.canonical import canon, decode, InvalidRecord  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
ZOO = ROOT / 'examples' / 'zoo'
CHECKER = certificate.checker_id()


def evidence_for(raw):
    """(projection bytes, certificate bytes, ModelID) for a machine that certifies."""
    report, packet = evidence.produce(raw, lab.identity(raw))
    assert report['status'] == 'verified_certificate', report['status']
    _, projected = projection.project(raw, lab.identity(raw))
    return projected, packet, decode(projected)['model']


def check(projected, cert, model, *, checker=CHECKER, projection_checker=None):
    return projection_check.check(projected, cert, model, checker,
                                  projection_checker or projection_check.projection_checker_id())


def flip(projected, index, bit):
    document = decode(projected)
    document['rows'][index]['next'][bit] = not document['rows'][index]['next'][bit]
    return canon(document)


def oracle(model, current, event):
    """Evaluate the model's rules with Python's own operators, not the Boolean module."""
    facts = dict(current, **event)
    out = {}
    for name, source in model['next'].items():
        expression = source.split('check', 1)[1]
        out[name] = bool(eval(expression.replace('&&', ' and ').replace('||', ' or ').replace('!', ' not '),
                              {'__builtins__': {}}, dict(facts, true=True, false=False)))
    return out


class Verdicts(unittest.TestCase):
    def setUp(self):
        self.projected, self.cert, self.model = evidence_for(two_bit())

    def test_a_faithful_projection_conforms(self):
        report = check(self.projected, self.cert, self.model)
        self.assertEqual((report['status'], projection_check.exit_code(report)), ('conforms', 0))
        self.assertEqual((report.get('checked_rows'), report.get('projection'), report.get('model')),
                         (8, hashlib.sha256(self.projected).hexdigest(), self.model))

    def test_one_flipped_cell_is_a_mismatch_with_the_registered_witness(self):
        report = check(flip(self.projected, 4, 'a'), self.cert, self.model)
        self.assertEqual((report['status'], projection_check.exit_code(report)), ('mismatch', 4))
        self.assertEqual(report.get('witness'), dict(state=dict(a=T, b=F), event=dict(e=F),
                                                     expected=dict(a=T, b=T), actual=dict(a=F, b=T)))
        witness = report['witness']
        self.assertEqual(oracle(decode(self.cert)['model'], witness['state'], witness['event']),
                         witness['expected'])

    def test_missing_and_duplicate_rows_are_invalid_before_any_certificate_work(self):
        rows = hand_made()['rows']
        missing, duplicate = rows[:5] + rows[6:], rows[:3] + [rows[2]] + rows[4:]
        for bad in (missing, duplicate):
            with self.assertRaises(InvalidRecord):
                check(with_rows(bad), b'not a certificate', self.model)

    def test_a_projection_of_another_model_is_invalid(self):
        document = decode(self.projected); document['model'] = 'f' * 64
        with self.assertRaises(InvalidRecord):
            check(canon(document), self.cert, self.model)

    def test_a_certificate_of_another_model_is_invalid(self):
        names = ['a', 'b', 'e']
        other = machine.create(dict(state=['a', 'b'], events=['e'], initial=[dict(a=F, b=F)], max_atp=1000,
                                    goals=[], invariant=rule(['a', 'b'], 'a || !a'),
                                    next={'a': rule(names, 'e'), 'b': rule(names, 'b')}))
        _, foreign, _ = evidence_for(other)
        with self.assertRaises(InvalidRecord):
            check(self.projected, foreign, self.model)

    def test_another_projection_checker_is_unavailable(self):
        report = check(self.projected, self.cert, self.model, projection_checker='0' * 64)
        self.assertEqual((report['status'], projection_check.exit_code(report)),
                         ('projection_checker_unavailable', 3))

    def test_a_certificate_for_another_machine_checker_is_unavailable(self):
        report = check(self.projected, self.cert, self.model, checker='0' * 64)
        self.assertEqual((report['status'], projection_check.exit_code(report)), ('checker_unavailable', 3))


class Zoo(unittest.TestCase):
    def test_every_certified_zoo_system_conforms_and_every_flip_is_caught(self):
        sys.path.insert(0, str(ZOO))
        import harness
        outcomes, rng = {}, random.Random(43)
        for system in harness.load(ZOO / 'systems'):
            raw = machine.create(harness.model(system, 'correct'))
            report, _ = evidence.produce(raw, lab.identity(raw))
            if report['status'] != 'verified_certificate':
                continue
            projected, cert, model = evidence_for(raw)
            rows = decode(projected)['rows']
            index = rng.randrange(len(rows)); bit = rng.choice(sorted(rows[index]['next']))
            outcomes[system['name']] = (check(projected, cert, model)['status'],
                                        check(flip(projected, index, bit), cert, model)['status'])
        self.assertEqual(len(outcomes), 11)
        self.assertEqual(set(outcomes.values()), {('conforms', 'mismatch')})


class Ceiling(unittest.TestCase):
    def test_the_verifier_ceiling_equals_the_producers(self):
        self.assertEqual(projection_check.MAX_PROJECTION, projection.MAX_PROJECTION)

    def test_the_rule_limit_it_is_derived_from_is_the_closures(self):
        from stargate import boolean
        names = ['a']
        boolean.program('fact a:bool check!a' + ' ' * (8192 - 19), names)
        with self.assertRaises(boolean.BooleanSyntax):
            boolean.program('fact a:bool check!a' + ' ' * (8193 - 19), names)

    def test_the_corner_conforms(self):
        base = decode(corner())
        state = base['state']
        spec = {k: base[k] for k in ('state', 'events', 'initial', 'next', 'max_atp', 'goals')}
        spec['invariant'] = ''.join('fact ' + n + ':bool ' for n in state) + 'check b || !b'
        raw = machine.create(spec)
        projected, cert, model = evidence_for(raw)
        self.assertGreater(len(projected), 4_000_000)
        self.assertEqual(check(projected, cert, model).get('status'), 'conforms')


class Readers(unittest.TestCase):
    def test_the_producer_and_the_verifier_read_the_same_structure(self):
        good = hand_made()
        rows = good['rows']
        cases = {'good': canon(good),
                 'missing': with_rows(rows[:5] + rows[6:]),
                 'duplicate': with_rows(rows[:3] + [rows[2]] + rows[4:]),
                 'order': with_rows([rows[1], rows[0]] + rows[2:]),
                 'verdict': canon(dict(good, conforms=True)),
                 'version': canon(dict(good, projection=2)),
                 'unsorted': canon(dict(good, state=['b', 'a']))}
        def answer(reader, raw):
            try: reader(raw); return 'accept'
            except InvalidRecord: return 'refuse'
        producer = {k: answer(projection.inspect, v) for k, v in cases.items()}
        verifier = {k: answer(projection_check.inspect, v) for k, v in cases.items()}
        self.assertEqual(verifier, producer)
        self.assertEqual(verifier, dict(good='accept', **{k: 'refuse' for k in cases if k != 'good'}))


class Closure(unittest.TestCase):
    def test_the_verifier_runs_from_its_six_files_alone(self):
        projected, cert, model = evidence_for(two_bit())
        expected = check(projected, cert, model)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); package = root / 'stargate'; package.mkdir()
            for name in projection_check.PROJECTION_SOURCES:
                shutil.copy(ROOT / 'src' / name, package / name)
            (root / 'p.json').write_bytes(projected); (root / 'c.json').write_bytes(cert)
            script = (
                'import json, sys\n'
                'sys.path.insert(0, sys.argv[1])\n'
                'from stargate import projection_check as p\n'
                'r = p.check(open(sys.argv[2], "rb").read(), open(sys.argv[3], "rb").read(), sys.argv[4], sys.argv[5], p.projection_checker_id())\n'
                'print(json.dumps(dict(report=r, modules=sorted(m for m in sys.modules if m.startswith("stargate")))))\n')
            result = subprocess.run([sys.executable, '-I', '-S', '-c', script, str(root), str(root / 'p.json'),
                                     str(root / 'c.json'), model, CHECKER], capture_output=True, text=True, cwd='/')
        self.assertEqual(result.returncode, 0, result.stderr)
        out = json.loads(result.stdout)
        self.assertEqual(out['report'], json.loads(json.dumps(expected)))
        self.assertEqual(set(out['modules']), {'stargate'} | {'stargate.' + n[:-3] for n in projection_check.PROJECTION_SOURCES if n != '__init__.py'})

    def test_the_closure_is_the_machine_checker_plus_one_file(self):
        self.assertEqual(projection_check.PROJECTION_SOURCES, certificate.SOURCES + ('projection_check.py',))
        for name in ('compiler.py', 'kernel.py', 'lab.py', 'machine.py', 'projection.py', 'search.py', 'cli.py'):
            self.assertNotIn(name, projection_check.PROJECTION_SOURCES)

    def test_the_projection_checker_id_is_the_identity_of_its_sources(self):
        sources = {n: (ROOT / 'src' / n).read_text() for n in projection_check.PROJECTION_SOURCES}
        self.assertEqual(projection_check.projection_checker_id(), certificate.identity(sources))
        self.assertNotEqual(projection_check.projection_checker_id(), CHECKER)

    def test_the_machine_checker_is_still_the_vertical_baseline(self):
        result = subprocess.run([sys.executable, str(ROOT / 'tools' / 'vertical_baseline.py'), '--check'],
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stdout)


class Command(unittest.TestCase):
    def test_sg_projection_check_exit_codes(self):
        projected, cert, model = evidence_for(two_bit())
        pid = projection_check.projection_checker_id()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / 'p.json').write_bytes(projected); (root / 'bad.json').write_bytes(flip(projected, 4, 'a'))
            (root / 'c.json').write_bytes(cert)
            def run(path, expected_pid=pid):
                out = io.StringIO()
                with contextlib.redirect_stdout(out), contextlib.redirect_stderr(io.StringIO()):
                    return cli.main(['projection-check', str(path), str(root / 'c.json'), '--expect-model', model,
                                     '--expect-checker', CHECKER, '--expect-projection-checker', expected_pid])
            codes = (run(root / 'p.json'), run(root / 'bad.json'), run(root / 'p.json', '0' * 64))
        self.assertEqual(codes, (0, 4, 3))

    def test_sg_projection_checker_prints_the_id(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = cli.main(['projection-checker'])
        self.assertEqual((code, json.loads(out.getvalue())), (0, dict(projection_checker=projection_check.projection_checker_id())))


class Control(unittest.TestCase):
    COMPARISON = """        if actual != expected:
"""

    def test_without_the_row_comparison_a_flipped_cell_conforms(self):
        source = (ROOT / 'src' / 'projection_check.py').read_text()
        self.assertIn(self.COMPARISON, source, 'mutation site not found: the control would prove nothing')
        import types
        mutant = types.ModuleType('stargate.projection_check_mutant'); mutant.__package__ = 'stargate'
        mutant.__file__, mutant.__loader__ = projection_check.__file__, projection_check.__loader__
        exec(compile(source.replace(self.COMPARISON, '        if False:\n'), 'mutant', 'exec'), mutant.__dict__)
        projected, cert, model = evidence_for(two_bit())
        bad = flip(projected, 4, 'a')
        self.assertEqual(check(bad, cert, model)['status'], 'mismatch')
        pid = mutant.projection_checker_id()
        self.assertEqual(mutant.check(bad, cert, model, CHECKER, pid)['status'], 'conforms')
