"""The machine proof checker of build 42 stays fixed through the projection vertical.

Expectations are pre-registered in vertical/REGISTRY.md.
"""
import copy
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

from stargate import certificate, KELVIN
from stargate.build import __version__

ROOT = Path(__file__).resolve().parent.parent
TOOL = ROOT / 'tools' / 'vertical_baseline.py'


def tool():
    spec = importlib.util.spec_from_file_location('vertical_baseline', TOOL)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def committed():
    return json.loads((ROOT / 'vertical' / 'baseline.json').read_text())


def run(*args):
    result = subprocess.run([sys.executable, str(TOOL), *args], capture_output=True, text=True)
    return result.returncode, result.stdout


class Baseline(unittest.TestCase):
    def test_the_committed_baseline_describes_this_source(self):
        code, out = run('--check')
        self.assertEqual((code, json.loads(out)['status']), (0, 'established'))
        self.assertEqual(committed()['machine_checker'], certificate.checker_id())

    def test_one_changed_digit_is_refused(self):
        baseline = committed()
        digest = baseline['machine_checker']
        baseline['machine_checker'] = digest[:-1] + ('0' if digest[-1] != '0' else '1')
        code, report = tool().check(baseline)
        self.assertEqual((code, report.get('reason')), (4, 'machine_checker_changed'))

    def test_every_file_of_the_closure_is_watched(self):
        refused = []
        for name in certificate.SOURCES:
            sources = certificate.sources()
            sources[name] += '# one byte more\n'
            code, report = tool().check(committed(), sources)
            if (code, report.get('reason')) == (4, 'machine_checker_changed'):
                refused.append(name)
        self.assertEqual(refused, list(certificate.SOURCES))

    def test_a_file_outside_the_closure_is_not_watched(self):
        for name in ('machine.py', 'cli.py'):
            self.assertNotIn(name, certificate.SOURCES)
        self.assertEqual(tool().check(committed(), certificate.sources())[0], 0)

    def test_another_temperature_is_refused(self):
        baseline = dict(committed(), temperature=KELVIN - 1)
        code, report = tool().check(baseline)
        self.assertEqual((code, report.get('reason')), (4, 'temperature_changed'))

    def test_the_source_build_may_be_newer_than_the_baseline_but_not_older(self):
        baseline_ahead_of_source = dict(committed(), build=str(int(__version__) + 1))
        code, report = tool().check(baseline_ahead_of_source)
        self.assertEqual((code, report.get('reason')), (4, 'build_older_than_baseline'))
        baseline_behind_source = dict(committed(), build=str(int(__version__) - 1))
        self.assertEqual(tool().check(baseline_behind_source)[0], 0)

    def test_malformed_baselines_are_invalid_input(self):
        good = committed()
        cases = {'unknown field': dict(good, extra=1),
                 'missing field': {k: v for k, v in good.items() if k != 'temperature'},
                 'short digest': dict(good, machine_checker='ab72'),
                 'upper-case digest': dict(good, machine_checker=good['machine_checker'].upper()),
                 'build not a number': dict(good, build='forty-two'),
                 'temperature as text': dict(good, temperature='32')}
        codes = {name: tool().check(case)[0] for name, case in cases.items()}
        self.assertEqual(codes, {name: 2 for name in cases})

    def test_a_missing_file_is_invalid_input(self):
        with tempfile.TemporaryDirectory() as tmp:
            code, _ = run('--check', '--baseline', str(Path(tmp) / 'nowhere.json'))
        self.assertEqual(code, 2)

    def test_the_gate_is_outside_every_closure(self):
        self.assertNotIn('vertical_baseline.py', certificate.SOURCES)
        self.assertFalse(str(TOOL).startswith(str(ROOT / 'src')))
