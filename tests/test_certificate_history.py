from stargate import transport
import copy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from stargate import certificate as c
from stargate.canonical import canon, decode, InvalidRecord


def proof(expr, states=None):
    return canon(dict(certificate=1, checker=c.checker_id(),
        model=dict(language='boolean-machine-1', state=['x'], events=[],
            initial=[{'x': False}], next={'x': 'fact x: bool\ncheck '+expr},
            invariant='fact x: bool\ncheck true', goals=[]),
        states=[{'x': False}, {'x': True}] if states is None else states, paths=[]))


class CertificateHistory(unittest.TestCase):
    def setUp(self):
        self.certs = [proof(expr) for expr in ('x', '!x', 'true')]
        self.anchor = c.identity(decode(self.certs[0])['model'])
        self.checker = c.checker_id()

    def history(self):
        # Construct untrusted data directly, independently of append/verify.
        return canon(dict(certificate_history=1, root=decode(self.certs[0]), steps=[
            {'parent': c.identity(decode(self.certs[i-1])['model']), 'certificate': decode(self.certs[i])}
            for i in (1, 2)]))

    def check(self, raw, **kw):
        return c.verify_history(raw, self.anchor, self.checker, **kw)

    def test_exact_tip_each_proof_once_and_matches_pairwise_changes(self):
        raw = self.history()
        with patch.object(c, 'verify', wraps=c.verify) as measured:
            report, tip = self.check(raw)
        self.assertEqual(measured.call_count, 3)
        self.assertEqual([x.args[0] for x in measured.call_args_list], self.certs)
        self.assertEqual((report['status'], report['transitions'], tip), ('verified_history', 2, self.certs[-1]))
        self.assertEqual(report['tip_model'], c.identity(decode(tip)['model']))
        self.assertEqual(report['tip_certificate'], c.identity(decode(tip)))
        self.assertEqual([x['index'] for x in report['checks']], [0, 1, 2])
        current = self.certs[0]
        for next_cert in self.certs[1:]:
            _, current = c.verify_change(c.pack_change(current, next_cert),
                c.identity(decode(current)['model']), self.checker)
        self.assertEqual(current, tip)

    def test_empty_history_checks_root_and_noop_is_legal(self):
        raw = c.start_history(self.certs[0])
        report, tip = self.check(raw)
        self.assertEqual((report['status'], report['transitions'], len(report['checks']), tip),
                         ('verified_history', 0, 1, self.certs[0]))
        bad = decode(raw); bad['root']['states'] = [{'x': True}]
        with self.assertRaisesRegex(InvalidRecord, 'initial'): self.check(canon(bad))
        report, appended = c.append_history(raw, self.certs[0], self.anchor, self.checker)
        self.assertEqual(report['transitions'], 1)
        self.assertEqual(self.check(appended)[1], self.certs[0])

    def test_root_parent_order_and_contract_are_bound(self):
        raw = self.history()
        with self.assertRaisesRegex(InvalidRecord, 'root'):
            c.verify_history(raw, '0'*64, self.checker)
        for kind in ('root', 'link', 'swap', 'contract', 'extra'):
            doc = decode(raw)
            if kind == 'root': doc['root'] = decode(self.certs[1])
            if kind == 'link': doc['steps'][1]['parent'] = self.anchor
            if kind == 'swap': doc['steps'].reverse()
            if kind == 'contract': doc['steps'][1]['certificate']['model']['invariant'] = 'fact x: bool\ncheck x || !x'
            if kind == 'extra': doc['tip'] = '0'*64
            with self.subTest(kind=kind), self.assertRaises(InvalidRecord): self.check(canon(doc))
        # Repeating a genuine step at the wrong parent is not a valid continuation.
        doc = decode(raw); doc['steps'][1] = copy.deepcopy(doc['steps'][0])
        with self.assertRaisesRegex(InvalidRecord, 'parent link'): self.check(canon(doc))

    def test_failed_tail_never_releases_prefix_or_appended_history(self):
        raw = self.history()
        for index in (0, 1):
            bad = decode(raw); bad['steps'][index]['certificate']['states'] = [{'x': False}]
            with self.subTest(index=index), self.assertRaisesRegex(InvalidRecord, 'closed'):
                self.check(canon(bad))
        # Root costs one edge, next proof two: failure is at candidate, not root.
        raw = c.start_history(proof('x', [{'x': False}]))
        report, appended = c.append_history(raw, self.certs[1], self.anchor, self.checker, max_steps=1)
        self.assertEqual((report['status'], report.get('failed'), appended), ('incomplete', 1, None))
        self.assertNotIn('tip_model', report)
        doc = decode(self.history()); doc['steps'][1]['certificate']['checker'] = '0'*64
        report, tip = self.check(canon(doc))
        self.assertEqual((report['status'], report.get('failed'), tip), ('checker_unavailable', 2, None))
        with patch.object(c, 'verify', side_effect=[{'status': 'verified_certificate'}, {'status':'checker_error'}]):
            report, tip = self.check(self.packet_without_checks())
            self.assertEqual((report['status'], tip, c.exit_code(report)), ('checker_error', None, 1))

    def packet_without_checks(self):
        return canon(dict(certificate_history=1, root=decode(self.certs[0]), steps=[
            {'parent': self.anchor, 'certificate': decode(self.certs[1])}]))

    def test_bound_and_inert_construction(self):
        raw = c.start_history(self.certs[0]); doc = decode(raw)
        step = {'parent': self.anchor, 'certificate': decode(self.certs[0])}
        doc['steps'] = [step]*32
        report, tip = self.check(canon(doc))
        self.assertEqual((report['transitions'], len(report['checks']), tip), (32, 33, self.certs[0]))
        with self.assertRaisesRegex(InvalidRecord, '32'):
            c.append_history(canon(doc), self.certs[0], self.anchor, self.checker)
        bad = decode(self.certs[0]); bad['states'] = [{'x': True}]
        with patch.object(c, 'verify', side_effect=AssertionError('must be inert')):
            raw = c.start_history(canon(bad))
            with tempfile.TemporaryDirectory() as tmp:
                out=Path(tmp)/'out'; report=transport.unpack_certificate(raw,out,license_text='test')
                self.assertEqual(report['status'], 'unchecked_history')
                self.assertEqual((out/'history.json').read_bytes(),raw)

    def test_cli_offline_append_output_and_refusal_parity(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); command=[sys.executable,'-I','-m','stargate']
            for i,cert in enumerate(self.certs): (root/f'c{i}').write_bytes(cert)
            args=['--expect-model',self.anchor,'--expect-checker',self.checker]
            start=subprocess.run(command+['certificate-history-start',str(root/'c0'),'--output',str(root/'h0')],capture_output=True)
            self.assertEqual(start.returncode,0,start.stderr)
            for i in (1,2):
                result=subprocess.run(command+['certificate-history-append',str(root/f'h{i-1}'),str(root/f'c{i}'),*args,'--output',str(root/f'h{i}')],capture_output=True)
                self.assertEqual(result.returncode,0,result.stderr)
            self.assertEqual((root/'h2').read_bytes(),self.history())
            result=subprocess.run(command+['evidence-unpack',str(root/'h2'),'--output',str(root/'offline')],capture_output=True)
            self.assertEqual(result.returncode,0,result.stderr)
            cli=command+['certificate-history-check',str(root/'h2')]
            replay=[sys.executable,'-I','-S',str(root/'offline/replay.py'),str(root/'offline/history.json'),'--history']
            reports=[]
            for i,prefix in enumerate((cli,replay)):
                out=root/f'tip{i}'
                result=subprocess.run(prefix+args+['--output',str(out)],capture_output=True)
                self.assertEqual(result.returncode,0,result.stderr);reports.append(json.loads(result.stdout))
                self.assertEqual(out.read_bytes(),self.certs[-1])
                again=subprocess.run(prefix+args+['--output',str(out)],capture_output=True)
                self.assertEqual(again.returncode,1);self.assertEqual(out.read_bytes(),self.certs[-1])
                pending=subprocess.run(prefix+args+['--max-steps','0','--output',str(root/'absent')],capture_output=True)
                self.assertEqual(pending.returncode,3,pending.stderr);self.assertFalse((root/'absent').exists())
            self.assertEqual(*reports)
            bad=decode(self.history());bad['steps'][1]['parent']=self.anchor
            for file in (root/'h2',root/'offline/history.json'): file.write_bytes(canon(bad))
            for prefix in (cli,replay):
                invalid=subprocess.run(prefix+args+['--output',str(root/'absent')],capture_output=True)
                self.assertEqual(invalid.returncode,2,invalid.stderr);self.assertFalse((root/'absent').exists())
            self.assertFalse(list((root/'offline').rglob('__pycache__')))


if __name__=='__main__':unittest.main()
