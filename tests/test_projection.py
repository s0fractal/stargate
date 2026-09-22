"""projection-1: a machine's full transition table as canonical data, unchecked.

Expectations are pre-registered in vertical/projection_REGISTRY.md.
"""
import contextlib
import hashlib
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from stargate import certificate, cli, lab, machine, projection
from stargate.canonical import canon, decode, InvalidRecord

ROOT = Path(__file__).resolve().parent.parent
ZOO = ROOT / 'examples' / 'zoo'
F, T = False, True


def rule(names, expression):
    return ''.join('fact ' + n + ': bool\n' for n in sorted(names)) + 'check ' + expression + '\n'


def two_bit(max_atp=1000):
    names = ['a', 'b', 'e']
    return machine.create(dict(
        state=['a', 'b'], events=['e'], initial=[dict(a=F, b=F)], max_atp=max_atp, goals=[],
        invariant=rule(['a', 'b'], 'a || !a'),
        next={'a': rule(names, 'a || e'), 'b': rule(names, 'a && !b')}))


# Registration outcome 1, copied from the table there.
EXPECTED = [((F, F, F), (F, F)), ((F, F, T), (T, F)), ((F, T, F), (F, F)), ((F, T, T), (T, F)),
            ((T, F, F), (T, T)), ((T, F, T), (T, T)), ((T, T, F), (T, F)), ((T, T, T), (T, F))]


def projected(raw=None):
    raw = raw or two_bit()
    return projection.project(raw, lab.identity(raw))


def hand_made():
    """The registered table written out by hand, without the projector."""
    raw = two_bit()
    model = certificate.identity(certificate.model_from_machine(machine.inspect(raw)))
    rows = [dict(state=dict(a=a, b=b), event=dict(e=e), next=dict(a=x, b=y))
            for (a, b, e), (x, y) in EXPECTED]
    return dict(projection=1, model=model, state=['a', 'b'], events=['e'], rows=rows)


def with_rows(rows):
    return canon(dict(hand_made(), rows=rows))


class Format(unittest.TestCase):
    def test_the_two_bit_machine_projects_to_the_registered_table(self):
        raw = two_bit()
        report, packet = projected(raw)
        document = decode(packet)
        rows = [((r['state']['a'], r['state']['b'], r['event']['e']), (r['next']['a'], r['next']['b']))
                for r in document.get('rows', [])]
        self.assertEqual(rows, EXPECTED)
        self.assertEqual((document.get('projection'), document.get('state'), document.get('events')),
                         (1, ['a', 'b'], ['e']))
        self.assertEqual(document.get('model'),
                         certificate.identity(certificate.model_from_machine(machine.inspect(raw))))
        self.assertEqual(report, dict(status='projected', model=document.get('model'), rows=8,
                                      projection_id=hashlib.sha256(packet).hexdigest()))

    def test_the_same_machine_projects_to_the_same_bytes(self):
        first, second = projected(), projected()
        self.assertEqual(first[1], second[1])
        self.assertEqual(first[0].get('projection_id'), hashlib.sha256(first[1]).hexdigest())
        self.assertEqual(len(decode(first[1]).get('rows', [])), 8)

    def test_the_projection_it_writes_is_the_hand_made_one(self):
        self.assertEqual(projected()[1], canon(hand_made()))

    def test_every_zoo_machine_projects(self):
        sys.path.insert(0, str(ZOO))
        import harness
        counts = {}
        for system in harness.load(ZOO / 'systems'):
            raw = machine.create(harness.model(system, 'correct'))
            report, packet = projection.project(raw, lab.identity(raw))
            counts[system['name']] = len(decode(packet).get('rows', []))
            self.assertEqual(report.get('rows'), counts[system['name']])
            self.assertEqual(counts[system['name']], 2 ** (len(system['state']) + len(system['events'])))
        self.assertEqual(len(counts), 13)
        self.assertEqual(counts['peterson'], 64)

    def test_a_machine_that_is_not_the_expected_one_is_invalid_input(self):
        raw = two_bit()
        with self.assertRaises(InvalidRecord):
            projection.project(raw, '0' * 64)


class Refusals(unittest.TestCase):
    def rows(self):
        return hand_made()['rows']

    def test_the_hand_made_projection_is_accepted(self):
        self.assertEqual(projection.inspect(canon(hand_made())), hand_made())

    def test_a_duplicated_row_is_refused(self):
        rows = self.rows(); rows[3] = rows[2]
        with self.assertRaisesRegex(InvalidRecord, 'duplicate row'):
            projection.inspect(with_rows(rows))

    def test_a_missing_row_is_refused(self):
        rows = self.rows(); del rows[5]
        with self.assertRaisesRegex(InvalidRecord, 'missing row'):
            projection.inspect(with_rows(rows))

    def test_rows_out_of_canonical_order_are_refused(self):
        rows = self.rows(); rows[0], rows[1] = rows[1], rows[0]
        with self.assertRaisesRegex(InvalidRecord, 'canonical order'):
            projection.inspect(with_rows(rows))

    def test_wrong_shapes_are_refused(self):
        good = hand_made()
        def variant(change):
            document = decode(canon(good)); change(document); return canon(document)
        def drop_bit(d): del d['rows'][0]['next']['b']
        def extra_row_field(d): d['rows'][0]['note'] = 'x'
        def verdict(d): d['conforms'] = True
        def not_boolean(d): d['rows'][0]['next']['a'] = 0
        def unsorted(d): d['state'] = ['b', 'a']
        def version(d): d['projection'] = 2
        def seven_bits(d): d['state'] = list('abcdfgh')
        def three_events(d): d['events'] = ['e', 'x', 'y']
        def overlap(d): d['events'] = ['a']
        cases = [drop_bit, extra_row_field, verdict, not_boolean, unsorted, version,
                 seven_bits, three_events, overlap]
        accepted = []
        for case in cases:
            try: projection.inspect(variant(case))
            except InvalidRecord: continue
            accepted.append(case.__name__)
        self.assertEqual(accepted, [])

    def test_bytes_that_are_not_canonical_are_refused(self):
        with self.assertRaises(InvalidRecord):
            projection.inspect(json.dumps(hand_made(), indent=1).encode())


class Command(unittest.TestCase):
    def run_cli(self, *args):
        out = io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(io.StringIO()):
            code = cli.main(list(args))
        return code, out.getvalue()

    def test_model_project_writes_the_projection_and_reports_it(self):
        raw = two_bit()
        with tempfile.TemporaryDirectory() as tmp:
            path, output = Path(tmp) / 'machine.json', Path(tmp) / 'projection.json'
            path.write_bytes(raw)
            code, out = self.run_cli('model-project', str(path), '--expect-machine', lab.identity(raw),
                                     '--output', str(output))
            self.assertEqual(code, 0)
            written = output.read_bytes() if output.exists() else b''
            self.assertEqual(json.loads(out).get('projection_id'), hashlib.sha256(written).hexdigest())
            self.assertEqual(written, projected(raw)[1])
            again, _ = self.run_cli('model-project', str(path), '--expect-machine', lab.identity(raw),
                                    '--output', str(output))
            self.assertNotEqual(again, 0)
            self.assertEqual(output.read_bytes(), written)

    def test_a_budget_that_runs_out_is_exit_3_and_writes_nothing(self):
        """Not registered in advance; added with the SPEC sentence that claims it."""
        raw = two_bit(max_atp=10)
        with tempfile.TemporaryDirectory() as tmp:
            path, output = Path(tmp) / 'machine.json', Path(tmp) / 'p.json'
            path.write_bytes(raw)
            code, out = self.run_cli('model-project', str(path), '--expect-machine', lab.identity(raw),
                                     '--output', str(output))
            self.assertEqual((code, json.loads(out)['status']), (3, 'incomplete'))
            self.assertFalse(output.exists())

    def test_the_wrong_expected_machine_is_exit_2(self):
        raw = two_bit()
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'machine.json'; path.write_bytes(raw)
            code, _ = self.run_cli('model-project', str(path), '--expect-machine', '0' * 64,
                                   '--output', str(Path(tmp) / 'p.json'))
            self.assertEqual(code, 2)
            self.assertFalse((Path(tmp) / 'p.json').exists())


class NoClaim(unittest.TestCase):
    """Registered control: PR-02 does not say a projection is right."""

    def test_a_flipped_cell_is_still_an_acceptable_projection(self):
        document = hand_made()
        document['rows'][4]['next']['a'] = not document['rows'][4]['next']['a']
        wrong = canon(document)
        self.assertNotEqual(wrong, canon(hand_made()))
        self.assertEqual(projection.inspect(wrong), document)

    def test_the_report_carries_no_verdict(self):
        report, _ = projected()
        self.assertEqual(set(report), {'status', 'model', 'rows', 'projection_id'})
        self.assertEqual(report['status'], 'projected')


class Closure(unittest.TestCase):
    def test_projection_is_in_no_checked_closure(self):
        self.assertNotIn('projection.py', certificate.SOURCES)
        self.assertNotIn('projection.py', lab.RUNTIME)

    def test_the_vertical_baseline_still_holds(self):
        result = subprocess.run([sys.executable, str(ROOT / 'tools' / 'vertical_baseline.py'), '--check'],
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stdout)


ORDER_CHECK = """    if keys != expected:
        raise InvalidRecord('rows are not in canonical order')
"""


class Control(unittest.TestCase):
    def test_without_the_order_check_swapped_rows_pass(self):
        source = (ROOT / 'src' / 'projection.py').read_text()
        self.assertIn(ORDER_CHECK, source, 'mutation site not found: the control would prove nothing')
        import types
        mutant = types.ModuleType('stargate.projection_mutant')
        mutant.__package__ = 'stargate'
        exec(compile(source.replace(ORDER_CHECK, ''), 'projection_mutant', 'exec'), mutant.__dict__)
        rows = hand_made()['rows']; rows[0], rows[1] = rows[1], rows[0]
        swapped = with_rows(rows)
        with self.assertRaises(InvalidRecord):
            projection.inspect(swapped)
        self.assertEqual(mutant.inspect(swapped)['rows'], rows)


def corner(extra=0):
    """Second registration: the largest projection the machine schema admits."""
    events = ['x', 'y']
    state = sorted(['a' * (8185 - 11 * 8 - 2 - 5 + extra)] + list('bcdef'))
    declare = lambda names: ''.join('fact ' + n + ':bool ' for n in sorted(names))
    rule = declare(state + events) + 'check!b'
    return machine.create(dict(state=state, events=events, initial=[{n: F for n in state}],
                               max_atp=1000, goals=[], invariant=declare(state) + 'check!b',
                               next={n: rule for n in state}))


class Ceiling(unittest.TestCase):
    def test_the_ceiling_is_the_registered_derivation(self):
        self.assertEqual(projection.MAX_PROJECTION, 4193586)

    def test_the_corner_machine_is_exactly_at_the_schema_limit(self):
        raw = corner()
        self.assertEqual(max(len(s.encode()) for s in decode(raw)['next'].values()), 8192)
        with self.assertRaisesRegex(Exception, 'source exceeds 8192 bytes'):
            corner(extra=1)

    def test_the_corner_machine_projects_within_the_ceiling(self):
        raw = corner()
        try:
            report, packet = projection.project(raw, lab.identity(raw))
        except InvalidRecord as exc:
            self.fail('a valid machine could not be projected: ' + str(exc))
        self.assertEqual((report['status'], report['rows']), ('projected', 256))
        self.assertLessEqual(len(packet), projection.MAX_PROJECTION)
        projection.inspect(packet)

    def test_one_byte_over_the_ceiling_is_refused_for_size(self):
        with self.assertRaisesRegex(InvalidRecord, 'within'):
            projection.inspect(b' ' * (projection.MAX_PROJECTION + 1))
        with self.assertRaises(InvalidRecord) as caught:
            projection.inspect(b' ' * projection.MAX_PROJECTION)
        self.assertNotIn('within', str(caught.exception))
