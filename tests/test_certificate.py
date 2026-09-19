import copy
import itertools
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from stargate import certificate as c, machine, lab
from stargate.canonical import canon, decode, InvalidRecord


def rule(names, expression):
    return ''.join('fact '+n+': bool\n' for n in sorted(names))+'check '+expression


class Certificates(unittest.TestCase):
    def setUp(self):
        self.model = dict(language='boolean-machine-1', state=['x'], events=['e'],
            initial=[{'x': False}], next={'x': rule(['x', 'e'], 'e')},
            invariant=rule(['x'], 'true'), goals=[{'x': True}])
        self.states = [{'x': False}, {'x': True}]
        self.paths = [{'goal': {'x': True}, 'trace': {'initial': {'x': False},
                       'steps': [{'event': {'e': True}, 'state': {'x': True}}]}}]

    def raw(self, model=None, states=None, paths=None):
        return canon(dict(certificate=1, checker=c.checker_id(),
            model=self.model if model is None else model,
            states=self.states if states is None else states,
            paths=self.paths if paths is None else paths))

    def check(self, raw=None, **kwargs):
        return c.verify(self.raw() if raw is None else raw, c.identity(self.model), c.checker_id(), **kwargs)

    def test_inductive_set_and_goal_path_verified_without_compiler_or_producer(self):
        with patch.object(machine, 'verify', side_effect=AssertionError('producer called')):
            report = self.check()
        self.assertEqual(report['status'], 'verified_certificate')
        self.assertEqual((report['checked_states'], report['checked_edges'], report['checked_path_steps']), (2, 4, 1))
        self.assertEqual(report['model_id'], c.identity(self.model))
        self.assertEqual(report['certificate_id'], c.identity(decode(self.raw())))
        self.assertNotIn('admitted', report)
        self.assertNotIn('atp_spent', report)
        self.assertNotIn('compiler.py', c.SOURCES)
        self.assertNotIn('machine.py', c.SOURCES)
        self.assertNotIn('kernel.py', c.SOURCES)

    def test_creation_never_relabels_checker_failure_as_invalid_evidence(self):
        with patch.object(c, 'verify', return_value={'status': 'checker_error'}):
            with self.assertRaises(c.CheckerError): c.create(self.model, self.states, self.paths)
        with patch.object(c, 'verify', return_value={'status': 'incomplete'}):
            with self.assertRaises(c.CheckerError): c.create(self.model, self.states, self.paths)

    def test_missing_initial_state_cannot_certify_a_safe_unrelated_component(self):
        self.model['next']['x'] = rule(['x', 'e'], 'x')
        self.model['goals'] = []
        with self.assertRaisesRegex(InvalidRecord, 'omits an initial'):
            self.check(self.raw(states=[{'x': True}], paths=[]))

    def test_missing_successor_and_event_branch_are_rejected(self):
        self.model['goals'] = []
        with self.assertRaisesRegex(InvalidRecord, 'not closed'):
            self.check(self.raw(states=[{'x': False}], paths=[]))
        # A broken event enumerator cannot turn partial closure into success.
        with patch.object(c.itertools, 'product', return_value=iter([(False,)])):
            report = self.check(self.raw(paths=[]))
        self.assertEqual(report['status'], 'checker_error')
        self.assertEqual(report['reason'], 'closure coverage mismatch')

    def test_bad_invariant_is_invalid_certificate_not_a_model_verdict(self):
        self.model['invariant'] = rule(['x'], '!x')
        with self.assertRaisesRegex(InvalidRecord, 'violates invariant'):
            self.check()

    def test_safe_overapproximation_is_allowed_but_not_false_reachability(self):
        self.model['next']['x'] = rule(['x', 'e'], 'x')
        self.model['goals'] = []
        self.assertEqual(self.check(self.raw(paths=[]))['status'], 'verified_certificate')
        self.model['goals'] = [{'x': True}]
        # True is in the closed certificate set but not reachable from false.
        with self.assertRaisesRegex(InvalidRecord, 'does not reproduce'):
            self.check()

    def test_all_goal_path_obligations_are_checked(self):
        variants = []
        missing = decode(self.raw()); missing['paths'] = []; variants.append((missing, 'one path'))
        bad_start = decode(self.raw()); bad_start['paths'][0]['trace']['initial'] = {'x': True}
        bad_start['paths'][0]['trace']['steps'] = []; variants.append((bad_start, 'initial state'))
        bad_step = decode(self.raw()); bad_step['paths'][0]['trace']['steps'][0]['event']['e'] = False
        variants.append((bad_step, 'does not reproduce'))
        bad_end = decode(self.raw()); bad_end['paths'][0]['trace']['steps'] = []
        variants.append((bad_end, 'does not reach'))
        for doc, reason in variants:
            with self.subTest(reason=reason), self.assertRaisesRegex(InvalidRecord, reason):
                self.check(canon(doc))

    def test_quota_never_turns_partial_closure_or_partial_goal_path_into_success(self):
        for quota in range(5):
            with self.subTest(quota=quota):
                report = self.check(max_steps=quota)
                self.assertEqual(report['status'], 'incomplete')
                self.assertEqual(report['checked_edges']+report['checked_path_steps'], quota)
                self.assertEqual(c.exit_code(report), 3)
        self.assertEqual(self.check(max_steps=5)['status'], 'verified_certificate')
        # The second step of a goal path also consumes quota, even on a cycle.
        paths = copy.deepcopy(self.paths)
        paths[0]['trace']['steps'].insert(0, {'event': {'e': False}, 'state': {'x': False}})
        report = self.check(self.raw(paths=paths), max_steps=5)
        self.assertEqual((report['status'], report['checked_path_steps']), ('incomplete', 1))
        self.assertEqual(self.check(self.raw(paths=paths), max_steps=6)['status'], 'verified_certificate')

    def test_model_anchor_prevents_weaker_contract_and_checker_pin_precedes_grammar(self):
        doc = decode(self.raw()); doc['model']['invariant'] = rule(['x'], 'x || !x')
        with self.assertRaisesRegex(InvalidRecord, 'recipient anchor'): self.check(canon(doc))
        doc = decode(self.raw()); doc['model']['invariant'] = 'foreign syntax'
        doc['checker'] = '0'*64
        with patch.object(c.boolean, 'program', side_effect=AssertionError('must not interpret')):
            report = c.verify(canon(doc), c.identity(doc['model']), c.checker_id())
        self.assertEqual(report['status'], 'checker_unavailable')
        self.assertEqual(c.verify(self.raw(), c.identity(self.model), '0'*64)['status'], 'checker_unavailable')

    def test_structure_duplicate_sets_extra_claims_and_non_boolean_values_refuse(self):
        variants = []
        for key, value in [('verdict', 'safe'), ('sources', {'bad.py': 'raise Exception()'})]:
            doc=decode(self.raw());doc[key]=value;variants.append(doc)
        for field in ('states',):
            doc=decode(self.raw());doc[field].append(doc[field][0]);variants.append(doc)
        doc=decode(self.raw());doc['states'][0]['x']=0;variants.append(doc)
        doc=decode(self.raw());doc['paths'][0]['trace']['steps']*=64;variants.append(doc)
        doc=decode(self.raw());doc['model']['initial']*=2;variants.append(doc)
        doc=decode(self.raw());doc['model']['goals']*=2;variants.append(doc)
        for doc in variants:
            with self.subTest(doc=str(doc)[:100]), self.assertRaises(InvalidRecord): self.check(canon(doc))

    def test_synchronous_bits_read_old_state(self):
        model=dict(language='boolean-machine-1',state=['a','b'],events=[], initial=[{'a':False,'b':True}],
            next={'a':rule(['a','b'],'b'),'b':rule(['a','b'],'a')},
            invariant=rule(['a','b'],'!(a && b)'),goals=[{'a':True,'b':False}])
        states=[{'a':False,'b':True},{'a':True,'b':False}]
        paths=[dict(goal=model['goals'][0],trace=dict(initial=model['initial'][0],steps=[dict(event={},state=states[1])]))]
        raw=c.create(model,states,paths)
        report=c.verify(raw,c.identity(model),c.checker_id())
        self.assertEqual(report['status'],'verified_certificate')
        self.assertEqual(report['checked_edges'],2)

    def test_multiple_initial_states_and_zero_step_goals(self):
        self.model['initial']=self.states
        self.model['goals']=self.states
        paths=[dict(goal=s,trace=dict(initial=s,steps=[])) for s in self.states]
        report=self.check(self.raw(paths=paths))
        self.assertEqual((report['status'],report['checked_path_steps']),('verified_certificate',0))

    def test_all_one_bit_transition_tables_and_invariants_against_independent_truth(self):
        for outputs in itertools.product((False,True),repeat=4):
            terms=[('e' if e else '!e')+' && '+('x' if x else '!x')
                   for (e,x),value in zip(itertools.product((False,True),repeat=2),outputs) if value]
            expression=' || '.join('('+t+')' for t in terms) or 'false'
            for values in itertools.product((False,True),repeat=2):
                inv='true' if all(values) else 'false' if not any(values) else 'x' if values[1] else '!x'
                reached={False};pending=[False]
                while pending:
                    old=pending.pop()
                    for event in (False,True):
                        target=outputs[2*int(event)+int(old)]
                        if target not in reached:reached.add(target);pending.append(target)
                model=copy.deepcopy(self.model);model['next']['x']=rule(['e','x'],expression)
                model['invariant']=rule(['x'],inv);model['goals']=[]
                raw=self.raw(model=model,states=[{'x':v} for v in sorted(reached)],paths=[])
                with self.subTest(outputs=outputs,invariant=values):
                    if all(values[int(v)] for v in reached):
                        self.assertEqual(c.verify(raw,c.identity(model),c.checker_id())['status'],'verified_certificate')
                    else:
                        with self.assertRaisesRegex(InvalidRecord,'violates invariant'):
                            c.verify(raw,c.identity(model),c.checker_id())

    def test_cli_production_and_offline_check_need_no_producer_modules(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            spec={k:self.model[k] for k in c.MODEL_FIELDS};spec['max_atp']=1000
            raw=machine.create(spec);(root/'machine.json').write_bytes(raw)
            command=[sys.executable,'-I','-m','stargate']
            produce=subprocess.run(command+['machine-certify',str(root/'machine.json'),'--expect-machine',lab.identity(raw),
                '--output',str(root/'cert.json')],capture_output=True,text=True,cwd='/')
            self.assertEqual(produce.returncode,0,produce.stderr)
            packet=(root/'cert.json').read_bytes();self.assertEqual(decode(packet)['model'],self.model)
            report=json.loads(produce.stdout);self.assertEqual(report['status'],'verified_certificate')
            c.unpack(packet,root/'offline',license_text=lab.LICENSE)
            self.assertEqual(set(json.loads((root/'offline/checker.json').read_bytes())),set(c.SOURCES))
            marker=root/'executed'
            for name in ('machine.py','compiler.py','sitecustomize.py','tempfile.py'):
                (root/'offline'/name).write_text('open('+repr(str(marker))+',"w").write("bad")')
            args=[str(root/'cert.json'),'--expect-model',c.identity(self.model),'--expect-checker',c.checker_id()]
            offline=subprocess.run([sys.executable,'-I','-S',str(root/'offline/replay.py'),*args],capture_output=True,text=True,cwd='/')
            self.assertEqual(offline.returncode,0,offline.stderr)
            self.assertEqual(json.loads(offline.stdout),report)
            self.assertFalse(marker.exists());self.assertFalse(list((root/'offline').rglob('__pycache__')))
            with self.assertRaises(FileExistsError):c.unpack(packet,root/'offline',license_text=lab.LICENSE)
            altered = decode(packet); altered['paths'][0]['trace']['steps'] = []
            (root/'forged.json').write_bytes(canon(altered))
            wrong_anchor = '0'*64
            for filename, anchor, quota, expected in [
                ('cert.json', wrong_anchor, c.MAX_STEPS, 2),
                ('forged.json', c.identity(self.model), c.MAX_STEPS, 2),
                ('cert.json', c.identity(self.model), 0, 3),
                ('missing.json', c.identity(self.model), c.MAX_STEPS, 3)]:
                argv=[str(root/filename),'--expect-model',anchor,'--expect-checker',c.checker_id(),'--max-steps',str(quota)]
                for prefix in (command+['certificate-check'], [sys.executable,'-I','-S',str(root/'offline/replay.py')]):
                    outcome=subprocess.run(prefix+argv,capture_output=True,text=True,cwd='/')
                    self.assertEqual(outcome.returncode,expected,(outcome.stdout,outcome.stderr))
                    self.assertNotIn('Traceback',outcome.stderr)
            checker_file=root/'offline/checker.json'
            original=checker_file.read_bytes()
            changed=json.loads(original);changed['boolean.py']+='\n# changed\n';checker_file.write_bytes(canon(changed))
            outcome=subprocess.run([sys.executable,'-I','-S',str(root/'offline/replay.py'),*args],capture_output=True,text=True)
            self.assertEqual(outcome.returncode,3,outcome.stderr)
            self.assertEqual(json.loads(outcome.stdout)['status'],'checker_unavailable')
            checker_file.unlink()
            outcome=subprocess.run([sys.executable,'-I','-S',str(root/'offline/replay.py'),*args],capture_output=True,text=True)
            self.assertEqual(outcome.returncode,3,outcome.stderr)
            self.assertNotIn('Traceback',outcome.stderr)
            checker_file.write_bytes(original)
            # No certificate is produced from an unfinished producer run.
            refused=subprocess.run(command+['machine-certify',str(root/'machine.json'),'--expect-machine',lab.identity(raw),
                '--max-edges','0','--output',str(root/'absent.json')],capture_output=True,text=True,cwd='/')
            self.assertEqual(refused.returncode,3,refused.stderr)
            self.assertFalse((root/'absent.json').exists())


if __name__ == '__main__':unittest.main()
