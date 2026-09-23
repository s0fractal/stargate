"""Which checker may authorize a new state. Registered in docs/ADMISSION_REGISTRY.md."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_pr_gate import ART, GOOD, PATHS, Repo, head_with, tool  # noqa: E402

from stargate import certificate, projection_check  # noqa: E402
from stargate.canonical import canon, decode  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
C1 = certificate.checker_id()
P1 = projection_check.projection_checker_id()
OLD_SOURCES = dict(certificate.sources(), **{'certificate.py': certificate.sources()['certificate.py']
                                             + '# a synthetic older checker, for the transition tests\n'})
C0 = certificate.identity(OLD_SOURCES)


def record(machine=C1, projection=P1, **extra):
    return canon(dict(dict(admission=1, machine_checker=machine, projection_checker=projection), **extra))


def restamp(cert, checker):
    """The same certificate, claimed by another checker closure."""
    doc = decode(cert); doc['checker'] = checker
    return canon(doc)


def repo_with(base_record):
    repo = Repo()
    files = {'model.json': ART['current']['model'], 'projection.json': ART['current']['projection']}
    if base_record is not None:
        files['admission.json'] = base_record
    base = repo.commit(files, 'base')
    return repo, base


def verdict(repo, base, head):
    try:
        code, report = tool().gate(str(repo.path), base, head, admission_path='admission.json', **PATHS)
    except ValueError as exc:
        code, report = 2, dict(status='invalid', error=str(exc))
    return code, report['status']


class Admission(unittest.TestCase):
    def test_1_the_base_record_admits_the_running_checkers(self):
        repo, base = repo_with(record())
        self.assertEqual(verdict(repo, base, head_with(repo, GOOD)), (0, 'verified'))

    def test_2_no_record_is_invalid_even_if_anchored(self):
        self.assertIn('`' + C1 + '`', (ROOT / 'ANCHORS.md').read_text())
        repo, base = repo_with(None)
        self.assertEqual(verdict(repo, base, head_with(repo, GOOD)), (2, 'invalid'))

    def test_2_malformed_records_are_invalid(self):
        for bad in (record(extra=1), record(machine='ab72'), canon(dict(admission=1, machine_checker=[C1, C0], projection_checker=P1))):
            repo, base = repo_with(bad)
            self.assertEqual(verdict(repo, base, head_with(repo, GOOD)), (2, 'invalid'))

    def test_3_a_head_cannot_rewrite_its_own_judge(self):
        repo, base = repo_with(record(machine=C0))
        head = head_with(repo, dict(GOOD, **{'admission.json': record(machine=C1)}))
        self.assertEqual(verdict(repo, base, head), (3, 'checker_unavailable'))

    def test_4_new_code_without_a_transition_fails_closed(self):
        repo, base = repo_with(record(machine=C0))
        self.assertEqual(verdict(repo, base, head_with(repo, GOOD)), (3, 'checker_unavailable'))

    def test_5_a_proof_only_for_the_old_checker_gets_no_admission(self):
        repo, base = repo_with(record(machine=C1))
        head = head_with(repo, dict(GOOD, **{'.stargate/evidence.json': certificate.pack_repair(
            restamp(ART['current']['proof'], C0), restamp(ART['fixed']['proof'], C0))}))
        self.assertEqual(verdict(repo, base, head), (3, 'checker_unavailable'))

    def test_5_but_it_still_verifies_offline_under_its_own_checker(self):
        cert = restamp(ART['fixed']['proof'], C0)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / 'cert.json').write_bytes(cert)
            (root / 'checker.json').write_bytes(canon(OLD_SOURCES))
            (root / 'replay.py').write_bytes((ROOT / 'src' / 'replay.py').read_bytes())
            result = subprocess.run([sys.executable, '-I', '-S', str(root / 'replay.py'), str(root / 'cert.json'),
                                     '--expect-model', certificate.identity(decode(cert)['model']),
                                     '--expect-checker', C0], capture_output=True, text=True, cwd='/')
        self.assertEqual((result.returncode, json.loads(result.stdout or '{}').get('status')), (0, 'verified_certificate'),
                         result.stderr[-300:])


class Control(unittest.TestCase):
    """The running code as the judge: admits test 4's pull request."""
    SITE = "    expect_checker, expect_projection_checker = admitted"

    def test_the_running_code_as_judge_admits_what_the_record_refuses(self):
        source = (ROOT / 'tools' / 'pr_gate.py').read_text()
        self.assertIn(self.SITE, source, 'mutation site not found: the control would prove nothing')
        mutant_source = source.replace(self.SITE, "    expect_checker, expect_projection_checker = "
                                       "certificate.checker_id(), projection_check.projection_checker_id()")
        namespace = {'__name__': 'pr_gate_mutant', '__file__': str(ROOT / 'tools' / 'pr_gate.py')}
        exec(compile(mutant_source, 'pr_gate_mutant', 'exec'), namespace)
        repo, base = repo_with(record(machine=C0))
        head = head_with(repo, GOOD)
        self.assertEqual(verdict(repo, base, head), (3, 'checker_unavailable'))
        code, report = namespace['gate'](str(repo.path), base, head, admission_path='admission.json', **PATHS)
        self.assertEqual((code, report['status']), (0, 'verified'))


class Record(unittest.TestCase):
    def test_the_committed_record_names_the_code_on_this_branch(self):
        """A change to the checker's code must come with an explicit change to the record;
        otherwise the gate on main would fail closed, and this test says so first."""
        record = decode((ROOT / 'guarded' / 'admission.json').read_bytes())
        self.assertEqual(record, dict(admission=1, machine_checker=C1, projection_checker=P1))

    def test_the_workflow_pins_no_checker(self):
        text = (ROOT / '.github' / 'workflows' / 'model-gate.yml').read_text()
        self.assertNotIn('EXPECT_CHECKER', text)
        self.assertIn('ADMISSION_PATH: guarded/admission.json', text)


class Exclusive(unittest.TestCase):
    """Codex's review of #80: a record and pins are strictly exclusive, in every combination."""

    def test_every_mixed_or_partial_combination_is_invalid(self):
        repo, base = repo_with(record())
        head = head_with(repo, GOOD)
        combos = {'record + machine pin': dict(admission_path='admission.json', expect_checker=C1),
                  'record + projection pin': dict(admission_path='admission.json', expect_projection_checker=P1),
                  'record + both pins': dict(admission_path='admission.json', expect_checker=C1, expect_projection_checker=P1),
                  'machine pin only': dict(expect_checker=C1),
                  'projection pin only': dict(expect_projection_checker=P1),
                  'nothing': dict()}
        accepted = []
        for name, options in combos.items():
            try:
                tool().gate(str(repo.path), base, head, **PATHS, **options)
            except ValueError:
                continue
            accepted.append(name)
        self.assertEqual(accepted, [])
