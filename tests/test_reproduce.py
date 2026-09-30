"""The handoff runner must not silently downgrade, swallow refusal or overwrite reports."""
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
with patch.object(sys, 'path', [str(ROOT / 'integration'), *sys.path]):
    spec = importlib.util.spec_from_file_location('consumer_reproduce', ROOT / 'integration/reproduce.py')
    runner = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(runner)


class ReproductionReport(unittest.TestCase):
    def test_missing_full_inputs_do_not_downgrade_to_public(self):
        with patch.object(runner, 'public_evidence') as public:
            report = runner.reproduce('full')
        self.assertEqual(report['status'], 'failed')
        self.assertEqual(report['profile'], 'full')
        self.assertEqual(report['stages'], [])
        public.assert_not_called()

    def test_failed_stage_stops_the_run_and_missing_evidence_cannot_pass(self):
        evidence = runner.public_evidence()
        for result in (ValueError('refused'), None):
            with self.subTest(result=result), patch.object(runner, 'preflight', return_value='test-rust'), \
                 patch.object(runner, 'public_evidence', return_value=evidence), \
                 patch.object(runner, 'execute') as execute:
                if isinstance(result, Exception):
                    execute.side_effect = result
                else:
                    execute.return_value = result
                report = runner.reproduce('full', Path('/unused'), Path('/unused'))
                self.assertEqual(report['status'], 'failed')
                self.assertEqual([s['name'] for s in report['stages']], ['public_models', 'warrant_adapter'])
                self.assertEqual(report['stages'][-1]['status'], 'failed')
                execute.assert_called_once()

    def test_empty_public_evidence_cannot_pass(self):
        with patch.object(runner, 'public_evidence', return_value={}):
            report = runner.reproduce('public')
        self.assertEqual(report['status'], 'failed')
        self.assertEqual(report['stages'][0]['status'], 'failed')

    def test_child_refusal_and_ignored_expect_results_are_errors(self):
        for code, output in ((1, b''), (0, b'{}\n')):
            with self.subTest(code=code), patch.object(runner.subprocess, 'run', return_value=
                    subprocess.CompletedProcess([], code, output, b'refused')):
                with self.assertRaises(ValueError):
                    runner.execute('sokol_queue', Path('/unused'), ROOT / runner.ARTIFACTS['queue'])

    def test_changed_saved_observation_is_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            files = list(runner.ARTIFACTS.values()) + ['integration/sokol_trace_probe.rs', 'integration/sokol_queue_probe.rs']
            for rel in files:
                target = root / rel
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(ROOT / rel, target)
            path = root / runner.ARTIFACTS['queue']
            data = json.loads(path.read_text())
            data['traces']['overflow'][2]['lost'] = 0
            path.write_text(json.dumps(data))
            with patch.object(runner, 'ROOT', root), self.assertRaises(ValueError):
                runner.public_evidence()

    def test_existing_report_is_never_overwritten(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'report.json'
            path.write_bytes(b'original report\n')
            run = subprocess.run([sys.executable, str(ROOT / 'integration/reproduce.py'),
                                  '--profile', 'public', '--output', str(path)], capture_output=True)
            self.assertEqual(run.returncode, 2)
            self.assertEqual(path.read_bytes(), b'original report\n')
