"""The read-only pull-request gate. Registered in docs/PR_GATE_REGISTRY.md."""
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

from stargate import certificate, evidence, lab, machine, projection, projection_check
from stargate.canonical import canon, decode

ROOT = Path(__file__).resolve().parent.parent
SPECS = ROOT / 'examples' / 'mcp-proxy' / 'specs'
GATE = ROOT / 'tools' / 'pr_gate.py'
CHECKER = certificate.checker_id()
PCHECKER = projection_check.projection_checker_id()
PATHS = dict(model_path='model.json', projection_path='projection.json', evidence_path='.stargate/evidence.json')


def tool():
    spec = importlib.util.spec_from_file_location('pr_gate', GATE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def artifacts(variant):
    raw = machine.create(json.loads((SPECS / (variant + '.json')).read_text()))
    report, proof = evidence.produce(raw, lab.identity(raw))
    _, table = projection.project(raw, lab.identity(raw))
    model = canon(certificate.model_from_machine(machine.inspect(raw)))
    return dict(model=model, proof=proof, projection=table, status=report['status'])


ART = {v: artifacts(v) for v in ('current', 'historic', 'fixed')}
REPAIR = certificate.pack_repair(ART['current']['proof'], ART['fixed']['proof'])
FOREIGN_REPAIR = certificate.pack_repair(ART['historic']['proof'], ART['fixed']['proof'])


class Repo:
    def __init__(self):
        self.path = Path(tempfile.mkdtemp())
        self.git('init', '-q', '-b', 'main')
        self.git('config', 'user.email', 'gate@test'); self.git('config', 'user.name', 'gate')

    def git(self, *args):
        return subprocess.run(['git', '-C', str(self.path), *args], check=True,
                              capture_output=True, text=True).stdout.strip()

    def commit(self, files, message='x'):
        for name, data in files.items():
            target = self.path / name
            if data is None:
                target.unlink(missing_ok=True); continue
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
        self.git('add', '-A'); self.git('commit', '-q', '--allow-empty', '-m', message)
        return self.git('rev-parse', 'HEAD')

    def state(self):
        return (self.git('for-each-ref'), self.git('status', '--porcelain'), self.git('rev-parse', 'HEAD'))


def base_repo():
    repo = Repo()
    base = repo.commit({'model.json': ART['current']['model'], 'projection.json': ART['current']['projection']}, 'base')
    return repo, base


def run(repo, base, head, **overrides):
    options = dict(PATHS, expect_checker=CHECKER, expect_projection_checker=PCHECKER)
    options.update(overrides)
    before = repo.state()
    try:
        code, report = tool().gate(str(repo.path), base, head, **options)
    except ValueError as exc:
        code, report = 2, dict(status='invalid', error=str(exc))
    after = repo.state()
    return code, report.get('status'), before == after


def head_with(repo, files):
    repo.git('checkout', '-q', '-B', 'pr')
    return repo.commit(files, 'pr')


GOOD = {'model.json': ART['fixed']['model'], 'projection.json': ART['fixed']['projection'],
        '.stargate/evidence.json': REPAIR}


class Verdicts(unittest.TestCase):
    def setUp(self):
        self.assertEqual((ART['current']['status'], ART['fixed']['status']),
                         ('verified_refutation', 'verified_certificate'))
        self.repo, self.base = base_repo()

    def check(self, files, expected, **overrides):
        head = head_with(self.repo, files)
        code, status, untouched = run(self.repo, self.base, head, **overrides)
        self.assertEqual((code, status), expected)
        self.assertTrue(untouched, 'the gate changed the repository')

    def test_01_nothing_guarded_changed(self):
        self.check({'README': b'docs only\n'}, (0, 'untouched'))

    def test_02_valid_repair_and_projection(self):
        self.check(GOOD, (0, 'verified'))

    def test_03_evidence_missing(self):
        self.check(dict(GOOD, **{'.stargate/evidence.json': None}), (3, 'unverified'))

    def test_04_evidence_not_json(self):
        self.check(dict(GOOD, **{'.stargate/evidence.json': b'not json'}), (2, 'invalid'))

    def test_05_evidence_for_another_parent(self):
        self.check(dict(GOOD, **{'.stargate/evidence.json': FOREIGN_REPAIR}), (2, 'invalid'))

    def test_06_another_checker_is_never_a_pass(self):
        code_status = None
        head = head_with(self.repo, GOOD)
        code, status, untouched = run(self.repo, self.base, head, expect_checker='0' * 64)
        self.assertEqual(code, 3)
        self.assertTrue(untouched)

    def test_07_flipped_projection_cell(self):
        table = decode(ART['fixed']['projection']); table['rows'][9]['next']['pending'] ^= True
        self.check(dict(GOOD, **{'projection.json': canon(table)}), (4, 'projection_mismatch'))

    def test_08_head_model_is_not_the_successor(self):
        self.check(dict(GOOD, **{'model.json': ART['historic']['model']}), (4, 'model_not_successor'))

    def test_09_stale_base(self):
        head = head_with(self.repo, GOOD)
        self.repo.git('checkout', '-q', 'main')
        moved = self.repo.commit({'other': b'main moved\n'}, 'main moves')
        code, status, untouched = run(self.repo, moved, head)
        self.assertEqual((code, status), (4, 'stale_base'))

    def test_10_the_verdict_is_about_the_given_head(self):
        good = head_with(self.repo, GOOD)
        bad = dict(GOOD); table = decode(ART['fixed']['projection']); table['rows'][9]['next']['pending'] ^= True
        later = self.repo.commit({'projection.json': canon(table)}, 'later push')
        self.assertEqual(run(self.repo, self.base, good)[:2], (0, 'verified'))
        self.assertEqual(run(self.repo, self.base, later)[:2], (4, 'projection_mismatch'))

    def test_11_projection_deleted(self):
        self.check(dict(GOOD, **{'projection.json': None}), (3, 'unverified'))

    def test_12_unknown_commit_is_invalid(self):
        self.assertEqual(run(self.repo, self.base, 'f' * 40)[:2], (2, 'invalid'))


class Control(unittest.TestCase):
    SITE = "    if successor_model != head_model:\n"

    def test_without_the_successor_check_a_different_head_model_passes(self):
        source = GATE.read_text()
        self.assertIn(self.SITE, source, 'mutation site not found: the control would prove nothing')
        namespace = {'__name__': 'pr_gate_mutant', '__file__': str(GATE)}
        exec(compile(source.replace(self.SITE, '    if False:\n'), 'pr_gate_mutant', 'exec'), namespace)
        repo, base = base_repo()
        head = head_with(repo, dict(GOOD, **{'model.json': ART['historic']['model']}))
        options = dict(PATHS, expect_checker=CHECKER, expect_projection_checker=PCHECKER)
        self.assertEqual(tool().gate(str(repo.path), base, head, **options)[0], 4)
        # the historic model's projection is not the head projection either, so give it its own
        head2 = repo.commit({'projection.json': ART['fixed']['projection']}, 'same projection')
        code, report = namespace['gate'](str(repo.path), base, head2, **options)
        self.assertEqual((code, report['status']), (0, 'verified'))
