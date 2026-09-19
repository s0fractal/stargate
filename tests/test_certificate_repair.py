import copy
import itertools
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from stargate import certificate as c, lab
from stargate.canonical import canon, decode, InvalidRecord


def model(next='x', invariant='true', goals=None):
    rule=lambda expr: 'fact x: bool\ncheck '+expr
    return dict(language='boolean-machine-1', state=['x'], events=[], initial=[{'x':False}],
                next={'x':rule(next)}, invariant=rule(invariant),
                goals=[{'x':True}] if goals is None else goals)


def cert(m, states=(False, True)):
    return canon(dict(certificate=1, checker=c.checker_id(), model=m,
        states=[{'x':v} for v in states], paths=[dict(goal=g, trace=dict(initial={'x':False},
        steps=[] if not g['x'] else [dict(event={},state={'x':True})])) for g in m['goals']]))


def objection(m, unsafe=False):
    claim=(dict(kind='unsafe', trace=dict(initial={'x':False}, steps=[dict(event={},state={'x':True})]))
           if unsafe else dict(kind='unreachable_goal', goal=m['goals'][0], states=[{'x':False}]))
    return canon(dict(refutation=1, checker=c.checker_id(),model=m,claim=claim))


class Repair(unittest.TestCase):
    def pair(self, unsafe=False):
        parent=model('!x','!x',[]) if unsafe else model()
        child=model('x','!x',[]) if unsafe else model('!x')
        return objection(parent,unsafe), cert(child,(False,) if unsafe else (False,True))

    def check(self, packet, **kw):
        doc=decode(packet)
        return c.verify_repair(packet,c.identity(doc['refutation']['model']),c.checker_id(),**kw)

    def test_both_defects_repaired_full_certificate_and_history_root(self):
        for unsafe in (False,True):
            ref,child=self.pair(unsafe)
            packet=c.pack_repair(ref,child)
            report,out=self.check(packet)
            self.assertEqual(report['status'],'verified_repair')
            self.assertEqual(c.exit_code(report),0)
            self.assertEqual(out,child)
            self.assertEqual(report['refutation_id'],c.identity(decode(ref)))
            self.assertEqual(report['successor_model'],c.identity(decode(child)['model']))
            self.assertEqual(report['successor_certificate'],c.identity(decode(child)))
            self.assertEqual([x['report']['status'] for x in report['checks']],
                             ['verified_refutation','verified_certificate'])
            history=c.start_history(out)
            hr,tip=c.verify_history(history,report['successor_model'],c.checker_id())
            self.assertEqual(hr['status'],'verified_history');self.assertEqual(tip,out)
            with self.assertRaises(InvalidRecord):c.inspect_change(packet)

    def test_packing_does_not_establish_objection_or_repair(self):
        ref,child=self.pair()
        false_ref=decode(ref);false_ref['claim']['states']=[{'x':True}]
        bad_child=decode(child);bad_child['model']['next']['x']='fact x: bool\ncheck x'
        for a,b in ((canon(false_ref),child),(ref,canon(bad_child))):
            packet=c.pack_repair(a,b)
            with self.assertRaises(InvalidRecord):self.check(packet)
        # A no-op cannot fix a genuinely refuted parent.
        bad_child['model']=decode(ref)['model']
        with self.assertRaises(InvalidRecord):self.check(c.pack_repair(ref,canon(bad_child)))

    def test_every_protected_field_and_parent_anchor(self):
        ref,child=self.pair()
        replacements=dict(language='other',state=['y'],events=['e'],initial=[{'x':True}],
                          invariant='fact x: bool\ncheck true || x',goals=[])
        for field,value in replacements.items():
            doc=decode(child);doc['model'][field]=value
            # Keep the modified certificate structurally well-formed wherever possible.
            if field=='goals':doc['paths']=[]
            if field=='events':
                doc['paths'][0]['trace']['steps'][0]['event']={'e':False}
                doc['model']['next']['x']='fact e: bool\n'+doc['model']['next']['x']
            if field=='initial':doc['paths'][0]['trace']={'initial':{'x':True},'steps':[]}
            if field=='state':
                def rename(v):
                    if isinstance(v,dict):return {('y' if k=='x' else k):rename(x) for k,x in v.items()}
                    if isinstance(v,list):return [rename(x) for x in v]
                    return v.replace('x','y') if isinstance(v,str) else v
                doc=rename(doc)
            if field != 'language':
                self.assertEqual(c.verify(canon(doc),c.identity(doc['model']),c.checker_id())['status'],'verified_certificate')
            with self.subTest(field=field),self.assertRaises(InvalidRecord):
                self.check(c.pack_repair(ref,canon(doc)))
        with self.assertRaisesRegex(InvalidRecord,'anchor'):
            c.verify_repair(c.pack_repair(ref,child),'0'*64,c.checker_id())

    def test_both_proofs_required_with_separate_quotas_and_checker_pins(self):
        ref,child=self.pair();packet=c.pack_repair(ref,child)
        for quota,failed in ((0,'refutation'),(1,'candidate')):
            report,out=self.check(packet,max_steps=quota)
            self.assertEqual((report['status'],report.get('failed'),out),('incomplete',failed,None))
            self.assertEqual(c.exit_code(report),3)
        for role in ('refutation','candidate'):
            doc=decode(packet);doc[role]['checker']='0'*64
            report,out=self.check(canon(doc))
            self.assertEqual((report['status'],report.get('failed'),out),('checker_unavailable',role,None))
        for function,failed in (('verify_refutation','refutation'),('verify','candidate')):
            with patch.object(c,function,return_value={'status':'checker_error'}):
                report,out=self.check(packet)
                self.assertEqual((report['status'],report.get('failed'),out),('checker_error',failed,None))
        with self.assertRaises(InvalidRecord):self.check(packet,max_steps=True)

    def test_repair_must_restore_all_goals_not_only_refuted_one(self):
        # Parent's false state is already a goal; true is the refuted second goal.
        parent=model(goals=[{'x':False},{'x':True}]);ref=decode(objection(parent))
        ref['claim']['goal']={'x':True}
        child=model('!x',goals=parent['goals'])
        report,out=self.check(c.pack_repair(canon(ref),cert(child)))
        self.assertEqual(report['status'],'verified_repair')
        damaged=decode(cert(child));damaged['paths'][0]['trace']['initial']={'x':True}
        with self.assertRaises(InvalidRecord):self.check(c.pack_repair(canon(ref),canon(damaged)))

    def test_exhaustive_truth_tables_repair_exactly_safe_goal_reaching_candidates(self):
        exprs=['false','x','!x','true'];tables=[(False,False),(False,True),(True,False),(True,True)]
        def reachable(table):
            result=[False]
            while table[result[-1]] not in result:result.append(table[result[-1]])
            return result
        tested=accepted=0
        for pi,ci,ii,goal in itertools.product(range(4),range(4),range(4),(False,True)):
            pseen=reachable(tables[pi]);cseen=reachable(tables[ci])
            unsafe=next((s for s in pseen if not tables[ii][s]),None)
            if unsafe is None and goal in pseen:continue
            pm=model(exprs[pi],exprs[ii],[{'x':goal}]);cm=model(exprs[ci],exprs[ii],pm['goals'])
            if unsafe is not None:
                claim=dict(kind='unsafe',trace=dict(initial={'x':False},steps=[] if unsafe is False else [dict(event={},state={'x':True})]))
            else:claim=dict(kind='unreachable_goal',goal={'x':goal},states=[{'x':s} for s in pseen])
            ref=canon(dict(refutation=1,checker=c.checker_id(),model=pm,claim=claim))
            child=cert(cm,cseen);packet=c.pack_repair(ref,child)
            expected=all(tables[ii][s] for s in cseen) and goal in cseen
            tested+=1
            if expected:
                report,out=self.check(packet)
                self.assertEqual(report['status'],'verified_repair');self.assertEqual(out,child);accepted+=1
            else:
                with self.assertRaises(InvalidRecord):self.check(packet)
        self.assertGreater(tested,0);self.assertGreater(accepted,0)

    def test_shape_rejects_verdicts_wrong_roles_and_noncanonical_bytes(self):
        ref,child=self.pair();packet=c.pack_repair(ref,child)
        with self.assertRaises(InvalidRecord):c.pack_repair(child,ref)
        for field,value in (('certified_repair',True),('verdict','repaired'),('parent','0'*64)):
            doc=decode(packet);doc[field]=value
            with self.assertRaises(InvalidRecord):c.inspect_repair(canon(doc))
        with self.assertRaises(InvalidRecord):c.inspect_repair(packet+b' ')

    def test_cli_offline_same_reports_no_outputs_on_failure(self):
        ref,child=self.pair();packet=c.pack_repair(ref,child)
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);(root/'ref').write_bytes(ref);(root/'child').write_bytes(child)
            command=[sys.executable,'-I','-m','stargate']
            def cli(*args):return subprocess.run(command+list(map(str,args)),capture_output=True)
            packed=cli('certificate-repair-pack',root/'ref',root/'child','--output',root/'packet')
            self.assertEqual(packed.returncode,0,packed.stderr)
            self.assertEqual(json.loads(packed.stdout)['status'],'unchecked_repair')
            self.assertEqual((root/'packet').read_bytes(),packet)
            exported=cli('certificate-repair-unpack',root/'packet','--output',root/'offline')
            self.assertEqual(exported.returncode,0,exported.stderr)
            pins=['--expect-model',c.identity(decode(ref)['model']),'--expect-checker',c.checker_id()]
            replay=[sys.executable,'-I','-S',str(root/'offline/replay.py'),str(root/'packet'),'--repair']
            for quota,code in ((0,3),(1,3),(c.MAX_STEPS,0)):
                args=pins+['--max-steps',str(quota)]
                a=cli('certificate-repair-check',root/'packet',*args,'--output',root/'out')
                b=subprocess.run(replay+args+['--output',str(root/'out2')],capture_output=True)
                self.assertEqual((a.returncode,b.returncode),(code,code),(a.stderr,b.stderr))
                self.assertEqual(json.loads(a.stdout),json.loads(b.stdout))
                if code:
                    self.assertFalse((root/'out').exists());self.assertFalse((root/'out2').exists())
                else:
                    self.assertEqual((root/'out').read_bytes(),child);self.assertEqual((root/'out2').read_bytes(),child)
            repeated=cli('certificate-repair-check',root/'packet',*pins,'--output',root/'out')
            self.assertEqual(repeated.returncode,1);self.assertEqual((root/'out').read_bytes(),child)
            self.assertFalse(list((root/'offline').rglob('__pycache__')))
            # Invalid candidate and wrong anchor have the same classification offline.
            broken=decode(packet);broken['candidate']['paths'][0]['trace']['steps']=[]
            (root/'broken').write_bytes(canon(broken))
            for path,anchor in ((root/'broken',pins[1]),(root/'packet','0'*64)):
                args=['--expect-model',anchor,*pins[2:]]
                a=cli('certificate-repair-check',path,*args,'--output',root/'never')
                b=subprocess.run(replay[:4]+[str(path),'--repair',*args,'--output',str(root/'never2')],capture_output=True)
                self.assertEqual((a.returncode,b.returncode),(2,2),(a.stderr,b.stderr))
                self.assertFalse((root/'never').exists());self.assertFalse((root/'never2').exists())


if __name__=='__main__':unittest.main()
