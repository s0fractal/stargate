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

    def recheck(self, output, name='fixed', **kwargs):
        source = ROOT/'examples/agent-evidence'/(name+'.json')
        return tool.check_handoff(output, hashlib.sha256(source.read_bytes()).hexdigest(),
                                  certificate.checker_id(), **kwargs)

    def test_handoff_recheck_all_modes_without_trusting_or_executing_packet_code(self):
        with tempfile.TemporaryDirectory() as tmp:
            parent = self.make_parent(tmp)
            for mode, name, options, code in [
                    ('certificate', 'fixed', {}, 0), ('refutation', 'stale', {}, 4),
                    ('repair', 'fixed', parent, 0),
                    ('search', 'stale', dict(search='synth', max_candidates=1), 0)]:
                with self.subTest(mode=mode):
                    out = Path(tmp)/mode
                    self.check_task(out, name, **options)
                    # Neither code nor a forged success/command in the packet is authority.
                    (out/'replay.py').write_text('raise RuntimeError("must not execute")')
                    (out/'checker.json').write_bytes(b'not a checker')
                    (out/'task-report.json').write_bytes(b'not even JSON')
                    before = {p.name: p.read_bytes() for p in out.iterdir()}
                    anchors = dict(expected_parent=parent['expected_parent']) if mode in ('repair', 'search') else {}
                    report, actual = self.recheck(out, name, **anchors)
                    self.assertEqual(actual, code)
                    self.assertEqual(report['authority'], 'observation_only')
                    self.assertEqual(before, {p.name: p.read_bytes() for p in out.iterdir()})
                    if anchors:
                        self.assertEqual(report['input_role'], 'parent' if mode == 'search' else 'candidate')

    def test_handoff_recheck_refuses_changed_data_and_ambiguous_proofs(self):
        for filename, replacement in [('input-spec.json', b'{}'), ('input.machine', b'{}'),
                                       ('certificate.json', b'{}'), ('refutation.json', b'{}')]:
            with self.subTest(filename=filename), tempfile.TemporaryDirectory() as tmp:
                out = Path(tmp)/'handoff'
                self.check_task(out)
                (out/filename).write_bytes(replacement)
                with self.assertRaises(ValueError):
                    self.recheck(out)
        with tempfile.TemporaryDirectory() as tmp:
            out, foreign = Path(tmp)/'handoff', Path(tmp)/'foreign'
            self.check_task(out)
            self.check_task(foreign, 'stale')
            (out/'certificate.json').unlink()
            (out/'refutation.json').write_bytes((foreign/'refutation.json').read_bytes())
            with self.assertRaises(ValueError):
                self.recheck(out)

    def test_repair_handoff_recheck_refuses_missing_or_changed_successor_and_candidate(self):
        for filename in ('successor.json', 'candidate-spec.json'):
            for content in (None, b'{}'):
                with self.subTest(filename=filename, content=content), tempfile.TemporaryDirectory() as tmp:
                    out = Path(tmp)/'search'
                    report, _ = self.check_task(out, 'stale', search='synth', max_candidates=1)
                    if content is None:
                        (out/filename).unlink()
                    else:
                        (out/filename).write_bytes(content)
                    with self.assertRaises((ValueError, OSError)):
                        self.recheck(out, 'stale', expected_parent=report['parent_model'])

    def test_handoff_recheck_requires_selected_parent_and_honors_refusal_and_budget(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)/'search'
            report, _ = self.check_task(out, 'stale', search='synth', max_candidates=1)
            for parent in (None, '0'*64):
                with self.assertRaises(ValueError):
                    self.recheck(out, 'stale', expected_parent=parent)
            result, code = self.recheck(out, 'stale', expected_parent=report['parent_model'], max_steps=0)
            self.assertEqual((result['status'], code), ('incomplete', 3))
            for checked, successor in [(dict(status='incomplete'), None),
                                       (dict(status='verified_repair'), None)]:
                with patch.object(certificate, 'verify_repair', return_value=(checked, successor)):
                    if successor is None and checked['status'] == 'verified_repair':
                        with self.assertRaises(ValueError):
                            self.recheck(out, 'stale', expected_parent=report['parent_model'])
                    else:
                        result, code = self.recheck(out, 'stale', expected_parent=report['parent_model'])
                        self.assertEqual((result['status'], code), ('incomplete', 3))

    def test_handoff_recheck_binds_valid_specifications_to_the_actual_repair(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)/'search'
            report, _ = self.check_task(out, 'stale', search='synth', max_candidates=1)
            candidate_path = out/'candidate-spec.json'
            original = candidate_path.read_bytes()
            changed = json.loads(original)
            changed['invariant'] += ' '
            changed_bytes = json.dumps(changed).encode()
            changed_machine = tool.machine.create(changed)
            candidate_path.write_bytes(changed_bytes)
            with self.assertRaisesRegex(ValueError, 'candidate specification differs'):
                self.recheck(out, 'stale', expected_parent=report['parent_model'])
            candidate_path.write_bytes(original)
            # Even a matching spec/machine pair selected by the recipient must be
            # related to the actual repair; valid syntax and hashes are insufficient.
            (out/'input-spec.json').write_bytes(changed_bytes)
            (out/'input.machine').write_bytes(changed_machine)
            with self.assertRaisesRegex(ValueError, 'neither repair parent nor candidate'):
                tool.check_handoff(out, hashlib.sha256(changed_bytes).hexdigest(),
                                   certificate.checker_id(), expected_parent=report['parent_model'])

    def test_handoff_cli_recheck_and_invalid_option_combination(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)/'handoff'
            report, _ = self.check_task(out)
            command = [sys.executable, str(ROOT/'tools/agent_task.py'), str(out),
                       '--check-handoff', '--expect-spec', report['spec_sha256'],
                       '--expect-checker', report['checker']]
            result = subprocess.run(command, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(json.loads(result.stdout)['status'], 'verified_certificate')
            result = subprocess.run(command + ['--output', str(Path(tmp)/'new')],
                                    capture_output=True, text=True)
            self.assertEqual(result.returncode, 2)
            self.assertEqual(json.loads(result.stdout)['status'], 'invalid')
            self.assertFalse((Path(tmp)/'new').exists())

    def test_failed_export_is_removed_and_same_task_can_retry(self):
        original_open = Path.open
        for filename, failure in [('input.machine', OSError),
                                  ('task-report.json', OSError),
                                  ('candidate-spec.json', KeyboardInterrupt)]:
            with self.subTest(filename=filename), tempfile.TemporaryDirectory() as tmp:
                output = Path(tmp)/'handoff'
                # Search exercises successor and candidate export as well as the report.
                options = dict(search='synth', max_candidates=1)
                def interrupted_open(path, *args, **kwargs):
                    if path.name == filename:
                        # Leave a real partially written file, not just a failed open.
                        with original_open(path, 'xb') as stream:
                            stream.write(b'partial')
                        raise failure('injected write interruption')
                    return original_open(path, *args, **kwargs)
                with patch.object(Path, 'open', interrupted_open):
                    with self.assertRaises(failure):
                        self.check_task(output, 'stale', **options)
                self.assertFalse(output.exists())
                report, code = self.check_task(output, 'stale', **options)
                self.assertEqual(code, 0)
                replay = subprocess.run([sys.executable, *report['replay_argv'][1:]],
                                        cwd=output, capture_output=True, text=True)
                self.assertEqual(replay.returncode, 0, replay.stderr)

    def test_destination_created_during_verification_is_preserved(self):
        original_unpack = transport.unpack_certificate
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp)/'handoff'
            def competing_export(*args, **kwargs):
                output.mkdir()
                (output/'sentinel').write_bytes(b'another writer')
                return original_unpack(*args, **kwargs)
            with patch.object(transport, 'unpack_certificate', competing_export):
                with self.assertRaises(FileExistsError):
                    self.check_task(output)
            self.assertEqual(list(output.iterdir()), [output/'sentinel'])
            self.assertEqual((output/'sentinel').read_bytes(), b'another writer')

    def test_cleanup_failure_preserves_original_error_and_never_returns_success(self):
        original_open = Path.open
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp)/'handoff'
            def failed_open(path, *args, **kwargs):
                if path.name == 'task-report.json':
                    raise OSError('original export failure')
                return original_open(path, *args, **kwargs)
            with patch.object(Path, 'open', failed_open), \
                 patch.object(tool.shutil, 'rmtree', side_effect=OSError('cleanup denied')):
                with self.assertRaisesRegex(OSError, 'original export failure') as caught:
                    self.check_task(output)
            self.assertIn('cleanup denied', caught.exception.__notes__[0])
            self.assertFalse((output/'task-report.json').exists())
            with self.assertRaises(ValueError):
                self.check_task(output)

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
