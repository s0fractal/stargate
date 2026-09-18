import itertools
import json
import os
from pathlib import Path
import random
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from stargate import boolean, compiler, kernel, lab
from stargate.canonical import canon, decode, InvalidRecord


def rule(expr, names=('a', 'b')):
    return ''.join(f'fact {name}: bool\n' for name in names) + 'check ' + expr


def proposal(raw, source):
    return dict(parent=lab.identity(raw), candidate=source)


class Lab(unittest.TestCase):
    def test_256_inputs_cheaper_candidate_and_cheaper_wrong_candidate(self):
        names = list('abcdefgh')
        expr = ' || '.join(names)
        raw = lab.create_world(rule('!!(' + expr + ')', names), names, objective='lower_max_atp')
        good, child = lab.verify_transition(raw, proposal(raw, rule(expr, names)))
        self.assertEqual((good['status'], good['admitted'], len(good['rows'])), ('equivalent', True, 256))
        self.assertEqual(good['max_atp'], {'parent': 98, 'candidate': 80})
        self.assertEqual([r['input'] for r in good['rows']],
                         [dict(zip(names, bits)) for bits in itertools.product((False, True), repeat=8)])
        for row in good['rows']:
            expected = any(row['input'].values())
            self.assertEqual(row['parent']['value'], expected)
            self.assertEqual(row['candidate']['value'], expected)
        self.assertEqual(decode(child)['predecessor'], lab.identity(raw))
        self.assertEqual(lab.identity(child), good['successor'])
        self.assertEqual(decode(raw)['rule'], rule('!!(' + expr + ')', names))
        wrong = rule(' && '.join(names), names)
        wrong_max = max(compiler.compile_source(wrong, facts=dict(zip(names, bits))).atp_spent
                        for bits in itertools.product((False, True), repeat=8))
        self.assertEqual(wrong_max, 80)
        self.assertLess(wrong_max, good['max_atp']['parent'])
        bad, child = lab.verify_transition(raw, proposal(raw, wrong))
        self.assertEqual((bad['status'], bad['admitted'], child), ('counterexample', False, None))
        self.assertEqual(bad['input'], dict(zip(names, [False]*7 + [True])))
        self.assertEqual((bad['rows'][-1]['parent']['value'], bad['rows'][-1]['candidate']['value']), (True, False))
        self.assertLess(bad['rows'][-1]['candidate']['atp'], bad['rows'][-1]['parent']['atp'])

    def test_parser_mutation_reaches_independent_comparison(self):
        raw = lab.create_world(rule('a || b'), ['a', 'b'])
        original = compiler.parse
        def broken(source, inputs=None):
            return original(source.replace('||', '&&'), inputs)
        with patch.object(compiler, 'parse', broken), patch.object(boolean, 'evaluate', wraps=boolean.evaluate) as second:
            report, child = lab.verify_transition(raw, proposal(raw, rule('a || b')))
        self.assertGreater(second.call_count, 0)
        self.assertEqual(report['status'], 'checker_error')
        self.assertEqual((report['status'], report['reason'], report['input'],
                          report['compiled'], report['oracle'], child),
                         ('checker_error', 'independent oracle disagreement',
                          {'a': False, 'b': True}, False, True, None))

    def test_candidate_also_has_to_agree_with_oracle(self):
        raw = lab.create_world(rule('!(!a && !b)'), ['a', 'b'])
        original = compiler.parse
        def broken(source, inputs=None):
            return original(source.replace('||', '&&'), inputs)
        with patch.object(compiler, 'parse', broken):
            report, child = lab.verify_transition(raw, proposal(raw, rule('a || b')))
        self.assertEqual(report['status'], 'checker_error')
        self.assertEqual((report['program'], report['input'], report['compiled'], report['oracle'], child),
                         ('candidate', {'a': False, 'b': True}, False, True, None))

    def test_lowering_mutation_hits_first_guard(self):
        raw = lab.create_world(rule('a && b'), ['a', 'b'])
        original = compiler.lower
        def broken(expr, facts):
            if expr[0] == 'and':
                expr = ('or', *expr[1:])
            return original(expr, facts)
        with patch.object(compiler, 'lower', broken):
            report, child = lab.verify_transition(raw, proposal(raw, rule('a && b')))
        self.assertEqual((report['status'], report['reason'], report['input'], child),
                         ('checker_error', 'SKI result disagrees with source interpreter',
                          {'a': False, 'b': True}, None))

    def test_budget_is_incomplete_syntax_is_invalid(self):
        raw = lab.create_world(rule('a || b'), ['a', 'b'], max_atp=1)
        report, child = lab.verify_transition(raw, proposal(raw, rule('a || b')))
        self.assertEqual((report['status'], report['rows'], report['admitted'], child), ('incomplete', [], False, None))
        with self.assertRaises(compiler.PolicyError) as caught:
            lab.verify_transition(raw, proposal(raw, rule('a ||')))
        self.assertNotIsInstance(caught.exception, compiler.CompileIncomplete)
        with self.assertRaises(compiler.CompileIncomplete):
            compiler.compile_source(rule('a || b'), facts={'a': False, 'b': False}, max_atp=1)
        with patch.object(compiler, 'compile_source', side_effect=kernel.ResourceFault('test limit')):
            report, child = lab.verify_transition(raw, proposal(raw, rule('a || b')))
        self.assertEqual((report['status'], child), ('incomplete', None))

    def test_equivalence_does_not_imply_improvement(self):
        raw = lab.create_world(rule('a || b'), ['a', 'b'], objective='lower_max_atp')
        report, child = lab.verify_transition(raw, proposal(raw, rule('a || b')))
        self.assertEqual((report['status'], report['admitted'], report.get('reason'), child),
                         ('equivalent', False, 'not_strictly_cheaper', None))

    def test_no_keys_and_no_computed_claim_fields(self):
        raw = lab.create_world('check true', [])
        report, child = lab.verify_transition(raw, proposal(raw, 'check !false'))
        self.assertEqual((report['status'], report['total_rows'], report['admitted']), ('equivalent', 1, True))
        for extra in ('signature', 'trust', 'atp', 'verdict', 'hash'):
            with self.subTest(extra=extra), self.assertRaises(InvalidRecord):
                lab.verify_transition(raw, dict(proposal(raw, 'check true'), **{extra: 'invented'}))
        with self.assertRaisesRegex(InvalidRecord, 'parent mismatch'):
            lab.verify_transition(raw, dict(parent='0'*64, candidate='check true'))
        with self.assertRaisesRegex(InvalidRecord, 'duplicate'):
            lab.read_proposal(b'{"parent":"x","parent":"y","candidate":"check true"}')
        self.assertEqual(lab.read_proposal(json.dumps(proposal(raw, 'check true'), indent=2).encode()),
                         proposal(raw, 'check true'))

    def test_runtime_and_packet_tampering(self):
        raw = lab.create_world('check true', [])
        doc = decode(raw)
        doc['sources']['compiler.py'] += '\n# different implementation\n'
        with self.assertRaises(lab.RuntimeMismatch):
            lab.verify_transition(canon(doc), proposal(canon(doc), 'check true'))
        doc = decode(raw); doc['sources']['../../escape'] = 'oops'
        with self.assertRaises(InvalidRecord): lab.inspect_world(canon(doc))
        with self.assertRaises(InvalidRecord): lab.inspect_world(raw + b'\n')
        for field, value in [('inputs', list('abcdefghi')), ('max_atp', True),
                             ('inputs', ['b', 'a']), ('max_atp', 10001),
                             ('objective', 'trust_me')]:
            doc = decode(raw); doc[field] = value
            with self.subTest(field=field), self.assertRaises(InvalidRecord):
                lab.inspect_world(canon(doc))

    def test_independent_parser_precedence_and_random_truth(self):
        rng = random.Random(1515)
        def generate(depth):
            if depth == 0:
                value = bool(rng.randrange(2))
                return ('true' if value else 'false'), value
            left, l = generate(depth-1)
            right, r = generate(depth-1)
            op = rng.choice(['&&', '||', '!'])
            if op == '!': return '!(' + left + ')', not l
            return '(' + left + op + right + ')', (l and r) if op == '&&' else (l or r)
        for expr, expected in [('true || false && false', True), ('!true && false', False),
                               ('!(false || true) || true', True), *[generate(4) for _ in range(100)]]:
            with self.subTest(expr=expr):
                self.assertEqual(boolean.evaluate(boolean.program('check '+expr, []), {}), expected)
        for text in ['check true false', 'check (true', 'check true)', 'check true &&',
                     'check true & false', 'check true == false', 'check ()', 'check !',
                     'check true(false)', 'fact a: bool check true', 'check missing']:
            with self.subTest(text=text), self.assertRaises(boolean.BooleanSyntax):
                boolean.program(text, [])

    def test_offline_replay_without_installed_package_or_site(self):
        raw = lab.create_world(rule('a || b'), ['a', 'b'])
        p = proposal(raw, rule('!(!a && !b)'))
        expected, successor = lab.verify_transition(raw, p)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)/'packet'
            lab.unpack_world(raw, root)
            (root/'proposal.json').write_text(json.dumps(p))
            result = subprocess.run([sys.executable, '-I', '-S', str(root/'replay.py'),
                                     str(root/'proposal.json'), str(root/'child.json')],
                                    cwd='/', capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(json.loads(result.stdout), expected)
            self.assertEqual((root/'child.json').read_bytes(), successor)
            self.assertEqual((root/'LICENSE').read_text(), lab.LICENSE)
            self.assertEqual((root/'replay.py').stat().st_mode & 0o777, 0o600)
            with self.assertRaises(FileExistsError): lab.unpack_world(raw, root)
            self.assertEqual((root/'child.json').read_bytes(), successor)

    def test_unpack_failure_cleanup_and_no_execution(self):
        raw = lab.create_world('check true', [])
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)/'packet'
            original_open = os.open
            def fail_write(path, flags, *args, **kwargs):
                if flags & os.O_WRONLY:
                    raise OSError('disk full')
                return original_open(path, flags, *args, **kwargs)
            with patch.object(lab.os, 'open', side_effect=fail_write):
                with self.assertRaises(OSError): lab.unpack_world(raw, root)
            self.assertFalse(root.exists())
            with patch.object(compiler, 'compile_source', side_effect=AssertionError('must not evaluate')):
                lab.unpack_world(raw, root)
            self.assertTrue((root/'world.json').exists())

    def test_cli_statuses_no_publication_on_refusal(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            def call(*args):
                p = subprocess.run([sys.executable, '-I', '-m', 'stargate', *map(str,args)],
                                   cwd=tmp, capture_output=True, text=True)
                return p.returncode, json.loads(p.stdout or p.stderr)
            (root/'rule').write_text(rule('a || b'))
            code, created = call('lab-create', root/'rule', '--input', 'a', '--input', 'b', '--output', root/'world')
            self.assertEqual(code, 0)
            self.assertEqual(call('lab-inspect', root/'world')[1]['world_id'], created['world_id'])
            raw = (root/'world').read_bytes()
            (root/'proposal').write_text(json.dumps(proposal(raw, rule('a && b'))))
            code, report = call('lab-check', root/'world', root/'proposal', '--output', root/'child')
            self.assertEqual((code, report['status']), (4, 'counterexample'))
            self.assertFalse((root/'child').exists())
            (root/'proposal').write_text(json.dumps(proposal(raw, rule('a || b'))))
            self.assertEqual(call('lab-check', root/'world', root/'proposal', '--output', root/'child')[0], 0)
            saved = (root/'child').read_bytes()
            self.assertEqual(call('lab-check', root/'world', root/'proposal', '--output', root/'child')[0], 1)
            self.assertEqual((root/'child').read_bytes(), saved)
            (root/'proposal').write_text(json.dumps(proposal(raw, rule('a ||'))))
            self.assertEqual(call('lab-check', root/'world', root/'proposal')[0], 2)
            small = lab.create_world(rule('a || b'), ['a','b'], max_atp=1)
            (root/'world').write_bytes(small)
            (root/'proposal').write_text(json.dumps(proposal(small, rule('a || b'))))
            self.assertEqual(call('lab-check', root/'world', root/'proposal')[0], 3)
            self.assertEqual(call('lab-check', root/'world', root/'absent')[0], 3)
            self.assertEqual(call('lab-check', root/'absent', root/'proposal')[0], 3)
            self.assertFalse((root/'.stargate').exists())


if __name__ == '__main__':
    unittest.main()
