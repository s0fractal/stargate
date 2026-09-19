import copy
import itertools
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from stargate import certificate as c, machine, compiler
from stargate.canonical import canon, decode, InvalidRecord


def rule(expr):
    return 'fact x: bool\ncheck ' + expr


def evidence(expr='!x', invariant='true', states=None, goals=None, paths=None):
    return canon(dict(certificate=1, checker=c.checker_id(),
        model=dict(language='boolean-machine-1', state=['x'], events=[],
                   initial=[{'x': False}], next={'x': rule(expr)}, invariant=rule(invariant),
                   goals=[] if goals is None else goals),
        states=[{'x': False}, {'x': True}] if states is None else states,
        paths=[] if paths is None else paths))


class CertifiedChanges(unittest.TestCase):
    def setUp(self):
        self.parent = evidence('x')
        self.candidate = evidence('!x')
        self.anchor = c.identity(decode(self.parent)['model'])

    def check(self, parent=None, candidate=None, **kw):
        raw = c.pack_change(self.parent if parent is None else parent,
                            self.candidate if candidate is None else candidate)
        return c.verify_change(raw, self.anchor, c.checker_id(), **kw)

    def test_changed_behavior_preserves_contract_without_bfs_or_compiler(self):
        with patch.object(machine, 'verify', side_effect=AssertionError('BFS used')), \
                patch.object(compiler, 'compile_source', side_effect=AssertionError('compiler used')):
            report, child = self.check()
        self.assertEqual(report['status'], 'verified_change')
        self.assertEqual(child, self.candidate)
        self.assertEqual(report['successor_model'], c.identity(decode(child)['model']))
        self.assertEqual(report['successor_certificate'], c.identity(decode(child)))
        self.assertEqual([r['role'] for r in report['checks']], ['parent', 'candidate'])
        self.assertEqual([r['report']['checked_edges'] for r in report['checks']], [2, 2])
        self.assertEqual(c.exit_code(report), 0)
        self.assertEqual(set(c.SOURCES), {'__init__.py', 'store.py', 'canonical.py', 'boolean.py', 'certificate.py'})
        # The output is reusable evidence under a new independently chosen anchor.
        reverse = c.pack_change(child, self.parent)
        report, grandchild = c.verify_change(reverse, c.identity(decode(child)['model']), c.checker_id())
        self.assertEqual(grandchild, self.parent)
        self.assertEqual(report['status'], 'verified_change')
        self.assertEqual(self.check(candidate=self.parent)[1], self.parent)  # no-op legal

    def test_all_protected_fields_refused_and_parent_anchor_required(self):
        changes = {'language': 'other', 'state': ['y'], 'events': ['e'],
                   'initial': [{'x': True}], 'invariant': rule('x || !x'), 'goals': [{'x': False}]}
        for field, value in changes.items():
            with self.subTest(field=field):
                child = decode(self.candidate); child['model'][field] = value
                if field == 'state':
                    child['model']['initial'] = [{'y': False}]
                    child['model']['next'] = {'y': 'fact y: bool\ncheck !y'}
                    child['model']['invariant'] = 'fact y: bool\ncheck true'
                    child['states'] = [{'y': False}, {'y': True}]
                if field == 'events':
                    child['model']['next']['x'] = 'fact e: bool\nfact x: bool\ncheck !x'
                if field == 'goals':
                    child['paths'] = [{'goal': {'x': False}, 'trace': {'initial': {'x': False}, 'steps': []}}]
                if field == 'language':
                    with self.assertRaises(InvalidRecord): self.check(candidate=canon(child))
                else:
                    with self.assertRaisesRegex(InvalidRecord, 'protected field'):
                        self.check(candidate=canon(child))
        raw = c.pack_change(self.parent, self.candidate)
        with self.assertRaisesRegex(InvalidRecord, 'recipient anchor'):
            c.verify_change(raw, '0'*64, c.checker_id())
        doc = decode(raw); doc['admitted'] = True
        with self.assertRaises(InvalidRecord): c.inspect_change(canon(doc))

    def test_both_proofs_are_rechecked_not_just_models_or_labels(self):
        for role in ('parent', 'candidate'):
            with self.subTest(role=role):
                cert = decode(self.parent if role == 'parent' else self.candidate)
                cert['states'] = [{'x': True}]  # omits the real initial
                with self.assertRaisesRegex(InvalidRecord, 'initial'):
                    self.check(**{role: canon(cert)})
        child = decode(self.candidate); child['states'] = [{'x': False}]
        with self.assertRaisesRegex(InvalidRecord, 'closed'):
            self.check(candidate=canon(child))

    def test_candidate_goal_needs_path_not_membership(self):
        goal = [{'x': True}]
        path = [{'goal': {'x': True}, 'trace': {'initial': {'x': False},
                 'steps': [{'event': {}, 'state': {'x': True}}]}}]
        parent = evidence('!x', goals=goal, paths=path)
        self.anchor = c.identity(decode(parent)['model'])
        # x holds at false forever: S contains true, but the supplied path lies.
        candidate = evidence('x', goals=goal, paths=path)
        with self.assertRaisesRegex(InvalidRecord, 'transition'):
            self.check(parent=parent, candidate=candidate)

    def test_quota_and_checker_refusals_never_release_successor(self):
        report, child = self.check(max_steps=0)
        self.assertEqual((report['status'], report.get('failed'), child), ('incomplete', 'parent', None))
        # Parent requires one edge, candidate two; same quota is applied to each.
        parent = evidence('x', states=[{'x': False}])
        report, child = self.check(parent=parent, max_steps=1)
        self.assertEqual((report['status'], report.get('failed'), child), ('incomplete', 'candidate', None))
        self.assertNotIn('successor_model', report)
        for role in ('parent', 'candidate'):
            cert = decode(self.parent if role == 'parent' else self.candidate); cert['checker'] = '0'*64
            report, child = self.check(**{role: canon(cert)})
            self.assertEqual((report['status'], report.get('failed'), child), ('checker_unavailable', role, None))
        with patch.object(c, 'verify', return_value={'status': 'checker_error'}):
            report, child = self.check()
            self.assertEqual((report['status'], child, c.exit_code(report)), ('checker_error', None, 1))

    def test_exhaustive_one_bit_changes_against_direct_transition_tables(self):
        expressions = ['false', 'x', '!x', 'true']
        tables = [(False, False), (False, True), (True, False), (True, True)]
        for pi, ci, ii in itertools.product(range(4), repeat=3):
            def reached(table):
                seen = {False}; current = False
                while table[current] not in seen:
                    current = table[current]; seen.add(current)
                return seen
            pset, cset = reached(tables[pi]), reached(tables[ci])
            safe = all(tables[ii][x] for x in pset | cset)
            parent = evidence(expressions[pi], expressions[ii], [{'x': x} for x in sorted(pset)])
            child = evidence(expressions[ci], expressions[ii], [{'x': x} for x in sorted(cset)])
            self.anchor = c.identity(decode(parent)['model'])
            with self.subTest(parent=pi, candidate=ci, invariant=ii):
                if safe:
                    report, actual = self.check(parent=parent, candidate=child)
                    self.assertEqual((report['status'], actual), ('verified_change', child))
                else:
                    with self.assertRaisesRegex(InvalidRecord, 'invariant'):
                        self.check(parent=parent, candidate=child)

    def test_cli_and_offline_exact_successor_refusals_and_no_overwrite(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); raw = c.pack_change(self.parent, self.candidate)
            (root/'parent').write_bytes(self.parent); (root/'candidate').write_bytes(self.candidate)
            command = [sys.executable, '-I', '-m', 'stargate']
            packed = subprocess.run(command+['certificate-change-pack', str(root/'parent'), str(root/'candidate'), '--output', str(root/'packet')], capture_output=True)
            self.assertEqual(packed.returncode, 0, packed.stderr)
            self.assertEqual((root/'packet').read_bytes(), raw)
            exported = subprocess.run(command+['certificate-change-unpack', str(root/'packet'), '--output', str(root/'offline')], capture_output=True)
            self.assertEqual(exported.returncode, 0, exported.stderr)
            replay = [sys.executable, '-I', '-S', str(root/'offline/replay.py'), str(root/'offline/change.json'), '--change']
            cli = command+['certificate-change-check', str(root/'packet')]
            args = ['--expect-model', self.anchor, '--expect-checker', c.checker_id()]
            results=[]
            for prefix, target in ((cli, root/'cli'), (replay, root/'replay')):
                result=subprocess.run(prefix+args+['--output',str(target)], capture_output=True)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(target.read_bytes(),self.candidate)
                results.append(json.loads(result.stdout))
                again=subprocess.run(prefix+args+['--output',str(target)],capture_output=True)
                self.assertEqual(again.returncode,1)
                self.assertEqual(target.read_bytes(),self.candidate)
                pending=subprocess.run(prefix+args+['--max-steps','0','--output',str(root/'absent')],capture_output=True)
                self.assertEqual(pending.returncode,3,pending.stderr)
                self.assertFalse((root/'absent').exists())
            self.assertEqual(*results)
            forged = decode(raw); forged['candidate']['states'] = [{'x': False}]
            for file in (root/'packet', root/'offline/change.json'):
                file.write_bytes(canon(forged))
            for prefix in (cli, replay):
                invalid = subprocess.run(prefix+args+['--output', str(root/'forged-child')], capture_output=True)
                self.assertEqual(invalid.returncode, 2, invalid.stderr)
                self.assertFalse((root/'forged-child').exists())
            self.assertFalse(list((root/'offline').rglob('__pycache__')))


if __name__ == '__main__': unittest.main()
