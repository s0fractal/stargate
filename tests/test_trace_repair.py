import importlib.util
import itertools
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
from stargate import certificate as c, evidence as e, search, machine, lab, boolean, transport
from stargate.canonical import canon, decode

ROOT=Path(__file__).resolve().parents[1]


def peterson():
    spec=importlib.util.spec_from_file_location('peterson',ROOT/'examples/peterson_repair.py')
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    return machine.create(module.model(False))


def one():
    return machine.create(dict(state=['x'],events=[],initial=[{'x':False}],next={'x':'fact x: bool\ncheck !x'},
        invariant='fact x: bool\ncheck !x',goals=[],max_atp=1000))


def run(raw,**kw):return e.repair_search(raw,lab.identity(raw),strategy='trace',**kw)


class TraceRepair(unittest.TestCase):
    def test_peterson_repaired_at_one_candidate_budget_matches_program_counter_oracle(self):
        raw=peterson()
        old,out=e.repair_search(raw,lab.identity(raw),max_candidates=1)
        self.assertEqual((old['status'],out),('search_incomplete',None))
        with patch.object(e,'produce',wraps=e.produce) as calls:
            result,packet=run(raw,max_candidates=1)
        self.assertEqual((result['status'],result['attempted'],result['producer_calls'],result['trace_checks']),('found',1,2,1))
        self.assertEqual(calls.call_count,2);self.assertEqual(result['rule_order'][0],'t')
        self.assertEqual(result['repair_checks'],1)
        candidate=decode(packet)['candidate'];model=candidate['model']
        original=c.model_from_machine(machine.inspect(raw))
        self.assertEqual({k:v for k,v in model.items() if k!='next'},{k:v for k,v in original.items() if k!='next'})
        self.assertEqual([n for n in model['state'] if model['next'][n]!=original['next'][n]],['t'])
        def bits(state):
            a,b,t=state
            return dict(a0=bool(a&1),a1=bool(a&2),b0=bool(b&1),b1=bool(b&2),t=bool(t))
        def oracle(state,event):
            a,b,t=state;pcs=[a,b];old=pcs[event]
            if old==0:pcs[event]=1
            elif old==1:pcs[event]=2;t=1-event
            elif old==2:pcs[event]=3 if pcs[1-event]==0 or t==event else 2
            else:pcs[event]=0
            return (*pcs,t)
        names=sorted(model['state']+model['events'])
        codes={n:boolean.program(source,names,allow_unused=True) for n,source in model['next'].items()}
        for a,b,t,event in itertools.product(range(4),range(4),range(2),range(2)):
            actual={n:boolean.evaluate(code,dict(bits((a,b,t)),s=bool(event))) for n,code in codes.items()}
            self.assertEqual(actual,bits(oracle((a,b,t),event)))
        seen={(0,0,0)};queue=list(seen)
        for state in queue:
            for event in (0,1):
                target=oracle(state,event)
                if target not in seen:seen.add(target);queue.append(target)
        self.assertEqual(len(seen),20)
        self.assertEqual({canon(bits(s)) for s in seen},{canon(s) for s in candidate['states']})
        checked,successor=c.verify_repair(packet,c.identity(original),c.checker_id())
        self.assertEqual(checked,result['repair']);self.assertEqual(successor,canon(candidate))

    def test_backward_slice_reaches_earlier_control_and_preserves_every_rule(self):
        raw=peterson();doc=machine.inspect(raw);_,proof=e.produce(raw,lab.identity(raw));trace=decode(proof)['claim']['trace']
        order=search.trace_order(doc,trace)
        self.assertEqual(order,['t','a0','a1','b0','b1'])
        suffix=dict(initial=trace['steps'][-2]['state'],steps=trace['steps'][-1:])
        self.assertNotEqual(search.trace_order(doc,suffix)[0],'t')
        original=list(search.machine_candidates(doc));guided=list(search.repair_candidates(doc,order))
        self.assertEqual(guided[-len(original):],original)
        self.assertLessEqual(len(guided)-len(original),8*len(doc['state']))
        # Renaming every signal cannot make the heuristic depend on a Peterson name.
        import re
        mapping=dict(a0='z0',a1='z1',b0='z2',b1='z3',t='control',s='clock')
        def rename(value):
            if isinstance(value,dict):return {mapping.get(k,k):rename(v) for k,v in value.items()}
            if isinstance(value,list):return [rename(v) for v in value]
            if isinstance(value,str):return re.sub(r'\b(a0|a1|b0|b1|t|s)\b',lambda m:mapping[m[0]],value)
            return value
        config=rename({k:doc[k] for k in ('state','events','initial','next','invariant','goals','max_atp')})
        config['state'].sort();config['events'].sort()
        r,p=run(machine.create(config),max_candidates=1)
        self.assertEqual(r['status'],'found');self.assertEqual(r['rule_order'][0],'control');self.assertIsNotNone(p)

    def test_compound_exchange_is_simultaneous_not_nested_and_keeps_old_neighborhood(self):
        names=['a','b','c','d','x'];decl=''.join('fact '+n+': bool\n' for n in names)
        doc=dict(state=names,events=[],next={n:decl+'check '+n for n in names})
        doc['next']['x']=decl+'check (a && b) || (x && !(c && d))'
        candidates=list(search.repair_candidates(doc,['x','a','b','c','d']))
        self.assertEqual(candidates[0]['x'],decl+'check ((c && d) || (x && !((a && b))))')
        self.assertEqual({n:candidates[0][n] for n in names if n!='x'},{n:doc['next'][n] for n in names if n!='x'})
        self.assertEqual(list(search.machine_candidates(doc)),candidates[1:])

    def test_passed_trace_still_needs_full_proof_and_new_trace_is_learned(self):
        decl='fact a: bool\nfact b: bool\n'
        raw=machine.create(dict(state=['a','b'],events=[],initial=[dict(a=False,b=False)],
            next={'a':decl+'check true','b':decl+'check true'},invariant=decl+'check !b',goals=[],max_atp=1000))
        proposals=[{'a':decl+'check true','b':decl+'check '+b} for b in ('a','a || b','false')]
        with patch.object(search,'repair_candidates',return_value=iter(proposals)),patch.object(e,'produce',wraps=e.produce) as calls:
            r,p=run(raw)
        self.assertEqual((r['status'],r['producer_calls'],r['trace_checks'],r['screened']),('found',3,5,1))
        self.assertEqual(calls.call_count,3)
        self.assertEqual([x['status'] for x in r['attempts']],['verified_refutation','screened','verified_certificate'])
        trace=r['attempts'][1]['witness'];self.assertEqual(len(trace['steps']),2)
        self.assertEqual([s['state'] for s in trace['steps']],[{'a':True,'b':False},{'a':True,'b':True}])
        self.assertEqual(decode(p)['candidate']['model']['next'],proposals[2])

    def test_screen_recomputes_candidate_states_and_checks_its_negative_claim(self):
        raw=one();rules=[{'x':'fact x: bool\ncheck true'},{'x':'fact x: bool\ncheck x'}]
        with patch.object(search,'repair_candidates',return_value=iter(rules)):
            r,p=run(raw)
        self.assertEqual((r['status'],r['screened'],r['producer_calls']),('found',1,2))
        self.assertEqual(decode(p)['candidate']['model']['next'],rules[1])
        # A lying replay using the parent's states for a safe candidate must not screen it.
        _,proof=e.produce(raw,lab.identity(raw));trace=decode(proof)['claim']['trace']
        with patch.object(search,'repair_candidates',return_value=iter(rules[1:])),patch.object(machine,'replay_trace',return_value={'status':'counterexample','trace':trace}):
            r,p=run(raw)
        self.assertEqual((r['status'],p),('checker_error',None))

    def test_partial_screen_is_not_refutation_and_checker_error_stops(self):
        raw=one();rules=[{'x':'fact x: bool\ncheck x'},{'x':'fact x: bool\ncheck false'}]
        original=machine.replay_trace
        calls=0
        def partial(*args):
            nonlocal calls
            calls+=1
            return {'status':'incomplete'} if calls==1 else original(*args)
        with patch.object(search,'repair_candidates',return_value=iter(rules)),patch.object(machine,'replay_trace',partial):r,p=run(raw)
        self.assertEqual((r['status'],r['incomplete_candidates'],r['screened']),('found',1,0));self.assertIsNotNone(p)
        for status,expected in [('incomplete','search_incomplete'),('checker_error','checker_error')]:
            with patch.object(search,'repair_candidates',return_value=iter(rules[:1])),patch.object(machine,'replay_trace',return_value={'status':status}):r,p=run(raw)
            self.assertEqual((r['status'],p),(expected,None))

    def test_cli_peterson_packet_replays_without_search_and_applies(self):
        raw=peterson()
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);world=root/'world.json';world.write_bytes(raw);packet=root/'repair.json'
            proc=subprocess.run([sys.executable,'-I','-m','stargate','repair-search',str(world),'--strategy','trace',
                '--expect-machine',lab.identity(raw),'--max-candidates','1','--output',str(packet)],capture_output=True,text=True)
            self.assertEqual(proc.returncode,0,proc.stderr)
            parent=c.model_from_machine(machine.inspect(raw));proof=decode(packet.read_bytes())
            transport.unpack_certificate(packet.read_bytes(),root/'offline',license_text=lab.LICENSE)
            proc=subprocess.run([sys.executable,'-I','-S',str(root/'offline/replay.py'),str(packet),'--repair',
                '--expect-model',c.identity(parent),'--expect-checker',c.checker_id(),'--output',str(root/'successor')],capture_output=True,text=True)
            self.assertEqual(proc.returncode,0,proc.stderr)
            self.assertEqual((root/'successor').read_bytes(),canon(proof['candidate']))
            repo=root/'models.git';subprocess.run(['git','init','--bare',str(repo)],check=True,capture_output=True)
            def git(*args,data=None):return subprocess.check_output(['git','--git-dir='+str(repo),*args],input=data).strip()
            blob=git('hash-object','-w','--stdin',data=canon(parent))
            tree=git('mktree',data=b'100644 blob '+blob+b'\tmodel.json\n')
            base=git('hash-object','-t','commit','-w','--stdin',data=b'tree '+tree+b'\nauthor Test <test@localhost> 1 +0000\ncommitter Test <test@localhost> 1 +0000\n\nroot\n').decode()
            git('update-ref','refs/heads/main',base)
            from stargate import apply
            r=apply.apply(packet.read_bytes(),repo,'refs/heads/main','model.json',base,c.checker_id())
            self.assertEqual(r['status'],'applied');self.assertEqual(git('show','refs/heads/main:model.json'),canon(proof['candidate']['model']))
            self.assertEqual(git('rev-parse','refs/heads/main^').decode(),base)
