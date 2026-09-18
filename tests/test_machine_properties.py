import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from stargate import machine, lab, compiler
from stargate.canonical import canon, decode, InvalidRecord
from test_machine import table_rule, wpl


def packet(table=(0,1,2,3), initials=(0,)):
    return machine.create(dict(state=['a','b'],events=[],
        initial=[dict(a=bool(i&2),b=bool(i&1)) for i in initials],max_atp=1000,
        next={n:table_rule(['a','b'],[bool(t&mask) for t in table]) for n,mask in [('a',2),('b',1)]},
        invariant=wpl(['a','b'],'(a && !a) && (b || !b)')))


def truth(p,state):
    if p['kind']=='bit': return state[p['name']]==p['value']
    if p['kind']=='equal': return len({state[p['left']],state[p['right']]})==1
    return (state[p['left']],state[p['right']]) != (True,False)


class MachineProperties(unittest.TestCase):
    def test_all_256_two_bit_transition_tables_and_every_claim(self):
        for code in range(256):
            table=[(code>>(2*i))&3 for i in range(4)]
            initial=code%4;raw=packet(table,(initial,));anchor=lab.identity(raw)
            reached=[];state=initial
            while state not in reached:
                reached.append(state);state=table[state]
            states=[dict(a=bool(i&2),b=bool(i&1)) for i in reached]
            discovery=machine.discover_properties(raw,anchor)
            self.assertEqual(discovery['status'],'complete')
            self.assertEqual(discovery['hypotheses'],7)
            self.assertEqual(discovery['observation']['reachable'],states)
            for result in discovery['results']:
                p=result['property'];violating=next((i for i,s in enumerate(states) if not truth(p,s)),None)
                expected='established' if violating is None else 'counterexample'
                self.assertEqual(result['status'],expected,(code,p))
                claim=dict(parent=anchor,property=p)
                checked=machine.verify_property(raw,claim,anchor)
                self.assertEqual(checked['status'],expected,(code,p))
                if violating is not None:
                    trace=dict(initial=states[0],steps=[dict(event={},state=s) for s in states[1:violating+1]])
                    self.assertEqual(result['trace'],trace)
                    self.assertEqual(checked['trace'],trace)
                else:
                    self.assertEqual(result['checked_states'],len(reached))
                    self.assertEqual(checked['checked_states'],len(reached))

    def test_observation_ignores_broken_invariant_but_never_returns_changed_machine(self):
        raw=packet((1,3,2,3));before=raw
        self.assertEqual(machine.verify(raw,lab.identity(raw))['status'],'counterexample')
        with patch.object(machine,'verify',wraps=machine.verify) as count:
            report=machine.discover_properties(raw,lab.identity(raw))
        self.assertEqual(count.call_count,1)
        self.assertEqual(report['status'],'complete')
        self.assertEqual(report['machine_id'],lab.identity(raw))
        observed=decode(count.call_args.args[0]);original=decode(raw)
        self.assertNotEqual(observed.pop('invariant'),original.pop('invariant'))
        self.assertEqual(observed,original)
        self.assertNotIn('successor',report);self.assertNotIn('admitted',report)
        self.assertEqual(raw,before)
        equal=next(r for r in report['results'] if r['property']['kind']=='equal')
        self.assertEqual(equal['status'],'counterexample')
        self.assertEqual(equal['trace'],dict(initial=dict(a=False,b=False),steps=[dict(event={},state=dict(a=False,b=True))]))

    def test_catalog_direction_initial_states_and_unreachable_states(self):
        raw=packet(initials=(2,0))
        report=machine.discover_properties(raw,lab.identity(raw))
        props=[r['property'] for r in report['results']]
        self.assertEqual(props,[dict(kind='bit',name=n,value=v) for n in ['a','b'] for v in [False,True]]+
            [dict(kind='equal',left='a',right='b'),dict(kind='implies',left='a',right='b'),dict(kind='implies',left='b',right='a')])
        self.assertEqual([r['status'] for r in report['results']],
            ['counterexample','counterexample','established','counterexample','counterexample','counterexample','established'])
        self.assertEqual(report['results'][5]['trace'],dict(initial=dict(a=True,b=False),steps=[]))
        # Unreachable b=true must not refute b=false.
        self.assertEqual(report['results'][2]['checked_states'],2)

    def test_quota_faults_and_observation_disagreement_produce_no_properties(self):
        raw=packet((1,3,2,3));anchor=lab.identity(raw)
        for quota in [0,1,2]:
            report=machine.discover_properties(raw,anchor,max_edges=quota)
            self.assertEqual(report['status'],'incomplete');self.assertEqual(report['results'],[])
            self.assertNotIn('hypotheses',report)
        self.assertEqual(machine.discover_properties(raw,anchor,max_edges=3)['status'],'complete')
        for status,expected in [('counterexample','checker_error'),('checker_error','checker_error'),('incomplete','incomplete')]:
            with patch.object(machine,'verify',return_value=dict(status=status,reason='injected')):
                report=machine.discover_properties(raw,anchor)
            self.assertEqual(report['status'],expected);self.assertEqual(report['results'],[])
        doc=decode(raw);doc['max_atp']=0;small=canon(doc)
        self.assertEqual(machine.discover_properties(small,lab.identity(small))['status'],'incomplete')

    def test_closed_graph_and_reachability_order_are_not_just_labels(self):
        raw=packet();anchor=lab.identity(raw);real=machine.verify
        def corrupt(packet,expected,**kw):
            g=real(packet,expected,**kw);g['edges']=[];return g
        with patch.object(machine,'verify',side_effect=corrupt):
            report=machine.discover_properties(raw,anchor)
        self.assertEqual(report['status'],'checker_error');self.assertEqual(report['results'],[])
        def disconnected(packet,expected,**kw):
            g=real(packet,expected,**kw);state=dict(a=True,b=False)
            g['reachable'].append(state);g['edges'].append(dict(state=state,event={},next=state))
            g['checked_edges']+=1;g['checked_invariants']+=1;return g
        with patch.object(machine,'verify',side_effect=disconnected):
            report=machine.discover_properties(raw,anchor)
        self.assertEqual(report['status'],'checker_error');self.assertEqual(report['results'],[])
        raw=packet((1,3,2,3))
        def reorder(packet,expected,**kw):
            g=real(packet,expected,**kw);g['reachable'].reverse();return g
        with patch.object(machine,'verify',side_effect=reorder):
            self.assertEqual(machine.discover_properties(raw,lab.identity(raw))['status'],'checker_error')

    def test_invalid_claims_and_recipient_anchor_fail_before_graph(self):
        raw=packet();anchor=lab.identity(raw)
        props=[dict(kind='bit',name='a',value=1),dict(kind='bit',name='z',value=False),
               dict(kind='equal',left='a',right='a'),dict(kind='implies',left='a',right='e'),
               dict(kind='temporal'),dict(kind='bit',name='a',value=False,proof=True)]
        with patch.object(machine,'verify',side_effect=AssertionError('no graph')):
            for prop in props:
                with self.assertRaises(InvalidRecord): machine.verify_property(raw,dict(parent=anchor,property=prop),anchor)
            with self.assertRaises(InvalidRecord):machine.discover_properties(raw,'0'*64)
            with self.assertRaises(InvalidRecord):machine.verify_property(raw,dict(parent='0'*64,property=dict(kind='bit',name='a',value=False)),anchor)

    def test_cli_and_offline_byte_identical_without_output(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);raw=packet((1,3,2,3));anchor=lab.identity(raw)
            source=root/'machine';source.write_bytes(raw);offline=root/'offline';desc=machine.unpack(raw,offline)
            claim=root/'claim';claim.write_text(json.dumps(dict(parent=anchor,property=dict(kind='equal',left='a',right='b'))))
            for mode,path,code,status in [('discover',source,0,'complete'),('claim',claim,4,'counterexample')]:
                outputs=[]
                for command in ([sys.executable,'-I','-m','stargate','machine-'+mode,str(source)]+([str(claim)] if mode=='claim' else []),
                    [sys.executable,'-I','-S',str(offline/'replay.py'),str(path),'--machine-'+mode,'--expect-runtime',desc['runtime_digest']]):
                    result=subprocess.run(command+['--expect-machine',anchor],cwd='/',capture_output=True,text=True)
                    self.assertEqual(result.returncode,code,result.stderr)
                    report=json.loads(result.stdout);self.assertEqual(report['status'],status)
                    outputs.append(result.stdout)
                self.assertEqual(json.loads(outputs[0]),json.loads(outputs[1]))
            result=subprocess.run([sys.executable,'-I','-S',str(offline/'replay.py'),str(source),str(root/'forbidden'),
                '--machine-discover','--expect-machine',anchor,'--expect-runtime',desc['runtime_digest']],capture_output=True,text=True)
            self.assertEqual(result.returncode,2);self.assertFalse((root/'forbidden').exists())

    def test_branching_events_shortest_trace_and_six_bit_catalog(self):
        from test_machine import branching_machine
        edges={(0,False):2,(0,True):4,(2,False):1,(2,True):1,
               (4,False):6,(4,True):6,(6,False):3,(6,True):3}
        raw,bits=branching_machine(edges,set());anchor=lab.identity(raw)
        claim=dict(parent=anchor,property=dict(kind='bit',name='c',value=False))
        result=machine.verify_property(raw,claim,anchor)
        self.assertEqual(result['status'],'counterexample')
        self.assertEqual(result['trace'],dict(initial=bits(0),steps=[
            dict(event=dict(z=False),state=bits(2)),dict(event=dict(z=False),state=bits(1))]))
        names=list('abcdef'); taut=' && '.join('('+n+' || !'+n+')' for n in names)
        raw=machine.create(dict(state=names,events=[],initial=[dict.fromkeys(names,False)],max_atp=1000,
            next={n:wpl(names,n+' && '+taut) for n in names},invariant=wpl(names,taut)))
        report=machine.discover_properties(raw,lab.identity(raw))
        self.assertEqual((report['status'],report['hypotheses']),('complete',57))
        self.assertEqual(len({canon(r['property']) for r in report['results']}),57)
        self.assertEqual(sum(r['status']=='established' for r in report['results']),51)

    def test_graph_counters_and_property_obligation_counts_are_enforced(self):
        raw=packet();real=machine.verify
        def miscount(packet,anchor,**kw):
            report=real(packet,anchor,**kw);report['checked_edges']-=1;return report
        with patch.object(machine,'verify',side_effect=miscount):
            report=machine.discover_properties(raw,lab.identity(raw))
        self.assertEqual(report['status'],'checker_error');self.assertEqual(report['results'],[])
        class Truncated(dict):
            def items(self):return list(super().items())[:1]
        states=Truncated({(False,False):dict(a=False,b=False),(False,True):dict(a=False,b=True)})
        report=machine._assess_property(dict(kind='bit',name='a',value=False),states,{})
        self.assertEqual(report['status'],'checker_error')

    def test_equality_requires_matching_bits_not_merely_a_mixed_graph(self):
        for initials,status in [((0,3),'established'),((1,2),'counterexample')]:
            raw=packet(initials=initials);anchor=lab.identity(raw)
            result=machine.verify_property(raw,dict(parent=anchor,property=dict(kind='equal',left='a',right='b')),anchor)
            self.assertEqual(result['status'],status)

    def test_discovery_order_is_checked_before_assessment(self):
        raw=packet((1,3,2,3));real=machine.verify
        def reorder(packet,expected,**kw):
            g=real(packet,expected,**kw);g['reachable'].reverse();return g
        with patch.object(machine,'verify',side_effect=reorder):
            report=machine.discover_properties(raw,lab.identity(raw))
        self.assertEqual(report['status'],'checker_error');self.assertEqual(report['results'],[])

    def test_cli_offline_refusal_classifications(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);raw=packet((1,3,2,3));anchor=lab.identity(raw)
            source=root/'machine';offline=root/'offline';desc=machine.unpack(raw,offline)
            foreign=decode(raw);foreign['sources']['machine.py']+='\n# foreign'
            for data,expected,quota,code,status in [(raw,anchor,0,3,'incomplete'),
                    (raw,'0'*64,256,2,'invalid'),(canon(foreign),lab.identity(canon(foreign)),256,3,'runtime_unavailable')]:
                source.write_bytes(data)
                for command in ([sys.executable,'-I','-m','stargate','machine-discover',str(source)],
                    [sys.executable,'-I','-S',str(offline/'replay.py'),str(source),'--machine-discover','--expect-runtime',desc['runtime_digest']]):
                    result=subprocess.run(command+['--expect-machine',expected,'--max-edges',str(quota)],cwd='/',capture_output=True,text=True)
                    self.assertNotIn('Traceback',result.stderr)
                    self.assertEqual((result.returncode,json.loads(result.stdout or result.stderr)['status']),(code,status))
            source.write_bytes(raw);claim=root/'claim'
            claim.write_text(json.dumps(dict(parent=anchor,property=dict(kind='bit',name='a',value=False),verdict='established')))
            for command in ([sys.executable,'-I','-m','stargate','machine-claim',str(source),str(claim)],
                [sys.executable,'-I','-S',str(offline/'replay.py'),str(claim),'--machine-claim','--expect-runtime',desc['runtime_digest']]):
                result=subprocess.run(command+['--expect-machine',anchor],cwd='/',capture_output=True,text=True)
                self.assertEqual((result.returncode,json.loads(result.stderr)['status']),(2,'invalid'))
