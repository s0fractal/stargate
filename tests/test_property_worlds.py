from stargate import transport
import io
import json
from contextlib import redirect_stdout, redirect_stderr
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from stargate import lab, properties, invariants, lineage, search, compiler
from stargate import cli
from stargate.canonical import canon, decode, InvalidRecord


def rule(expr):return 'fact a: bool\nfact b: bool\ncheck '+expr


def obligations():
    return [dict(kind='monotone',input=n) for n in ('a','b')] + [
        dict(kind='case',facts={'a':False,'b':False},value=False),
        dict(kind='case',facts={'a':True,'b':True},value=True)]


def world(expr='a && b', **kw):
    return lab.create_world(rule(expr),['a','b'],properties=obligations(),**kw)


def check(raw,expr):
    return lab.verify_transition(raw,dict(parent=lab.identity(raw),candidate=rule(expr)))


class PropertyWorlds(unittest.TestCase):
    def test_behavior_can_change_only_under_explicit_contract(self):
        raw=world(); report,tip=check(raw,'a || b')
        self.assertEqual(report['status'],'satisfies')
        self.assertEqual((report['admitted'],report['changed_rows']),(True,2))
        self.assertEqual(report['max_atp'],{'parent':14,'candidate':14})
        self.assertEqual(decode(tip)['rule'],rule('a || b'))
        for key,value in decode(raw).items():
            if key not in ('rule','predecessor'):self.assertEqual(decode(tip).get(key),value)
        self.assertEqual(decode(tip)['predecessor'],lab.identity(raw))
        for role in ('parent','candidate'):
            self.assertEqual([x['status'] for x in report['property_results'][role]],['established']*4)
        strict=lab.create_world(rule('a && b'),['a','b'])
        report,tip=check(strict,'a || b')
        self.assertEqual((report['status'],report['admitted']),('counterexample',False))
        self.assertIsNone(tip)
        strict_doc=decode(strict);strict_doc['properties']=obligations()
        with self.assertRaises(InvalidRecord):lab.inspect_world(canon(strict_doc))

    def test_all_256_parent_candidate_pairs_against_truth_vectors(self):
        assignments=[dict(a=False,b=False),dict(a=False,b=True),dict(a=True,b=False),dict(a=True,b=True)]
        values=[[bool(f & (1 << i)) for i in range(4)] for f in range(16)]
        def program(v):
            terms=['('+('a' if d['a'] else '!a')+' && '+('b' if d['b'] else '!b')+')'
                   for d,x in zip(assignments,v) if x]
            return ' || '.join(terms) if terms else '(a && !a) || (b && !b)'
        def holds(v):
            return (not v[0] and v[3] and all(not v[a] or v[b] for a,b in ((0,2),(1,3),(0,1),(2,3))))
        accepted=0
        for p,pv in enumerate(values):
            raw=world(program(pv))
            for c,cv in enumerate(values):
                with self.subTest(parent=p,candidate=c):
                    r,tip=check(raw,program(cv))
                    expected='parent_rejected' if not holds(pv) else 'counterexample' if not holds(cv) else 'satisfies'
                    self.assertEqual(r['status'],expected)
                    self.assertEqual(r['admitted'],holds(pv) and holds(cv))
                    self.assertEqual(tip is not None,holds(pv) and holds(cv))
                    self.assertEqual(r['changed_rows'],sum(x!=y for x,y in zip(pv,cv)))
                    if tip is not None:accepted+=1
                    else:
                        vv=pv if r['program']=='parent' else cv
                        for row in r['witness']:
                            self.assertEqual(row['value'],vv[assignments.index(row['input'])])
                        prop=r['property']
                        if prop['kind']=='case':
                            self.assertEqual(r['witness'][0]['input'],prop['facts'])
                            self.assertNotEqual(r['witness'][0]['value'],prop['value'])
                        else:
                            low,high=r['witness']
                            self.assertEqual((low['value'],high['value']),(True,False))
                            self.assertFalse(low['input'][prop['input']]);self.assertTrue(high['input'][prop['input']])
        self.assertEqual(accepted,16)

    def test_case_selects_exact_assignment_not_a_reversed_or_partial_one(self):
        facts=[dict(a=False,b=False),dict(a=False,b=True),dict(a=True,b=False),dict(a=True,b=True)]
        for function in range(16):
            values=[bool(function & (1 << i)) for i in range(4)]
            rows=[dict(input=f,value=v) for f,v in zip(facts,values)]
            for i,assignment in enumerate(facts):
                for expected in (False,True):
                    p=dict(kind='case',facts=assignment,value=expected)
                    r=properties.assess(['a','b'],rows,p)
                    with self.subTest(function=function,input=i,expected=expected):
                        self.assertEqual(r['status'],'established' if values[i]==expected else 'counterexample')
                        self.assertEqual(r['checked'],1)
                        if values[i]!=expected:self.assertEqual(r['witness'],[rows[i]])
        raw=lab.create_world('check true',[],properties=[dict(kind='case',facts={},value=True)])
        r,tip=lab.verify_transition(raw,dict(parent=lab.identity(raw),candidate='check true'))
        self.assertEqual((r['status'],r['admitted']),('satisfies',True))
        names=list('abcdefgh'); expression=' || '.join(names)
        source=''.join('fact '+n+': bool\n' for n in names)+'check '+expression
        raw=lab.create_world(source,names,properties=[dict(kind='case',facts=dict.fromkeys(names,False),value=False)])
        r,tip=lab.verify_transition(raw,dict(parent=lab.identity(raw),candidate=source))
        self.assertEqual((r['status'],r['total_rows']),('satisfies',256))

    def test_cost_budget_and_checker_boundaries(self):
        r,tip=check(world(objective='lower_max_atp'),'a || b')
        self.assertFalse(r['admitted'])
        self.assertEqual((r['status'],r['reason']),('satisfies','not_strictly_cheaper'))
        self.assertIsNone(tip)
        r,tip=check(world('!!(a && b)',objective='lower_max_atp'),'a || b')
        self.assertTrue(r['admitted']);self.assertLess(r['max_atp']['candidate'],r['max_atp']['parent'])
        r,tip=check(world(max_atp=1),'a || b')
        self.assertEqual(r['status'],'incomplete');self.assertIsNone(tip)
        with patch.object(compiler,'compile_source',side_effect=compiler.CompilerBug('planted')):
            r,tip=check(world(),'a || b')
        self.assertEqual(r['status'],'checker_error');self.assertIsNone(tip)
        original=compiler.parse
        def wrong(source,inputs=None,**kw):return original(source.replace('||','&&'),inputs,**kw)
        raw=world()
        with patch.object(compiler,'parse',wrong):r,tip=check(raw,'a || b')
        self.assertEqual((r['status'],r['program']),('checker_error','candidate'))
        self.assertIsNone(tip)

    def test_contract_shape_and_proposal_cannot_weaken_it(self):
        for props in ([],{},obligations()*9,[obligations()[0]]*2,
                      [dict(kind='case',facts={'a':False},value=False)],
                      [dict(kind='case',facts={'a':False,'b':1},value=False)],
                      [dict(kind='case',facts={'a':False,'b':False},value=0)],
                      [dict(kind='monotone',input='x')]):
            with self.subTest(props=props),self.assertRaises(InvalidRecord):
                lab.create_world(rule('a && b'),['a','b'],properties=props)
        raw=world()
        for field,value in [('properties',[]),('objective','satisfy'),('contract','boolean-exhaustive-1')]:
            with self.subTest(field=field),self.assertRaises(InvalidRecord):
                lab.verify_transition(raw,dict(parent=lab.identity(raw),candidate=rule('a || b'),**{field:value}))
        with self.assertRaises(InvalidRecord):world(objective='equivalence')
        with self.assertRaises(InvalidRecord):lab.create_world(rule('a && b'),['a','b'],objective='satisfy')
        doc=decode(raw);del doc['properties']
        with self.assertRaises(InvalidRecord):lab.inspect_world(canon(doc))

    def test_observation_does_not_require_parent_to_satisfy_contract(self):
        raw=world('!(a && b)')
        r,tip=check(raw,'a || b')
        self.assertEqual(r['status'],'parent_rejected');self.assertIsNone(tip)
        found=invariants.discover(raw)
        self.assertEqual(found['status'],'complete')
        self.assertEqual([r['value'] for r in found['table']],[True,True,True,False])
        claim=dict(parent=lab.identity(raw),property=dict(kind='case',facts={'a':True,'b':True},value=False))
        r=invariants.verify_claim(raw,claim)
        self.assertEqual((r['status'],r['parent'],r['checked']),('established',lab.identity(raw),1))
        self.assertNotIn('admitted',r)

    def test_search_does_not_screen_allowed_behavior_changes(self):
        raw=world()
        r,tip=search.search(raw)
        self.assertEqual((r['status'],r['attempted'],r['full_checks'],r['screened']),('found',2,2,0))
        self.assertEqual(r['attempts'][0]['verification']['status'],'counterexample')
        self.assertEqual(r['experience']['counterexamples'],[])
        self.assertEqual(decode(tip)['rule'],rule('(a || b)'))
        memory=r['experience']
        r2,tip2=search.search(raw,experience=memory)
        self.assertEqual(tip2,tip)
        memory['counterexamples']=[dict(candidate=rule('a || b'),input={'a':False,'b':True})]
        with self.assertRaisesRegex(InvalidRecord,'equivalence counterexamples'):
            search.search(raw,experience=memory)
        r,tip=search.search(world('!(a && b)'))
        self.assertEqual((r['status'],r['full_checks']),('parent_rejected',1));self.assertIsNone(tip)

    def test_lineage_and_offline_enforce_properties(self):
        root=world(); proposal=dict(parent=lab.identity(root),candidate=rule('a || b'))
        r,history=lineage.append(lineage.create(root),proposal,lab.identity(root))
        self.assertEqual(r['status'],'verified_lineage')
        _,tip=lineage.verify(history,lab.identity(root))
        bad=dict(parent=lab.identity(tip),candidate=rule('!(a && b)'))
        r,failed=lineage.append(history,bad,lab.identity(root))
        self.assertEqual((r['status'],r['failed_step']),('not_admitted',1));self.assertIsNone(failed)
        altered=decode(history);altered['root']['properties']=obligations()[:2]
        with self.assertRaisesRegex(InvalidRecord,'recipient anchor'):
            lineage.verify(canon(altered),lab.identity(root))
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp);transport.unpack_lineage(history,path/'offline')
            args=[sys.executable,'-I','-S',str(path/'offline/replay.py'),str(path/'offline/lineage.json'),str(path/'tip.json'),
                  '--lineage','--expect-root',lab.identity(root),'--expect-runtime',lab.runtime_digest(decode(root)['sources'])]
            run=subprocess.run(args,cwd='/',capture_output=True,text=True)
            self.assertEqual(run.returncode,0,run.stderr)
            self.assertEqual((path/'tip.json').read_bytes(),tip)
            r,_=lineage.verify(history,lab.identity(root));self.assertEqual(json.loads(run.stdout),r)
            doc=decode(history);doc['proposals'].append(bad)
            (path/'offline/lineage.json').write_bytes(canon(doc));(path/'tip.json').unlink()
            run=subprocess.run(args,cwd='/',capture_output=True,text=True)
            self.assertEqual(run.returncode,4,run.stderr);self.assertFalse((path/'tip.json').exists())

    def test_cli_creates_inspects_and_classifies_contract(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp);(path/'rule.wpl').write_text(rule('a && b'))
            (path/'props.json').write_text(json.dumps(obligations()))
            def run(*args):
                out,err=io.StringIO(),io.StringIO()
                with redirect_stdout(out),redirect_stderr(err):code=cli.main(list(map(str,args)))
                return code,json.loads(out.getvalue() or err.getvalue())
            code,_=run('lab-create',path/'rule.wpl','--input','a','--input','b','--properties',path/'props.json','--output',path/'world.json')
            self.assertEqual(code,0);raw=(path/'world.json').read_bytes()
            code,r=run('inspect', '--expect-kind', 'lab',path/'world.json')
            self.assertEqual((code,r['contract'],r['objective'],r['properties']),(0,'boolean-properties-1','satisfy',obligations()))
            for expr,expected in [('a || b',0),('!(a && b)',4)]:
                (path/'proposal.json').write_text(json.dumps(dict(parent=lab.identity(raw),candidate=rule(expr))))
                code,r=run('lab-check',path/'world.json',path/'proposal.json')
                self.assertEqual(code,expected)
            # Empty contract is not silently interpreted as the equivalence default.
            for bad in ('[]','null'):
                (path/'props.json').write_text(bad)
                code,r=run('lab-create',path/'rule.wpl','--input','a','--input','b','--properties',path/'props.json','--output',path/'never.json')
                self.assertEqual((code,r['status']),(2,'invalid'));self.assertFalse((path/'never.json').exists())


if __name__=='__main__':unittest.main()
