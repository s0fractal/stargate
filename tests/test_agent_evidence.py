"""Check the workflow's event abstraction independently of its WPL expressions."""
import importlib.util
import itertools
import json
from pathlib import Path
import unittest

from stargate import lab, machine, projection
from stargate.projection_runtime import ProjectionMachine

ROOT = Path(__file__).resolve().parents[1]


class AgentEvidence(unittest.TestCase):
    def test_fixed_rules_match_event_meaning_on_every_row(self):
        spec = json.loads((ROOT / 'examples/agent-evidence/fixed.json').read_text())
        raw = machine.create(spec)
        _, table = projection.project(raw, lab.identity(raw))
        runtime = ProjectionMachine.from_bytes(table)
        for eligible, fresh, a, b in itertools.product((False, True), repeat=4):
            expected = dict(eligible=eligible, fresh=fresh)
            if not a and b:
                expected = dict(eligible=False, fresh=False)
            elif a and not b:
                expected['fresh'] = True
            elif a and b:
                expected['eligible'] = eligible or fresh
            self.assertEqual(runtime.step(dict(eligible=eligible, fresh=fresh), dict(a=a, b=b)), expected)

    def test_agent_task_replays_repair_and_refusal_controls(self):
        spec = importlib.util.spec_from_file_location('agent_evidence', ROOT / 'integration/agent_evidence.py')
        tool = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(tool)
        report, artifacts = tool.run()
        self.assertEqual(report['status'], 'passed')
        self.assertEqual(set(artifacts), {'stale.machine', 'fixed.machine', 'stale.proof',
                                         'fixed.proof', 'repair.json', 'successor.json'})
        self.assertEqual(report['controls'], dict(wrong_model='rejected', incomplete_successor='withheld',
                                                 world_change='rejected'))
