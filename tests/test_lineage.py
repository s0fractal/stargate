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

from stargate import lab, lineage, cli, compiler
from stargate.canonical import canon, decode, InvalidRecord


def rule(expr):
    return 'fact a: bool\nfact b: bool\nfact c: bool\ncheck ' + expr


def history(max_atp=1000):
    root = lab.create_world(rule('!!!!(a || b) || c'), list('abc'),
                            objective='lower_max_atp', max_atp=max_atp)
    first = dict(parent=lab.identity(root), candidate=rule('!!(a || b) || c'))
    _, middle = lab.verify_transition(root, first)
    second = dict(parent=lab.identity(middle), candidate=rule('(a || b) || c'))
    _, tip = lab.verify_transition(middle, second)
    raw = canon(dict(stargate_lineage=32, root=decode(root), proposals=[first, second]))
    return raw, root, middle, tip


class Lineage(unittest.TestCase):
    def test_two_generations_replay_every_step_and_preserve_contract(self):
        raw, root, middle, tip = history()
        with patch.object(lab, 'verify_transition', wraps=lab.verify_transition) as gate:
            report, rebuilt = lineage.verify(raw, lab.identity(root))
        self.assertEqual(report['status'], 'verified_lineage')
        self.assertEqual((report['checked_steps'], report['total_steps']), (2, 2))
        self.assertEqual(gate.call_count, 2)
        self.assertEqual([c.args[0] for c in gate.call_args_list], [root, middle])
        self.assertEqual(rebuilt, tip)
        self.assertEqual(report['tip'], lab.identity(tip))
        self.assertEqual([r['max_atp'] for r in report['transitions']],
                         [dict(parent=61,candidate=43), dict(parent=43,candidate=25)])
        for name in decode(root):
            if name not in ('rule', 'predecessor'):
                self.assertEqual(decode(rebuilt)[name], decode(root)[name])
        self.assertEqual(decode(rebuilt)['rule'], rule('(a || b) || c'))
        self.assertEqual(decode(rebuilt)['predecessor'], lab.identity(middle))
        # Sequential append gives exactly the same transcript, no stored reports.
        current = lineage.create(root)
        for proposal in decode(raw)['proposals']:
            r, current = lineage.append(current, proposal, lab.identity(root))
            self.assertEqual(r['status'], 'verified_lineage')
        self.assertEqual(current, raw)

    def test_second_failure_never_returns_a_valid_prefix_as_tip(self):
        raw, root, _, _ = history()
        for candidate, reason in [(rule('a && b && c'), 'counterexample'),
                                  (rule('!!(a || b) || c'), 'equivalent')]:
            doc = decode(raw); doc['proposals'][1]['candidate'] = candidate
            report, tip = lineage.verify(canon(doc), lab.identity(root))
            self.assertEqual((report['status'], report['failed_step'], report['checked_steps']),
                             ('not_admitted', 1, 2))
            self.assertEqual(report['transitions'][-1]['status'], reason)
            self.assertIsNone(tip)
            self.assertNotIn('tip', report)
            prefix = canon(dict(doc, proposals=doc['proposals'][:1]))
            r, appended = lineage.append(prefix, doc['proposals'][1], lab.identity(root))
            self.assertEqual(r['status'], 'not_admitted')
            self.assertIsNone(appended)

    def test_recipient_anchor_and_order_are_binding(self):
        raw, root, _, _ = history()
        with self.assertRaisesRegex(InvalidRecord, 'recipient anchor'):
            lineage.verify(raw, '0'*64)
        for proposals in [list(reversed(decode(raw)['proposals'])),
                          decode(raw)['proposals'][1:],
                          [decode(raw)['proposals'][0]]*2]:
            doc = decode(raw); doc['proposals'] = proposals
            with self.assertRaisesRegex(InvalidRecord, 'parent mismatch'):
                lineage.verify(canon(doc), lab.identity(root))
        doc = decode(raw); doc['root']['objective'] = 'equivalence'
        with self.assertRaisesRegex(InvalidRecord, 'recipient anchor'):
            lineage.verify(canon(doc), lab.identity(root))
        # Empty histories explicitly mean zero transitions, not evaluation.
        with patch.object(lab, 'verify_transition', side_effect=AssertionError('unexpected eval')):
            r, tip = lineage.verify(lineage.create(root), lab.identity(root))
        self.assertEqual((r['checked_steps'], r['total_steps'], tip), (0, 0, root))

    def test_parent_rejected_is_visible_in_api_cli_and_offline(self):
        root = lab.create_world('check false', [],
                                properties=[dict(kind='constant', value=True)])
        proposal = dict(parent=lab.identity(root), candidate='check true')
        raw = canon(dict(stargate_lineage=32, root=decode(root), proposals=[proposal]))
        report, tip = lineage.verify(raw, lab.identity(root))
        self.assertEqual((report['status'], report['failed_step'], report['checked_steps']),
                         ('parent_rejected', 0, 1))
        self.assertEqual(report['transitions'][0]['status'], 'parent_rejected')
        self.assertIsNone(tip)
        self.assertNotIn('tip', report)
        appended_report, appended = lineage.append(lineage.create(root), proposal, lab.identity(root))
        self.assertEqual(appended_report, report)
        self.assertIsNone(appended)
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)
            transport.unpack_lineage(raw, path/'offline')
            history_path = path/'offline'/'lineage.json'
            output = path/'tip.json'
            commands = [
                [sys.executable, '-I', '-m', 'stargate', 'lineage-check', str(history_path),
                 '--expect-root', lab.identity(root), '--output', str(output)],
                [sys.executable, '-I', '-S', str(path/'offline'/'replay.py'),
                 str(history_path), str(output), '--lineage', '--expect-root', lab.identity(root),
                 '--expect-runtime', lab.runtime_digest(decode(root)['sources'])]]
            for command in commands:
                with self.subTest(command=command):
                    result = subprocess.run(command, cwd='/', capture_output=True, text=True)
                    self.assertEqual(result.returncode, 4, result.stderr)
                    self.assertEqual(json.loads(result.stdout), report)
                    self.assertFalse(output.exists())

    def test_incomplete_and_checker_error_are_not_refutations(self):
        raw, root, _, _ = history()
        doc = decode(raw); doc['root']['max_atp'] = 1
        small_root = canon(doc['root'])
        doc['proposals'] = [dict(parent=lab.identity(small_root), candidate=rule('!!(a || b) || c'))]
        r, tip = lineage.verify(canon(doc), lab.identity(small_root))
        self.assertEqual((r['status'], r['failed_step']), ('incomplete', 0))
        self.assertIsNone(tip); self.assertNotIn('tip', r)
        with patch.object(compiler, 'compile_source', side_effect=compiler.CompilerBug('planted lowering error')):
            r, tip = lineage.verify(raw, lab.identity(root))
        self.assertEqual(r['status'], 'checker_error'); self.assertIsNone(tip)
        with patch.object(lab, 'verify_transition', return_value=({'admitted':True},None)):
            r, tip = lineage.verify(raw, lab.identity(root))
        self.assertEqual(r['status'], 'checker_error'); self.assertIsNone(tip)

    def test_shape_limits_and_caller_inputs(self):
        raw, root, _, _ = history()
        for field,value in [('stargate_lineage',True), ('proposals',{}),
                            ('proposals',decode(raw)['proposals']*17)]:
            doc=decode(raw);doc[field]=value
            with self.subTest(field=field),self.assertRaises(InvalidRecord):lineage.inspect(canon(doc))
        doc=decode(raw);doc['admitted']=True
        with self.assertRaises(InvalidRecord):lineage.inspect(canon(doc))
        doc=decode(raw);doc['proposals'][0]['verdict']='pass'
        with self.assertRaises(InvalidRecord):lineage.inspect(canon(doc))
        with self.assertRaises(InvalidRecord):lineage.inspect(raw+b'\n')
        with self.assertRaises(InvalidRecord):lineage.inspect(b' '* (lineage.MAX_LINEAGE+1))
        original=decode(raw)['proposals'][0]
        saved=canon(original)
        lineage.append(lineage.create(root), original, lab.identity(root))
        self.assertEqual(canon(original),saved)

    def test_coverage_guard_and_full_step_limit(self):
        raw, root, _, _ = history()
        class SkippedTail(list):
            def __iter__(self): return iter(self[:1])
        doc = decode(raw); doc['proposals'] = SkippedTail(doc['proposals'])
        with patch.object(lineage, 'inspect', return_value=doc):
            report, tip = lineage.verify(raw, lab.identity(root))
        self.assertEqual(report['status'], 'checker_error')
        self.assertIsNone(tip)
        root = lab.create_world('check true', [])
        current = root; proposals = []
        for _ in range(32):
            proposal = dict(parent=lab.identity(current), candidate='check true')
            proposals.append(proposal)
            _, current = lab.verify_transition(current, proposal)
        raw = canon(dict(stargate_lineage=32, root=decode(root), proposals=proposals))
        report, tip = lineage.verify(raw, lab.identity(root))
        self.assertEqual((report['status'], report['checked_steps']), ('verified_lineage', 32))
        self.assertEqual(tip, current)
        with self.assertRaises(InvalidRecord):
            lineage.append(raw, dict(parent=lab.identity(tip), candidate='check true'), lab.identity(root))

    def test_cli_and_offline_reconstruct_identical_tip(self):
        raw, root, _, tip=history()
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp); (path/'world.json').write_bytes(root)
            def run(*args):
                out,err=io.StringIO(),io.StringIO()
                with redirect_stdout(out),redirect_stderr(err):code=cli.main(list(map(str,args)))
                return code,json.loads(out.getvalue() or err.getvalue())
            code,r=run('lineage-start',path/'world.json','--output',path/'zero.json')
            self.assertEqual(code,0)
            current=path/'zero.json'
            for i,p in enumerate(decode(raw)['proposals']):
                (path/'proposal.json').write_text(json.dumps(p))
                target=path/f'{i}.json'
                code,r=run('lineage-append',current,path/'proposal.json','--expect-root',lab.identity(root),'--output',target)
                self.assertEqual((code,r['status']),(0,'verified_lineage'))
                current=target
            self.assertEqual(current.read_bytes(),raw)
            code,r=run('lineage-check',current,'--expect-root',lab.identity(root),'--output',path/'tip.json')
            self.assertEqual(code,0);self.assertEqual((path/'tip.json').read_bytes(),tip)
            code,_=run('lineage-check',current,'--expect-root',lab.identity(root),'--output',path/'tip.json')
            self.assertEqual(code,1);self.assertEqual((path/'tip.json').read_bytes(),tip)
            code,_=run('unpack', '--expect-kind', 'lineage',current,'--output',path/'offline')
            self.assertEqual(code,0)
            args=[sys.executable,'-I','-S',str(path/'offline/replay.py'),str(path/'offline/lineage.json'),str(path/'offline-tip.json'),
                  '--lineage','--expect-root',lab.identity(root),'--expect-runtime',lab.runtime_digest(decode(root)['sources'])]
            replay=subprocess.run(args,cwd='/',capture_output=True,text=True)
            self.assertEqual(replay.returncode,0,replay.stderr)
            self.assertEqual(json.loads(replay.stdout),r)
            self.assertEqual((path/'offline-tip.json').read_bytes(),tip)
            self.assertFalse(list((path/'offline').rglob('__pycache__')))
            # The launcher refuses a missing independent root, before executing.
            args=args[:-4]+args[-2:]
            replay=subprocess.run(args,cwd='/',capture_output=True,text=True)
            self.assertEqual(replay.returncode,2)

    def test_offline_invalid_anchor_is_not_a_checker_failure(self):
        raw, root, _, _ = history()
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)/'offline'
            transport.unpack_lineage(raw, path)
            output = Path(tmp)/'no-tip.json'
            runtime = lab.runtime_digest(decode(root)['sources'])
            def replay(anchor, digest=runtime):
                return subprocess.run([sys.executable,'-I','-S',str(path/'replay.py'),
                    str(path/'lineage.json'),str(output),'--lineage','--expect-root',anchor,
                    '--expect-runtime',digest],cwd='/',capture_output=True,text=True)
            for anchor in ('0'*64, 'not-a-hash'):
                r = replay(anchor)
                self.assertEqual(r.returncode, 2, r.stderr)
                self.assertEqual(json.loads(r.stderr)['status'], 'invalid')
                self.assertEqual(r.stdout, '')
                self.assertNotIn('Traceback', r.stderr)
                self.assertFalse(output.exists())
            # A genuine checker exception must not be relabelled as invalid input.
            # The test deliberately authenticates this broken runtime's new digest.
            doc = decode(raw)
            source = doc['root']['sources']['lineage.py']
            old = '    record_hash(expected_root)'
            self.assertEqual(source.count(old), 1)
            source = source.replace(old, "    raise RuntimeError('planted checker failure')")
            doc['root']['sources']['lineage.py'] = source
            (path/'stargate/lineage.py').write_text(source)
            (path/'lineage.json').write_bytes(canon(doc))
            r = replay(lab.identity(canon(doc['root'])), lab.runtime_digest(doc['root']['sources']))
            self.assertEqual(r.returncode, 1)
            self.assertEqual(json.loads(r.stdout)['status'], 'checker_error')
            self.assertIn('planted checker failure', json.loads(r.stdout)['error'])
            self.assertNotIn('"status": "invalid"', r.stderr)
            self.assertFalse(output.exists())

    def test_historical_and_foreign_runtimes_agree_across_all_entrypoints(self):
        historical = Path(__file__).with_name('world-build17-9a52255.json').read_bytes()
        self.assertEqual(lab.identity(historical), '3ef32eb7c844bcf93b5b60e4113ea980365e2d805e751e64a663870d2b1f74b9')
        current = lab.create_world('check true', [])
        changed = decode(current); changed['sources']['lab.py'] += '\n# foreign runtime'
        removed = decode(current); del removed['sources']['lineage.py']
        added = decode(current); added['sources']['future.py'] = '# future module'
        malformed = decode(historical); malformed['sources']['lab.py'] = None
        cases = [('historical',historical,3,'runtime_unavailable'),
                 ('changed-bytes',canon(changed),3,'runtime_unavailable'),
                 ('removed-module',canon(removed),3,'runtime_unavailable'),
                 ('added-module',canon(added),3,'runtime_unavailable'),
                 ('malformed',canon(malformed),2,'invalid')]
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp); offline = path/'offline'
            # The launcher/runtime are current; the supplied history is independent.
            transport.unpack_lineage(lineage.create(current), offline)
            runtime = lab.runtime_digest(decode(current)['sources'])
            for name,root,expected,status in cases:
                with self.subTest(case=name):
                    world_path = path/'foreign-world.json'; world_path.write_bytes(root)
                    history_path = path/'foreign-history.json'
                    history_path.write_bytes(canon(dict(stargate_lineage=32,root=decode(root),proposals=[])))
                    output = path/'must-not-exist.json'
                    anchor = lab.identity(root)
                    for args in [('inspect', '--expect-kind', 'lab',str(world_path)),
                                 ('lineage-check',str(history_path),'--expect-root',anchor,'--output',str(output))]:
                        out,err=io.StringIO(),io.StringIO()
                        with redirect_stdout(out),redirect_stderr(err): code=cli.main(list(args))
                        self.assertEqual(code,expected)
                        self.assertEqual(json.loads(err.getvalue())['status'],status)
                        self.assertEqual(out.getvalue(),'')
                        self.assertFalse(output.exists())
                    run=subprocess.run([sys.executable,'-I','-S',str(offline/'replay.py'),
                        str(history_path),str(output),'--lineage','--expect-root',anchor,
                        '--expect-runtime',runtime],cwd='/',capture_output=True,text=True)
                    self.assertEqual(run.returncode,expected,run.stderr)
                    self.assertEqual(json.loads(run.stderr)['status'],status)
                    self.assertNotIn('Traceback',run.stderr)
                    self.assertEqual(run.stdout,'')
                    self.assertFalse(output.exists())

    def test_cli_distinguishes_incomplete_invalid_and_checker_failure(self):
        raw, root, _, _ = history()
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'history.json'
            path.write_bytes(raw)
            def run(anchor):
                out,err=io.StringIO(),io.StringIO()
                with redirect_stdout(out),redirect_stderr(err):
                    code=cli.main(['lineage-check',str(path),'--expect-root',anchor])
                return code,json.loads(out.getvalue() or err.getvalue())['status']
            self.assertEqual(run('0'*64),(2,'invalid'))
            with patch.object(compiler,'compile_source',side_effect=compiler.CompilerBug('broken')):
                self.assertEqual(run(lab.identity(root)),(1,'checker_error'))
            doc=decode(raw); doc['root']['max_atp']=1
            small=canon(doc['root']);doc['proposals']=doc['proposals'][:1]
            doc['proposals'][0]['parent']=lab.identity(small)
            path.write_bytes(canon(doc))
            self.assertEqual(run(lab.identity(small)),(3,'incomplete'))
            path.unlink()
            self.assertEqual(run(lab.identity(root)),(3,'unverified'))

    def test_unpack_failure_cleans_only_its_new_directory(self):
        raw,_,_,_=history()
        real_open=transport.os.open
        def fail_final(path,*args,**kwargs):
            if Path(path).name=='lineage.json':raise OSError('planted final write failure')
            return real_open(path,*args,**kwargs)
        with tempfile.TemporaryDirectory() as tmp:
            out=Path(tmp)/'unpacked'
            with patch.object(transport.os,'open',fail_final),self.assertRaises(OSError):
                transport.unpack_lineage(raw,out)
            self.assertFalse(out.exists())
            out.mkdir();(out/'keep').write_bytes(b'keep')
            with self.assertRaises(FileExistsError):transport.unpack_lineage(raw,out)
            self.assertEqual((out/'keep').read_bytes(),b'keep')

    def test_cli_refusal_never_writes_tip_or_transcript(self):
        raw,root,_,_=history()
        doc=decode(raw);doc['proposals'][1]['candidate']=rule('a && b && c')
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp);(path/'bad.json').write_bytes(canon(doc))
            (path/'proposal.json').write_bytes(canon(doc['proposals'][1]))
            prefix=canon(dict(doc,proposals=doc['proposals'][:1]))
            (path/'prefix.json').write_bytes(prefix)
            for command,args in [('lineage-check',[path/'bad.json']),
                                 ('lineage-append',[path/'prefix.json',path/'proposal.json'])]:
                out=io.StringIO()
                with redirect_stdout(out):
                    code=cli.main([command,*map(str,args),'--expect-root',lab.identity(root),'--output',str(path/'never.json')])
                self.assertEqual(code,4)
                self.assertFalse((path/'never.json').exists())
            with self.assertRaises(FileExistsError):transport.unpack_lineage(raw,path)
            self.assertEqual((path/'prefix.json').read_bytes(),prefix)


if __name__=='__main__':unittest.main()
