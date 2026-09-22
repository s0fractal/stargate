"""A fixed table runtime executes a projection by lookup and nothing else.

Expectations are pre-registered in vertical/table_runtime_REGISTRY.md.
"""
import ast
import contextlib
import hashlib
import io
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_projection import hand_made, two_bit, with_rows  # noqa: E402
from test_projection_check import CHECKER, check, evidence_for, flip  # noqa: E402

from stargate import cli, evidence, lab, machine, projection, projection_runtime  # noqa: E402
from stargate.canonical import canon, decode  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
ZOO = ROOT / 'examples' / 'zoo'
SOURCE = ROOT / 'src' / 'projection_runtime.py'
Machine = projection_runtime.ProjectionMachine


def zoo():
    sys.path.insert(0, str(ZOO))
    import harness
    return [(system['name'], machine.create(harness.model(system, 'correct')))
            for system in harness.load(ZOO / 'systems')]


def answers(fsm, projected):
    """(expected, actual) next for every row of the projection."""
    rows = decode(projected)['rows']
    return [row['next'] for row in rows], [fsm.step(row['state'], row['event']) for row in rows]


class Execution(unittest.TestCase):
    def test_every_zoo_projection_is_executed_row_for_row(self):
        wrong, counts = [], {}
        for name, raw in zoo():
            _, projected = projection.project(raw, lab.identity(raw))
            expected, actual = answers(Machine.from_bytes(projected), projected)
            counts[name] = sum(e == a for e, a in zip(expected, actual))
            if expected != actual: wrong.append(name)
        self.assertEqual(wrong, [])
        self.assertEqual((len(counts), counts['peterson']), (13, 64))

    def test_a_certified_projection_conforms_and_the_runtime_executes_it(self):
        checked = 0
        for name, raw in zoo():
            report, _ = evidence.produce(raw, lab.identity(raw))
            if report['status'] != 'verified_certificate': continue
            projected, cert, model = evidence_for(raw)
            self.assertEqual(check(projected, cert, model)['status'], 'conforms', name)
            expected, actual = answers(Machine.from_bytes(projected), projected)
            self.assertEqual(actual, expected, name)
            checked += 1
        self.assertEqual(checked, 11)

    def test_the_same_bytes_load_to_the_same_machine(self):
        projected = canon(hand_made())
        first, second = Machine.from_bytes(projected), Machine.from_bytes(projected)
        self.assertEqual(answers(first, projected)[1], answers(second, projected)[1])
        self.assertEqual(getattr(first, 'projection_id', None), hashlib.sha256(projected).hexdigest())
        self.assertEqual(getattr(first, 'projection_id', None), getattr(second, 'projection_id', None))
        self.assertEqual((getattr(first, 'state_names', None), getattr(first, 'event_names', None),
                          getattr(first, 'model', None)), (['a', 'b'], ['e'], hand_made()['model']))

    def test_an_answer_cannot_change_the_table(self):
        fsm = Machine.from_bytes(canon(hand_made()))
        answer = fsm.step(dict(a=True, b=False), dict(e=False))
        answer['a'] = False
        self.assertEqual(fsm.step(dict(a=True, b=False), dict(e=False)), dict(a=True, b=True))


class Refusals(unittest.TestCase):
    def test_unknown_states_and_events_are_refused(self):
        fsm = Machine.from_bytes(canon(hand_made()))
        state, event = dict(a=True, b=False), dict(e=False)
        bad_states = [dict(a=True), dict(a=True, b=False, c=True), dict(a=1, b=False), [True, False]]
        bad_events = [{}, dict(e=False, f=True), dict(e=0), [False]]
        def refused(call, word):
            try: call()
            except ValueError as exc: return 'unknown ' + word in str(exc)
            except Exception: return False
            return False
        outcomes = ([refused(lambda v=v: fsm.step(v, event), 'state') for v in bad_states] +
                    [refused(lambda v=v: fsm.step(state, v), 'event') for v in bad_events])
        self.assertEqual(outcomes, [True] * 8)

    def test_malformed_projections_are_refused_at_load(self):
        good = hand_made(); rows = good['rows']
        over = b' ' * (projection.MAX_PROJECTION + 1)
        cases = {'duplicate': with_rows(rows[:3] + [rows[2]] + rows[4:]),
                 'missing': with_rows(rows[:5] + rows[6:]),
                 'swapped': with_rows([rows[1], rows[0]] + rows[2:]),
                 'extra field': canon(dict(good, conforms=True)),
                 'non-canonical': json.dumps(good, indent=1).encode(),
                 'duplicate key': canon(good).replace(b'{"events"', b'{"events":["e"],"events"', 1),
                 'over the ceiling': over}
        loaded = []
        for name, raw in cases.items():
            try: Machine.from_bytes(raw)
            except ValueError: continue
            loaded.append(name)
        self.assertEqual(loaded, [])

    def test_the_ceiling_is_the_producers(self):
        self.assertEqual(projection_runtime.MAX_PROJECTION, projection.MAX_PROJECTION)


class NoInterpreter(unittest.TestCase):
    def test_only_the_standard_library_and_no_dynamic_code(self):
        tree = ast.parse(SOURCE.read_text())
        imports = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import): imports |= {a.name for a in node.names}
            if isinstance(node, ast.ImportFrom): imports.add(('.' * node.level) + (node.module or ''))
        self.assertLessEqual(imports, {'json', 'hashlib', 'itertools', 'pathlib'})
        forbidden = {'eval', 'exec', 'compile', '__import__', 'importlib', 'getattr', 'setattr',
                     'globals', 'pickle', 'marshal', 'boolean', 'compiler', 'stargate'}
        names = {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)} | \
                {n.attr for n in ast.walk(tree) if isinstance(n, ast.Attribute)}
        self.assertEqual(names & forbidden, set())

    def test_every_parameter_is_one_of_the_documented_data_inputs(self):
        """A name whitelist: the proxy for 'no callable is accepted', stated as what it is."""
        tree = ast.parse(SOURCE.read_text())
        parameters = {a.arg for f in ast.walk(tree) if isinstance(f, (ast.FunctionDef, ast.Lambda))
                      for a in f.args.args + f.args.kwonlyargs}
        self.assertLessEqual(parameters, {'self', 'cls', 'raw', 'path', 'state', 'event'})


class Materialize(unittest.TestCase):
    def test_three_files_digests_and_a_standalone_run(self):
        projected = canon(hand_made())
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); (root / 'p.json').write_bytes(projected)
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                code = cli.main(['projection-materialize', str(root / 'p.json'), '--lang', 'python', '--output', str(root / 'app')])
            app = root / 'app'
            files = sorted(p.name for p in app.iterdir()) if app.exists() else []
            self.assertEqual((code, files), (0, ['RUNTIME.json', 'projection.json', 'runtime.py']))
            self.assertEqual((app / 'runtime.py').read_bytes(), SOURCE.read_bytes())
            self.assertEqual((app / 'projection.json').read_bytes(), projected)
            manifest = json.loads((app / 'RUNTIME.json').read_text())
            self.assertEqual(manifest, dict(runtime='python-table-1', model=hand_made()['model'],
                                            runtime_digest=hashlib.sha256(SOURCE.read_bytes()).hexdigest(),
                                            projection=hashlib.sha256(projected).hexdigest()))
            self.assertEqual(json.loads(out.getvalue()), manifest)
            script = ('import json, sys\nsys.path.insert(0, ".")\nfrom runtime import ProjectionMachine as M\n'
                      'm = M.load("projection.json")\n'
                      'print(json.dumps([m.step(r["state"], r["event"]) for r in json.load(open("projection.json"))["rows"]]))\n')
            result = subprocess.run([sys.executable, '-I', '-S', '-c', script], cwd=app, capture_output=True, text=True)
            again = subprocess.run([sys.executable, '-m', 'stargate', 'projection-materialize', str(root / 'p.json'),
                                    '--lang', 'python', '--output', str(app)], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout), [r['next'] for r in hand_made()['rows']])
        self.assertNotEqual(again.returncode, 0)

    def test_a_malformed_projection_is_not_materialized(self):
        rows = hand_made()['rows']
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); (root / 'p.json').write_bytes(with_rows(rows[:5] + rows[6:]))
            with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                code = cli.main(['projection-materialize', str(root / 'p.json'), '--lang', 'python', '--output', str(root / 'app')])
            self.assertEqual((code, (root / 'app').exists()), (2, False))


class Controls(unittest.TestCase):
    def test_the_runtime_executes_a_flipped_cell_and_the_verifier_rejects_it(self):
        projected, cert, model = evidence_for(two_bit())
        bad = flip(projected, 4, 'a')
        row = decode(bad)['rows'][4]
        self.assertEqual(Machine.from_bytes(bad).step(row['state'], row['event']), row['next'])
        self.assertNotEqual(row['next'], decode(projected)['rows'][4]['next'])
        self.assertEqual(check(bad, cert, model)['status'], 'mismatch')

    DOMAIN_CHECK_START = '        # domain check: begin\n'
    DOMAIN_CHECK_END = '        # domain check: end\n'

    def test_without_the_domain_check_a_conflicting_table_loads(self):
        source = SOURCE.read_text()
        self.assertIn(self.DOMAIN_CHECK_START, source, 'mutation site not found: the control would prove nothing')
        start = source.index(self.DOMAIN_CHECK_START); end = source.index(self.DOMAIN_CHECK_END)
        namespace = {'__name__': 'runtime_mutant'}
        exec(compile(source[:start] + source[end:], 'runtime_mutant', 'exec'), namespace)
        rows = hand_made()['rows']
        twin = json.loads(json.dumps(rows[2])); twin['next']['a'] = not twin['next']['a']
        planted = with_rows(rows[:3] + [twin] + rows[4:])
        with self.assertRaises(ValueError):
            Machine.from_bytes(planted)
        mutant = namespace['ProjectionMachine'].from_bytes(planted)
        answer = mutant.step(rows[2]['state'], rows[2]['event'])
        self.assertIn(answer, (rows[2]['next'], twin['next']))
        with self.assertRaises(KeyError):
            mutant.step(rows[3]['state'], rows[3]['event'])


class Closure(unittest.TestCase):
    def test_every_anchored_digest_is_unchanged(self):
        for tool in ('anchors.py', 'vertical_baseline.py'):
            result = subprocess.run([sys.executable, str(ROOT / 'tools' / tool), '--check'], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, tool + ': ' + result.stdout)
