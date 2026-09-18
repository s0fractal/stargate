import itertools
import tempfile
from pathlib import Path
import unittest
from unittest.mock import patch
from stargate import compiler,boolean,lab,machine,search,policy,records
from stargate.canonical import canon,decode

SOURCE='fact a: bool\nfact b: bool\ncheck a'

class LabInputs(unittest.TestCase):
    def test_unused_declarations_have_no_artificial_atp_cost(self):
        costs=[]
        for a,b in itertools.product([False,True],repeat=2):
            facts=dict(a=a,b=b)
            result=compiler.compile_source(SOURCE,facts=facts,allow_unused=True)
            costs.append(result.atp_spent)
            self.assertEqual(result.value,a)
            self.assertEqual(boolean.evaluate(boolean.program(SOURCE,['a','b'],allow_unused=True),facts),a)
        self.assertEqual(costs,[3,3,0,0])
        for method in [lambda:compiler.compile_source(SOURCE,facts=dict(a=True,b=False)),
                       lambda:boolean.program(SOURCE,['a','b'])]:
            with self.assertRaises((compiler.PolicyError,boolean.BooleanSyntax)):method()

    def test_authoring_refuses_unused_facts_before_record_creation(self):
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
        from stargate.store import Store
        key=Ed25519PrivateKey.generate()
        with tempfile.TemporaryDirectory() as tmp:
            store=Store(tmp)
            # Positive control: real signing and storage work with these fixtures.
            accepted=policy.author_policy('fact a: bool\ncheck a',dict(a=True),store,key)
            self.assertEqual(accepted['decision'],'accept')
            before={p.name:p.read_bytes() for p in Path(tmp).iterdir()}
            with patch.object(policy,'create_record',wraps=policy.create_record) as create:
                with self.assertRaises(ValueError) as refusal:
                    policy.author_policy(SOURCE,dict(a=True,b=False),store,key)
                self.assertIsInstance(refusal.exception,compiler.PolicyError)
                self.assertIn('unused',str(refusal.exception))
                create.assert_not_called()
            self.assertEqual({p.name:p.read_bytes() for p in Path(tmp).iterdir()},before)

    def test_both_lab_parsers_still_require_exact_declarations(self):
        for source in ['fact a: bool\ncheck a','fact a: bool\nfact b: bool\nfact c: bool\ncheck a',
                       'fact a: bool\nfact b: bool\ncheck c']:
            with self.assertRaises((compiler.PolicyError,boolean.BooleanSyntax)):lab.create_world(source,['a','b'])
        raw=lab.create_world(SOURCE,['a','b'])
        report,child=lab.verify_transition(raw,dict(parent=lab.identity(raw),candidate=SOURCE))
        self.assertEqual(report['status'],'equivalent');self.assertTrue(report['admitted'])
        self.assertEqual(len(report['rows']),4)
        self.assertEqual([r['parent']['value'] for r in report['rows']],[False,False,True,True])

    def test_machine_changes_search_and_discovery_accept_irrelevant_inputs(self):
        def rule(expr):return 'fact a: bool\nfact b: bool\ncheck '+expr
        raw=machine.create(dict(state=['a','b'],events=[],initial=[dict(a=False,b=False)],
            next=dict(a=rule('a'),b=rule('!b')),invariant=rule('!a'),max_atp=1000))
        anchor=lab.identity(raw)
        self.assertEqual(machine.verify(raw,anchor)['status'],'established')
        report=machine.discover_properties(raw,anchor)
        self.assertEqual(report['status'],'complete')
        report,child=machine.verify_change(raw,dict(parent=anchor,next=dict(a=rule('false'),b=rule('b'))),anchor)
        self.assertTrue(report['admitted'])
        report,child=search.search_machine(raw,anchor)
        self.assertEqual(report['status'],'found');self.assertIsNotNone(child)

    def test_signed_provenance_cannot_opt_out_of_used_fact_rule(self):
        # A genuine compiled raw computation may exist; binding it to signed
        # provenance must still invoke strict compilation and reject unused facts.
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
        from stargate import kernel
        facts=dict(a=True,b=False)
        compiled=compiler.compile_source(SOURCE,facts=facts,allow_unused=True)
        objects=dict(compiled.objects)
        rule=SOURCE.encode();fact_bytes=canon(facts)
        objects[kernel.sha(rule)]=rule;objects[kernel.sha(fact_bytes)]=fact_bytes
        binding=dict(rule=kernel.sha(rule).hex(),facts=kernel.sha(fact_bytes).hex())
        with self.assertRaisesRegex(ValueError, 'unused'):
            records.create_record(compiled.check,objects,Ed25519PrivateKey.generate(),policy=binding)
