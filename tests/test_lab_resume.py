import itertools
import random
import unittest
from unittest.mock import patch

from stargate import lab, compiler, boolean, kernel
from stargate.canonical import canon, decode, InvalidRecord


def rule(expr, names=('a', 'b', 'c')):
    return ''.join('fact '+name+': bool\n' for name in names)+'check '+expr


def setup(parent='a || b || c', candidate='a || b || c', **options):
    raw = lab.create_world(rule(parent), list('abc'), **options)
    return raw, dict(parent=lab.identity(raw), candidate=rule(candidate))


class LabResume(unittest.TestCase):
    def finish(self, raw, proposal, chunks):
        state = lab.start_transition(raw, proposal)
        sizes = itertools.cycle(chunks)
        while state.status == 'suspended':
            lab.resume_transition(state, rows=next(sizes))
        return state

    def test_slicing_matches_all_terminal_outcomes_and_exact_successors(self):
        cases = [
            (*setup(), 'equivalent', True),
            (*setup(candidate='a && b && c'), 'counterexample', False),
            (*setup(objective='lower_max_atp'), 'equivalent', False),
            (*setup(parent='!!(a || b || c)', objective='lower_max_atp'), 'equivalent', True),
            (*setup(max_atp=1), 'incomplete', False),
            (*setup(parent='a && b && c', properties=[dict(kind='monotone', input='a')]), 'satisfies', True),
            (*setup(candidate='!a || b || c', properties=[dict(kind='monotone', input='a')]), 'counterexample', False),
            (*setup(properties=[dict(kind='constant', value=False)]), 'parent_rejected', False),
        ]
        rng = random.Random(20)
        for raw, proposal, status, admitted in cases:
            expected, child = lab.verify_transition(raw, proposal)
            self.assertEqual((expected['status'], expected['admitted']), (status, admitted))
            for chunks in ([1], [3], [0, 2, 5], [rng.randint(1, 5) for _ in range(8)]):
                with self.subTest(status=status, chunks=chunks):
                    state = self.finish(raw, proposal, chunks)
                    self.assertEqual(state.status, status)
                    self.assertEqual(canon(state.report), canon(expected))
                    self.assertEqual(state.successor, child)
                    with self.assertRaisesRegex(InvalidRecord, 'only a suspended'):
                        lab.resume_transition(state, rows=1)

    def test_exact_ordered_work_is_retained_and_quota_never_overshoots(self):
        raw, proposal = setup()
        compile_real, oracle_real, eval_real = compiler.compile_source, boolean.evaluate, kernel.eval_receipt
        def measured(chunks):
            events = []
            def compile(source, **kw):
                events.append(('compile', source, tuple(kw['facts'].items()), kw['max_atp']))
                return compile_real(source, **kw)
            def oracle(code, facts):
                events.append(('oracle', tuple(facts.items())))
                return oracle_real(code, facts)
            def evaluate(*args, **kw):
                events.append(('eval', args[0], args[1]))
                return eval_real(*args, **kw)
            with patch.object(compiler, 'compile_source', side_effect=compile), \
                 patch.object(boolean, 'evaluate', side_effect=oracle), \
                 patch.object(kernel, 'eval_receipt', side_effect=evaluate):
                state = lab.start_transition(raw, proposal)
                self.assertEqual(events, [])
                sizes = itertools.cycle(chunks)
                while state.status == 'suspended':
                    before = len(state.report['rows'])
                    quota = next(sizes)
                    prior = len(events)
                    lab.resume_transition(state, rows=quota)
                    self.assertEqual(len(state.report['rows']), min(8, before+quota))
                    if quota == 0:
                        self.assertEqual(len(events), prior)
                    if len(state.report['rows']) < 8:
                        self.assertEqual(state.status, 'suspended')
                        self.assertFalse(state.report['admitted'])
                        self.assertIsNone(state.successor)
                return events, state.report
        whole, expected = measured([256])
        self.assertEqual(sum(e[0] == 'compile' for e in whole), 16)
        self.assertEqual(sum(e[0] == 'oracle' for e in whole), 16)
        self.assertEqual(sum(e[0] == 'eval' for e in whole), 32)  # compiler plus exact-budget replay
        for chunks in ([1], [0, 3, 2], [7, 1]):
            events, report = measured(chunks)
            self.assertEqual(events, whole)
            self.assertEqual(report, expected)

    def test_inputs_and_report_snapshots_cannot_replace_owned_work(self):
        raw, proposal = setup()
        expected = lab.verify_transition(raw, proposal)
        state = lab.start_transition(raw, proposal, rows=1)
        proposal['candidate'] = rule('a && b && c')
        proposal['parent'] = '0'*64
        report = state.report
        report['rows'][0]['parent']['value'] = True
        report['rows'].clear()
        report.update(status='equivalent', admitted=True, total_rows=0)
        with self.assertRaises(InvalidRecord):
            lab.resume_transition(report, rows=256)
        lab.resume_transition(state, rows=256)
        self.assertEqual((state.report, state.successor), expected)
        terminal = state.report
        terminal['admitted'] = False
        self.assertTrue(state.report['admitted'])

    def test_no_inputs_and_eight_inputs_finish_on_exact_last_row(self):
        for names in ([], list('abcdefgh')):
            source = rule(' || '.join(names) if names else 'true', names)
            raw = lab.create_world(source, names)
            proposal = dict(parent=lab.identity(raw), candidate=source)
            state = lab.start_transition(raw, proposal)
            for count in range(1, 2**len(names)+1):
                lab.resume_transition(state, rows=1)
                self.assertEqual(len(state.report['rows']), count)
                self.assertEqual(state.status, 'equivalent' if count == 2**len(names) else 'suspended')
            self.assertIsNotNone(state.successor)

    def test_bad_quota_and_bad_input_do_no_work_and_do_not_consume_state(self):
        raw, proposal = setup()
        state = lab.start_transition(raw, proposal)
        with patch.object(compiler, 'compile_source', side_effect=AssertionError('must not execute')):
            for quota in (-1, 257, True, 1.0, None):
                with self.subTest(quota=quota):
                    with self.assertRaises(InvalidRecord): lab.start_transition(raw, proposal, rows=quota)
                    with self.assertRaises(InvalidRecord): lab.resume_transition(state, rows=quota)
            with self.assertRaises(InvalidRecord):
                lab.start_transition(raw, dict(parent='0'*64, candidate='check true'))
            with self.assertRaises(compiler.PolicyError):
                lab.start_transition(raw, dict(parent=lab.identity(raw), candidate=rule('a &&')))
            lab.resume_transition(state, rows=0)
        self.assertEqual(state.status, 'suspended')
        lab.resume_transition(state, rows=256)
        self.assertTrue(state.report['admitted'])

    def test_incomplete_checker_error_and_unexpected_fault_never_resume(self):
        raw, proposal = setup()
        for failure, status in [(compiler.CompileIncomplete('budget'), 'incomplete'),
                                (kernel.ResourceFault('local limit'), 'incomplete'),
                                (compiler.CompilerBug('lowering'), 'checker_error')]:
            state = lab.start_transition(raw, proposal, rows=1)
            with patch.object(compiler, 'compile_source', side_effect=failure):
                lab.resume_transition(state, rows=1)
            self.assertEqual(state.status, status)
            self.assertEqual(len(state.report['rows']), 1)
            self.assertIsNone(state.successor)
            with self.assertRaises(InvalidRecord): lab.resume_transition(state, rows=1)
        state = lab.start_transition(raw, proposal, rows=1)
        # Deliberately contradict row 001's true output.
        with patch.object(boolean, 'evaluate', return_value=False):
            lab.resume_transition(state, rows=1)
        self.assertEqual(state.status, 'checker_error')
        self.assertIn('oracle disagreement', state.report['reason'])
        with self.assertRaises(InvalidRecord): lab.resume_transition(state, rows=1)
        state = lab.start_transition(raw, proposal, rows=1)
        with patch.object(compiler, 'compile_source', side_effect=RuntimeError('unexpected')):
            with self.assertRaisesRegex(RuntimeError, 'unexpected'): lab.resume_transition(state, rows=1)
        self.assertEqual(state.status, 'faulted')
        self.assertFalse(state.report['admitted'])
        self.assertIsNone(state.successor)
        with self.assertRaises(InvalidRecord): lab.resume_transition(state, rows=1)

    def test_suspended_and_faulted_reports_are_progress_not_verdicts(self):
        raw, proposal = setup()
        for expected_status in ('suspended', 'faulted'):
            with self.subTest(status=expected_status):
                state = lab.start_transition(raw, proposal, rows=3)
                if expected_status == 'faulted':
                    with patch.object(compiler, 'compile_source', side_effect=RuntimeError('interrupted')):
                        with self.assertRaisesRegex(RuntimeError, 'interrupted'):
                            lab.resume_transition(state, rows=1)
                report = state.report
                # Pin the public snapshot, not merely the object's status.
                self.assertEqual(report['status'], expected_status)
                self.assertIs(report['admitted'], False)
                self.assertIsNone(state.successor)
                # Exact progress shape excludes verdict-only fields such as
                # successor, reason, max_atp, witness and property_results.
                self.assertEqual(set(report), {
                    'status', 'parent', 'runtime_digest', 'candidate',
                    'rows', 'total_rows', 'admitted'})
                self.assertEqual(report['total_rows'], 8)
                self.assertEqual([row['input'] for row in report['rows']], [
                    {'a': False, 'b': False, 'c': False},
                    {'a': False, 'b': False, 'c': True},
                    {'a': False, 'b': True, 'c': False}])
        # Actual ATP exhaustion must retain its terminal classification.
        limited, proposal = setup(max_atp=1)
        exhausted = lab.start_transition(limited, proposal, rows=1)
        self.assertEqual(exhausted.report['status'], 'incomplete')
        self.assertIs(exhausted.report['admitted'], False)
        self.assertIn('reason', exhausted.report)
        self.assertIsNone(exhausted.successor)

    def test_interleaved_sessions_own_separate_work(self):
        raw, yes = setup()
        no = dict(yes, candidate=rule('a && b && c'))
        left = lab.start_transition(raw, yes, rows=1)
        right = lab.start_transition(raw, no, rows=1)
        lab.resume_transition(left, rows=2)
        self.assertEqual(len(right.report['rows']), 1)
        lab.resume_transition(right, rows=1)
        self.assertEqual(right.status, 'counterexample')
        lab.resume_transition(left, rows=256)
        self.assertEqual(left.status, 'equivalent')
        self.assertIsNotNone(left.successor)
        self.assertIsNone(right.successor)
