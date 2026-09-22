import argparse
import ast
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from stargate import certificate as c, cli, evidence, experiment, lab, machine, transport
from stargate.canonical import canon,InvalidRecord

ROOT=Path(__file__).resolve().parents[1]


class Transport(unittest.TestCase):
    def test_real_surface_removes_six_commands_without_aliases(self):
        choices=next(a.choices for a in cli.parser()._actions if isinstance(a,argparse._SubParsersAction))
        self.assertEqual(len(choices),56)
        for name in ('machine-certify','certificate-unpack','refutation-unpack','certificate-change-unpack','certificate-history-unpack','certificate-repair-unpack'):
            self.assertNotIn(name,choices)
        self.assertIn('unpack',choices)
        self.assertIn('inspect',choices)

    def test_anchor_table_matches_this_snapshot(self):
        table=(ROOT/'ANCHORS.md').read_text()
        for pin in (c.checker_id(),lab.runtime_digest(lab.runtime_sources()),experiment.controller_id(),transport.replay_digest()):
            self.assertIn('`'+pin+'`',table)
        self.assertIn('untagged PR candidate',table)

    def test_transport_edits_do_not_rename_the_checker_but_semantics_edits_do(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);package=root/'stargate';package.mkdir()
            for n,text in c.sources().items():(package/n).write_text(text)
            script='import sys;sys.path.insert(0,sys.argv[1]);from stargate import certificate as c;print(c.checker_id())'
            def identity():return subprocess.check_output([sys.executable,'-I','-c',script,str(root)],text=True).strip()
            before=identity();self.assertEqual(before,c.checker_id())
            for name in ('transport.py','replay.py'):(package/name).write_text('raise RuntimeError("must never load")')
            self.assertEqual(identity(),before)
            (package/'certificate.py').write_text((package/'certificate.py').read_text()+'\n# semantic closure changed\n')
            self.assertNotEqual(identity(),before)

    def test_three_exports_use_identical_launcher_with_distinct_closures(self):
        w=lab.create_world('fact a: bool\ncheck a',['a'])
        m=dict(language='boolean-machine-1',state=['x'],events=[],initial=[{'x':False}],
               next={'x':'fact x: bool\ncheck x'},invariant='fact x: bool\ncheck !x',goals=[])
        proof=c.create(m,[{'x':False}],[])
        corpus={'corpus':1,'cases':[{'name':'identity','inputs':['a'],'rule':'fact a: bool\ncheck a','max_atp':100}]}
        runtime=experiment.pack_runtime()
        ex=experiment.create(runtime,runtime,corpus)
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            transport.unpack_certificate(proof,root/'proof',license_text='test')
            transport.unpack_world(w,root/'lab')
            transport.unpack_experiment(ex,root/'experiment')
            for name in ('proof','lab','experiment'):
                self.assertEqual((root/name/'replay.py').read_bytes(),transport.replay_source().encode())
            for flags in ([],['-I'],['-S']):
                refused=subprocess.run([sys.executable,*flags,str(root/'proof/replay.py'),str(root/'proof/certificate.json'),
                    '--expect-checker',c.checker_id(),'--expect-model',c.identity(m)],capture_output=True)
                self.assertEqual(refused.returncode,1)
                self.assertIn(b'requires python -I -S',refused.stderr)
            marker=root/'shadow-executed'
            (root/'experiment/selectors.py').write_text('from pathlib import Path\nPath('+repr(str(marker))+').touch()\nraise RuntimeError("unhashed module executed")')
            result=subprocess.run([sys.executable,'-I','-S',str(root/'experiment/replay.py'),str(root/'experiment/experiment.json'),
                '--expect-controller',experiment.controller_id(),'--execute-runtimes'],capture_output=True)
            self.assertEqual(result.returncode,0,result.stderr)
            self.assertFalse(marker.exists())
            self.assertEqual(set(json.loads((root/'proof/checker.json').read_bytes())),set(c.SOURCES))
            self.assertNotIn('transport.py',c.SOURCES);self.assertNotIn('replay.py',c.SOURCES)
            for bad in (canon({'certificate':True}),canon({'certificate':1,'refutation':1}),b' '* (c.MAX_BYTES+1)):
                with self.assertRaises(InvalidRecord):transport.unpack_certificate(bad,root/'bad',license_text='')
                self.assertFalse((root/'bad').exists())

    def test_peterson_against_explicit_program_counter_oracle_and_offline(self):
        spec=importlib.util.spec_from_file_location('peterson_example',ROOT/'examples/peterson_repair.py')
        example=importlib.util.module_from_spec(spec);spec.loader.exec_module(example)
        from collections import deque
        def step(s,p,good):
            a,b,t=s;pcs=[a,b];old=pcs[p]
            if old==0:pcs[p]=1
            elif old==1:pcs[p]=2;t=1-p if good else p
            elif old==2:pcs[p]=3 if pcs[1-p]==0 or t==p else 2
            else:pcs[p]=0
            return (*pcs,t)
        def bits(s):
            a,b,t=s
            return dict(a0=bool(a&1),a1=bool(a&2),b0=bool(b&1),b1=bool(b&2),t=bool(t))
        packets=[]
        for good in (False,True):
            seen={(0,0,0):0};queue=deque(seen);bad=None
            while queue:
                state=queue.popleft()
                if state[0]==state[1]==3 and bad is None:bad=seen[state]
                for event in (0,1):
                    dst=step(state,event,good)
                    if dst not in seen:seen[dst]=seen[state]+1;queue.append(dst)
            raw=machine.create(example.model(good))
            report,proof=evidence.produce(raw,lab.identity(raw));packets.append(proof)
            self.assertEqual(report['status'],'verified_certificate' if good else 'verified_refutation')
            doc=json.loads(proof)
            if good:
                self.assertEqual(len(seen),20);self.assertIsNone(bad)
                self.assertEqual({tuple(sorted(bits(s).items())) for s in seen},{tuple(sorted(s.items())) for s in doc['states']})
            else:
                self.assertEqual(bad,6);trace=doc['claim']['trace'];self.assertEqual(len(trace['steps']),6)
                state=(0,0,0)
                for entry in trace['steps']:
                    state=step(state,int(entry['event']['s']),False);self.assertEqual(bits(state),entry['state'])
                self.assertEqual(state[:2],(3,3))
        repair=c.pack_repair(*packets);anchor=c.identity(json.loads(packets[0])['model'])
        report,tip=c.verify_repair(repair,anchor,c.checker_id())
        self.assertEqual(report['status'],'verified_repair');self.assertEqual(tip,packets[1])
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);transport.unpack_certificate(repair,root/'offline',license_text='test')
            cmd=[sys.executable,'-I','-S',str(root/'offline/replay.py'),str(root/'offline/repair.json'),'--repair','--expect-model',anchor,'--expect-checker',c.checker_id(),'--output',str(root/'tip')]
            p=subprocess.run(cmd,capture_output=True)
            self.assertEqual(p.returncode,0,p.stderr);self.assertEqual(json.loads(p.stdout),report)
            self.assertEqual((root/'tip').read_bytes(),tip)


if __name__=='__main__':unittest.main()
