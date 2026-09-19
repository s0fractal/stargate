import copy
import itertools
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from stargate import composition as co, machine, lab, compiler, boolean
from stargate.canonical import canon,decode,InvalidRecord


def rule(names,expr):
    return ''.join('fact '+n+': bool\n' for n in sorted(names))+'check '+expr


def delivery():
    return dict(components={
        'producer':dict(state=['sent'],inputs=['ack'],next={'sent':rule(['sent','ack'],'sent || !ack')}),
        'consumer':dict(state=['received'],inputs=['request'],next={'received':rule(['received','request'],'received || request')})},
        wires={'producer.ack':'consumer.received','consumer.request':'producer.sent'},events=[],
        initial=[{'producer.sent':False,'consumer.received':False}],
        invariant=rule(['producer.sent','consumer.received'],'!consumer.received || producer.sent'),
        goals=[{'producer.sent':True,'consumer.received':True}],max_atp=1000)


def proposal(raw,expr):
    return dict(parent=lab.identity(raw),component='producer',next={'sent':rule(['sent','ack'],expr)})


class Composition(unittest.TestCase):
    def test_local_contracts_pass_but_joint_protocol_fails_with_shortest_trace(self):
        spec=delivery();spec['components']['producer']['next']['sent']=rule(['sent','ack'],'!ack')
        for component in spec['components'].values():
            bit=component['state'][0]
            local=machine.create(dict(state=[bit],events=component['inputs'],next=component['next'],
                initial=[{bit:False}],invariant=rule([bit],'true'),goals=[{bit:True}],max_atp=1000))
            self.assertEqual(machine.verify(local,lab.identity(local))['status'],'established')
        raw=co.create(spec);r=co.verify(raw,lab.identity(raw))
        self.assertEqual(r['status'],'counterexample')
        self.assertEqual(r['check']['trace'],dict(initial={'consumer.received':False,'producer.sent':False},steps=[
            dict(event={},state={'consumer.received':False,'producer.sent':True}),
            dict(event={},state={'consumer.received':True,'producer.sent':True}),
            dict(event={},state={'consumer.received':True,'producer.sent':False})]))

    def test_single_component_change_preserves_every_other_byte_of_contract(self):
        raw=co.create(delivery());anchor=lab.identity(raw)
        r,child=co.verify_change(raw,proposal(raw,'true'),anchor)
        self.assertEqual(r['status'],'safety_preserved');self.assertTrue(r['admitted'])
        expected=decode(raw);expected['components']['producer']['next']=proposal(raw,'true')['next']
        self.assertEqual(child,canon(expected));self.assertEqual(r['successor'],lab.identity(child))
        r,child=co.verify_change(raw,proposal(raw,'!ack'),anchor)
        self.assertFalse(r['admitted']);self.assertIsNone(child)
        self.assertEqual((r['status'],r['program']),('counterexample','candidate'))
        r,child=co.verify_change(raw,proposal(raw,'sent'),anchor)
        self.assertFalse(r['admitted']);self.assertIsNone(child)
        self.assertEqual((r['status'],r['program']),('goal_unreachable','candidate'))

    def test_order_and_feedback_use_one_old_state(self):
        spec=delivery();raw=co.create(spec)
        swapped=copy.deepcopy(spec);swapped['components']=dict(reversed(list(swapped['components'].items())))
        swapped['wires']=dict(reversed(list(swapped['wires'].items())))
        self.assertEqual(co.create(swapped),raw)
        r=co.verify(raw,lab.identity(raw));self.assertEqual(r['status'],'established')
        self.assertEqual(r['check']['edges'][0]['next'],{'consumer.received':False,'producer.sent':True})
        # Symmetric cross-coupling swaps 01 <-> 10. An in-place update collapses it.
        s=dict(components={n:dict(state=['q'],inputs=['p'],next={'q':rule(['p','q'],'p')}) for n in ['a','b']},
            wires={'a.p':'b.q','b.p':'a.q'},events=[],initial=[{'a.q':False,'b.q':True}],
            invariant=rule(['a.q','b.q'],'a.q || b.q'),goals=[{'a.q':True,'b.q':False}],max_atp=1000)
        raw=co.create(s);r=co.verify(raw,lab.identity(raw))
        self.assertEqual(r['status'],'established')
        self.assertEqual(r['check']['reachable'],[{'a.q':False,'b.q':True},{'a.q':True,'b.q':False}])
        self.assertEqual(r['check']['checked_edges'],2)

    def test_external_events_and_fanout_have_shared_snapshot(self):
        s=dict(components={n:dict(state=['q'],inputs=['p'],next={'q':rule(['p','q'],'p')}) for n in ['a','b']},
            wires={'a.p':'env.e','b.p':'env.e'},events=['e'],initial=[{'a.q':False,'b.q':False}],
            invariant=rule(['a.q','b.q'],'(a.q && b.q) || (!a.q && !b.q)'),
            goals=[{'a.q':True,'b.q':True}],max_atp=1000)
        raw=co.create(s);r=co.verify(raw,lab.identity(raw))
        self.assertEqual(r['status'],'established');self.assertEqual(r['check']['checked_edges'],4)
        self.assertEqual(r['check']['goal_witnesses'][0]['trace']['steps'],[
            dict(event={'env.e':True},state={'a.q':True,'b.q':True})])

    def test_quota_and_budget_are_not_false_absence(self):
        raw=co.create(delivery());anchor=lab.identity(raw)
        for quota in [0,1,2]:
            with self.subTest(quota=quota):
                r=co.verify(raw,anchor,max_edges=quota)
                self.assertEqual(r['status'],'incomplete')
                self.assertNotIn('unreached_goals',r['check'])
                changed,child=co.verify_change(raw,proposal(raw,'true'),anchor,max_edges=quota)
                self.assertFalse(changed['admitted']);self.assertIsNone(child)
                self.assertEqual((changed['status'],changed['program']),('incomplete','parent'))
        self.assertEqual(co.verify(raw,anchor,max_edges=3)['status'],'established')
        spec=delivery();spec['max_atp']=0;raw=co.create(spec)
        self.assertEqual(co.verify(raw,lab.identity(raw))['status'],'incomplete')

    def test_candidate_quota_after_complete_parent_cannot_admit_or_claim_absence(self):
        spec=dict(components={
            'a':dict(state=['p','q'],inputs=[],next={n:rule(['p','q'],'true') for n in ['p','q']}),
            'b':dict(state=['r'],inputs=[],next={'r':rule(['r'],'r')})},wires={},events=[],
            initial=[{'a.p':False,'a.q':False,'b.r':False}],
            invariant=rule(['a.p','a.q','b.r'],'true'),goals=[{'a.p':True,'a.q':True,'b.r':False}],max_atp=1000)
        raw=co.create(spec);anchor=lab.identity(raw)
        p=dict(parent=anchor,component='a',next={'p':rule(['p','q'],'p || q'),'q':rule(['p','q'],'!q')})
        full,child=co.verify_change(raw,p,anchor,max_edges=4)
        self.assertTrue(full['admitted']);self.assertIsNotNone(child)
        r,child=co.verify_change(raw,p,anchor,max_edges=2)
        self.assertEqual((r['status'],r['admitted'],child),('incomplete',False,None))
        self.assertEqual(r['program'],'candidate')
        self.assertEqual(r['checks']['parent']['status'],'established')
        candidate=r['checks']['candidate']['check']
        self.assertEqual(candidate['checked_edges'],2)
        self.assertNotIn(spec['goals'][0],candidate['reachable'])
        self.assertNotIn('unreached_goals',candidate)
        self.assertNotIn('goal_witnesses',candidate)

    def test_broken_parent_cannot_be_repaired_and_wrong_anchor_refuses_before_work(self):
        for expr,status in [('!ack','counterexample'),('sent','goal_unreachable')]:
            spec=delivery();spec['components']['producer']['next']['sent']=rule(['ack','sent'],expr)
            raw=co.create(spec);r,child=co.verify_change(raw,proposal(raw,'true'),lab.identity(raw))
            self.assertFalse(r['admitted'])
            self.assertEqual((r['status'],r['program'],child),('parent_rejected','parent',None))
            self.assertEqual(r['checks']['parent']['status'],status);self.assertNotIn('candidate',r['checks'])
        raw=co.create(delivery())
        with patch.object(co,'_bridge',side_effect=AssertionError('must not evaluate')):
            with self.assertRaises(InvalidRecord):co.verify(raw,'0'*64)
            with self.assertRaises(InvalidRecord):co.verify_change(raw,proposal(raw,'true'),'0'*64)

    def test_proposal_cannot_change_contract_interfaces_or_other_component(self):
        raw=co.create(delivery());anchor=lab.identity(raw);p=proposal(raw,'true')
        for field,value in [('wires',{}),('goals',[]),('invariant',rule(['consumer.received','producer.sent'],'true')),
                            ('components',{}),('initial',[]),('max_atp',10000),('sources',{}),('state',[])]:
            with self.subTest(field=field),self.assertRaises(InvalidRecord):co.verify_change(raw,dict(p,**{field:value}),anchor)
        for bad in [dict(p,component='missing'),dict(p,next={}),dict(p,next={'received':rule(['sent','ack'],'true')}),
                    dict(p,parent='0'*64)]:
            with self.assertRaises(InvalidRecord):co.verify_change(raw,bad,anchor)
        with self.assertRaises(compiler.PolicyError):
            co.verify_change(raw,dict(p,next={'sent':rule(['ack','sent'],'consumer.received')}),anchor)

    def test_shape_wiring_names_and_exact_declarations(self):
        edits=[lambda s:s['wires'].pop('producer.ack'),lambda s:s['wires'].update({'x.y':'producer.sent'}),
               lambda s:s['wires'].update({'producer.ack':'consumer.request'}),
               lambda s:s['wires'].update({'producer.ack':True}),lambda s:s['components'].pop('producer'),
               lambda s:s['components'].update({'env':s['components'].pop('producer')}),
               lambda s:s['components']['producer'].update(state=['a.b']),
               lambda s:s['components']['producer'].update(inputs=['sent']),
               lambda s:s['initial'][0].pop('producer.sent'),lambda s:s.update(goals=[{'producer.sent':True}]),
               lambda s:s.update(events=['a','b','c']),lambda s:s['components']['producer']['next'].update(sent='check true')]
        for edit in edits:
            s=delivery();edit(s)
            with self.subTest(spec=s),self.assertRaises((InvalidRecord,compiler.PolicyError)):co.create(s)
        with self.assertRaises(ValueError):co.read_spec(b'{"wires":{},"wires":{}}')
        raw=co.create(delivery());doc=decode(raw)
        with self.assertRaises(InvalidRecord):co.inspect(raw+b' ')
        with self.assertRaises(InvalidRecord):co.inspect(canon(dict(doc,goals=None)))
        del doc['goals'];doc['sources']['composition.py']+='\n# other'
        with self.assertRaises(lab.RuntimeMismatch):co.inspect(canon(doc))

    def test_translation_is_checked_against_original_rules_on_the_whole_domain(self):
        raw=co.create(delivery());anchor=lab.identity(raw)
        original=co._lower
        def wrong(source,mapping,names):
            lowered=original(source,mapping,names)
            return lowered.replace('! consumer.received','consumer.received')
        with patch.object(co,'_lower',side_effect=wrong),patch.object(machine,'verify',side_effect=AssertionError('bridge must stop')):
            r=co.verify(raw,anchor)
            self.assertEqual(r['status'],'checker_error');self.assertIn('translation',r['reason'])
        mapping=co._mapping
        def wrong_wire(doc,name):
            result=mapping(doc,name)
            if name=='consumer':result['request']='consumer.received'
            return result
        with patch.object(co,'_mapping',side_effect=wrong_wire):
            self.assertEqual(co.verify(raw,anchor)['status'],'checker_error')
        # Actual original-rule oracle is called for ALL four assignments, two bits.
        with patch.object(boolean,'evaluate',wraps=boolean.evaluate) as oracle:
            co._bridge(decode(raw),decode(co._product(decode(raw))))
            self.assertEqual(oracle.call_count,8)
        with patch.object(co.itertools,'product',return_value=iter([(False,False)])):
            with self.assertRaisesRegex(compiler.CompilerBug,'coverage'):co._bridge(decode(raw),decode(co._product(decode(raw))))

    def test_lowering_keeps_whole_names_comments_and_operator_grouping(self):
        names=['a','aa','p'];source=rule(names,'a || aa && !p')+' # a aa p ignored\n'
        lowered=co._lower(source,{'a':'x.a','aa':'x.aa','p':'y.p'},['x.a','x.aa','y.p'])
        expr,_=compiler.parse(lowered,dict.fromkeys(['x.a','x.aa','y.p'],False),allow_unused=True)
        for a,aa,p in itertools.product([False,True],repeat=3):
            self.assertEqual(compiler.interpret(expr,{'x.a':a,'x.aa':aa,'y.p':p}),a or aa and not p)

    def test_all_two_bit_cross_wired_transition_pairs_against_table_bfs(self):
        def table_rule(mask):
            terms=[]
            for q,p in itertools.product([False,True],repeat=2):
                if mask & (1 << (2*int(q)+int(p))):
                    terms.append('('+('q' if q else '!q')+' && '+('p' if p else '!p')+')')
            return rule(['p','q'],' || '.join(terms) if terms else 'false')
        for am,bm in itertools.product(range(16),repeat=2):
            # Direct table oracle has no WPL parser or product translation.
            step=lambda a,b:(bool(am & (1 << (2*int(a)+int(b)))),bool(bm & (1 << (2*int(b)+int(a)))))
            initial=(bool(am & 1),bool(bm & 1));queue=[initial];distance={initial:0}
            for state in queue:
                target=step(*state)
                if target not in distance:distance[target]=distance[state]+1;queue.append(target)
            forbidden=(bool(am & 2),bool(bm & 2));goal=(bool(am & 4),bool(bm & 4))
            values=lambda t:{'a.q':t[0],'b.q':t[1]}
            inv='!('+('a.q' if forbidden[0] else '!a.q')+' && '+('b.q' if forbidden[1] else '!b.q')+')'
            spec=dict(components={n:dict(state=['q'],inputs=['p'],next={'q':table_rule(mask)}) for n,mask in [('a',am),('b',bm)]},
                wires={'a.p':'b.q','b.p':'a.q'},events=[],initial=[values(initial)],
                invariant=rule(['a.q','b.q'],inv),goals=[values(goal)],max_atp=10000)
            raw=co.create(spec);r=co.verify(raw,lab.identity(raw))
            expected='counterexample' if forbidden in distance else 'goal_unreachable' if goal not in distance else 'established'
            with self.subTest(a=am,b=bm):
                self.assertEqual(r['status'],expected)
                graph=r['check']
                if expected=='counterexample':
                    self.assertEqual(len(graph['trace']['steps']),distance[forbidden])
                    end=graph['trace']['steps'][-1]['state'] if graph['trace']['steps'] else graph['trace']['initial']
                    self.assertEqual(end,values(forbidden))
                else:
                    self.assertEqual(graph['reachable'],[values(t) for t in queue])
                    self.assertEqual(graph['checked_edges'],len(queue))
                    if expected=='established':self.assertEqual(len(graph['goal_witnesses'][0]['trace']['steps']),distance[goal])
                    else:self.assertEqual(graph['unreached_goals'],[values(goal)])

    def test_cli_offline_match_success_failure_quota_and_no_child_on_refusal(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);raw=co.create(delivery());path=root/'composition.json';path.write_bytes(raw)
            anchor=lab.identity(raw);unpacked=root/'offline';desc=co.unpack(raw,unpacked)
            cli=[sys.executable,'-I','-m','stargate'];offline=[sys.executable,'-I','-S',str(unpacked/'replay.py')]
            def run(command,code):
                result=subprocess.run(command,cwd='/',capture_output=True,text=True)
                self.assertEqual(result.returncode,code,result.stdout+result.stderr)
                return json.loads(result.stdout or result.stderr)
            for quota,code in [(3,0),(0,3)]:
                a=run(cli+['composition-check',str(path),'--expect-composition',anchor,'--max-edges',str(quota)],code)
                b=run(offline+[str(path),'--composition','--expect-composition',anchor,'--expect-runtime',desc['runtime_digest'],'--max-edges',str(quota)],code)
                self.assertEqual(a,b)
            for expr,code in [('true',0),('!ack',4),('sent',4)]:
                p=root/'proposal.json';p.write_bytes(canon(proposal(raw,expr)));aout=root/('cli-'+expr);bout=root/('offline-'+expr)
                a=run(cli+['composition-change',str(path),str(p),'--expect-composition',anchor,'--output',str(aout)],code)
                b=run(offline+[str(p),str(bout),'--composition-change','--expect-composition',anchor,'--expect-runtime',desc['runtime_digest']],code)
                self.assertEqual(a,b)
                if code==0:self.assertEqual(aout.read_bytes(),bout.read_bytes())
                else:self.assertFalse(aout.exists());self.assertFalse(bout.exists())
            run(offline+[str(path),'--composition','--expect-composition','0'*64,'--expect-runtime',desc['runtime_digest']],2)
            spec=root/'spec.json';spec.write_text(json.dumps(delivery(),indent=2));created=root/'created'
            run(cli+['composition-create',str(spec),'--output',str(created)],0);self.assertEqual(created.read_bytes(),raw)
            # Hashes do not execute packet code; missing/foreign data keeps refusal classes.
            doc=decode(raw);doc['sources']['composition.py']+='\n# foreign';path.write_bytes(canon(doc))
            for command in [cli+['composition-check',str(path)],offline+[str(path),'--composition','--expect-runtime',desc['runtime_digest']]]:
                self.assertEqual(run(command+['--expect-composition',lab.identity(path.read_bytes())],3)['status'],'runtime_unavailable')
