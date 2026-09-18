import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from stargate import invariants as inv, lab, compiler
from stargate.canonical import canon, decode, InvalidRecord


def world(expr='a && (b || !b)', **kwargs):
    return lab.create_world('fact a: bool\nfact b: bool\ncheck '+expr,['a','b'],**kwargs)


def claim(raw, kind, **kw):
    return dict(parent=lab.identity(raw), property=dict(kind=kind, **kw))


class Invariants(unittest.TestCase):
    def test_discovery_finds_real_semantic_irrelevance_and_rechecks(self):
        raw=world(objective='lower_max_atp')
        with patch.object(lab,'verify_transition', wraps=lab.verify_transition) as gate:
            result=inv.discover(raw)
        self.assertEqual(gate.call_count,1)
        self.assertEqual(result['status'],'complete')
        self.assertEqual((result['total_rows'],result['hypotheses']),(4,6))
        self.assertEqual([r['status'] for r in result['results']],
                         ['counterexample','counterexample','counterexample','established','established','established'])
        self.assertEqual([r['value'] for r in result['table']],[False,False,True,True])
        self.assertEqual(result['table_digest'],lab.identity(canon(result['table'])))
        for discovered in result['results']:
            checked=inv.verify_claim(raw,discovered['claim'])
            for field in discovered:
                self.assertEqual(checked[field],discovered[field])
            self.assertNotIn('admitted',checked)
            self.assertNotIn('successor',checked)
        independent=inv.verify_claim(raw,claim(raw,'independent',input='b'))
        self.assertEqual((independent['status'],independent['checked']),('established',2))

    def test_all_six_properties_of_all_sixteen_two_input_functions(self):
        assignments=[{'a':False,'b':False},{'a':False,'b':True},
                     {'a':True,'b':False},{'a':True,'b':True}]
        for function in range(16):
            values=[bool(function & (1 << i)) for i in range(4)]
            terms=['('+('a' if d['a'] else '!a')+' && '+('b' if d['b'] else '!b')+')'
                   for d,v in zip(assignments,values) if v]
            expr=' || '.join(terms) if terms else '(a && !a) || (b && !b)'
            raw=world(expr)
            report=inv.discover(raw)
            self.assertEqual(report['status'],'complete')
            pairs={'a':[(0,2),(1,3)], 'b':[(0,1),(2,3)]}
            expected=[not any(values),all(values)]
            for name in ('a','b'):
                expected.extend([all(values[x]==values[y] for x,y in pairs[name]),
                                 all(not values[x] or values[y] for x,y in pairs[name])])
            for r,holds in zip(report['results'],expected):
                with self.subTest(function=function,prop=r['claim']['property']):
                    self.assertEqual(r['status'],'established' if holds else 'counterexample')
                    if holds:
                        self.assertEqual(r['checked'],4 if r['claim']['property']['kind']=='constant' else 2)
                    else:
                        for row in r['witness']:
                            self.assertEqual(row['value'],values[assignments.index(row['input'])])
                        prop=r['claim']['property']
                        if prop['kind']=='constant':
                            self.assertNotEqual(r['witness'][0]['value'],prop['value'])
                        else:
                            left,right=r['witness']
                            self.assertFalse(left['input'][prop['input']]);self.assertTrue(right['input'][prop['input']])
                            self.assertEqual({n:v for n,v in left['input'].items() if n!=prop['input']},
                                             {n:v for n,v in right['input'].items() if n!=prop['input']})
                            if prop['kind']=='monotone':
                                self.assertEqual((left['value'],right['value']),(True,False))
                            else: self.assertNotEqual(left['value'],right['value'])

    def test_eight_inputs_and_zero_inputs(self):
        names=list('abcdefgh')
        raw=lab.create_world(''.join('fact '+n+': bool\n' for n in names)+'check '+' || '.join(names),names)
        report=inv.discover(raw)
        self.assertEqual((report['status'],report['total_rows'],len(report['results'])),('complete',256,18))
        self.assertEqual(sum(r['status']=='established' for r in report['results']),8)
        raw=lab.create_world('check true',[])
        report=inv.discover(raw)
        self.assertEqual([r['status'] for r in report['results']],['counterexample','established'])
        self.assertEqual(report['total_rows'],1)

    def test_binding_shape_and_no_computed_fields(self):
        raw=world()
        for bad in [dict(parent='0'*64,property={'kind':'constant','value':True}),
                    claim(raw,'constant',value=1),claim(raw,'constant',value=True,verdict='established'),
                    claim(raw,'independent',input='missing'),claim(raw,'unknown'),
                    dict(claim(raw,'monotone',input='a'),proof='trusted'),
                    claim(raw,'independent',input=['a'])]:
            with self.subTest(bad=bad),self.assertRaises(InvalidRecord): inv.verify_claim(raw,bad)
        doc=decode(raw);doc['sources']['invariants.py']+='\n# modified\n'
        with self.assertRaises(lab.RuntimeMismatch): inv.discover(canon(doc))

    def test_incomplete_and_checker_fault_establish_nothing(self):
        raw=world(max_atp=1)
        self.assertEqual(inv.discover(raw)['status'],'incomplete')
        self.assertEqual(inv.discover(raw)['results'],[])
        self.assertEqual(inv.verify_claim(raw,claim(raw,'independent',input='b'))['status'],'incomplete')
        with self.assertRaises(InvalidRecord): inv.verify_claim(raw,claim(raw,'independent',input='no'))
        raw=world('a || b');original=compiler.parse
        def broken(source,inputs=None,**kw):return original(source.replace('||','&&'),inputs,**kw)
        with patch.object(compiler,'parse',broken):
            r=inv.discover(raw)
        self.assertEqual((r['status'],r['results']),('checker_error',[]))
        checked,_=lab.verify_transition(raw,{'parent':lab.identity(raw),'candidate':decode(raw)['rule']})
        for rows in (checked['rows'][:-1],list(reversed(checked['rows'])),[checked['rows'][0]]*4):
            with patch.object(lab,'verify_transition',return_value=(dict(checked,rows=rows),None)):
                self.assertEqual(inv.verify_claim(raw,claim(raw,'constant',value=True))['status'],'checker_error')
                self.assertEqual(inv.discover(raw)['status'],'checker_error')

    def test_cli_and_standalone_claim_replay(self):
        raw=world()
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);(root/'world.json').write_bytes(raw)
            lab.unpack_world(raw,root/'offline')
            def cli(*args):
                p=subprocess.run([sys.executable,'-I','-m','stargate',*map(str,args)],cwd='/',capture_output=True,text=True)
                return p.returncode,json.loads(p.stdout or p.stderr)
            code,r=cli('lab-discover',root/'world.json','--output',root/'catalog.json')
            self.assertEqual((code,r['status']),(0,'complete'))
            self.assertEqual(decode((root/'catalog.json').read_bytes()),r)
            for prop,expected in [('b',0),('a',4)]:
                c=claim(raw,'independent',input=prop);(root/'claim.json').write_text(json.dumps(c))
                code,r=cli('lab-check-invariant',root/'world.json',root/'claim.json')
                self.assertEqual(code,expected)
                p=subprocess.run([sys.executable,'-I','-S',str(root/'offline/replay.py'),
                    '--expect-runtime',lab.runtime_digest(decode(raw)['sources']),'--invariant',str(root/'claim.json')],
                    cwd='/',capture_output=True,text=True)
                self.assertEqual(p.returncode,expected,p.stderr)
                self.assertEqual(json.loads(p.stdout),r)
            small=world(max_atp=1);(root/'world.json').write_bytes(small)
            code,r=cli('lab-discover',root/'world.json','--output',root/'missing.json')
            self.assertEqual((code,r['status']),(3,'incomplete'))
            self.assertFalse((root/'missing.json').exists())
            self.assertFalse((root/'.stargate').exists())


if __name__=='__main__':unittest.main()
