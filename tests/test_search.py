import io
import json
from contextlib import redirect_stdout
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from stargate import cli, compiler, lab, search
from stargate.canonical import canon, decode, InvalidRecord


def rule(expression):
    return 'fact a: bool\nfact b: bool\nfact c: bool\ncheck ' + expression


def world(expression='!!(a || b) || c', **kw):
    return lab.create_world(rule(expression), ['a','b','c'], objective='lower_max_atp', **kw)


class Search(unittest.TestCase):
    def test_actual_generator_finds_change_and_allows_independent_replay(self):
        raw = world()
        report, successor = search.search(raw)
        self.assertEqual(report['status'], 'found')
        self.assertEqual((report['attempted'], report['full_checks'], report['screened']), (5, 4, 1))
        self.assertEqual([a['status'] for a in report['attempts']],
                         ['counterexample','counterexample','equivalent','screened','equivalent'])
        checked, rebuilt = lab.verify_transition(raw, report['proposal'])
        self.assertTrue(checked['admitted'])
        self.assertEqual(successor, rebuilt)
        self.assertEqual(decode(successor)['rule'], report['proposal']['candidate'])
        self.assertEqual(decode(successor)['predecessor'], lab.identity(raw))
        self.assertLess(checked['max_atp']['candidate'], checked['max_atp']['parent'])
        self.assertEqual((report, successor), search.search(raw))

    def test_experience_is_replayed_and_prunes_before_full_check(self):
        raw = world()
        previous, _ = search.search(raw)
        memory = previous['experience']
        before = canon(memory)
        with patch.object(lab, 'verify_transition', wraps=lab.verify_transition) as gate:
            report, child = search.search(raw, experience=memory)
        self.assertEqual(canon(memory), before)
        self.assertEqual(report['status'], 'found')
        self.assertGreater(report['screened'], previous['screened'])
        self.assertLess(gate.call_count, previous['full_checks'])
        self.assertEqual(report['full_checks'], gate.call_count)
        self.assertEqual(child, lab.verify_transition(raw, report['proposal'])[1])
        for example in report['experience']['counterexamples']:
            _, row = search._probe(lab.inspect_world(raw), example['candidate'], example['input'])
            self.assertNotEqual(row['parent']['value'], row['candidate']['value'])

    def test_fabricated_foreign_or_malformed_experience_cannot_prune(self):
        raw = world()
        report, _ = search.search(raw)
        for field in ('parent', 'runtime_digest'):
            memory = decode(canon(report['experience'])); memory[field] = '0'*64
            with self.subTest(field=field), self.assertRaises(InvalidRecord):
                search.search(raw, experience=memory)
        memory = decode(canon(report['experience']))
        memory['counterexamples'][0]['candidate'] = rule('!!(a || b) || c')
        with self.assertRaisesRegex(InvalidRecord, 'does not reproduce'):
            search.search(raw, experience=memory)
        for facts in ({'a':False}, {'a':0,'b':False,'c':False}):
            memory = decode(canon(report['experience']))
            memory['counterexamples'][0]['input'] = facts
            with self.subTest(facts=facts), self.assertRaises(InvalidRecord):
                search.search(raw, experience=memory)

    def test_unreplayable_experience_is_not_a_negative_example(self):
        raw = world()
        previous, _ = search.search(raw)
        for exception, status in [(compiler.CompileIncomplete('budget'), 'incomplete'),
                                  (compiler.CompilerBug('fault'), 'checker_error')]:
            with self.subTest(status=status), patch.object(compiler, 'compile_source', side_effect=exception):
                report, child = search.search(raw, experience=previous['experience'])
                self.assertEqual((report['status'], report['attempted'], child), (status,0,None))

    def test_passing_known_examples_never_admits_without_full_gate(self):
        raw = world()
        # Negation first teaches all-false. This wrong conjunction matches that
        # row but disagrees elsewhere. A finite sample is not equivalence.
        streams = [rule('!(!!(a || b) || c)'), rule('a && b && c')]
        with patch.object(search, 'candidates', return_value=iter(streams)), \
             patch.object(lab, 'verify_transition', wraps=lab.verify_transition) as gate:
            report, child = search.search(raw)
        self.assertEqual((report['status'], child), ('neighborhood_exhausted', None))
        self.assertEqual(gate.call_count, 2)
        self.assertEqual(report['attempts'][1]['status'], 'counterexample')

    def test_limits_exhaustion_and_faults_are_not_no_solution(self):
        raw = world()
        report, child = search.search(raw, max_candidates=1)
        self.assertEqual((report['status'], report['reason'], report['attempted'], child),
                         ('search_incomplete','candidate_limit',1,None))
        report, child = search.search(world(max_atp=1))
        self.assertEqual((report['status'], child), ('search_incomplete',None))
        self.assertGreater(report['incomplete_candidates'], 0)
        with patch.object(compiler, 'compile_source', side_effect=compiler.CompilerBug('planted')):
            report, child = search.search(raw)
        self.assertEqual((report['status'], child), ('checker_error',None))
        for n in (0, True, 257):
            with self.subTest(n=n), self.assertRaises(InvalidRecord): search.search(raw, max_candidates=n)

    def test_parent_cost_budget_still_finds_cheaper_successor(self):
        for budget in (43,48):
            with self.subTest(budget=budget):
                raw = world(max_atp=budget)
                report, child = search.search(raw)
                self.assertEqual(report['status'], 'found')
                self.assertEqual(report['attempts'][0]['status'], 'incomplete')
                self.assertGreater(report['incomplete_candidates'], 0)
                self.assertNotIn(report['attempts'][0]['candidate'],
                                 [e['candidate'] for e in report['experience']['counterexamples']])
                verified, expected = lab.verify_transition(raw, report['proposal'])
                self.assertEqual(verified['max_atp'], {'parent':43,'candidate':25})
                self.assertEqual(child, expected)

    def test_screening_oracle_is_checked_for_both_programs(self):
        from stargate import boolean
        raw = world()
        parent = rule('!!(a || b) || c')
        candidate = rule('(a || b) || c')
        original_eval = boolean.evaluate
        original_gate = lab.verify_transition
        for affected in (parent, candidate):
            armed = False
            code = boolean.program(affected, ['a','b','c'])
            def oracle(program, facts):
                value = original_eval(program, facts)
                return not value if armed and program == code else value
            def gate(*args, **kwargs):
                nonlocal armed
                result = original_gate(*args, **kwargs)
                armed = True
                return result
            with self.subTest(affected=affected), \
                 patch.object(search, 'candidates', return_value=iter([rule('!(!!(a || b) || c)'),candidate])), \
                 patch.object(boolean, 'evaluate', side_effect=oracle), \
                 patch.object(lab, 'verify_transition', side_effect=gate) as calls:
                report, child = search.search(raw)
                self.assertEqual(calls.call_count, 1)  # Fault caught by screening, not the later full gate.
                self.assertEqual((report['status'], report['attempts'][1]['status'], child),
                                 ('checker_error','checker_error',None))

    def test_screening_incomplete_skips_only_that_candidate(self):
        raw = world()
        actual = search._probe
        blocked = rule('!!(!!(a || b) || c)')
        candidate = rule('(a || b) || c')
        def probe(doc, text, facts):
            if text == blocked: return {'status':'incomplete', 'reason':'planted budget'}, None
            return actual(doc,text,facts)
        with patch.object(search,'candidates', return_value=iter([rule('!(!!(a || b) || c)'),blocked,candidate])), \
             patch.object(search,'_probe',side_effect=probe):
            report, child = search.search(raw)
        self.assertEqual([a['status'] for a in report['attempts']], ['counterexample','incomplete','equivalent'])
        self.assertEqual((report['status'],report['incomplete_candidates']),('found',1))
        self.assertEqual(child, lab.verify_transition(raw,report['proposal'])[1])

    def test_exhausted_with_incomplete_candidate_exits_three(self):
        raw = world(max_atp=43)
        only = rule('!(!!(a || b) || c)')
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);(root/'world').write_bytes(raw)
            out=io.StringIO()
            with patch.object(search,'candidates',return_value=iter([only])), redirect_stdout(out):
                code=cli.main(['lab-search',str(root/'world'),'--output',str(root/'child')])
            report=json.loads(out.getvalue())
            self.assertEqual((code,report['status'],report.get('reason'),report['incomplete_candidates']),
                             (3,'search_incomplete','incomplete_candidates',1))
            self.assertEqual(report['experience']['counterexamples'],[])
            self.assertFalse((root/'child').exists())

    def test_exact_duplicate_does_not_spend_full_gate_again(self):
        raw = world()
        same = rule('!!(a || b) || c')
        with patch.object(search, 'candidates', return_value=iter([same,same])):
            report, child = search.search(raw)
        self.assertEqual((report['status'],report['full_checks'],child),('neighborhood_exhausted',1,None))
        self.assertEqual(report['attempts'][1]['status'],'duplicate')

    def test_cli_and_no_output_on_budget_refusal(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); (root/'world').write_bytes(world())
            def run(*argv):
                out = io.StringIO()
                with redirect_stdout(out): code = cli.main(list(argv))
                return code,json.loads(out.getvalue())
            code, report = run('lab-search',str(root/'world'),'--max-candidates','1','--output',str(root/'child'))
            self.assertEqual((code,report['status']),(3,'search_incomplete'))
            self.assertFalse((root/'child').exists())
            code, report = run('lab-search',str(root/'world'),'--output',str(root/'child'))
            self.assertEqual((code,report['status']),(0,'found'))
            self.assertEqual(decode((root/'child').read_bytes())['rule'],report['proposal']['candidate'])
            (root/'experience').write_text(json.dumps(report['experience']))
            code, resumed = run('lab-search',str(root/'world'),'--experience',str(root/'experience'))
            self.assertEqual((code,resumed['status']),(0,'found'))
            self.assertGreater(resumed['screened'],report['screened'])
