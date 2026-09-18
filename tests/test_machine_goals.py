import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
from stargate import machine,lab,search,compiler
from stargate.canonical import canon,decode,InvalidRecord
from test_machine import table_rule,wpl


def world(expr='!q',goals=None,initials=(False,),invariant='true'):
    return machine.create(dict(state=['q'],events=[],initial=[dict(q=q) for q in initials],
        next={'q':wpl(['q'],expr)},invariant=wpl(['q'],invariant),max_atp=1000,
        goals=[dict(q=True)] if goals is None else goals))


class MachineGoals(unittest.TestCase):
    def test_freezing_is_refused_but_goals_cannot_be_removed_by_proposal(self):
        raw=world();anchor=lab.identity(raw)
        p=dict(parent=anchor,next={'q':wpl(['q'],'q')})
        report,child=machine.verify_change(raw,p,anchor)
        self.assertFalse(report['admitted'])
        self.assertEqual((report['status'],report['program'],report['admitted'],child),
                         ('goal_unreachable','candidate',False,None))
        self.assertEqual(report['checks']['candidate']['unreached_goals'],[dict(q=True)])
        self.assertNotIn('trace',report['checks']['candidate'])
        with self.assertRaises(InvalidRecord):machine.verify_change(raw,dict(p,goals=[]),anchor)
        p['next']={'q':wpl(['q'],'true')}
        report,child=machine.verify_change(raw,p,anchor)
        self.assertTrue(report['admitted']);self.assertEqual(decode(child)['goals'],[dict(q=True)])
        self.assertEqual(report['checks']['candidate']['goal_witnesses'],[dict(goal=dict(q=True),
            trace=dict(initial=dict(q=False),steps=[dict(event={},state=dict(q=True))]))])

    def test_all_one_bit_graphs_invariants_initials_and_goal_sets(self):
        for transition in range(4):
            table=[bool(transition&(1<<i)) for i in range(2)]
            for inv in range(4):
                safe=[bool(inv&(1<<i)) for i in range(2)]
                for initials in [(False,),(True,),(False,True)]:
                    reached=set(initials)
                    while not {table[int(q)] for q in reached}<=reached:reached|={table[int(q)] for q in reached}
                    for goal_mask in range(4):
                        goals=[dict(q=bool(i)) for i in range(2) if goal_mask&(1<<i)]
                        raw=machine.create(dict(state=['q'],events=[],initial=[dict(q=q) for q in initials],
                            next={'q':table_rule(['q'],table)},invariant=table_rule(['q'],safe),goals=goals,max_atp=1000))
                        r=machine.verify(raw,lab.identity(raw))
                        expected=('counterexample' if not all(safe[int(q)] for q in reached) else
                                  'goal_unreachable' if any(g['q'] not in reached for g in goals) else 'established')
                        self.assertEqual(r['status'],expected,(transition,inv,initials,goals))
                        if expected!='counterexample':
                            self.assertEqual([w['goal'] for w in r['goal_witnesses']],[g for g in goals if g['q'] in reached])
                            for witness in r['goal_witnesses']:
                                trace=witness['trace'];q=trace['initial']['q'];self.assertIn(q,initials)
                                for step in trace['steps']:
                                    q=table[int(q)];self.assertEqual(step,dict(event={},state=dict(q=q)))
                                self.assertEqual(dict(q=q),witness['goal'])
                                self.assertEqual(len(trace['steps']),0 if q in initials else 1)

    def test_incomplete_graph_does_not_claim_goals_missing_or_satisfied(self):
        raw=world();anchor=lab.identity(raw)
        report=machine.verify(raw,anchor,max_edges=1)
        self.assertEqual(report['status'],'incomplete')
        self.assertIn(dict(q=True),report['reachable'])
        self.assertNotIn('goal_witnesses',report);self.assertNotIn('unreached_goals',report)
        with patch.object(machine,'_witness',side_effect=compiler.CompilerBug('broken trace')):
            self.assertEqual(machine.verify(raw,anchor)['status'],'checker_error')

    def test_goals_are_existential_and_initial_goals_need_no_transition(self):
        raw=world('q',initials=(False,True));r=machine.verify(raw,lab.identity(raw))
        self.assertEqual(r['status'],'established')
        self.assertEqual(r['goal_witnesses'],[dict(goal=dict(q=True),trace=dict(initial=dict(q=True),steps=[]))])
        # q=false never reaches q=true; the OTHER allowed initial state suffices.

    def test_unsafe_or_unreachable_parent_cannot_be_repaired_as_a_child(self):
        raw=world('q');anchor=lab.identity(raw)
        report,child=machine.verify_change(raw,dict(parent=anchor,next={'q':wpl(['q'],'true')}),anchor)
        self.assertEqual((report['status'],report['program'],child),('parent_rejected','parent',None))
        self.assertEqual(report['checks']['parent']['status'],'goal_unreachable')
        report,child=search.search_machine(raw,anchor)
        self.assertEqual((report['status'],child),('parent_rejected',None))

    def test_observation_drops_goals_without_admitting_that_view(self):
        raw=world('q');anchor=lab.identity(raw)
        report=machine.discover_properties(raw,anchor)
        self.assertEqual(report['status'],'complete');self.assertEqual(report['machine_id'],anchor)
        self.assertNotIn('successor',report);self.assertEqual(report['observation']['goal_witnesses'],[])
        self.assertEqual(decode(raw)['goals'],[dict(q=True)])

    def test_search_never_learns_unreachable_goals_as_safety_counterexamples(self):
        raw=world();anchor=lab.identity(raw)
        with patch.object(search,'machine_candidates',return_value=iter([{'q':wpl(['q'],'q')}])):
            report,child=search.search_machine(raw,anchor,max_candidates=2)
        self.assertEqual(report['status'],'neighborhood_exhausted');self.assertIsNone(child)
        self.assertEqual(report['attempts'][0]['status'],'goal_unreachable')
        self.assertEqual(report['experience']['counterexamples'],[])

    def test_goal_shape_and_runtime_before_schema(self):
        raw=world();doc=decode(raw)
        for goals in [None,{},[{}],[dict(q=1)],[dict(q=True)]*2,[dict(extra=False)]]:
            with self.assertRaises(InvalidRecord):machine.inspect(canon(dict(doc,goals=goals)))
        del doc['goals']
        with self.assertRaises(InvalidRecord):machine.inspect(canon(doc))
        doc['sources']['machine.py']+='\n# older runtime'
        with self.assertRaises(lab.RuntimeMismatch):machine.inspect(canon(doc))
        spec={k:decode(raw)[k] for k in ['state','events','initial','next','invariant','max_atp']}
        self.assertEqual(decode(machine.create(spec))['goals'],[])

    def test_cli_and_offline_agree_on_goal_refusal_and_witnesses(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);raw=world();offline=root/'offline';desc=machine.unpack(raw,offline)
            path=root/'world'
            for packet,code,status in [(raw,0,'established'),(world('q'),4,'goal_unreachable')]:
                path.write_bytes(packet);outputs=[]
                for command in ([sys.executable,'-I','-m','stargate','machine-check',str(path)],
                    [sys.executable,'-I','-S',str(offline/'replay.py'),str(path),'--machine','--expect-runtime',desc['runtime_digest']]):
                    r=subprocess.run(command+['--expect-machine',lab.identity(packet)],cwd='/',capture_output=True,text=True)
                    self.assertEqual(r.returncode,code,r.stderr);report=json.loads(r.stdout)
                    self.assertEqual(report['status'],status);outputs.append(report)
                self.assertEqual(outputs[0],outputs[1])
            proposal=root/'proposal';proposal.write_text(json.dumps(dict(parent=lab.identity(raw),next={'q':wpl(['q'],'q')})))
            output=root/'child'
            r=subprocess.run([sys.executable,'-I','-S',str(offline/'replay.py'),str(proposal),str(output),'--machine-change',
                '--expect-machine',lab.identity(raw),'--expect-runtime',desc['runtime_digest']],capture_output=True,text=True)
            self.assertEqual(r.returncode,4,r.stderr);self.assertFalse(output.exists())
            self.assertEqual(json.loads(r.stdout)['status'],'goal_unreachable')
