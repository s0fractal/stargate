import itertools
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
from stargate import certificate as c, evidence as e, machine, lab, search, transport
from stargate.canonical import canon,decode,InvalidRecord

ROOT=Path(__file__).resolve().parents[1]


def one(next='!x', invariant='!x', goals=None):
    rule=lambda value:'fact x: bool\ncheck '+value
    return machine.create(dict(state=['x'],events=[],initial=[{'x':False}],
        next={'x':rule(next)},invariant=rule(invariant),goals=goals or [],max_atp=1000))


def run(raw,**kw):return e.repair_search(raw,lab.identity(raw),**kw)


def value(source,x):
    # Independent oracle over generated test expressions, never received source.
    expr=source.split('check ',1)[1].replace('&&',' and ').replace('||',' or ').replace('!',' not ')
    return eval(expr,{'__builtins__':{}},{'x':x,'true':True,'false':False})


def holds(model):
    seen={False};current=False
    while True:
        nxt=value(model['next']['x'],current)
        if nxt in seen:break
        seen.add(nxt);current=nxt
    return all(value(model['invariant'],v) for v in seen) and all(g['x'] in seen for g in model['goals'])


class RepairSearch(unittest.TestCase):
    def test_actual_interlock_generator_finds_guard_repair_with_all_goals(self):
        raw=machine.create(json.loads((ROOT/'examples/interlock.json').read_text()))
        with patch.object(e,'produce',wraps=e.produce) as calls:
            report,packet=run(raw)
        self.assertEqual(report['status'],'found')
        self.assertEqual(report['attempted'],3)
        self.assertEqual(report['producer_calls'],calls.call_count)
        self.assertEqual(report['repair_checks'],1)
        self.assertEqual(e.repair_exit_code(report),0)
        doc=decode(packet);parent=c.model_from_machine(machine.inspect(raw))
        self.assertEqual(doc['refutation']['model'],parent)
        child=doc['candidate']['model']
        self.assertEqual(child['next']['armed'],parent['next']['armed'])
        self.assertEqual(child['next']['open'].split('check ')[1],'(request && armed)')
        self.assertEqual(child['goals'],[{'armed':True,'open':True}])
        # Independent synchronous transition table; no parser or checker helpers.
        def reachable(fixed):
            seen={(False,False)};queue=list(seen)
            for armed,opened in queue:
                for request in (False,True):
                    target=(request,(request and armed) if fixed else (request or armed))
                    if target not in seen:seen.add(target);queue.append(target)
            return seen
        self.assertIn((False,True),reachable(False))
        self.assertEqual(reachable(True),{(False,False),(True,False),(True,True)})
        self.assertEqual({(s['armed'],s['open']) for s in doc['candidate']['states']},reachable(True))
        state=(False,False)
        trace=doc['refutation']['claim']['trace']
        self.assertEqual(trace['initial'],{'armed':False,'open':False})
        for step in trace['steps']:
            request=step['event']['request'];state=(request,request or state[0])
            self.assertEqual(state,(step['state']['armed'],step['state']['open']))
        self.assertEqual(state,(False,True))
        checked,out=c.verify_repair(packet,c.identity(parent),c.checker_id())
        self.assertEqual(checked,report['repair']);self.assertEqual(out,canon(doc['candidate']))

    def test_exhaustive_one_bit_real_neighborhood_matches_independent_oracle(self):
        for expr,inv,goal in itertools.product(('false','x','!x','true'),repeat=3):
            # Map four goal cases onto none, false, true, both.
            goals={'false':[], 'x':[{'x':False}], '!x':[{'x':True}], 'true':[{'x':False},{'x':True}]}[goal]
            raw=one(expr,inv,goals);doc=machine.inspect(raw);parent=c.model_from_machine(doc)
            candidates=[dict(parent,next=r) for r in search.machine_candidates(doc)]
            repair=next((m for m in candidates if holds(m)),None)
            report,packet=run(raw,max_candidates=256)
            with self.subTest(expr=expr,inv=inv,goals=goals):
                expected='not_needed' if holds(parent) else 'found' if repair else 'neighborhood_exhausted'
                self.assertEqual(report['status'],expected)
                self.assertEqual(packet is not None,expected=='found')
                if packet:
                    candidate=decode(packet)['candidate']['model']
                    self.assertFalse(holds(parent));self.assertTrue(holds(candidate))
                    self.assertEqual(candidate,repair)

    def test_parent_faults_and_invalid_limits_stop_before_generation(self):
        for raw,kw,status in ((one('x'),{},'not_needed'),(one(),{'max_edges':0},'incomplete'),
                              (one(),{'max_steps':0},'incomplete')):
            with patch.object(search,'machine_candidates',side_effect=AssertionError('must not generate')):
                report,packet=run(raw,**kw)
            self.assertEqual((report['status'],packet),(status,None))
        for n in (True,0,257):
            with self.assertRaises(InvalidRecord):run(one(),max_candidates=n)
        with self.assertRaises(InvalidRecord):e.repair_search(one(),'0'*64)

    def test_incomplete_candidate_is_skipped_but_never_proves_exhaustion(self):
        raw=one();real=e.produce;calls=0
        def limited(*args,**kw):
            nonlocal calls
            calls+=1
            return ({'status':'incomplete'},None) if calls==2 else real(*args,**kw)
        # Two occurrences of the same valid rule would deduplicate, so use distinct text.
        rules=[{'x':'fact x: bool\ncheck x'},{'x':'fact x: bool\ncheck x && x'}]
        with patch.object(search,'machine_candidates',return_value=iter(rules)),patch.object(e,'produce',limited):
            report,packet=run(raw)
        self.assertEqual((report['status'],report['incomplete_candidates'],report['producer_calls']),('found',1,3))
        self.assertIsNotNone(packet)
        calls=0
        with patch.object(search,'machine_candidates',return_value=iter(rules[:1])),patch.object(e,'produce',limited):
            report,packet=run(raw)
        self.assertEqual((report['status'],packet,e.repair_exit_code(report)),('search_incomplete',None,3))
        with patch.object(search,'machine_candidates',return_value=iter([])):
            report,packet=run(raw)
        self.assertEqual((report['status'],packet,e.repair_exit_code(report)),('neighborhood_exhausted',None,4))
        report,packet=run(raw,max_candidates=1)
        # The first real candidate repairs this one-bit model; interlock needs three.
        self.assertEqual(report['status'],'found')
        interlock=machine.create(json.loads((ROOT/'examples/interlock.json').read_text()))
        report,packet=run(interlock,max_candidates=1)
        self.assertEqual((report['status'],report['reason'],packet),('search_incomplete','candidate_limit',None))

    def test_checker_error_stops_and_forged_positive_proof_never_escapes(self):
        raw=one();real=e.produce
        for fault in ('checker_error','lying_certificate','other_model'):
            calls=0
            def forged(*args,**kw):
                nonlocal calls
                calls+=1
                if calls==1:return real(*args,**kw)
                if fault=='checker_error':return {'status':'checker_error'},None
                report,packet=real(*args,**kw);self.assertEqual(report['status'],'verified_certificate')
                doc=decode(packet)
                if fault=='lying_certificate':doc['states']=[{'x':True}]
                else:doc['model']['next']['x']='fact x: bool\ncheck false'
                return report,canon(doc)
            with self.subTest(fault=fault),patch.object(e,'produce',forged):report,packet=run(raw)
            self.assertEqual((report['status'],packet,e.repair_exit_code(report)),('checker_error',None,1))
            self.assertEqual(calls,2)

    def test_final_repair_verdict_and_successor_both_control_publication(self):
        raw=one()
        rules={'x':'fact x: bool\ncheck x'}
        # Positive control: the producer and real final check accept this candidate.
        with patch.object(search,'machine_candidates',return_value=iter([rules])):
            accepted,packet=run(raw)
        self.assertEqual(accepted['status'],'found')
        self.assertIsNotNone(packet)
        successor=canon(decode(packet)['candidate'])
        for status,output,expected,code in (
            ('incomplete',None,'search_incomplete',3),
            ('checker_error',None,'checker_error',1),
            ('verified_repair',None,'checker_error',1),
            ('incomplete',successor,'search_incomplete',3),
            ('checker_error',successor,'checker_error',1),
        ):
            with self.subTest(status=status,has_successor=output is not None), \
                 patch.object(search,'machine_candidates',return_value=iter([rules])), \
                 patch.object(c,'verify_repair',return_value=({'status':status},output)) as gate:
                report,packet=run(raw)
                self.assertEqual(gate.call_count,1)
                self.assertEqual(report['repair_checks'],1)
                self.assertEqual(report['attempts'][0]['status'],'verified_certificate')
                self.assertIsNone(packet)
                self.assertEqual(report['status'],expected)
                self.assertEqual(e.repair_exit_code(report),code)
                self.assertEqual(report['incomplete_candidates'],int(status=='incomplete'))

    def test_cli_search_existing_replay_and_git_application(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);raw=machine.create(json.loads((ROOT/'examples/interlock.json').read_text()))
            world=root/'world.json';world.write_bytes(raw);packet=root/'repair.json'
            cmd=[sys.executable,'-I','-m','stargate','repair-search',str(world),'--expect-machine',lab.identity(raw),'--output',str(packet)]
            stopped=subprocess.run(cmd+['--max-edges','0'],capture_output=True,text=True)
            self.assertEqual(stopped.returncode,3,stopped.stderr);self.assertFalse(packet.exists())
            done=subprocess.run(cmd,capture_output=True,text=True)
            self.assertEqual(done.returncode,0,done.stderr);self.assertEqual(json.loads(done.stdout)['status'],'found')
            proof=decode(packet.read_bytes());parent=proof['refutation']['model']
            transport.unpack_certificate(packet.read_bytes(),root/'offline',license_text=lab.LICENSE)
            replay=subprocess.run([sys.executable,'-I','-S',str(root/'offline/replay.py'),str(packet),
                '--repair','--expect-model',c.identity(parent),'--expect-checker',c.checker_id(),
                '--output',str(root/'successor.json')],capture_output=True,text=True)
            self.assertEqual(replay.returncode,0,replay.stderr)
            self.assertEqual((root/'successor.json').read_bytes(),canon(proof['candidate']))
            repo=root/'models.git'
            subprocess.run(['git','init','--bare',str(repo)],check=True,capture_output=True)
            def git(*args,data=None):return subprocess.check_output(['git','--git-dir='+str(repo),*args],input=data).strip()
            blob=git('hash-object','-w','--stdin',data=canon(parent))
            tree=git('mktree',data=b'100644 blob '+blob+b'\tmodel.json\n')
            base=git('hash-object','-t','commit','-w','--stdin',data=b'tree '+tree+b'\nauthor Test <test@localhost> 1 +0000\ncommitter Test <test@localhost> 1 +0000\n\nroot\n').decode()
            git('update-ref','refs/heads/main',base)
            applied=subprocess.run([sys.executable,'-I','-m','stargate','model-apply',str(packet),
                '--repository',str(repo),'--ref','refs/heads/main','--model-path','model.json',
                '--expect-commit',base,'--expect-checker',c.checker_id()],capture_output=True,text=True)
            self.assertEqual(applied.returncode,0,applied.stderr)
            self.assertEqual(git('show','refs/heads/main:model.json'),canon(proof['candidate']['model']))
            self.assertEqual(git('rev-parse','refs/heads/main^').decode(),base)
