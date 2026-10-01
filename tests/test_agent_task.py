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

    def test_search_finds_repair_and_exports_editable_candidate_for_offline_replay(self):
        from stargate import machine
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)/'search'
            report, code = self.check_task(out, 'stale', search='synth', max_candidates=1)
            self.assertEqual((report['status'], code), ('verified_repair', 0))
            self.assertEqual(report['search']['attempted'], 1)
            candidate = (out/'candidate-spec.json').read_bytes()
            self.assertEqual(hashlib.sha256(candidate).hexdigest(), report['candidate_spec_sha256'])
            raw = machine.create(json.loads(candidate))
            self.assertEqual(certificate.identity(certificate.model_from_machine(json.loads(raw))),
                             report['successor_model'])
            self.assertEqual(hashlib.sha256((out/'replay.py').read_bytes()).hexdigest(), transport.replay_digest())
            replay = subprocess.run([sys.executable, *report['replay_argv'][1:], '--output', 'replayed.json'],
                                    cwd=out, capture_output=True, text=True)
            self.assertEqual(replay.returncode, 0, replay.stderr)
            self.assertEqual((out/'replayed.json').read_bytes(), (out/'successor.json').read_bytes())

    def test_search_stops_at_explicit_budget_without_export_or_escalation(self):
        cases = [('stale', 'one-edit', 1, 'search_incomplete', 3),
                 ('stale', 'one-edit', 256, 'neighborhood_exhausted', 4),
                 ('fixed', 'synth', 1, 'not_needed', 4)]
        for name, strategy, quota, status, expected in cases:
            with self.subTest(status=status), tempfile.TemporaryDirectory() as tmp:
                out = Path(tmp)/'search'
                report, code = self.check_task(out, name, search=strategy, max_candidates=quota)
                self.assertEqual((report['status'], code), (status, expected))
                self.assertLessEqual(report['search']['attempted'], quota)
                self.assertEqual(report['search']['strategy'], strategy)
                self.assertFalse(out.exists())
        with tempfile.TemporaryDirectory() as tmp:
            for kwargs in (dict(search='synth'), dict(max_candidates=1),
                           dict(search='synth', max_candidates=0),
                           dict(search='synth', max_candidates=257),
                           dict(search='synth', max_candidates=1, repair_parent=Path('/unused'), expected_parent='0'*64)):
                with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                    self.check_task(Path(tmp)/'none', 'stale', **kwargs)

    def test_search_success_label_does_not_replace_evidence_or_parent_binding(self):
        from stargate import evidence, lab, machine
        foreign = machine.create(json.loads((ROOT/'examples/publisher-binding/stale.json').read_text()))
        _, foreign_proof = evidence.repair_search(foreign, lab.identity(foreign), strategy='synth', max_candidates=1)
        for result in ((dict(status='found'), None), (dict(status='found'), b'{}'),
                       (dict(status='found'), foreign_proof), (None, None)):
            with self.subTest(result=result[0]), tempfile.TemporaryDirectory() as tmp:
                out = Path(tmp)/'search'
                with patch.object(tool.evidence, 'repair_search', return_value=result):
                    try:
                        report, code = self.check_task(out, 'stale', search='synth', max_candidates=1)
                    except ValueError:
                        pass
                    else:
                        self.assertEqual(code, 1)
                self.assertFalse(out.exists())

    def test_search_final_refusal_and_missing_successor_block_export(self):
        from stargate import evidence, lab, machine
        raw = machine.create(json.loads((ROOT/'examples/agent-evidence/stale.json').read_text()))
        produced, proof = evidence.repair_search(raw, lab.identity(raw), strategy='synth', max_candidates=1)
        for verdict, code in ((dict(status='incomplete'), 3), (dict(status='verified_repair'), 1)):
            with tempfile.TemporaryDirectory() as tmp:
                out = Path(tmp)/'search'
                with patch.object(tool.evidence, 'repair_search', return_value=(produced, proof)), \
                     patch.object(tool.certificate, 'verify_repair', return_value=(verdict, None)):
                    report, actual = self.check_task(out, 'stale', search='synth', max_candidates=1)
                self.assertEqual(actual, code)
                self.assertFalse(out.exists())
