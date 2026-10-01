"""Joint admission must consume both current, independently checked contracts."""
import importlib.util
import itertools
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from stargate import certificate, lab, projection
from stargate.projection_runtime import ProjectionMachine

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('shared_action', ROOT/'integration/shared_action.py')
tool = importlib.util.module_from_spec(spec)
spec.loader.exec_module(tool)


class SharedAction(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.report, cls.artifacts = tool.run()
        cls.world = cls.artifacts['world.json']
        cls.contracts = {role: cls.artifacts[role+'.json'] for role in tool.ROLES}
        cls.selections = json.loads(cls.artifacts['selections.json'])

    def inputs(self, name):
        result = self.report['cases'][name]
        proofs = {role: self.artifacts[name+'/'+role+'/'+
                  ('certificate.json' if result['checks'][role]['check']['status'] == 'verified_certificate'
                   else 'refutation.json')] for role in tool.ROLES}
        return self.artifacts[name+'/candidate.json'], proofs

    def check(self, name, **overrides):
        candidate, proofs = self.inputs(name)
        args = dict(world=self.world, candidate=candidate, contracts=self.contracts, proofs=proofs,
                    expected_world=self.selections['world'],
                    expected_candidate=self.selections['candidates'][name],
                    expected_contracts=self.selections['contracts'], expected_checker=self.selections['checker'])
        args.update(overrides)
        return tool.check(**args)

    def test_only_one_candidate_satisfies_both_selected_contracts(self):
        for name in ('premature', 'hoard', 'guarded'):
            report = self.check(name)
            self.assertEqual(report['admitted'], name == 'guarded')
            self.assertEqual(report['status'], 'admissible' if name == 'guarded' else 'candidate_refuted')
        self.assertEqual(self.report['objections']['premature']['custodian']['kind'], 'unsafe')
        self.assertEqual(self.report['objections']['hoard']['reclaimer']['kind'], 'unreachable_goal')
        self.assertEqual(self.report['global_incompatibility'], 'not_established')

    def test_transition_tables_match_resource_semantics_on_all_48_rows(self):
        for name in ('premature', 'hoard', 'guarded'):
            candidate, _ = self.inputs(name)
            _, raw, _ = tool.materialize(self.world, candidate, self.contracts['custodian'])
            _, table = projection.project(raw, lab.identity(raw))
            runtime = ProjectionMachine.from_bytes(table)
            for ack, held, a, b in itertools.product((False, True), repeat=4):
                releases = b and (name == 'premature' or (name == 'guarded' and ack))
                expected = dict(ack=ack or a, held=held and not releases)
                self.assertEqual(runtime.step(dict(ack=ack, held=held), dict(a=a, b=b)), expected)

    def test_missing_foreign_and_substituted_inputs_never_admit(self):
        candidate, proofs = self.inputs('guarded')
        _, stale = self.inputs('hoard')
        for changes in [dict(proofs={'custodian': proofs['custodian']}),
                        dict(proofs=dict(proofs, custodian=stale['custodian'])),
                        dict(contracts=dict(self.contracts, custodian=self.contracts['reclaimer'])),
                        dict(candidate=self.inputs('premature')[0]),
                        dict(world=self.world+b' '),
                        dict(proofs=dict(proofs, reclaimer=b'{}'))]:
            with self.subTest(changes=list(changes)), self.assertRaises(ValueError):
                self.check('guarded', **changes)

    def test_one_incomplete_party_blocks_joint_admission_even_if_other_passes(self):
        verify = tool.evidence.verify
        _, proofs = self.inputs('guarded')
        for role in tool.ROLES:
            def limited(raw, *args, **kwargs):
                if raw == proofs[role]:
                    return dict(status='incomplete')
                return verify(raw, *args, **kwargs)
            with patch.object(tool.evidence, 'verify', limited):
                result = self.check('guarded')
            self.assertFalse(result['admitted'])
            self.assertEqual(result['status'], 'undetermined')
        self.assertFalse(self.check('guarded', max_steps=0)['admitted'])
        self.assertEqual(self.check('guarded', expected_checker='0'*64)['status'], 'checker_unavailable')

    def test_valid_proof_under_weakened_policy_cannot_replace_owner_requirement(self):
        candidate, proofs = self.inputs('premature')
        weakened = json.loads(self.contracts['custodian'])
        weakened['invariant'] = weakened['invariant'].replace('held || ack', 'true')
        weakened_bytes = json.dumps(weakened).encode()
        _, raw, _ = tool.materialize(self.world, candidate, weakened_bytes)
        produced, proof = tool.evidence.produce(raw, lab.identity(raw))
        self.assertEqual(produced['status'], 'verified_certificate')
        with self.assertRaisesRegex(ValueError, 'recipient selection'):
            self.check('premature', contracts=dict(self.contracts, custodian=weakened_bytes),
                       proofs=dict(proofs, custodian=proof))

    def test_saved_evidence_can_be_rechecked_without_producer(self):
        task_spec = importlib.util.spec_from_file_location('agent_task', ROOT/'tools/agent_task.py')
        task = importlib.util.module_from_spec(task_spec)
        task_spec.loader.exec_module(task)
        with tempfile.TemporaryDirectory() as tmp:
            for name in ('premature', 'hoard', 'guarded'):
                for role in tool.ROLES:
                    prefix = name+'/'+role+'/'
                    out = Path(tmp)/name/role
                    out.mkdir(parents=True)
                    for filename, raw in self.artifacts.items():
                        if filename.startswith(prefix):
                            (out/filename[len(prefix):]).write_bytes(raw)
                    expected_spec = tool.digest(self.artifacts[prefix+'input-spec.json'])
                    with patch.object(tool.evidence, 'produce', side_effect=AssertionError('must not produce')):
                        checked, code = task.check_handoff(out, expected_spec, self.selections['checker'])
                    expected = self.report['cases'][name]['checks'][role]['check']['status']
                    self.assertEqual(checked['status'], expected)
                    self.assertEqual(code, 0 if expected == 'verified_certificate' else 4)
