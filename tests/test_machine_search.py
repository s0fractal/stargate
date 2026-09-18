import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from contextlib import redirect_stdout, redirect_stderr

from stargate import machine, search, lab, cli, compiler, boolean, kernel
from stargate.canonical import canon, decode, InvalidRecord
from test_machine import wpl
from test_machine_change import parent, proposal


def fixture():
    raw = parent(); doc = decode(raw)
    unsafe = proposal(raw, True)['next']
    # Different syntax, same unsafe event-driven path.
    second = dict(unsafe, a=wpl(['a','b'], '!!b && (a || !a)'))
    safe = proposal(raw)['next']
    bad = canon(dict(doc, next=unsafe))
    witness = machine.verify(bad, lab.identity(bad))['trace']
    memory = dict(parent=lab.identity(raw), runtime_digest=lab.runtime_digest(doc['sources']),
                  counterexamples=[dict(next=unsafe, trace=witness)])
    return raw, [unsafe, second, safe], memory


class MachineSearch(unittest.TestCase):
    def test_trace_recomputes_candidate_states_and_both_oracles(self):
        raw, rules, memory = fixture(); trace = memory['counterexamples'][0]['trace']
        safe = canon(dict(decode(raw), next=rules[2]))
        result = machine.replay_trace(safe, trace)
        self.assertEqual(result['status'], 'trace_passed')
        self.assertEqual(result['trace'], dict(initial=dict(a=False,b=False), steps=[
            dict(event={},state=dict(a=False,b=True)),dict(event={},state=dict(a=False,b=True))]))
        self.assertEqual(result['checked_steps'], 2)
        bad = canon(dict(decode(raw), next=rules[0]))
        result = machine.replay_trace(bad, trace)
        self.assertEqual((result['status'],result['trace']), ('counterexample',trace))
        real = boolean.evaluate
        with patch.object(boolean, 'evaluate', side_effect=lambda code, facts: not real(code,facts)):
            self.assertEqual(machine.replay_trace(safe,trace)['status'],'checker_error')
        # Independently break only the next-rule oracle, leaving invariant checks intact.
        inv = lab._program(decode(safe)['invariant'],['a','b'])
        with patch.object(boolean,'evaluate',side_effect=lambda code,facts: real(code,facts) if code==inv else not real(code,facts)):
            self.assertEqual(machine.replay_trace(safe,trace)['status'],'checker_error')

    def test_experience_reduces_gate_calls_never_admits_without_gate(self):
        raw,rules,memory=fixture()
        outputs=[]
        for incoming, expected_calls, expected_screened in [(None,2,1),(memory,1,2)]:
            with patch.object(search,'machine_candidates',return_value=iter(rules)), \
                 patch.object(machine,'verify_change',wraps=machine.verify_change) as gate, \
                 patch.object(machine,'replay_trace',wraps=machine.replay_trace) as replay:
                report,child=search.search_machine(raw,lab.identity(raw),experience=incoming)
            self.assertEqual(report['status'],'found')
            self.assertEqual((report['full_checks'],gate.call_count),(expected_calls,expected_calls))
            self.assertEqual(report['trace_checks'],replay.call_count)
            self.assertEqual(report['screened'],expected_screened)
            self.assertEqual(report['attempted'],3)
            self.assertEqual(report['proposal'],dict(parent=lab.identity(raw),next=rules[2]))
            verified,expected=machine.verify_change(raw,report['proposal'],lab.identity(raw))
            self.assertTrue(verified['admitted']);self.assertEqual(child,expected)
            outputs.append(child)
        self.assertEqual(outputs[0],outputs[1])
        # Passing every stored trace is never itself admission.
        with patch.object(search,'machine_candidates',return_value=iter([rules[2]])), \
             patch.object(machine,'verify_change',return_value=(dict(status='incomplete',admitted=False),None)) as gate:
            report,child=search.search_machine(raw,lab.identity(raw),experience=memory)
        self.assertEqual(report['status'],'search_incomplete');self.assertIsNone(child)
        self.assertEqual(gate.call_count,1)
        self.assertEqual(report['incomplete_candidates'],1)

    def test_fabricated_or_foreign_experience_cannot_screen(self):
        raw,rules,memory=fixture()
        variants=[]
        for field in ['parent','runtime_digest']:
            m=decode(canon(memory));m[field]='0'*64;variants.append(m)
        m=decode(canon(memory));m['counterexamples'][0]['trace']['steps'][-1]['state']['a']=False;variants.append(m)
        m=decode(canon(memory));m['counterexamples'][0]['next']=rules[2];variants.append(m)
        m=decode(canon(memory));m['counterexamples'][0]['trace']['initial']['a']=True;variants.append(m)
        m=decode(canon(memory));m['counterexamples'][0]['trace']['steps'][0]['event']={'extra':False};variants.append(m)
        m=decode(canon(memory));m['counterexamples'][0]['trace']['steps']*=3;variants.append(m)
        m=decode(canon(memory));m['counterexamples'][0]['trace']['steps'][0]['state']['b']=1;variants.append(m)
        m=decode(canon(memory));m['counterexamples'][0]['verdict']='counterexample';variants.append(m)
        with patch.object(search,'machine_candidates',side_effect=AssertionError('search must not start')):
            for m in variants:
                with self.subTest(memory=m),self.assertRaises(InvalidRecord):
                    search.search_machine(raw,lab.identity(raw),experience=m)

    def test_incomplete_candidates_continue_and_never_enter_experience(self):
        raw,rules,memory=fixture(); real=machine.verify_change
        def check(packet,p,anchor,**kw):
            if p['next']==rules[0]:return dict(status='incomplete',admitted=False),None
            return real(packet,p,anchor,**kw)
        with patch.object(search,'machine_candidates',return_value=iter([rules[0],rules[2]])), \
             patch.object(machine,'verify_change',side_effect=check):
            report,child=search.search_machine(raw,lab.identity(raw))
        self.assertEqual(report['status'],'found');self.assertIsNotNone(child)
        self.assertEqual(report['incomplete_candidates'],1)
        self.assertEqual(report['experience']['counterexamples'],[])
        with patch.object(search,'machine_candidates',return_value=iter([rules[0]])), \
             patch.object(machine,'verify_change',side_effect=check):
            report,child=search.search_machine(raw,lab.identity(raw))
        self.assertEqual(report['status'],'search_incomplete');self.assertIsNone(child)
        self.assertEqual(report['experience']['counterexamples'],[])

    def test_screening_incomplete_continues_but_checker_error_stops(self):
        raw,rules,memory=fixture(); real=machine.replay_trace
        for status in ['incomplete','checker_error']:
            def probe(packet,trace):
                if decode(packet)['next']==rules[1]:return dict(status=status,reason='injected')
                return real(packet,trace)
            with patch.object(search,'machine_candidates',return_value=iter([rules[1],rules[2]])), \
                 patch.object(machine,'replay_trace',side_effect=probe):
                report,child=search.search_machine(raw,lab.identity(raw),experience=memory)
            self.assertEqual(report['status'],'found' if status=='incomplete' else 'checker_error')
            self.assertEqual(child is not None,status=='incomplete')
            self.assertEqual(report['attempted'],2 if status=='incomplete' else 1)
            self.assertEqual(report['experience'],memory)
        for exception,status in [(kernel.ResourceFault('local'),'incomplete'),(compiler.CompilerBug('bug'),'checker_error')]:
            with patch.object(compiler,'compile_source',side_effect=exception):
                self.assertEqual(machine.replay_trace(raw,memory['counterexamples'][0]['trace'])['status'],status)
        for status in ['incomplete','checker_error']:
            with patch.object(machine,'replay_trace',return_value=dict(status=status,reason='injected')), \
                 patch.object(search,'machine_candidates',side_effect=AssertionError('no search')):
                report,child=search.search_machine(raw,lab.identity(raw),experience=memory)
            self.assertEqual(report['status'],status);self.assertIsNone(child)

    def test_parent_anchor_quota_and_unsafe_parent_precede_search(self):
        raw,rules,memory=fixture()
        with patch.object(search,'machine_candidates',side_effect=AssertionError('no search')):
            with self.assertRaises(InvalidRecord):search.search_machine(raw,'0'*64)
            report,child=search.search_machine(raw,lab.identity(raw),max_edges=0)
            self.assertEqual(report['status'],'incomplete');self.assertIsNone(child)
            bad=canon(dict(decode(raw),next=rules[0]))
            report,child=search.search_machine(bad,lab.identity(bad))
            self.assertEqual(report['status'],'parent_rejected');self.assertIsNone(child)
            for limit in [0,257,True,1.0]:
                with self.assertRaises(InvalidRecord):search.search_machine(raw,lab.identity(raw),max_candidates=limit)

    def test_real_generator_limit_duplicates_and_exhaustion(self):
        raw,rules,memory=fixture(); doc=decode(raw)
        generated=list(search.machine_candidates(doc))
        self.assertTrue(generated)
        for item in generated:
            self.assertEqual(set(item),set(doc['next']))
            self.assertLessEqual(sum(item[k]!=doc['next'][k] for k in item),1)
        report,child=search.search_machine(raw,lab.identity(raw))
        self.assertEqual(report['status'],'found');self.assertIsNotNone(child)
        verified,output=machine.verify_change(raw,report['proposal'],lab.identity(raw))
        self.assertTrue(verified['admitted']);self.assertEqual(child,output)
        with patch.object(search,'machine_candidates',return_value=iter([doc['next'],doc['next']])):
            report,child=search.search_machine(raw,lab.identity(raw),max_candidates=3)
        self.assertEqual(report['status'],'neighborhood_exhausted');self.assertEqual(report['full_checks'],0)
        self.assertEqual([a['status'] for a in report['attempts']],['duplicate','duplicate'])
        with patch.object(search,'machine_candidates',return_value=iter([rules[0],rules[2]])):
            report,child=search.search_machine(raw,lab.identity(raw),max_candidates=1)
        self.assertEqual(report['status'],'search_incomplete');self.assertEqual(report['reason'],'candidate_limit')
        self.assertIsNone(child)

    def test_cli_real_search_and_retained_output(self):
        raw,rules,memory=fixture()
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);src=root/'machine';output=root/'out';src.write_bytes(raw)
            args=['machine-search',str(src),'--expect-machine',lab.identity(raw),'--output',str(output)]
            stdout=io.StringIO()
            with redirect_stdout(stdout):code=cli.main(args)
            self.assertEqual(code,0);report=json.loads(stdout.getvalue())
            self.assertEqual(report['status'],'found')
            self.assertEqual(output.read_bytes(),machine.verify_change(raw,report['proposal'],lab.identity(raw))[1])
            saved=output.read_bytes()
            experience=root/'experience';experience.write_text(json.dumps(report['experience']))
            stdout=io.StringIO()
            with redirect_stdout(stdout): code=cli.main(args[:-2]+['--experience',str(experience)])
            self.assertEqual(code,0)
            reused=json.loads(stdout.getvalue())
            self.assertEqual(reused['successor'],report['successor'])
            self.assertLess(reused['full_checks'],report['full_checks'])
            experience.write_text('null')
            with redirect_stderr(io.StringIO()),redirect_stdout(io.StringIO()):
                code=cli.main(args+['--experience',str(experience)])
            self.assertEqual(code,2);self.assertEqual(output.read_bytes(),saved)
            with redirect_stderr(io.StringIO()),redirect_stdout(io.StringIO()):code=cli.main(args)
            self.assertEqual(code,1);self.assertEqual(output.read_bytes(),saved)
            for extra,expected in [(['--max-edges','0'],3),(['--expect-machine','0'*64],2)]:
                with redirect_stderr(io.StringIO()),redirect_stdout(io.StringIO()):code=cli.main(args+extra)
                self.assertEqual(code,expected);self.assertEqual(output.read_bytes(),saved)


    def test_event_values_drive_replay_not_claimed_states(self):
        raw=machine.create(dict(state=['q'],events=['e'],initial=[dict(q=False)],
            next={'q':wpl(['e','q'],'q && (e || !e)')},invariant=wpl(['q'],'!q'),max_atp=1000))
        bad=canon(dict(decode(raw),next={'q':wpl(['e','q'],'e || q')}))
        trace=dict(initial=dict(q=False),steps=[dict(event=dict(e=True),state=dict(q=True))])
        self.assertEqual(machine.replay_trace(bad,trace)['status'],'counterexample')
        safe=machine.replay_trace(raw,trace)
        self.assertEqual(safe['status'],'trace_passed')
        self.assertEqual(safe['trace']['steps'],[dict(event=dict(e=True),state=dict(q=False))])
        trace['steps'][0]['event']['e']=False
        changed=machine.replay_trace(bad,trace)
        self.assertEqual(changed['status'],'trace_passed')
        self.assertEqual(changed['trace']['steps'],[dict(event=dict(e=False),state=dict(q=False))])

    def test_candidate_edge_quota_is_forwarded_to_full_gate(self):
        raw,rules,memory=fixture()
        with patch.object(search,'machine_candidates',return_value=iter([rules[2]])), \
             patch.object(machine,'verify_change',wraps=machine.verify_change) as gate:
            report,child=search.search_machine(raw,lab.identity(raw),max_edges=1)
        self.assertEqual(report['status'],'search_incomplete');self.assertIsNone(child)
        self.assertEqual(report['incomplete_candidates'],1)
        self.assertEqual(gate.call_args.kwargs,dict(max_edges=1))
        self.assertEqual(report['experience']['counterexamples'],[])

    def test_cli_found_proposal_is_independently_replayed_offline(self):
        import subprocess
        import sys
        raw,_,_=fixture()
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);source=root/'parent';source.write_bytes(raw)
            child=root/'child';offline=root/'offline';desc=machine.unpack(raw,offline)
            result=subprocess.run([sys.executable,'-I','-m','stargate','machine-search',str(source),
                '--expect-machine',lab.identity(raw),'--output',str(child)],cwd='/',capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stderr)
            report=json.loads(result.stdout);p=root/'proposal';p.write_text(json.dumps(report['proposal']))
            output=root/'replayed'
            result=subprocess.run([sys.executable,'-I','-S',str(offline/'replay.py'),str(p),str(output),
                '--machine-change','--expect-machine',lab.identity(raw),'--expect-runtime',desc['runtime_digest']],
                cwd='/',capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stderr)
            verified=json.loads(result.stdout)
            self.assertEqual(verified,report['attempts'][-1]['verification'])
            self.assertEqual(output.read_bytes(),child.read_bytes())
