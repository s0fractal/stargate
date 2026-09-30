"""A handoff must be replayable and must not turn a producer verdict into proof."""
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from stargate import certificate, transport
from stargate.canonical import canon

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('agent_task', ROOT / 'tools/agent_task.py')
tool = importlib.util.module_from_spec(spec)
spec.loader.exec_module(tool)


class AgentTask(unittest.TestCase):
    def check_task(self, output, name='fixed', **kwargs):
        path = ROOT / 'examples/agent-evidence' / (name+'.json')
        return tool.run(path, hashlib.sha256(path.read_bytes()).hexdigest(),
                        certificate.checker_id(), output, **kwargs)

    def test_certificate_and_refutation_replay_without_installed_package(self):
        for name, code in [('fixed', 0), ('stale', 4)]:
            with self.subTest(name=name), tempfile.TemporaryDirectory() as tmp:
                output = Path(tmp) / 'handoff'
                report, actual = self.check_task(output, name)
                self.assertEqual(actual, code)
                # Authenticate launcher against our installed copy, not packet metadata.
                self.assertEqual(hashlib.sha256((output/'replay.py').read_bytes()).hexdigest(),
                                 transport.replay_digest())
                replay = subprocess.run([sys.executable, *report['replay_argv'][1:]], cwd=output,
                                        capture_output=True, text=True)
                self.assertEqual(replay.returncode, code, replay.stderr)
                self.assertEqual(json.loads(replay.stdout)['status'], report['status'])
                # A real changed proof must fail even with the unchanged success report.
                proof = output / ('certificate.json' if code == 0 else 'refutation.json')
                doc = json.loads(proof.read_text())
                doc['model']['invariant'] += ' '
                proof.write_bytes(canon(doc))
                replay = subprocess.run([sys.executable, *report['replay_argv'][1:]], cwd=output,
                                        capture_output=True, text=True)
                self.assertEqual(replay.returncode, 2)

    def test_incomplete_run_and_producer_lies_publish_nothing(self):
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / 'handoff'
            report, code = self.check_task(output, max_edges=0)
            self.assertEqual((report['status'], code), ('incomplete', 3))
            self.assertFalse(output.exists())
            for produced, proof in [(dict(status='verified_certificate'), None),
                                    (dict(status='verified_certificate'), b'{}'),
                                    (dict(status='unexpected'), None)]:
                with patch.object(tool.evidence, 'produce', return_value=(produced, proof)):
                    try:
                        report, code = self.check_task(output)
                    except ValueError:
                        pass
                    else:
                        self.assertEqual(code, 1)
                    self.assertFalse(output.exists())

    def test_input_anchor_and_existing_output_are_not_overridden(self):
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / 'handoff'
            path = ROOT / 'examples/agent-evidence/fixed.json'
            with self.assertRaises(ValueError):
                tool.run(path, '0'*64, certificate.checker_id(), output)
            self.assertFalse(output.exists())
            report, code = tool.run(path, hashlib.sha256(path.read_bytes()).hexdigest(), '0'*64, output)
            self.assertEqual((report['status'], code), ('checker_unavailable', 3))
            self.assertFalse(output.exists())
            output.mkdir()
            (output/'sentinel').write_text('keep')
            with self.assertRaises(ValueError):
                self.check_task(output)
            self.assertEqual((output/'sentinel').read_text(), 'keep')

    def make_parent(self, tmp):
        report, code = self.check_task(Path(tmp)/'parent', 'stale')
        self.assertEqual(code, 4)
        return dict(repair_parent=Path(tmp)/'parent/refutation.json', expected_parent=report['model_id'])

    def test_repair_preserves_objection_and_replays_successor_offline(self):
        with tempfile.TemporaryDirectory() as tmp:
            parent = self.make_parent(tmp)
            out = Path(tmp)/'repair'
            report, code = self.check_task(out, **parent)
            self.assertEqual((report['status'], code), ('verified_repair', 0))
            packet = json.loads((out/'repair.json').read_text())
            self.assertEqual(canon(packet['refutation']), parent['repair_parent'].read_bytes())
            self.assertEqual(hashlib.sha256((out/'replay.py').read_bytes()).hexdigest(), transport.replay_digest())
            replay = subprocess.run([sys.executable, *report['replay_argv'][1:], '--output', 'replayed.json'],
                                    cwd=out, capture_output=True, text=True)
            self.assertEqual(replay.returncode, 0, replay.stderr)
            self.assertEqual((out/'replayed.json').read_bytes(), (out/'successor.json').read_bytes())

    def test_unsafe_candidate_wrong_parent_and_incomplete_repair_publish_nothing(self):
        with tempfile.TemporaryDirectory() as tmp:
            parent = self.make_parent(tmp)
            out = Path(tmp)/'repair'
            report, code = self.check_task(out, 'stale', **parent)
            self.assertEqual((report['status'], code), ('not_repaired', 4))
            self.assertFalse(out.exists())
            with self.assertRaises(ValueError):
                self.check_task(out, **dict(parent, expected_parent='0'*64))
            report, code = self.check_task(out, max_steps=0, **parent)
            self.assertEqual((report['status'], code), ('incomplete', 3))
            self.assertFalse(out.exists())
            # Exercise a refusal at the last gate, after candidate production succeeds.
            with patch.object(tool.certificate, 'verify_repair', return_value=(dict(status='incomplete'), None)):
                report, code = self.check_task(out, **parent)
            self.assertEqual((report['status'], code), ('incomplete', 3))
            self.assertFalse(out.exists())

    def test_certified_world_change_is_not_an_allowed_repair(self):
        with tempfile.TemporaryDirectory() as tmp:
            parent = self.make_parent(tmp)
            spec = json.loads((ROOT/'examples/agent-evidence/fixed.json').read_text())
            spec['next']['fresh'] = spec['next']['fresh'].split('check ')[0] + 'check true\n'
            path = Path(tmp)/'cheat.json'
            path.write_text(json.dumps(spec))
            out = Path(tmp)/'repair'
            with self.assertRaisesRegex(ValueError, 'world rule'):
                tool.run(path, hashlib.sha256(path.read_bytes()).hexdigest(), certificate.checker_id(), out, **parent)
            self.assertFalse(out.exists())

    def test_success_label_without_correct_successor_is_not_publishable(self):
        with tempfile.TemporaryDirectory() as tmp:
            parent = self.make_parent(tmp)
            out = Path(tmp)/'repair'
            for successor in (None, parent['repair_parent'].read_bytes()):
                with patch.object(tool.certificate, 'verify_repair',
                                  return_value=(dict(status='verified_repair'), successor)):
                    try:
                        report, code = self.check_task(out, **parent)
                    except ValueError:
                        pass
                    else:
                        self.assertEqual((report['status'], code), ('checker_error', 1))
                    self.assertFalse(out.exists())
