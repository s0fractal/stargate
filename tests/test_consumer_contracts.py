"""Contract boundaries: unchanged roots, live-goal meaning, real consumer oracles."""
import importlib.util
import json
from pathlib import Path
import unittest

from stargate import certificate, evidence, lab, machine, projection
from stargate.canonical import decode
from stargate.projection_runtime import ProjectionMachine

ROOT = Path(__file__).resolve().parents[1]


def tool(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / 'integration' / (name + '.py'))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class ConsumerContracts(unittest.TestCase):
    def test_new_mcp_roots_only_add_explicit_world_and_hand_repair_verifies(self):
        proofs = {}
        for variant in ('current', 'fixed'):
            new = json.loads((ROOT / 'examples/mcp-owned' / (variant + '.json')).read_text())
            old = json.loads((ROOT / 'examples/mcp-proxy/specs' / (variant + '.json')).read_text())
            self.assertEqual(new, dict(old, world=['calls.one', 'calls.two']))
            raw = machine.create(new)
            report, proofs[variant] = evidence.produce(raw, lab.identity(raw))
            self.assertEqual(report['status'], 'verified_refutation' if variant == 'current' else 'verified_certificate')
        packet = certificate.pack_repair(proofs['current'], proofs['fixed'])
        report, successor = certificate.verify_repair(packet, certificate.identity(decode(proofs['current'])['model']),
                                                       certificate.checker_id())
        self.assertEqual(report['status'], 'verified_repair')
        self.assertIsNotNone(successor)

    def test_live_goal_allows_an_infinite_self_loop_if_a_completion_path_exists(self):
        raw = machine.create(dict(state=['done'], events=['go'], initial=[dict(done=False)],
            next=dict(done='fact done: bool\nfact go: bool\ncheck done || go\n'),
            invariant='fact done: bool\ncheck true\n', goals=[dict(done=True)],
            live_goals=[dict(done=True)], max_atp=1000))
        report, proof = evidence.produce(raw, lab.identity(raw))
        self.assertEqual(report['status'], 'verified_certificate')
        _, table = projection.project(raw, lab.identity(raw))
        runtime = ProjectionMachine.from_bytes(table)
        self.assertEqual(runtime.step(dict(done=False), dict(go=False)), dict(done=False))
        self.assertEqual(runtime.step(dict(done=False), dict(go=True)), dict(done=True))

    def test_delivery_model_and_oracle_reject_losing_an_unknown_ack(self):
        harness = tool('sokol_delivery')
        reports, runtime = harness.models()
        self.assertEqual(reports['synth']['status'], 'found')
        self.assertEqual(reports['comparison']['unequal_reachable_rows'], 0)
        rows = {name: dict(pending=int(name not in harness.KNOWN), done=int(name in harness.KNOWN),
                          lost=0, error=name not in harness.KNOWN) for name in harness.CASES}
        self.assertEqual(harness.mismatches(rows, runtime), [])
        rows['unknown'] = dict(pending=0, done=1, lost=0, error=False)
        self.assertEqual(harness.mismatches(rows, runtime), ['unknown'])
