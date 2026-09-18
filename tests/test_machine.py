import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
from contextlib import redirect_stdout, redirect_stderr

from stargate import machine, lab, compiler, boolean, kernel, cli
from stargate.canonical import canon, decode, InvalidRecord


def wpl(names, expr):
    return ''.join('fact '+n+': bool\n' for n in names)+'check '+expr


def table_rule(names, table):
    parts=[]
    for index,value in enumerate(table):
        if value:
            parts.append('('+' && '.join(n if index & (1 << (len(names)-j-1)) else '!'+n
                                        for j,n in enumerate(names))+')')
    expr=' || '.join(parts) if parts else '('+names[0]+' && !'+names[0]+')'
    # Ensure constants also use every name without altering the truth table.
    expr='('+expr+')'+''.join(' && ('+n+' || !'+n+')' for n in names if not parts)
    return wpl(names,expr)


def simple(next_expr='q || e', invariant='q', initial=True):
    return machine.create(dict(state=['q'],events=['e'],initial=[dict(q=initial)],
        next={'q':wpl(['e','q'],next_expr)},invariant=wpl(['q'],invariant),max_atp=1000))


def check(raw, **kw): return machine.verify(raw,lab.identity(raw),**kw)


def branching_machine(edges, bad):
    # A..F are literal integers 0..5, encoded in a,b,c; z chooses the edge.
    names = ['a', 'b', 'c', 'z']
    bits = lambda state: dict(a=bool(state & 4), b=bool(state & 2), c=bool(state & 1))
    targets = [edges.get((index >> 1, bool(index & 1)), index >> 1) for index in range(16)]
    rules = {name: table_rule(names, [bool(target & mask) for target in targets])
             for name, mask in zip(['a', 'b', 'c'], [4, 2, 1])}
    raw = machine.create(dict(state=['a', 'b', 'c'], events=['z'], initial=[bits(0)],
        next=rules, invariant=table_rule(['a', 'b', 'c'], [state not in bad for state in range(8)]),
        max_atp=1000))
    return raw, bits


class Machine(unittest.TestCase):
    def test_all_one_bit_event_machines_against_independent_graph(self):
        for mask in range(16):
            transitions=[bool(mask & (1 << index)) for index in range(4)]
            for inv_mask in range(4):
                safe=[bool(inv_mask & (1 << index)) for index in range(2)]
                for initials in ([False],[True],[False,True]):
                    with self.subTest(mask=mask,invariant=inv_mask,initials=initials):
                        raw=machine.create(dict(state=['q'],events=['e'],initial=[dict(q=q) for q in initials],
                            next={'q':table_rule(['e','q'],transitions)},
                            invariant=table_rule(['q'],safe),max_atp=1000))
                        reachable=set(initials)
                        while True:
                            expanded=reachable | {transitions[2*int(e)+int(q)] for q in reachable for e in (False,True)}
                            if expanded==reachable:break
                            reachable=expanded
                        expected=all(safe[int(q)] for q in reachable)
                        result=check(raw)
                        self.assertEqual(result['status'],'established' if expected else 'counterexample')
                        if expected:
                            self.assertEqual({s['q'] for s in result['reachable']},reachable)
                            self.assertEqual(result['checked_invariants'],len(reachable))
                            self.assertEqual(result['checked_edges'],2*len(reachable))
                        else:
                            trace=result['trace'];q=trace['initial']['q']
                            self.assertIn(q,initials)
                            for step in trace['steps']:
                                self.assertTrue(safe[int(q)])
                                q=transitions[2*int(step['event']['e'])+int(q)]
                                self.assertEqual(step['state'],dict(q=q))
                            self.assertFalse(safe[int(q)])

    def test_synchronous_updates_and_shortest_delayed_counterexample(self):
        raw=machine.create(dict(state=['a','b'],events=[],initial=[dict(a=False,b=False)],
            next={'a':wpl(['a','b'],'b && (a || !a)'),
                  'b':wpl(['a','b'],'!a && (b || !b)')},
            invariant=wpl(['a','b'],'!a && (b || !b)'),max_atp=1000))
        r=check(raw)
        self.assertEqual(r['status'],'counterexample')
        self.assertEqual(r['trace'],dict(initial=dict(a=False,b=False),steps=[
            dict(event={},state=dict(a=False,b=True)),dict(event={},state=dict(a=True,b=True))]))
        self.assertEqual(r['checked_edges'],2)
        self.assertEqual(r['checked_invariants'],3)
        # In-place updates would produce 10 instead of synchronous 11.
        self.assertEqual(r['edges'][-1]['next'],dict(a=True,b=True))

    def test_fifo_finds_two_step_violation_before_three_step_branch(self):
        # A→B→F(bad), A→C→D→E(bad). LIFO follows C first and returns length 3.
        edges = {(0, False): 1, (0, True): 2,
                 (1, False): 5, (1, True): 5,
                 (2, False): 3, (2, True): 3,
                 (3, False): 4, (3, True): 4}
        raw, bits = branching_machine(edges, {4, 5})
        result = check(raw)
        self.assertEqual(result['status'], 'counterexample')
        self.assertEqual(result['trace'], dict(initial=bits(0), steps=[
            dict(event={'z': False}, state=bits(1)),
            dict(event={'z': False}, state=bits(5))]))

    def test_rediscovery_preserves_first_parent_and_shortest_trace(self):
        # A→B→E→F(bad), A→C→B. Reparenting B through C lengthens the witness.
        edges = {(0, False): 1, (0, True): 2,
                 (1, False): 4, (1, True): 4,
                 (2, False): 1, (2, True): 1,
                 (4, False): 5, (4, True): 5}
        raw, bits = branching_machine(edges, {5})
        result = check(raw)
        self.assertEqual(result['status'], 'counterexample')
        self.assertEqual(result['trace'], dict(initial=bits(0), steps=[
            dict(event={'z': False}, state=bits(1)),
            dict(event={'z': False}, state=bits(4)),
            dict(event={'z': False}, state=bits(5))]))
        # Prove this fixture actually traverses the rediscovery edge C→B.
        self.assertIn(dict(state=bits(2), event={'z': False}, next=bits(1)), result['edges'])

    def test_cyclic_witness_ancestry_is_bounded_checker_error(self):
        states = {(False,): {'q': False}, (True,): {'q': True}}
        parents = {(False,): ((True,), {}), (True,): ((False,), {})}
        real = machine._witness
        with self.assertRaisesRegex(compiler.CompilerBug, 'exceeds reachable states'):
            real((True,), states, parents)
        # N nodes / N-1 edges is legitimate; the guard must not truncate it.
        parents[(False,)] = None
        self.assertEqual(real((True,), states, parents),
                         dict(initial={'q': False}, steps=[dict(event={}, state={'q': True})]))
        parents[(False,)] = ((True,), {})
        with patch.object(machine, '_witness', side_effect=lambda *_: real((True,), states, parents)):
            result = check(simple(initial=False))
        self.assertEqual(result['status'], 'checker_error')
        self.assertEqual(result['reason'], 'witness ancestry exceeds reachable states')
        self.assertNotIn('trace', result)

    def test_unreachable_bad_states_do_not_refute_and_self_loops_close(self):
        raw=simple()
        r=check(raw)
        self.assertEqual(r['status'],'established')  # q=false violates invariant but is unreachable
        self.assertEqual(r['reachable'],[dict(q=True)])
        self.assertEqual(r['checked_edges'],2)
        self.assertEqual([e['event'] for e in r['edges']],[dict(e=False),dict(e=True)])
        doc=decode(raw);doc['initial'].append(dict(q=False))
        r=check(canon(doc))
        self.assertEqual(r['status'],'counterexample')
        self.assertEqual(r['trace'],dict(initial=dict(q=False),steps=[]))

    def test_quota_exact_completion_and_initial_violation_precede_edges(self):
        raw=simple()
        for quota in (0,1):
            result=check(raw,max_edges=quota)
            self.assertEqual((result['status'],result['reason'],result['checked_edges']),('incomplete','edge_quota',quota))
            self.assertNotIn('trace',result)
        self.assertEqual(check(raw,max_edges=2)['status'],'established')
        self.assertEqual(check(simple(initial=False),max_edges=0)['status'],'counterexample')
        for bad in (-1,257,True,1.0):
            with self.assertRaises(InvalidRecord):check(raw,max_edges=bad)

    def test_initial_invariant_and_transition_resource_failures_are_not_refutations(self):
        raw=simple()
        original=compiler.compile_source
        for at in (1,2):
            calls=[]
            def fail(source,**kw):
                calls.append(source)
                if len(calls)==at:raise kernel.ResourceFault('local bound')
                return original(source,**kw)
            with patch.object(compiler,'compile_source',side_effect=fail):r=check(raw)
            self.assertEqual(r['status'],'incomplete')
            self.assertNotIn('trace',r)
        low=decode(raw);low['max_atp']=0
        self.assertEqual(check(canon(low))['status'],'incomplete')
        with patch.object(compiler,'compile_source',side_effect=compiler.CompilerBug('bad lowering')):
            self.assertEqual(check(raw)['status'],'checker_error')
        real=boolean.evaluate
        with patch.object(boolean,'evaluate',side_effect=lambda code,facts:not real(code,facts)):
            r=check(raw)
        self.assertEqual(r['status'],'checker_error')
        self.assertEqual(r['reason'],'machine independent oracle disagreement')

    def test_enumeration_fault_is_checker_error_not_safety(self):
        raw=simple()
        for events in ([],[(False,)],[(False,),(False,)],[(True,),(False,)]):
            with patch.object(machine.itertools,'product',return_value=events):r=check(raw)
            self.assertEqual(r['status'],'checker_error')
            self.assertNotIn('trace',r)

    def test_final_coverage_guard_rejects_missing_duplicate_and_open_edges(self):
        report=check(simple())
        closed=lambda r:machine._closed(r,{(True,):dict(q=True)},['q'],['e'],[(False,),(True,)])
        self.assertTrue(closed(report))
        mutations=[lambda r:r['edges'].pop(),
                   lambda r:r['edges'].__setitem__(1,r['edges'][0]),
                   lambda r:r['edges'][0].update(next=dict(q=False)),
                   lambda r:r.update(checked_edges=1),lambda r:r.update(checked_invariants=0)]
        for mutate in mutations:
            altered=decode(canon(report));mutate(altered)
            with self.subTest(mutate=mutate):self.assertFalse(closed(altered))
        with patch.object(machine,'_closed',return_value=False):r=check(simple())
        self.assertEqual(r['status'],'checker_error')
        self.assertEqual(r['reason'],'reachable graph is not fully checked')

    def test_shape_runtime_anchor_and_inspection_do_no_evaluation(self):
        raw=simple()
        edits=[lambda d:d.update(state=[]),lambda d:d.update(events=['q']),
               lambda d:d.update(initial=[]),lambda d:d['initial'].append(d['initial'][0]),
               lambda d:d['initial'][0].update(q=1),lambda d:d.update(next={}),
               lambda d:d.update(proof='yes'),lambda d:d.update(stargate_machine=True),
               lambda d:d.update(guide='different')]
        with patch.object(compiler,'compile_source',side_effect=AssertionError('must not evaluate')):
            self.assertEqual(machine.describe(raw)['status'],'unchecked_machine')
            with self.assertRaisesRegex(InvalidRecord,'recipient anchor'):machine.verify(raw,'0'*64)
            for edit in edits:
                doc=decode(raw);edit(doc)
                with self.subTest(edit=edit),self.assertRaises(InvalidRecord):machine.inspect(canon(doc))
            with self.assertRaises(InvalidRecord):machine.inspect(raw+b'\n')
            old=decode(raw);old['sources']['machine.py']+='\n# other runtime'
            with self.assertRaises(lab.RuntimeMismatch):machine.inspect(canon(old))

    def test_cli_offline_agree_on_safe_trace_quota_anchor_and_foreign_runtime(self):
        raw=simple();bad=simple(next_expr='q && !e')
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);offline=root/'offline';desc=machine.unpack(raw,offline)
            self.assertEqual(desc['status'],'unchecked_machine')
            self.assertEqual((offline/'machine.json').stat().st_mode & 0o777,0o600)
            path=root/'input.json'
            cases=[(raw,256,lab.identity(raw),0,'established'),
                   (bad,256,lab.identity(bad),4,'counterexample'),
                   (raw,1,lab.identity(raw),3,'incomplete'),
                   (raw,256,'0'*64,2,'invalid')]
            changed=decode(raw);changed['sources']['machine.py']+='\n# changed'
            cases.append((canon(changed),256,lab.identity(canon(changed)),3,'runtime_unavailable'))
            for data,quota,anchor,code,status in cases:
                path.write_bytes(data);results=[]
                for command in ([sys.executable,'-I','-m','stargate','machine-check',str(path),
                                 '--expect-machine',anchor,'--max-edges',str(quota)],
                                [sys.executable,'-I','-S',str(offline/'replay.py'),str(path),'--machine',
                                 '--expect-machine',anchor,'--max-edges',str(quota),
                                 '--expect-runtime',desc['runtime_digest']]):
                    result=subprocess.run(command,cwd='/',capture_output=True,text=True)
                    self.assertNotIn('Traceback',result.stderr)
                    report=json.loads(result.stdout or result.stderr)
                    self.assertEqual((result.returncode,report['status']),(code,status))
                    results.append(report)
                self.assertEqual(results[0],results[1])
            with self.assertRaises(FileExistsError):machine.unpack(raw,offline)
            self.assertTrue((offline/'machine.json').exists())

    def test_cli_create_and_readonly_inspect(self):
        doc=decode(simple());spec={k:doc[k] for k in ('state','events','initial','next','invariant','max_atp')}
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'spec';output=Path(tmp)/'machine'
            path.write_text(json.dumps(spec,indent=2))
            with redirect_stdout(io.StringIO()),redirect_stderr(io.StringIO()):
                code=cli.main(['machine-create',str(path),'--output',str(output)])
            self.assertEqual(code,0);self.assertEqual(output.read_bytes(),machine.create(spec))
            out=io.StringIO()
            with redirect_stdout(out),patch.object(compiler,'compile_source',side_effect=AssertionError('inspect')):
                code=cli.main(['machine-inspect',str(output)])
            self.assertEqual((code,json.loads(out.getvalue())['status']),(0,'unchecked_machine'))
            path.write_text('{"state": [], "state": ["q"]}')
            with redirect_stdout(io.StringIO()),redirect_stderr(io.StringIO()):
                code=cli.main(['machine-create',str(path),'--output',str(Path(tmp)/'bad')])
            self.assertEqual(code,2)
            self.assertFalse((Path(tmp)/'bad').exists())
