import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from stargate import machine, lab, compiler
from stargate.canonical import canon, decode, InvalidRecord
from test_machine import wpl, table_rule


def parent():
    return machine.create(dict(state=['a', 'b'], events=[], initial=[dict(a=False, b=False)],
        next={n: wpl(['a', 'b'], f'{n} && (a || !a) && (b || !b)') for n in ['a', 'b']},
        invariant=wpl(['a', 'b'], '!a && (b || !b)'), max_atp=1000))


def proposal(raw, bad=False):
    return dict(parent=lab.identity(raw), next={
        'a': wpl(['a', 'b'], 'b && (a || !a)' if bad else 'a && (b || !b)'),
        'b': wpl(['a', 'b'], '(a || !a) && (b || !b)')})


def change(raw, p=None, **kw):
    return machine.verify_change(raw, proposal(raw) if p is None else p, lab.identity(raw), **kw)


class MachineChange(unittest.TestCase):
    def test_successor_changes_behavior_and_preserves_every_other_byte(self):
        raw = parent(); p = proposal(raw)
        report, child = change(raw, p)
        self.assertEqual(report['status'], 'safety_preserved')
        self.assertTrue(report['admitted'])
        self.assertEqual(child, canon(dict(decode(raw), next=p['next'])))
        self.assertEqual(report['successor'], lab.identity(child))
        self.assertEqual(report['parent'], lab.identity(raw))
        self.assertEqual(report['checks']['parent']['reachable'], [dict(a=False, b=False)])
        self.assertEqual(report['checks']['candidate']['reachable'],
                         [dict(a=False, b=False), dict(a=False, b=True)])
        before = decode(raw); after = decode(child)
        self.assertEqual(after.pop('next'), p['next']); before.pop('next')
        self.assertEqual(after, before)
        self.assertEqual(change(raw, p), (report, child))
        # An unchanged machine is allowed, without inventing a new identity.
        same, output = change(child, dict(parent=lab.identity(child), next=decode(child)['next']))
        self.assertTrue(same['admitted']); self.assertEqual(output, child)

    def test_candidate_new_reachable_states_are_checked_and_trace_is_literal(self):
        raw = parent(); report, child = change(raw, proposal(raw, bad=True))
        self.assertEqual(report['status'], 'counterexample')
        self.assertEqual((report['status'], report['program'], report['admitted'], child),
                         ('counterexample', 'candidate', False, None))
        self.assertNotIn('successor', report)
        self.assertEqual(report['checks']['candidate']['trace'], dict(initial=dict(a=False, b=False),
            steps=[dict(event={}, state=dict(a=False, b=True)), dict(event={}, state=dict(a=True, b=True))]))

    def test_broken_parent_cannot_be_repaired_through_admission(self):
        raw = parent(); broken = canon(dict(decode(raw), next=proposal(raw, True)['next']))
        fix = dict(parent=lab.identity(broken), next=decode(raw)['next'])
        with patch.object(machine, 'verify', wraps=machine.verify) as count:
            report, child = change(broken, fix)
        self.assertEqual(report['status'], 'parent_rejected')
        self.assertEqual((report['status'], report['program'], child), ('parent_rejected', 'parent', None))
        self.assertFalse(report['admitted']); self.assertEqual(count.call_count, 1)
        self.assertEqual(list(report['checks']), ['parent'])

    def test_each_budget_and_checker_failure_is_not_admission(self):
        raw = parent()
        # Parent closes in one edge; candidate needs two. The quota is per graph.
        for quota, role in [(0, 'parent'), (1, 'candidate')]:
            report, output = change(raw, max_edges=quota)
            self.assertEqual((report['status'], report['program'], output), ('incomplete', role, None))
            self.assertFalse(report['admitted']); self.assertNotIn('successor', report)
        for status in ['incomplete', 'checker_error']:
            for role in ['parent', 'candidate']:
                real = machine.verify
                def injected(packet, anchor, **kw):
                    if (packet == raw) == (role == 'parent'): return dict(status=status, reason='injected')
                    return real(packet, anchor, **kw)
                with patch.object(machine, 'verify', side_effect=injected): report, output = change(raw)
                self.assertEqual((report['status'], report['program'], output), (status, role, None))
                self.assertFalse(report['admitted'])

    def test_proposal_and_recipient_anchors_and_contract_override_rejected_before_work(self):
        raw = parent(); p = proposal(raw)
        bad = [dict(p, parent='0'*64), dict(p, next={}), dict(p, next=dict(p['next'], extra='check true')),
               dict(p, next=dict(p['next'], a='check true'))]
        for field in ['initial', 'state', 'events', 'invariant', 'max_atp', 'sources', 'admitted', 'successor']:
            bad.append(dict(p, **{field: decode(raw).get(field)}))
        with patch.object(machine, 'verify', side_effect=AssertionError('must not evaluate')):
            for item in bad:
                with self.subTest(item=item), self.assertRaises((InvalidRecord, compiler.PolicyError)): change(raw, item)
            with self.assertRaises(InvalidRecord): machine.verify_change(raw, p, '0'*64)
            for quota in [True, -1, 257, 1.0]:
                with self.assertRaises(InvalidRecord): change(raw, max_edges=quota)
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)/'p.json'
            path.write_text(json.dumps(p, indent=2)); self.assertEqual(machine.read_change(path), p)
            path.write_text('{"parent":"x","parent":"y","next":{}}')
            with self.assertRaises(InvalidRecord): machine.read_change(path)

    def test_all_one_bit_parent_candidate_pairs_against_direct_graph(self):
        # 4 transition tables x 4 candidates x 4 invariants x 3 initial sets.
        def safe(table, allowed, initial):
            reached = set(initial)
            while not {table[int(x)] for x in reached} <= reached:
                reached |= {table[int(x)] for x in reached}
            return all(allowed[int(x)] for x in reached)
        for pm in range(4):
            pt = [bool(pm & (1 << x)) for x in range(2)]
            for cm in range(4):
                ct = [bool(cm & (1 << x)) for x in range(2)]
                for im in range(4):
                    allowed = [bool(im & (1 << x)) for x in range(2)]
                    for initial in [[False], [True], [False, True]]:
                        raw = machine.create(dict(state=['q'], events=[], initial=[dict(q=q) for q in initial],
                            next={'q': table_rule(['q'], pt)}, invariant=table_rule(['q'], allowed), max_atp=1000))
                        p = dict(parent=lab.identity(raw), next={'q': table_rule(['q'], ct)})
                        expected = ('parent_rejected' if not safe(pt, allowed, initial) else
                                    'counterexample' if not safe(ct, allowed, initial) else 'safety_preserved')
                        with self.subTest(parent=pm, candidate=cm, invariant=im, initial=initial):
                            report, output = change(raw, p)
                            self.assertEqual(report['status'], expected)
                            self.assertEqual(report['admitted'], expected == 'safety_preserved')
                            self.assertEqual(output, canon(dict(decode(raw), next=p['next'])) if report['admitted'] else None)

    def test_cli_and_offline_same_reports_outputs_and_refusals(self):
        raw = parent()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); offline = root/'offline'; desc = machine.unpack(raw, offline)
            source = root/'machine.json'; source.write_bytes(raw)
            prop = root/'proposal.json'
            for p, quota, anchor, code, status in [
                (proposal(raw), 256, lab.identity(raw), 0, 'safety_preserved'),
                (proposal(raw, True), 256, lab.identity(raw), 4, 'counterexample'),
                (proposal(raw), 1, lab.identity(raw), 3, 'incomplete'),
                (proposal(raw), 256, '0'*64, 2, 'invalid')]:
                prop.write_text(json.dumps(p)); reports=[]; outputs=[]
                for mode in ['cli', 'offline']:
                    output = root/('out-'+mode)
                    if output.exists(): output.unlink()
                    command = ([sys.executable, '-I', '-m', 'stargate', 'machine-change', str(source), str(prop), '--output', str(output)]
                        if mode == 'cli' else [sys.executable, '-I', '-S', str(offline/'replay.py'), str(prop), str(output),
                            '--machine-change', '--expect-runtime', desc['runtime_digest']])
                    result = subprocess.run(command + ['--expect-machine', anchor, '--max-edges', str(quota)], cwd='/', capture_output=True, text=True)
                    self.assertNotIn('Traceback', result.stderr)
                    report = json.loads(result.stdout or result.stderr)
                    self.assertEqual((result.returncode, report['status']), (code, status))
                    self.assertEqual(output.exists(), code == 0)
                    reports.append(report); outputs.append(output.read_bytes() if output.exists() else None)
                self.assertEqual(reports[0], reports[1]); self.assertEqual(outputs[0], outputs[1])

    def test_cli_offline_parent_runtime_missing_and_occupied_destination(self):
        raw = parent()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); offline = root/'offline'; desc = machine.unpack(raw, offline)
            source = root/'machine.json'; prop = root/'proposal.json'; output = root/'out'
            broken = canon(dict(decode(raw), next=proposal(raw, True)['next']))
            foreign = decode(raw); foreign['sources']['machine.py'] += '\n# foreign runtime'
            cases = [
                (broken, dict(parent=lab.identity(broken), next=decode(raw)['next']), False, 4, 'parent_rejected'),
                (canon(foreign), proposal(canon(foreign)), False, 3, 'runtime_unavailable'),
                (raw, None, False, 3, 'unverified'),
                (raw, proposal(raw), True, 1, 'operation_error')]
            for packet, p, occupied, code, status in cases:
                source.write_bytes(packet); (offline/'machine.json').write_bytes(packet)
                if p is None:
                    if prop.exists(): prop.unlink()
                else: prop.write_text(json.dumps(p))
                for mode in ['cli', 'offline']:
                    if output.exists(): output.unlink()
                    if occupied: output.write_bytes(b'keep')
                    command = ([sys.executable, '-I', '-m', 'stargate', 'machine-change', str(source), str(prop), '--output', str(output)]
                        if mode == 'cli' else [sys.executable, '-I', '-S', str(offline/'replay.py'), str(prop), str(output),
                            '--machine-change', '--expect-runtime', desc['runtime_digest']])
                    result = subprocess.run(command + ['--expect-machine', lab.identity(packet)], cwd='/', capture_output=True, text=True)
                    self.assertNotIn('Traceback', result.stderr)
                    report = json.loads(result.stdout or result.stderr)
                    self.assertEqual((result.returncode, report['status']), (code, status))
                    self.assertEqual(output.read_bytes() if output.exists() else None, b'keep' if occupied else None)
