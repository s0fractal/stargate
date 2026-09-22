from stargate import transport
import copy
import itertools
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from stargate import certificate as c, compiler, machine
from stargate.canonical import canon, decode, InvalidRecord


def rule(names, expr):
    return ''.join('fact '+n+': bool\n' for n in sorted(names))+'check '+expr


def model(next='!x', invariant='!x'):
    return dict(language='boolean-machine-1',state=['x'],events=[],initial=[{'x':False}],
        next={'x':rule(['x'],next)},invariant=rule(['x'],invariant),goals=[{'x':True}])


def unsafe(steps=None):
    return dict(kind='unsafe',trace=dict(initial={'x':False},steps=[{'event':{},'state':{'x':True}}] if steps is None else steps))


def exclusion(states=None):
    return dict(kind='unreachable_goal',goal={'x':True},states=[{'x':False}] if states is None else states)


class Refutations(unittest.TestCase):
    def raw(self, m, claim):
        return canon(dict(refutation=1,checker=c.checker_id(),model=m,claim=claim))

    def check(self,m,claim,**kw):
        return c.verify_refutation(self.raw(m,claim),c.identity(m),c.checker_id(),**kw)

    def test_unsafe_path_is_recomputed_without_producer_and_zero_step_allowed(self):
        m=model()
        with patch.object(compiler,'compile_source',side_effect=AssertionError('compiler')), \
                patch.object(machine,'verify',side_effect=AssertionError('BFS')):
            report=self.check(m,unsafe())
        self.assertEqual((report['status'],report['checked_steps'],report['endpoint'],c.exit_code(report)),
                         ('verified_refutation',1,{'x':True},4))
        report=self.check(model(invariant='false'),unsafe([]),max_steps=0)
        self.assertEqual((report['status'],report['checked_steps']),('verified_refutation',0))
        self.assertNotIn('admitted',report);self.assertNotIn('successor',report)
        self.assertEqual(len(c.SOURCES),5)

    def test_unsafe_initial_transition_and_endpoint_each_required(self):
        claim=unsafe([]);claim['trace']['initial']={'x':True}
        with self.assertRaisesRegex(InvalidRecord,'initial'):self.check(model(next='x'),claim)
        claim=unsafe();claim['trace']['steps'][0]['state']={'x':False}
        with self.assertRaisesRegex(InvalidRecord,'transition'):self.check(model(),claim)
        with self.assertRaisesRegex(InvalidRecord,'endpoint'):self.check(model(invariant='true'),unsafe())
        with self.assertRaisesRegex(InvalidRecord,'endpoint'):self.check(model(),unsafe([]))

    def test_exclusion_is_inductive_not_a_search_claim_and_need_not_be_safe(self):
        report=self.check(model(next='x',invariant='false'),exclusion())
        self.assertEqual((report['status'],report['checked_steps'],report['goal']),('verified_refutation',1,{'x':True}))
        omitted=dict(language='boolean-machine-1',state=['x','y'],events=[],initial=[{'x':True,'y':False}],
            next={'x':rule(['x','y'],'x'),'y':rule(['x','y'],'x')},invariant=rule(['x','y'],'true'),goals=[{'x':True,'y':True}])
        claim=dict(kind='unreachable_goal',goal={'x':True,'y':True},states=[{'x':False,'y':False}])
        with self.assertRaisesRegex(InvalidRecord,'initial'):
            self.check(omitted,claim)
        with self.assertRaisesRegex(InvalidRecord,'contains the goal'):
            self.check(model(next='!x'),exclusion([{'x':False},{'x':True}]))
        with self.assertRaisesRegex(InvalidRecord,'closed'):
            self.check(model(next='!x'),exclusion())
        m=model(next='x');m['goals']=[]
        with self.assertRaisesRegex(InvalidRecord,'required goal'):self.check(m,exclusion())

    def test_quota_checker_anchor_and_coverage_never_become_refutation(self):
        for m,claim in ((model(),unsafe()),(model(next='x'),exclusion())):
            report=self.check(m,claim,max_steps=0)
            self.assertEqual((report['status'],report['checked_steps'],c.exit_code(report)),('incomplete',0,3))
            with self.assertRaisesRegex(InvalidRecord,'anchor'):
                c.verify_refutation(self.raw(m,claim),'0'*64,c.checker_id())
            raw=decode(self.raw(m,claim));raw['checker']='0'*64
            with patch.object(c,'_model',wraps=c._model) as parsed:
                report=c.verify_refutation(canon(raw),c.identity(m),c.checker_id())
                self.assertFalse(any(call.kwargs['programs'] for call in parsed.call_args_list))
            self.assertEqual(report['status'],'checker_unavailable')
        # A faulty event enumerator cannot establish closure from no events.
        with patch.object(c.itertools,'product',return_value=[]):
            report=self.check(model(next='x'),exclusion())
            self.assertEqual((report['status'],c.exit_code(report)),('checker_error',1))
        m=model(next='x');m['events']=['e'];m['next']['x']=rule(['x','e'],'x')
        with patch.object(c.itertools,'product',return_value=[(False,), (False,)]):
            self.assertEqual(self.check(m,exclusion())['status'],'checker_error')
        with patch.object(c,'verify_refutation',return_value={'status':'checker_error'}):
            with self.assertRaises(c.CheckerError):c.create_refutation(model(),unsafe())

    def test_exhaustive_one_bit_event_models_against_direct_tables(self):
        assignments=list(itertools.product((False,True),repeat=2)) # x,e
        invariants=[('false',(False,False)),('x',(False,True)),('!x',(True,False)),('true',(True,True))]
        for table in itertools.product((False,True),repeat=4):
            terms=['('+' && '.join(n if b else '!'+n for n,b in zip(('x','e'),bits))+')'
                   for bits,value in zip(assignments,table) if value]
            for expr,truth in invariants:
                m=model(invariant=expr);m['events']=['e'];m['next']={'x':rule(['e','x'],' || '.join(terms) or 'false')}
                for length in range(3):
                    for events in itertools.product((False,True),repeat=length):
                        state=False;steps=[]
                        for event in events:
                            state=table[2*int(state)+int(event)]
                            steps.append({'event':{'e':event},'state':{'x':state}})
                        if truth[state]:
                            with self.assertRaisesRegex(InvalidRecord,'endpoint'):self.check(m,unsafe(steps))
                        else:self.assertEqual(self.check(m,unsafe(steps))['status'],'verified_refutation')
                for values in ((False,),(True,),(False,True)):
                    valid=False in values and True not in values and all(table[2*int(x)+int(e)] in values for x in values for e in (False,True))
                    claim=exclusion([{'x':v} for v in values])
                    if valid:self.assertEqual(self.check(m,claim)['status'],'verified_refutation')
                    else:
                        with self.assertRaises(InvalidRecord):self.check(m,claim)

    def test_synchronous_multibit_updates_use_old_state(self):
        m=dict(language='boolean-machine-1',state=['x','y'],events=[],initial=[{'x':False,'y':True}],
            next={'x':rule(['x','y'],'y'),'y':rule(['x','y'],'x')},
            invariant=rule(['x','y'],'!x'),goals=[])
        claim=dict(kind='unsafe',trace=dict(initial={'x':False,'y':True},steps=[{'event':{},'state':{'x':True,'y':False}}]))
        self.assertEqual(self.check(m,claim)['endpoint'],{'x':True,'y':False})
        claim['trace']['steps'][0]['state']['y']=True
        with self.assertRaisesRegex(InvalidRecord,'transition'):self.check(m,claim)

    def test_structure_and_inert_unpack(self):
        raw=self.raw(model(),unsafe())
        for field,value in (('refutation',True),('claim',None),('claim',{'kind':'unknown'})):
            doc=decode(raw);doc[field]=value
            with self.assertRaises(InvalidRecord):c.inspect_refutation(canon(doc))
        with patch.object(c,'verify_refutation',side_effect=AssertionError('must not execute')):
            with tempfile.TemporaryDirectory() as tmp:
                report=transport.unpack_certificate(raw,Path(tmp)/'out',license_text='test')
                self.assertEqual(report['status'],'unchecked_refutation')
                self.assertEqual((Path(tmp)/'out/refutation.json').read_bytes(),raw)

    def test_cli_creation_offline_and_invalid_data_are_distinct(self):
        for m,claim in ((model(),unsafe()),(model(next='x'),exclusion())):
            with self.subTest(kind=claim['kind']),tempfile.TemporaryDirectory() as tmp:
                root=Path(tmp);(root/'model').write_bytes(canon(m));(root/'claim').write_bytes(canon(claim))
                cmd=[sys.executable,'-I','-m','stargate']
                create=cmd+['refutation-create',str(root/'model'),str(root/'claim'),'--output',str(root/'proof')]
                result=subprocess.run(create,capture_output=True)
                self.assertEqual(result.returncode,4,result.stderr)
                self.assertEqual((root/'proof').read_bytes(),self.raw(m,claim))
                again=subprocess.run(create,capture_output=True);self.assertEqual(again.returncode,1)
                result=subprocess.run(cmd+['unpack', '--expect-kind', 'evidence',str(root/'proof'),'--output',str(root/'offline')],capture_output=True)
                self.assertEqual(result.returncode,0,result.stderr)
                args=['--expect-model',c.identity(m),'--expect-checker',c.checker_id()]
                cli=cmd+['refutation-check',str(root/'proof')]
                offline=[sys.executable,'-I','-S',str(root/'offline/replay.py'),str(root/'offline/refutation.json'),'--refutation']
                reports=[]
                for prefix in (cli,offline):
                    result=subprocess.run(prefix+args,capture_output=True)
                    self.assertEqual(result.returncode,4,result.stderr);reports.append(json.loads(result.stdout))
                    pending=subprocess.run(prefix+args+['--max-steps','0'],capture_output=True)
                    self.assertEqual(pending.returncode,3,pending.stderr)
                    wrong=subprocess.run(prefix+['--expect-model','0'*64,'--expect-checker',c.checker_id()],capture_output=True)
                    self.assertEqual(wrong.returncode,2,wrong.stderr)
                self.assertEqual(*reports)
                bad=subprocess.run(offline+args+['--output',str(root/'no')],capture_output=True)
                self.assertEqual(bad.returncode,2);self.assertFalse((root/'no').exists())
                self.assertFalse(list((root/'offline').rglob('__pycache__')))
                # A false endpoint / non-closed set must not be published by authoring.
                m['next']['x']=rule(['x'],'x' if claim['kind']=='unsafe' else '!x')
                (root/'model').write_bytes(canon(m));(root/'proof').unlink()
                result=subprocess.run(create,capture_output=True)
                self.assertEqual(result.returncode,2,result.stderr);self.assertFalse((root/'proof').exists())


if __name__=='__main__':unittest.main()
