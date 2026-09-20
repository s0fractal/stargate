import copy
import itertools
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from stargate import certificate as c, evidence as e, machine, lab
from stargate.canonical import canon,decode,InvalidRecord


def rule(expr):return 'fact x: bool\ncheck '+expr


def world(next='!x',invariant='true',goals=None):
    return machine.create(dict(state=['x'],events=[],initial=[{'x':False}],
        next={'x':rule(next)},invariant=rule(invariant),max_atp=1000,
        goals=[{'x':True}] if goals is None else goals))


class Evidence(unittest.TestCase):
    def produce(self,raw,**kw):return e.produce(raw,lab.identity(raw),**kw)

    def test_all_three_complete_outcomes_recheck_as_standalone_data(self):
        for raw,kind,status in ((world(),'certificate','verified_certificate'),
            (world(invariant='!x'),'refutation','verified_refutation'),
            (world(next='x'),'refutation','verified_refutation')):
            with self.subTest(status=status):
                report,packet=self.produce(raw)
                self.assertEqual(report['status'],status)
                self.assertIsNotNone(packet)
                self.assertEqual(e.kind(packet),kind)
                expected_model=c.model_from_machine(machine.inspect(raw))
                self.assertEqual(decode(packet)['model'],expected_model)
                checked=e.verify(packet,c.identity(expected_model),c.checker_id())
                self.assertEqual(report['check'],checked)
                self.assertEqual(report['machine_id'],lab.identity(raw))
                self.assertEqual(report['model_id'],c.identity(expected_model))
                self.assertNotEqual(report['machine_id'],report['model_id'])
                self.assertNotIn('sources',decode(packet))
        self.assertNotIn('evidence.py',c.SOURCES)
        self.assertNotIn('evidence.py',lab.RUNTIME)

    def test_false_producer_verdicts_are_checker_errors_never_published(self):
        safe=world();bad=world(invariant='!x');stuck=world(next='x')
        safe_report=machine.verify(safe,lab.identity(safe))
        bad_report=machine.verify(bad,lab.identity(bad))
        stuck_report=machine.verify(stuck,lab.identity(stuck))
        for raw,lie in ((bad,safe_report),(safe,bad_report),(safe,stuck_report)):
            with self.subTest(lie=lie['status']),patch.object(e.machine,'verify',return_value=lie):
                report,packet=self.produce(raw)
                self.assertEqual((report['status'],report['phase'],packet),('checker_error','evidence',None))
        for lie in (None,{}, {'status':'unknown'},{'status':'established'}, {'status':'goal_unreachable','unreached_goals':[]}):
            with self.subTest(lie=lie),patch.object(e.machine,'verify',return_value=lie):
                report,packet=self.produce(safe)
                self.assertEqual((report['status'],packet),('checker_error',None))

    def test_input_model_anchor_is_not_taken_from_producer(self):
        raw=world();report=machine.verify(raw,lab.identity(raw))
        report['model']=c.model_from_machine(machine.inspect(world(invariant='false')))
        report['model_id']='0'*64;report['machine_id']='0'*64
        with patch.object(e.machine,'verify',return_value=report):
            result,packet=self.produce(raw)
        self.assertEqual(result['status'],'verified_certificate')
        self.assertIsNotNone(packet)
        self.assertEqual(decode(packet)['model'],c.model_from_machine(machine.inspect(raw)))
        self.assertEqual(result['machine_id'],lab.identity(raw))
        with patch.object(e.machine,'verify',side_effect=AssertionError('must not produce')):
            with self.assertRaisesRegex(InvalidRecord,'anchor'):e.produce(raw,'0'*64)
            with self.assertRaises(InvalidRecord):self.produce(raw,max_steps=True)

    def test_both_quota_phases_and_producer_faults_yield_no_packet(self):
        for options,phase in (({'max_edges':0},'producer'),({'max_steps':0},'evidence')):
            report,packet=self.produce(world(),**options)
            self.assertEqual((report['status'],report['phase'],packet),('incomplete',phase,None))
            self.assertEqual(c.exit_code(report),3)
        for status in ('incomplete','checker_error'):
            report=machine.verify(world(),lab.identity(world()));report['status']=status
            with patch.object(e.machine,'verify',return_value=report),patch.object(e,'verify',side_effect=AssertionError('must not check partial evidence')):
                result,packet=self.produce(world())
                self.assertEqual((result['status'],packet),(status,None))
        for status in ('incomplete','checker_unavailable','checker_error','unexpected','verified_refutation'):
            with patch.object(e,'verify',return_value={'status':status}):
                result,packet=self.produce(world())
                self.assertEqual(result['status'], 'checker_error' if status in ('unexpected','verified_refutation') else status)
                self.assertIsNone(packet)

    def test_exhaustive_one_bit_models_match_independent_reachability(self):
        expressions=['false','x','!x','true']
        tables=[(False,False),(False,True),(True,False),(True,True)]
        for ni,ii,goal in itertools.product(range(4),range(4),(False,True)):
            raw=world(expressions[ni],expressions[ii],[{'x':goal}])
            seen={False};state=False
            while tables[ni][state] not in seen:
                state=tables[ni][state];seen.add(state)
            expected='unsafe' if any(not tables[ii][s] for s in seen) else 'unreachable_goal' if goal not in seen else 'certificate'
            report,packet=self.produce(raw)
            doc=decode(packet)
            self.assertEqual('certificate' if e.kind(packet)=='certificate' else doc['claim']['kind'],expected)
            self.assertEqual(report['status'],'verified_certificate' if expected=='certificate' else 'verified_refutation')

    def test_dispatch_never_accepts_ambiguous_or_other_packet_types(self):
        raw=world();_,packet=self.produce(raw)
        doc=decode(packet);doc['refutation']=1
        for value in (doc,{},None,{'certificate_history':1}, {'certificate':True}):
            with self.subTest(value=value),self.assertRaises(InvalidRecord):e.kind(canon(value))
        with self.assertRaises(InvalidRecord):e.verify(packet,'0'*64,c.checker_id())
        report=e.verify(packet,c.identity(decode(packet)['model']),'0'*64)
        self.assertEqual(report['status'],'checker_unavailable')

    def test_cli_production_check_export_and_offline_parity(self):
        cases=[(world(),0),(world(invariant='!x'),4),(world(next='x'),4)]
        for raw,exitcode in cases:
            with self.subTest(exitcode=exitcode),tempfile.TemporaryDirectory() as tmp:
                root=Path(tmp);(root/'machine').write_bytes(raw)
                cmd=[sys.executable,'-I','-m','stargate']
                args=['machine-evidence',str(root/'machine'),'--expect-machine',lab.identity(raw),'--output',str(root/'proof')]
                for flag in ('--max-edges','--max-steps'):
                    pending=subprocess.run(cmd+args+[flag,'0'],capture_output=True)
                    self.assertEqual(pending.returncode,3,pending.stderr);self.assertFalse((root/'proof').exists())
                produced=subprocess.run(cmd+args,capture_output=True)
                self.assertEqual(produced.returncode,exitcode,produced.stderr)
                report=json.loads(produced.stdout);saved=(root/'proof').read_bytes()
                repeat=subprocess.run(cmd+args,capture_output=True)
                self.assertEqual(repeat.returncode,1);self.assertEqual((root/'proof').read_bytes(),saved)
                pins=['--expect-model',report['model_id'],'--expect-checker',c.checker_id()]
                checked=subprocess.run(cmd+['evidence-check',str(root/'proof'),*pins],capture_output=True)
                self.assertEqual(checked.returncode,exitcode,checked.stderr)
                self.assertEqual(json.loads(checked.stdout),report['check'])
                exported=subprocess.run(cmd+['unpack', '--expect-kind', 'evidence',str(root/'proof'),'--output',str(root/'offline')],capture_output=True)
                self.assertEqual(exported.returncode,0,exported.stderr)
                kind=e.kind(saved);name='certificate.json' if kind=='certificate' else 'refutation.json'
                offline=[sys.executable,'-I','-S',str(root/'offline/replay.py'),str(root/'offline'/name),*pins]
                if kind=='refutation':offline+=['--refutation']
                replay=subprocess.run(offline,capture_output=True)
                self.assertEqual(replay.returncode,exitcode,replay.stderr)
                self.assertEqual(json.loads(replay.stdout),report['check'])
                self.assertFalse(list((root/'offline').rglob('__pycache__')))


if __name__=='__main__':unittest.main()
