from stargate import transport
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
from contextlib import redirect_stdout, redirect_stderr

from stargate import lab, labtask, compiler, kernel, cli
from stargate.canonical import canon, decode, InvalidRecord


def rule(expr):
    return 'fact a: bool\nfact b: bool\nfact c: bool\ncheck '+expr


def setup(parent='a || b || c', candidate='a || b || c', **kw):
    world = lab.create_world(rule(parent), list('abc'), **kw)
    proposal = dict(parent=lab.identity(world), candidate=rule(candidate))
    return world, proposal


def packet(rows=2, **kw):
    world, proposal = setup(**kw)
    report, raw = labtask.start(world, proposal, rows=rows)
    return world, proposal, report, raw


class LabTask(unittest.TestCase):
    def test_transfer_rechecks_prefix_then_adds_rows_and_matches_whole(self):
        world, proposal, first, raw = packet()
        expected, tip = lab.verify_transition(world, proposal)
        self.assertEqual((first['status'], first['output_kind'], first['replayed_rows'], first['new_rows']),
                         ('suspended', 'task', 0, 2))
        anchor = labtask.identity(world, proposal)
        calls = []
        real = compiler.compile_source
        def count(source, **kw):
            calls.append((source, kw['facts'].copy()))
            return real(source, **kw)
        with patch.object(compiler, 'compile_source', side_effect=count):
            second, next_raw = labtask.resume(raw, anchor, rows=3)
        self.assertEqual((second['replayed_rows'], second['new_rows']), (2, 3))
        self.assertEqual(len(calls), 10)
        self.assertEqual([facts for _, facts in calls[::2]], [
            dict(a=False,b=False,c=False), dict(a=False,b=False,c=True),
            dict(a=False,b=True,c=False), dict(a=False,b=True,c=True), dict(a=True,b=False,c=False)])
        self.assertEqual(second['task_id'], first['task_id'])
        self.assertNotEqual(second['packet_id'], first['packet_id'])
        self.assertEqual(len(decode(next_raw)['prefix']), 5)
        with patch.object(compiler, 'compile_source', wraps=real) as counted:
            final, successor = labtask.resume(next_raw, anchor, rows=256)
        self.assertEqual(counted.call_count, 16)  # all 8 rows, including 5 rechecked
        self.assertEqual((final['replayed_rows'], final['new_rows'], final['output_kind']), (5, 3, 'world'))
        self.assertEqual(final['verification'], expected)
        self.assertEqual(successor, tip)
        self.assertTrue(final['admitted'])

    def test_zero_new_rows_still_rechecks_imported_work_and_is_byte_stable(self):
        world, proposal, _, raw = packet()
        with patch.object(compiler, 'compile_source', wraps=compiler.compile_source) as counted:
            report, output = labtask.resume(raw, labtask.identity(world, proposal), rows=0)
        self.assertEqual(counted.call_count, 4)
        self.assertEqual((report['replayed_rows'], report['new_rows']), (2, 0))
        self.assertEqual(output, raw)
        self.assertFalse(report['admitted'])
        self.assertEqual(report['verification']['status'], 'suspended')

    def test_forged_results_never_become_work_even_with_recomputed_packet_hash(self):
        world, proposal, _, raw = packet()
        anchor = labtask.identity(world, proposal)
        for field, value in [('value', True), ('atp', 1), ('term', '0'*64)]:
            for role in ('parent', 'candidate'):
                with self.subTest(field=field, role=role):
                    doc = decode(raw)
                    self.assertNotEqual(doc['prefix'][0][role][field], value)
                    doc['prefix'][0][role][field] = value
                    altered = canon(doc)
                    self.assertNotEqual(lab.identity(altered), lab.identity(raw))
                    self.assertEqual(labtask.describe(altered)['status'], 'unverified_progress')
                    with self.assertRaisesRegex(InvalidRecord, 'does not reproduce'):
                        labtask.resume(altered, anchor, rows=256)
        # A prefix claims a matching row at which the actual candidate is false.
        world, proposal = setup(candidate='a && b && c')
        _, honest = labtask.start(world, proposal, rows=1)
        forged = decode(honest)
        copied = decode(raw)['prefix'][1]
        forged['prefix'].append(copied)
        with self.assertRaisesRegex(InvalidRecord, 'does not reproduce'):
            labtask.resume(canon(forged), labtask.identity(world, proposal), rows=256)

    def test_recipient_anchor_binds_world_and_candidate_before_evaluation(self):
        world, proposal, _, raw = packet()
        changed = decode(raw); changed['proposal']['candidate'] = rule('!!(a || b || c)')
        changed_world = decode(raw); changed_world['world']['max_atp'] = 999
        changed_world['proposal']['parent'] = lab.identity(canon(changed_world['world']))
        with patch.object(compiler, 'compile_source', side_effect=AssertionError('must not evaluate')):
            for data, anchor in [(raw,'0'*64), (canon(changed),labtask.identity(world,proposal)),
                                 (canon(changed_world),labtask.identity(world,proposal))]:
                with self.subTest(anchor=anchor), self.assertRaisesRegex(InvalidRecord, 'recipient anchor'):
                    labtask.resume(data, anchor, rows=256)

    def test_shape_order_and_completion_claims_are_rejected(self):
        world, proposal, _, raw = packet()
        mutations = [lambda d: d.update(admitted=True), lambda d: d.update(stargate_task=True),
                     lambda d: d.update(prefix={}), lambda d: d['prefix'].reverse(),
                     lambda d: d['prefix'].append(d['prefix'][0]),
                     lambda d: d['prefix'][0]['input'].update(a=0),
                     lambda d: d['prefix'][0]['parent'].update(atp=True),
                     lambda d: d['prefix'][0]['candidate'].update(value=0),
                     lambda d: d['prefix'][0].update(verdict='pass'),
                     lambda d: d['proposal'].update(proof='claimed')]
        complete = decode(raw); complete['prefix'] = lab.verify_transition(world, proposal)[0]['rows']
        malformed = [canon(complete), raw+b'\n', b'{"stargate_task":32,"stargate_task":32}']
        for mutate in mutations:
            doc=decode(raw); mutate(doc); malformed.append(canon(doc))
        with patch.object(compiler,'compile_source',side_effect=AssertionError('must not evaluate')):
            for bad in malformed:
                with self.subTest(bad=bad[:100]), self.assertRaises(InvalidRecord): labtask.inspect(bad)
            for quota in (-1,257,True,1.0):
                with self.assertRaises(InvalidRecord): labtask.resume(raw,labtask.identity(world,proposal),rows=quota)

    def test_truncating_progress_is_allowed_but_does_not_skip_verification(self):
        world, proposal, _, raw = packet(rows=5)
        doc=decode(raw); doc['prefix']=[]
        with patch.object(compiler,'compile_source',wraps=compiler.compile_source) as calls:
            result, tip=labtask.resume(canon(doc),labtask.identity(world,proposal),rows=256)
        self.assertEqual(calls.call_count,16)
        self.assertEqual((result['replayed_rows'],result['new_rows']),(0,8))
        self.assertEqual(tip,lab.verify_transition(world,proposal)[1])

    def test_claimed_completed_row_cannot_exhaust_fixed_world_budget(self):
        _,_,_,raw=packet(rows=1)
        for claimed in (5, 6):
            doc=decode(raw)
            doc['world']['max_atp']=5
            world=canon(doc['world'])
            doc['proposal']['parent']=lab.identity(world)
            for role in ('parent','candidate'): doc['prefix'][0][role]['atp']=claimed
            with self.subTest(claimed=claimed):
                if claimed == 5:
                    # Well-shaped lie: only actual execution can refute it.
                    self.assertEqual(labtask.describe(canon(doc))['status'],'unverified_progress')
                with self.assertRaises(InvalidRecord) as caught:
                    labtask.resume(canon(doc),labtask.identity(world,doc['proposal']),rows=256)
                if claimed == 5:
                    self.assertIn('prefix does not reproduce: world budget exhausted',str(caught.exception))
        # Without a completion claim the same budget failure is not a lie.
        doc['prefix']=[]
        result,output=labtask.resume(canon(doc),labtask.identity(world,doc['proposal']),rows=1)
        self.assertEqual(result['status'],'incomplete')
        self.assertEqual(result['verification'].get('incomplete_kind'),'world_budget')
        self.assertIsNone(output)

    def test_local_fault_with_budget_message_is_still_unverified(self):
        world,proposal,_,raw=packet(rows=1)
        # Same text as budget exhaustion: classification must follow the type.
        fault=kernel.ResourceFault('policy did not finish within the compile budget')
        with patch.object(kernel,'eval_receipt',side_effect=fault) as calls:
            report,output=labtask.resume(raw,labtask.identity(world,proposal),rows=256)
        self.assertEqual(calls.call_count,1)
        self.assertEqual((report['status'],report['new_rows'],report['output_kind']),('incomplete',0,None))
        self.assertNotIn('incomplete_kind',report['verification'])
        self.assertFalse(report['admitted'])
        self.assertIsNone(output)

    def test_local_replay_failure_is_not_accusation_or_forward_progress(self):
        world, proposal, _, raw=packet()
        for fault,status in [(kernel.ResourceFault('limit'),'incomplete'),
                             (compiler.CompileIncomplete('fuel'),'incomplete'),
                             (compiler.CompilerBug('disagreement'),'checker_error')]:
            with self.subTest(status=status), patch.object(compiler,'compile_source',side_effect=fault):
                report,output=labtask.resume(raw,labtask.identity(world,proposal),rows=256)
            self.assertEqual((report['status'],report['new_rows'],report['output_kind']),(status,0,None))
            self.assertFalse(report['admitted']); self.assertIsNone(output)

    def test_all_terminal_contract_outcomes_are_preserved(self):
        cases=[(dict(candidate='a && b && c'),'counterexample',False),
               (dict(max_atp=1),'incomplete',False),
               (dict(objective='lower_max_atp'),'equivalent',False),
               (dict(properties=[dict(kind='constant',value=False)]),'parent_rejected',False),
               (dict(parent='a && b && c',properties=[dict(kind='monotone',input='a')]),'satisfies',True)]
        for kw,status,admitted in cases:
            with self.subTest(status=status):
                world,proposal=setup(**kw)
                _,raw=labtask.start(world,proposal)
                report,output=labtask.resume(raw,labtask.identity(world,proposal),rows=256)
                expected,successor=lab.verify_transition(world,proposal)
                self.assertEqual((report['status'],report['admitted']),(status,admitted))
                self.assertEqual(report['verification'],expected)
                self.assertEqual(output,successor)
                self.assertEqual(report['output_kind'],'world' if admitted else None)

    def test_zero_inputs_has_only_empty_pending_prefix(self):
        world=lab.create_world('check true',[])
        proposal=dict(parent=lab.identity(world),candidate='check true')
        _,raw=labtask.start(world,proposal)
        self.assertEqual(decode(raw)['prefix'],[])
        report,tip=labtask.resume(raw,labtask.identity(world,proposal),rows=1)
        self.assertTrue(report['admitted']); self.assertIsNotNone(tip)

    def test_cli_and_plain_offline_agree_and_never_publish_on_failure(self):
        world,proposal,_,raw=packet()
        anchor=labtask.identity(world,proposal)
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); offline=root/'offline'
            description=transport.unpack_task(raw,offline)
            self.assertEqual(description['status'],'unverified_progress')
            self.assertEqual(description['replay_digest'],lab.identity((offline/'replay.py').read_bytes()))
            self.assertIn('replay.py task.json next.json --task', (offline/'README.txt').read_text())
            self.assertEqual((offline/'task.json').stat().st_mode & 0o777,0o600)
            runtime=lab.runtime_digest(decode(world)['sources'])
            source=offline/'task.json'
            def run(data, quota, expected_anchor=anchor):
                source.write_bytes(data)
                results=[]
                for name,command in [
                    ('cli',[sys.executable,'-I','-m','stargate','lab-task-resume',str(source),
                            '--expect-task',expected_anchor,'--rows',str(quota),'--output']),
                    ('offline',[sys.executable,'-I','-S',str(offline/'replay.py'),str(source),
                                '--task','--expect-task',expected_anchor,'--rows',str(quota),
                                '--expect-runtime',runtime])]:
                    output=root/(name+'.json')
                    if output.exists(): output.unlink()
                    p=subprocess.run(command+[str(output)],cwd='/',capture_output=True,text=True)
                    self.assertNotIn('Traceback',p.stderr)
                    results.append((p.returncode,json.loads(p.stdout or p.stderr),output.read_bytes() if output.exists() else None))
                self.assertEqual(results[0],results[1])
                return results[0]
            code,report,output=run(raw,1)
            self.assertEqual((code,report['output_kind']),(3,'task'))
            code,report,output=run(output,256)
            self.assertEqual((code,report['output_kind']),(0,'world'))
            self.assertEqual(output,lab.verify_transition(world,proposal)[1])
            for bad in [canon(dict(decode(raw),prefix={})),raw+b'\n']:
                code,_,output=run(bad,1);self.assertEqual(code,2);self.assertIsNone(output)
            changed=decode(raw);changed['prefix'][0]['parent']['value']=True
            code,_,output=run(canon(changed),256);self.assertEqual(code,2);self.assertIsNone(output)
            code,_,output=run(raw,1,'0'*64);self.assertEqual(code,2);self.assertIsNone(output)
            foreign=decode(raw);foreign['world']['sources']['lab.py']+='\n# foreign'
            code,_,output=run(canon(foreign),1);self.assertEqual(code,3);self.assertIsNone(output)
            for claimed in (5,6):
                forged=decode(raw);forged['world']['max_atp']=5
                altered_world=canon(forged['world'])
                forged['proposal']['parent']=lab.identity(altered_world)
                for row in forged['prefix']:
                    for role in ('parent','candidate'): row[role]['atp']=claimed
                forged_anchor=labtask.identity(altered_world,forged['proposal'])
                code,_,output=run(canon(forged),256,forged_anchor)
                self.assertEqual(code,2);self.assertIsNone(output)
            forged['prefix']=[]
            code,report,output=run(canon(forged),1,forged_anchor)
            self.assertEqual((code,report['status']),(3,'incomplete'));self.assertIsNone(output)
            syntax=decode(raw);syntax['proposal']['candidate']=rule('a &&')
            code,_,output=run(canon(syntax),1);self.assertEqual(code,2);self.assertIsNone(output)

    def test_unpack_write_failure_cleans_only_owned_directory(self):
        _,_,_,raw=packet()
        real_open=os.open
        def fail(path, flags, *args, **kwargs):
            if str(path).endswith('/task.json') and flags & os.O_CREAT:
                raise OSError('planted task write failure')
            return real_open(path, flags, *args, **kwargs)
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); marker=root/'keep'; marker.write_bytes(b'keep')
            with patch.object(transport.os,'open',side_effect=fail):
                with self.assertRaisesRegex(OSError,'planted task write failure'):
                    transport.unpack_task(raw,root/'output')
            self.assertFalse((root/'output').exists())
            self.assertEqual(marker.read_bytes(),b'keep')

    def test_start_can_finish_without_emitting_a_pending_task(self):
        world,proposal=setup()
        report,output=labtask.start(world,proposal,rows=256)
        expected,tip=lab.verify_transition(world,proposal)
        self.assertEqual((report['status'],report['output_kind'],report['replayed_rows'],report['new_rows']),
                         ('equivalent','world',0,8))
        self.assertEqual(report['verification'],expected)
        self.assertEqual(output,tip)

    def test_cli_start_inspect_and_occupied_output(self):
        world,proposal=setup()
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); w=root/'world'; p=root/'proposal'; out=root/'output'
            w.write_bytes(world);p.write_bytes(canon(proposal))
            def invoke(*args):
                stdout,stderr=io.StringIO(),io.StringIO()
                with redirect_stdout(stdout),redirect_stderr(stderr): code=cli.main(list(args))
                return code,json.loads(stdout.getvalue() or stderr.getvalue())
            code,report=invoke('lab-task-start',str(w),str(p),'--rows','2','--output',str(out))
            self.assertEqual((code,report['status']),(3,'suspended'))
            original=out.read_bytes()
            with patch.object(compiler,'compile_source',side_effect=AssertionError('inspect must not execute')):
                code,description=invoke('lab-task-inspect',str(out))
            self.assertEqual((code,description['status']),(0,'unverified_progress'))
            code,_=invoke('lab-task-resume',str(out),'--expect-task',report['task_id'],'--rows','256','--output',str(out))
            self.assertEqual(code,1);self.assertEqual(out.read_bytes(),original)
            code,_=invoke('lab-task-resume',str(root/'absent'),'--expect-task',report['task_id'],'--output',str(root/'unused'))
            self.assertEqual(code,3);self.assertFalse((root/'unused').exists())
            with self.assertRaises(FileExistsError):transport.unpack_task(original,root)
            self.assertEqual(out.read_bytes(),original)
