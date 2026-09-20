from stargate import transport
import itertools
import io
from contextlib import redirect_stdout, redirect_stderr
import json
import os
from pathlib import Path
import random
import py_compile
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from stargate import boolean, compiler, kernel, lab, cli
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
        self.assertEqual(decode(child)['rule'], rule(expr, names))
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
        def broken(source, inputs=None, **kw):
            return original(source.replace('||', '&&'), inputs, **kw)
        with patch.object(compiler, 'parse', broken), patch.object(boolean, 'evaluate', wraps=boolean.evaluate) as second:
            report, child = lab.verify_transition(raw, proposal(raw, rule('a || b')))
        self.assertGreater(second.call_count, 0)
        self.assertEqual(report['status'], 'checker_error')
        self.assertEqual((report['status'], report['reason'], report['input'],
                          report['compiled'], report['oracle'], child),
                         ('checker_error', 'independent oracle disagreement',
                          {'a': False, 'b': True}, False, True, None))

    def test_parent_only_oracle_disagreement(self):
        raw = lab.create_world(rule('a || b'), ['a', 'b'])
        candidate = rule('!(!a && !b)')
        original = compiler.parse
        def broken(source, inputs=None, **kw):
            return original(source.replace('||', '&&'), inputs, **kw)
        with patch.object(compiler, 'parse', broken):
            report, child = lab.verify_transition(raw, proposal(raw, candidate))
        self.assertEqual(report['status'], 'checker_error')
        self.assertEqual((report['program'], report['input'], child),
                         ('parent', {'a': False, 'b': True}, None))

    def test_lowering_fault_is_checker_error_through_cli(self):
        raw = lab.create_world(rule('a && b'), ['a', 'b'])
        original = compiler.lower
        def broken(expr, facts):
            return original(('or', *expr[1:]) if expr[0] == 'and' else expr, facts)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root/'world').write_bytes(raw)
            (root/'proposal').write_text(json.dumps(proposal(raw, rule('a && b'))))
            output = io.StringIO()
            with patch.object(compiler, 'lower', broken), redirect_stdout(output):
                code = cli.main(['lab-check', str(root/'world'), str(root/'proposal'),
                                 '--output', str(root/'child')])
            self.assertEqual(code, 1)
            self.assertEqual(json.loads(output.getvalue())['status'], 'checker_error')
            self.assertFalse((root/'child').exists())

    def test_candidate_also_has_to_agree_with_oracle(self):
        raw = lab.create_world(rule('!(!a && !b)'), ['a', 'b'])
        original = compiler.parse
        def broken(source, inputs=None, **kw):
            return original(source.replace('||', '&&'), inputs, **kw)
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
        with self.assertRaises(lab.RuntimeMismatch): lab.inspect_world(canon(doc))
        with self.assertRaises(InvalidRecord): lab.inspect_world(raw + b'\n')
        for field, value in [('inputs', list('abcdefghi')), ('max_atp', True),
                             ('inputs', ['b', 'a']), ('max_atp', 10001),
                             ('objective', 'trust_me')]:
            doc = decode(raw); doc[field] = value
            with self.subTest(field=field), self.assertRaises(InvalidRecord):
                lab.inspect_world(canon(doc))

    def test_historical_runtime_precedes_guide_and_license_matching(self):
        # Captured from accepted 9a52255; all source strings match that Git tree.
        raw = Path(__file__).with_name('world-build17-9a52255.json').read_bytes()
        self.assertEqual(lab.identity(raw), '3ef32eb7c844bcf93b5b60e4113ea980365e2d805e751e64a663870d2b1f74b9')
        old = decode(raw)
        self.assertNotEqual(old['guide'], lab.GUIDE)
        with self.assertRaises(lab.RuntimeMismatch): lab.inspect_world(raw)
        out = io.StringIO()
        with redirect_stderr(out):
            code = cli.main(['inspect', '--expect-kind', 'lab', str(Path(__file__).with_name('world-build17-9a52255.json'))])
        self.assertEqual((code, json.loads(out.getvalue())['status']), (3, 'runtime_unavailable'))
        for field in ('guide', 'license'):
            current = decode(lab.create_world('check true', []))
            current[field] += '\nchanged text'
            with self.subTest(field=field):
                with self.assertRaises(InvalidRecord): lab.inspect_world(canon(current))
                current['sources']['lab.py'] += '\n# other runtime'
                with self.assertRaises(lab.RuntimeMismatch): lab.inspect_world(canon(current))

    def test_different_text_source_sets_are_unavailable_not_invalid(self):
        raw = lab.create_world('check true', [])
        for change in ('add', 'remove', 'empty', 'rename'):
            doc = decode(raw)
            if change == 'add': doc['sources']['future.py'] = '# not executed'
            elif change == 'remove': del doc['sources']['lineage.py']
            elif change == 'empty': doc['sources'] = {}
            else: doc['sources']['new-name.py'] = doc['sources'].pop('lineage.py')
            with self.subTest(change=change), self.assertRaises(lab.RuntimeMismatch):
                lab.inspect_world(canon(doc))
        # Names are inert data; unsupported maps refuse before any extraction.
        doc = decode(raw); doc['sources']['../../escape'] = 'raise AssertionError()'
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp)/'unpacked'
            with self.assertRaises(lab.RuntimeMismatch): transport.unpack_world(canon(doc), output)
            self.assertFalse(output.exists())

    def test_malformed_runtime_material_is_still_invalid(self):
        raw = Path(__file__).with_name('world-build17-9a52255.json').read_bytes()
        for field in ('guide', 'license', 'sources'):
            doc = decode(raw); doc[field] = None
            with self.subTest(field=field), self.assertRaises(InvalidRecord):
                lab.inspect_world(canon(doc))
        for value in (None, 7, {}, []):
            doc = decode(raw); doc['sources']['lab.py'] = value
            with self.subTest(value=value), self.assertRaises(InvalidRecord):
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
            transport.unpack_world(raw, root)
            (root/'proposal.json').write_text(json.dumps(p))
            result = subprocess.run([sys.executable, '-I', '-S', str(root/'replay.py'),
                                     str(root/'proposal.json'), str(root/'child.json'),
                                     '--expect-runtime', lab.runtime_digest(decode(raw)['sources'])],
                                    cwd='/', capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(json.loads(result.stdout), expected)
            self.assertEqual((root/'child.json').read_bytes(), successor)
            self.assertEqual((root/'LICENSE').read_text(), lab.LICENSE)
            self.assertEqual((root/'replay.py').stat().st_mode & 0o777, 0o600)
            with self.assertRaises(FileExistsError): transport.unpack_world(raw, root)
            self.assertEqual((root/'child.json').read_bytes(), successor)

    def test_runtime_digest_and_replay_preflight(self):
        import hashlib
        raw = lab.create_world(rule('a || b'), ['a', 'b'])
        sources = decode(raw)['sources']
        expected = hashlib.sha256(json.dumps(sources, sort_keys=True, ensure_ascii=False,
                                 separators=(',', ':')).encode()).hexdigest()
        report, _ = lab.verify_transition(raw, proposal(raw, rule('a || b')))
        self.assertEqual(report['runtime_digest'], expected)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)/'packet'
            transport.unpack_world(raw, root)
            (root/'proposal.json').write_text(json.dumps(proposal(raw, rule('a && b'))))
            argv = [sys.executable, '-I', '-S', str(root/'replay.py'),
                    str(root/'proposal.json'), str(root/'child.json')]
            missing = subprocess.run(argv, cwd='/', capture_output=True, text=True)
            self.assertEqual(missing.returncode, 2)
            self.assertFalse((root/'child.json').exists())
            # An actually malicious packet would also replace its self-check.
            # Keep a separately trusted launcher, and assert refusal BEFORE import.
            marker = root/'executed'
            bad = root/'stargate/lab.py'
            bad.write_text("from pathlib import Path\nPath(" + repr(str(marker)) + ").touch()\n" +
                           sources['lab.py'].replace("if doc['contract'] == 'boolean-exhaustive-1' and results[0]['value'] != results[1]['value']:", 'if False:'))
            # Keep packet and extracted malicious runtime mutually consistent:
            # without independent preflight, their self-pin would pass.
            changed = decode(raw)
            changed['sources']['lab.py'] = bad.read_text()
            changed_raw = canon(changed)
            (root/'world.json').write_bytes(changed_raw)
            (root/'proposal.json').write_text(json.dumps(proposal(changed_raw, rule('a && b'))))
            result = subprocess.run(argv + ['--expect-runtime', expected],
                                    cwd='/', capture_output=True, text=True)
            self.assertEqual(result.returncode, 3, result.stderr)
            data = json.loads(result.stdout)
            self.assertEqual((data['status'], data['expected_runtime'], data['admitted']),
                             ('runtime_unavailable', expected, False))
            self.assertNotEqual(data['runtime_digest'], expected)
            self.assertFalse(marker.exists())
            self.assertFalse((root/'child.json').exists())

    def test_replay_ignores_adjacent_modules_and_valid_poisoned_pyc(self):
        names = list('abcdefgh')
        raw = lab.create_world(rule(' || '.join(names), names), names)
        expected = lab.runtime_digest(decode(raw)['sources'])
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)/'packet'
            transport.unpack_world(raw, root)
            marker = root/'executed'
            payload = ("from pathlib import Path\nPath(" + repr(str(marker)) + ").touch()\n"
                       "import itertools\nitertools.product = lambda *a, **kw: [(False,)*kw['repeat']]\n")
            # Both top-level shadowing and a timestamp-valid module cache are
            # outside the source-map digest. Test each with a fresh process.
            for attack in ('neighbor', 'bytecode'):
                with self.subTest(attack=attack):
                    marker.unlink(missing_ok=True)
                    if attack == 'neighbor':
                        (root/'tempfile.py').write_text(payload)
                    else:
                        (root/'tempfile.py').unlink()
                        target = root/'stargate/boolean.py'
                        original = target.read_bytes()
                        original_stat = target.stat()
                        poisoned = payload.encode() + original
                        poisoned += b' ' * ((len(original)-len(poisoned)) % 4)
                        # Timestamp pyc validity checks source size and mtime.
                        # Write a header with the original size after compilation.
                        target.write_bytes(poisoned)
                        os.utime(target, ns=(original_stat.st_atime_ns, original_stat.st_mtime_ns))
                        cache = Path(py_compile.compile(str(target), doraise=True,
                                    invalidation_mode=py_compile.PycInvalidationMode.TIMESTAMP))
                        cached = bytearray(cache.read_bytes())
                        cached[12:16] = len(original).to_bytes(4, 'little')
                        cache.write_bytes(cached)
                        target.write_bytes(original)
                        os.utime(target, ns=(original_stat.st_atime_ns, original_stat.st_mtime_ns))
                    for expr, status, code in [(' || '.join(names), 'equivalent', 0),
                                               (' && '.join(names), 'counterexample', 4)]:
                        (root/'proposal.json').write_text(json.dumps(proposal(raw, rule(expr, names))))
                        result = subprocess.run([sys.executable, '-I', '-S', str(root/'replay.py'),
                                      '--expect-runtime', expected, str(root/'proposal.json')],
                                      cwd='/', capture_output=True, text=True)
                        self.assertEqual(result.returncode, code, result.stderr)
                        report = json.loads(result.stdout)
                        self.assertEqual(report['status'], status)
                        if code == 0:
                            self.assertEqual(len(report['rows']), 256)
                        self.assertFalse(marker.exists())

    def test_replay_executes_snapshot_not_later_disk_contents(self):
        raw = lab.create_world(rule('a || b'), ['a', 'b'])
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)/'packet'
            transport.unpack_world(raw, root)
            (root/'proposal.json').write_text(json.dumps(proposal(raw, rule('a || b'))))
            # Harness instrumentation of the trusted launcher simulates a file
            # changing after hashing. It is not a packet-provided hook.
            injection = "(root / 'stargate' / 'boolean.py').write_text('raise RuntimeError(123)')"
            anchor = '        load(texts, names)'
            original = transport.replay_source()
            self.assertIn(anchor, original)
            (root/'replay.py').write_text(original.replace(anchor, '        '+injection+'\n'+anchor))
            result = subprocess.run([sys.executable, '-I', '-S', str(root/'replay.py'),
                           '--expect-runtime', lab.runtime_digest(decode(raw)['sources']),
                           str(root/'proposal.json')], cwd='/', capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(json.loads(result.stdout)['status'], 'equivalent')
            self.assertEqual((root/'stargate/boolean.py').read_text(), 'raise RuntimeError(123)')

    def test_incomplete_or_duplicate_enumeration_is_checker_error(self):
        raw = lab.create_world(rule('a || b'), ['a', 'b'])
        p = proposal(raw, rule('a || b'))
        for rows in [[(False, False)], [(False, False)]*4]:
            with self.subTest(rows=rows), patch.object(lab.itertools, 'product', return_value=rows):
                report, child = lab.verify_transition(raw, p)
                self.assertEqual((report['status'], report['admitted'], child), ('checker_error', False, None))

    def test_unpack_failure_cleanup_and_no_execution(self):
        raw = lab.create_world('check true', [])
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)/'packet'
            original_open = os.open
            def fail_write(path, flags, *args, **kwargs):
                if flags & os.O_WRONLY:
                    raise OSError('disk full')
                return original_open(path, flags, *args, **kwargs)
            with patch.object(transport.os, 'open', side_effect=fail_write):
                with self.assertRaises(OSError): transport.unpack_world(raw, root)
            self.assertFalse(root.exists())
            with patch.object(compiler, 'compile_source', side_effect=AssertionError('must not evaluate')):
                transport.unpack_world(raw, root)
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
            self.assertEqual(call('inspect', '--expect-kind', 'lab', root/'world')[1]['world_id'], created['world_id'])
            self.assertEqual(call('inspect', '--expect-kind', 'lab', root/'world')[1]['runtime_digest'],
                             lab.runtime_digest(lab.runtime_sources()))
            self.assertEqual(call('inspect', '--expect-kind', 'lab', root/'world')[1]['replay_digest'],
                             lab.identity(transport.replay_source().encode()))
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
