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
    """Registered control: removing step 7 alone lets outcome 8 pass. Measured: it does
    not — step 8 checks the projection against the HEAD model's ID, which also binds the
    head model, so the mutant refuses at step 8 (invalid). The registration is left as
    written. The planted pull request passes only when step 7 is removed AND step 8 is
    anchored to the successor's model instead of the head's; both mutants run below."""
    SITE = "    if successor_model != head_model:\n"
    ANCHOR = "certificate.identity(head_model),"

    def mutant(self, *replacements):
        source = GATE.read_text()
        for old, new in replacements:
            self.assertIn(old, source, 'mutation site not found: the control would prove nothing')
            source = source.replace(old, new)
        namespace = {'__name__': 'pr_gate_mutant', '__file__': str(GATE)}
        exec(compile(source, 'pr_gate_mutant', 'exec'), namespace)
        return namespace['gate']

    def planted(self):
        repo, base = base_repo()
        head = head_with(repo, dict(GOOD, **{'model.json': ART['historic']['model']}))
        return repo, base, head, dict(PATHS, expect_checker=CHECKER, expect_projection_checker=PCHECKER)

    def outcome(self, gate, *args, **kwargs):
        try:
            code, report = gate(*args, **kwargs)
            return code, report['status']
        except ValueError:
            return 2, 'invalid'

    def test_the_real_gate_refuses_the_planted_pull_request(self):
        repo, base, head, options = self.planted()
        self.assertEqual(self.outcome(tool().gate, str(repo.path), base, head, **options), (4, 'model_not_successor'))

    def test_without_step_7_alone_step_8_still_refuses(self):
        repo, base, head, options = self.planted()
        gate = self.mutant((self.SITE, '    if False:\n'))
        self.assertEqual(self.outcome(gate, str(repo.path), base, head, **options), (2, 'invalid'))

    def test_without_both_bindings_the_planted_pull_request_passes(self):
        repo, base, head, options = self.planted()
        gate = self.mutant((self.SITE, '    if False:\n'),
                           (self.ANCHOR, "certificate.identity(successor_model),"))
        self.assertEqual(self.outcome(gate, str(repo.path), base, head, **options), (0, 'verified'))


class Actuator(unittest.TestCase):
    """Codex's review of #66: the GitHub layer around the gate."""

    def test_a_report_that_does_not_parse_or_disagree_is_never_a_pass(self):
        finish = tool().finish
        cases = {'empty report, exit 0': ('', 0),
                 'not JSON, exit 0': ('garbage', 0),
                 'no status, exit 0': ('{"base": "x"}', 0),
                 'refusal status, exit 0': ('{"status": "projection_mismatch"}', 0),
                 'pass status, exit 3': ('{"status": "verified"}', 3)}
        passed = [name for name, (text, code) in cases.items() if finish(code, text) == 0]
        self.assertEqual(passed, [])
        self.assertEqual(finish(0, '{"status": "verified"}'), 0)
        self.assertEqual(finish(0, '{"status": "untouched"}'), 0)
        self.assertEqual(finish(4, '{"status": "projection_mismatch"}'), 4)

    def test_the_action_installs_nothing_and_uses_no_other_action(self):
        text = (ROOT / 'action.yml').read_text()
        self.assertNotIn('pip install', text)
        self.assertNotIn('uses:', text)
        self.assertNotIn('set +e', text)

    def test_the_gate_runs_from_source_without_site_packages(self):
        """python -I -S: no site-packages, so no installed stargate and no pip dependency."""
        fixture = Path(tempfile.mkdtemp()) / 'fx'
        out = subprocess.run([sys.executable, str(ROOT / 'tools' / 'pr_gate_fixture.py'), str(fixture)],
                             capture_output=True, text=True, check=True).stdout
        values = dict(line.split('=', 1) for line in out.split())
        result = subprocess.run([sys.executable, '-I', '-S', str(GATE), '--repository', str(fixture),
                                 '--base', values['base'], '--head', values['good'], '--model-path', 'model.json',
                                 '--projection-path', 'projection.json', '--evidence-path', '.stargate/evidence.json',
                                 '--expect-checker', values['checker'],
                                 '--expect-projection-checker', values['projection_checker']],
                                capture_output=True, text=True, cwd='/')
        self.assertEqual(result.returncode, 0, result.stderr[-300:])
        self.assertEqual(json.loads(result.stdout)['status'], 'verified')


class Worktree(unittest.TestCase):
    """Found in PR-09b's local check: in a git worktree `.git` is a file, not a directory,
    and the gate took the working tree itself as the Git directory."""

    def test_a_worktree_path_reads_the_same_commits(self):
        repo, base = base_repo()
        head = head_with(repo, GOOD)
        tree = Path(tempfile.mkdtemp()) / 'wt'
        repo.git('worktree', 'add', '-q', str(tree), head)
        options = dict(PATHS, expect_checker=CHECKER, expect_projection_checker=PCHECKER)
        try:
            code, report = tool().gate(str(tree), base, head, **options)
        except ValueError as exc:
            code, report = 2, dict(status='invalid', error=str(exc))
        self.assertEqual((code, report['status']), (0, 'verified'), report.get('error'))
