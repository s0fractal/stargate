import copy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from stargate import experiment as e, lab
from stargate.canonical import InvalidRecord, canon, decode


class ExperimentTests(unittest.TestCase):
    def setUp(self):
        self.corpus = {'corpus': 1, 'cases': [
            {'name': 'or', 'inputs': ['a', 'b'], 'rule': 'fact a: bool\nfact b: bool\ncheck a || b', 'max_atp': 1000},
            {'name': 'and', 'inputs': ['a', 'b'], 'rule': 'fact a: bool\nfact b: bool\ncheck a && b', 'max_atp': 1000}]}
        self.runtime = e.pack_runtime()

    def packet(self, parent=None, candidate=None, corpus=None, timeout=30):
        return e.create(parent or self.runtime, candidate or self.runtime,
                        self.corpus if corpus is None else corpus, timeout=timeout)

    def mutate(self, before, after):
        doc = decode(self.runtime)
        self.assertIn(before, doc['sources']['compiler.py'])
        doc['sources']['compiler.py'] = doc['sources']['compiler.py'].replace(before, after)
        return canon(doc)

    def run_packet(self, raw):
        return e.run(raw, expect_controller=e.controller_id(), execute=True)

    def test_agreement_is_full_ordered_observation_not_admission(self):
        raw = self.packet()
        result = self.run_packet(raw)
        self.assertEqual(result['status'], 'agreement')
        self.assertEqual([r['index'] for r in result['rows']], list(range(8)))
        self.assertEqual([r['oracle'] for r in result['rows']], [False, True, True, True, False, False, False, True])
        for row in result['rows']:
            self.assertEqual(row['parent'], row['candidate'])
            self.assertEqual(row['oracle'], row['parent']['value'])
        self.assertEqual(result['experiment_id'], e.digest(decode(raw)))
        self.assertEqual(result['corpus'], e.digest(self.corpus))
        self.assertEqual(result['parent'], e.digest(e.runtime(self.runtime)))
        self.assertEqual(result['incomplete_rows'], [])
        self.assertNotIn('admitted', result)
        self.assertNotIn('successor', result)

    def test_oracle_checks_both_subjects_even_when_they_agree_wrongly(self):
        bad = self.mutate('return CompiledPolicy(check, objects, value, receipt.atp_spent)',
                          'return CompiledPolicy(check, objects, not value, receipt.atp_spent)')
        for parent, candidate, roles in [(bad, self.runtime, {'parent'}),
                                         (self.runtime, bad, {'candidate'}), (bad, bad, {'parent', 'candidate'})]:
            with self.subTest(roles=roles):
                result = self.run_packet(self.packet(parent, candidate))
                self.assertEqual(result['status'], 'oracle_disagreement')
                self.assertEqual({x['role'] for x in result['oracle_disagreements']}, roles)
                self.assertEqual(len(result['oracle_disagreements']), 8 * len(roles))
                self.assertEqual(e.exit_code(result), 4)

    def test_new_corpus_case_exposes_shared_parser_bug_without_rewriting_old_evidence(self):
        wrong = self.mutate("take('||'); expr = ('or', expr, conjunction(depth))",
                            "take('||'); expr = ('and', expr, conjunction(depth))")
        small = {'corpus': 1, 'cases': [self.corpus['cases'][1]]}
        old_packet = self.packet(wrong, wrong, small)
        old = self.run_packet(old_packet)
        self.assertEqual(old['status'], 'agreement')
        new = self.run_packet(self.packet(wrong, wrong))
        self.assertEqual(new['status'], 'oracle_disagreement')
        self.assertEqual(new['oracle_disagreements'], [
            {'index': 1, 'role': 'parent'}, {'index': 1, 'role': 'candidate'},
            {'index': 2, 'role': 'parent'}, {'index': 2, 'role': 'candidate'}])
        self.assertEqual(new['differences'], [])
        self.assertEqual(new['incomplete_rows'], [])
        self.assertEqual(old['parent'], new['parent'])
        self.assertEqual(old['candidate'], new['candidate'])
        self.assertNotEqual(old['corpus'], new['corpus'])
        self.assertNotEqual(old['experiment_id'], new['experiment_id'])
        self.assertEqual(self.run_packet(old_packet)['status'], 'agreement')

    def test_cost_difference_has_concrete_witness_and_is_not_a_semantic_verdict(self):
        changed = self.mutate('return CompiledPolicy(check, objects, value, receipt.atp_spent)',
                              'return CompiledPolicy(check, objects, value, receipt.atp_spent + 1)')
        result = self.run_packet(self.packet(candidate=changed))
        self.assertEqual(result['status'], 'difference')
        self.assertEqual(result['differences'], list(range(8)))
        self.assertEqual(result['oracle_disagreements'], [])
        for row in result['rows']:
            self.assertEqual(row['parent']['value'], row['candidate']['value'])
            self.assertEqual(row['candidate']['atp_spent'], row['parent']['atp_spent'] + 1)

    def test_budget_and_subject_guard_are_incomplete_not_counterexamples(self):
        corpus = copy.deepcopy(self.corpus)
        for case in corpus['cases']: case['max_atp'] = 0
        result = self.run_packet(self.packet(corpus=corpus))
        self.assertEqual(result['status'], 'incomplete')
        self.assertTrue(result['incomplete_rows'])
        guarded = self.mutate('    expr, facts = parse(source, facts, allow_unused=allow_unused)',
                              '    raise CompilerBug("injected guard")\n    expr, facts = parse(source, facts, allow_unused=allow_unused)')
        result = self.run_packet(self.packet(candidate=guarded))
        self.assertEqual(result['status'], 'incomplete')
        self.assertIn('subject_checker_error', [r['candidate'].get('reason') for r in result['rows']])
        self.assertEqual(result['oracle_disagreements'], [])

    def test_execution_requires_independent_pin_and_explicit_flag(self):
        raw = self.packet()
        with patch.object(e, '_run', side_effect=AssertionError('must not execute')):
            with self.assertRaises(InvalidRecord): e.run(raw, expect_controller=e.controller_id())
            self.assertEqual(e.run(raw, expect_controller='0' * 64, execute=True)['status'], 'controller_unavailable')
            doc = decode(raw); doc['controller'] = '0' * 64
            self.assertEqual(self.run_packet(canon(doc))['status'], 'controller_unavailable')

    def test_controller_mismatch_precedes_program_interpretation_not_shape_checks(self):
        doc = decode(self.packet())
        doc['corpus']['cases'][0]['rule'] = 'unknown future grammar'
        doc['controller'] = '0' * 64
        raw = canon(doc)
        with patch.object(e.compiler, 'parse', side_effect=AssertionError('must not interpret a foreign controller corpus')):
            self.assertEqual(e.describe(raw)['status'], 'intact')
            self.assertEqual(self.run_packet(raw)['status'], 'controller_unavailable')
        doc['controller'] = e.controller_id()
        with self.assertRaises(ValueError): self.run_packet(canon(doc))
        doc['controller'] = '0' * 64
        doc['corpus']['cases'][0]['rule'] = 42
        with self.assertRaises(InvalidRecord): self.run_packet(canon(doc))

    def test_inspection_and_export_are_inert(self):
        with tempfile.TemporaryDirectory() as tmp:
            marker = Path(tmp) / 'executed'
            doc = decode(self.runtime)
            doc['sources']['__init__.py'] += '\nopen(' + repr(str(marker)) + ', "w").write("bad")\n'
            raw = self.packet(candidate=canon(doc))
            self.assertEqual(e.describe(raw)['status'], 'intact')
            e.unpack(raw, Path(tmp) / 'out')
            self.assertEqual((Path(tmp) / 'out' / 'LICENSE').read_text(), (Path(__file__).resolve().parents[1] / 'LICENSE').read_text())
            self.assertEqual((Path(tmp) / 'out' / 'README.md').read_text(), e.GUIDE)
            self.assertFalse(marker.exists())
            with self.assertRaises(FileExistsError): e.unpack(raw, Path(tmp) / 'out')
            self.assertTrue((Path(tmp) / 'out' / 'experiment.json').is_file())

    def test_foreign_source_map_and_bad_corpus_rejected_without_execution(self):
        raw = self.packet()
        variants = []
        for value in (None, 3, {'x.py': 'pass'}):
            doc = decode(raw); doc['candidate'] = value; variants.append(doc)
        for change in ('verdict', 'duplicate', 'unsorted', 'float_budget', 'empty'):
            doc = decode(raw)
            if change == 'verdict': doc['corpus']['cases'][0]['verdict'] = True
            if change == 'duplicate': doc['corpus']['cases'][1]['name'] = 'or'
            if change == 'unsorted': doc['corpus']['cases'][0]['inputs'] = ['b', 'a']
            if change == 'float_budget': doc['corpus']['cases'][0]['max_atp'] = True
            if change == 'empty': doc['corpus']['cases'] = []
            variants.append(doc)
        with patch.object(e, '_run', side_effect=AssertionError('must not execute')):
            for doc in variants:
                with self.subTest(doc=str(doc)[:80]), self.assertRaises(InvalidRecord): self.run_packet(canon(doc))

    def test_row_coverage_order_and_types_are_required(self):
        task = [{'max_atp': 100}, {'max_atp': 100}]
        good = [{'index': i, 'observation': {'status': 'complete', 'value': True, 'atp_spent': 0, 'term': '0' * 64}} for i in range(2)]
        e._observations(good, task)
        bad = [good[:1], list(reversed(good)), [good[0], good[0]]]
        for field, value in [('value', 1), ('atp_spent', True), ('atp_spent', 101), ('term', 'wrong')]:
            variant = copy.deepcopy(good); variant[0]['observation'][field] = value; bad.append(variant)
        for variant in bad:
            with self.subTest(variant=variant), self.assertRaises(InvalidRecord): e._observations(variant, task)
        # Exercise the actual process/report boundary, not only the validator.
        truncated = self.mutate('import re', 'import re\nprint("[]")\nraise SystemExit(0)')
        result = self.run_packet(self.packet(candidate=truncated))
        self.assertEqual((result['status'], result.get('reason')), ('incomplete', 'invalid_subject_report'))

    def test_deadline_and_process_failure_are_incomplete(self):
        for code, reason in [('while True: pass', 'deadline'), ('raise RuntimeError("broken")', 'subject_process_failed')]:
            changed = self.mutate('import re', 'import re\n' + code)
            result = self.run_packet(self.packet(candidate=changed, timeout=1))
            self.assertEqual((result['status'], result.get('role'), result.get('reason')), ('incomplete', 'candidate', reason))

    def test_output_limit_is_not_an_observation(self):
        changed = self.mutate('import re', 'import re\nprint("x" * (3 * 1024 * 1024))\nraise SystemExit(0)')
        result = self.run_packet(self.packet(candidate=changed))
        self.assertEqual((result['status'], result.get('reason')), ('incomplete', 'output_limit'))

    def test_build_metadata_is_outside_both_computation_closures(self):
        self.assertNotIn('build.py', e.SUBJECT)
        self.assertNotIn('build.py', lab.RUNTIME)
        texts = e.sources(e.SUBJECT)
        self.assertNotIn('__version__', texts['__init__.py'])
        with tempfile.TemporaryDirectory() as tmp:
            for name, source in texts.items(): (Path(tmp) / name).write_text(source)
            (Path(tmp) / 'build.py').write_text('__version__ = "999"\n')
            self.assertEqual(e.pack_runtime(tmp), self.runtime)
            (Path(tmp) / 'compiler.py').write_text(texts['compiler.py'] + '\n# changed\n')
            self.assertNotEqual(e.pack_runtime(tmp), self.runtime)

    def test_cli_and_plain_python_replay_match_with_hostile_neighbors(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); out = root / 'offline'
            raw = self.packet(); e.unpack(raw, out)
            marker = root / 'shadowed'
            for name in ('tempfile.py', 'sitecustomize.py', 'subprocess.py'):
                (out / name).write_text('open(' + repr(str(marker)) + ', "w").write("bad")\nraise RuntimeError("shadowed")')
            args = [str(out / 'experiment.json'), '--expect-controller', e.controller_id(), '--execute-runtimes']
            cli = subprocess.run([sys.executable, '-I', '-m', 'stargate', 'experiment-check', *args], capture_output=True, text=True, cwd='/')
            replay = subprocess.run([sys.executable, '-I', '-S', str(out / 'replay.py'), *args], capture_output=True, text=True, cwd='/')
            self.assertEqual((cli.returncode, replay.returncode), (0, 0), (cli.stderr, replay.stderr))
            self.assertEqual(json.loads(cli.stdout), json.loads(replay.stdout))
            self.assertFalse(marker.exists())
            self.assertFalse(list(out.rglob('__pycache__')))
            source_map = json.loads((out / 'controller.json').read_bytes())
            source_map['experiment.py'] += '\n# tampered controller\n'
            (out / 'controller.json').write_bytes(canon(source_map))
            replay = subprocess.run([sys.executable, '-I', '-S', str(out / 'replay.py'), *args], capture_output=True, text=True)
            self.assertEqual(replay.returncode, 3)
            self.assertEqual(json.loads(replay.stdout)['status'], 'controller_unavailable')


if __name__ == '__main__': unittest.main()
