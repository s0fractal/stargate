from itertools import product
from pathlib import Path
import json
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from stargate import kernel as k, policy as p
from stargate.records import canon, decode, public_key, verify_record
from stargate.store import Store

EXAMPLE = Path(__file__).with_name('eligibility.wpl').read_text()
RULE = 'fact within_window: bool\nfact retroactive: bool\ncheck within_window && !retroactive'
FACTS = {'within_window': True, 'retroactive': False}


class Policy(unittest.TestCase):
    def test_example_truth_table_and_real_verification(self):
        key = Ed25519PrivateKey.from_private_bytes(bytes(range(32)))
        for window, retro in product((False, True), repeat=2):
            source = (f'fact within_window: bool = {str(window).lower()}\n'
                      f'fact retroactive: bool = {str(retro).lower()}\n'
                      'check within_window && !retroactive')
            with self.subTest(window=window, retro=retro), tempfile.TemporaryDirectory() as tmp:
                store = Store(tmp)
                result = p.author_policy(RULE, dict(within_window=window, retroactive=retro), store, key)
                expected = window and not retro
                self.assertEqual(result['policy_value'], expected)
                self.assertEqual(result['decision'], 'accept' if expected else 'reject')
                report = verify_record(store.read(result['object']), store, {public_key(key)})
                self.assertEqual(report['decision'], result['decision'])
                self.assertEqual(report['outcome']['result_hash'], (k.K_H if expected else k.FALSE_H).hex())
                self.assertEqual(report['outcome']['exit'], 'normal_form')
                self.assertEqual(report['outcome']['atp_spent'], result['atp_spent'])
                self.assertEqual(result['check']['expect'], k.K_H.hex())
                self.assertEqual(store.read(result['policy']['rule']), RULE.encode())

    def test_precedence_parentheses_and_boolean_operators(self):
        cases = [
            ('true || false && false', True),
            ('(true || false) && false', False),
            ('!true || false', False),
            ('!(true || false)', False),
            ('!!false || !false', True),
        ]
        for expr, expected in cases:
            with self.subTest(expr=expr):
                self.assertEqual(p.compile_source('check ' + expr).value, expected)

    def test_compile_reproducible_and_changes_with_facts(self):
        a = p.compile_source(EXAMPLE)
        b = p.compile_source(EXAMPLE)
        c = p.compile_source(EXAMPLE.replace('retroactive: bool = false', 'retroactive: bool = true'))
        self.assertEqual(a.check, b.check)
        self.assertEqual(a.objects, b.objects)
        self.assertNotEqual(a.check['term'], c.check['term'])
        self.assertTrue(a.value); self.assertFalse(c.value)

    def test_unsupported_or_ambiguous_sources_refused(self):
        cases = [
            'fact a: int = 1 check a', 'check 1 < 2', 'check x',
            'fact a: bool = true fact a: bool = false check a',
            'fact a: bool = true check true', 'check true check false',
            'check true; ignored', 'check true & false', 'check false()',
            'check ' + '(' * 34 + 'true' + ')' * 34,
            'check ' + '!' * 300 + 'true', '#' * 8193, 'check true\ud800',
            'fact check: bool = true check true',
        ]
        for source in cases:
            with self.subTest(source=source[:60]), self.assertRaises(p.PolicyError):
                p.compile_source(source)

    def test_budget_failure_writes_nothing(self):
        key = Ed25519PrivateKey.generate()
        for budget in (-1, True, 1.5, 0, 2**32):
            with tempfile.TemporaryDirectory() as tmp:
                with self.assertRaises(p.PolicyError):
                    p.author_policy(RULE, FACTS, Store(tmp), key, max_atp=budget)
                self.assertEqual(list(Path(tmp).iterdir()), [])

    def test_wrong_lowering_refused_before_emission(self):
        with tempfile.TemporaryDirectory() as tmp:
            with patch.object(p, 'lower', return_value=('thunk', k.K_H)):
                with self.assertRaises(p.CompilerBug):
                    p.author_policy('check false', {}, Store(tmp), Ed25519PrivateKey.generate())
            self.assertEqual(list(Path(tmp).iterdir()), [])

    def test_serialized_budget_mutation_is_caught(self):
        original = p.canon
        def mutate(doc):
            return original(dict(doc, atp=0))
        with patch.object(p, 'canon', mutate), self.assertRaises(p.CompilerBug):
            p.compile_source(EXAMPLE)

    def test_cli_policy_then_verify_and_flip_input(self):
        with tempfile.TemporaryDirectory() as tmp:
            def run(*args):
                r = subprocess.run([sys.executable, '-m', 'stargate', '--store', tmp+'/objects', *args],
                                   capture_output=True, text=True)
                self.assertEqual(r.returncode, 0, r.stdout+r.stderr)
                return json.loads(r.stdout)
            key_path = tmp+'/key'; pub = run('keygen', key_path)['key']
            source = Path(tmp)/'rule.wpl'; source.write_text(RULE)
            facts = Path(tmp)/'facts.json'; facts.write_text(json.dumps(FACTS))
            first = run('policy', str(source), '--facts', str(facts), '--key', key_path)
            self.assertEqual(run('verify', first['object'], '--trust', pub)['decision'], 'accept')
            facts.write_text(json.dumps(dict(FACTS, retroactive=True)))
            second = run('policy', str(source), '--facts', str(facts), '--key', key_path)
            self.assertEqual(run('verify', second['object'], '--trust', pub)['decision'], 'reject')
            self.assertNotEqual(first['record'], second['record'])
            # Retaining a changed local source cannot rewrite the first signed term.
            self.assertEqual(run('verify', first['object'], '--trust', pub)['decision'], 'accept')
