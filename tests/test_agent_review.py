"""The shadow agent reviewer's publisher (tools/agent_review.py, docs/AGENT_REVIEW.md).

The reviewer CLI is replaced by a fake executable; what is tested is what surrounds it:
binding, isolation of the reviewer, the verdict contract and the status it yields.
"""
import contextlib
import importlib.util
import io
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parent.parent
# CI runs these tests from outside the checkout with -I, so `tests` is not a package there.
_spec = importlib.util.spec_from_file_location('_pr_gate_publish_tests', ROOT / 'tests' / 'test_pr_gate_publish.py')
_shared = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_shared)
FakeGitHub, FIXTURE, REPO = _shared.FakeGitHub, _shared.FIXTURE, _shared.REPO
REVIEW = ROOT / 'tools' / 'agent_review.py'
SECRET = 'oauth-test-credential-0123456789'
CONTEXT = 'stargate/agent-review'


def module(source=None):
    if source is None:
        spec = importlib.util.spec_from_file_location('agent_review', REVIEW)
        loaded = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(loaded)
        return loaded
    namespace = {'__name__': 'agent_review_mutant', '__file__': str(REVIEW)}
    exec(compile(source, 'agent_review_mutant', 'exec'), namespace)
    return type('Mutant', (), {k: staticmethod(v) if callable(v) else v for k, v in namespace.items()})


def answer(verdict, *findings, summary='s'):
    return dict(verdict=verdict, summary=summary,
                findings=[dict(severity=s, location='f.py:1', claim='c') for s in findings])


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp()); self.addCleanup(shutil.rmtree, self.tmp)
        out = subprocess.run([sys.executable, str(FIXTURE), str(self.tmp / 'origin')],
                             capture_output=True, text=True, check=True).stdout
        self.v = dict(line.split('=', 1) for line in out.split())
        subprocess.run(['git', 'clone', '-q', str(self.tmp / 'origin'), str(self.tmp / 'clone')], check=True)
        self.seen = self.tmp / 'seen.json'

    def fake_claude(self, stdout, exit_code=0):
        """An executable that records what the reviewer would see, prints `stdout`, exits."""
        path = self.tmp / 'claude'
        path.write_text(f'''#!{sys.executable}
import json, os, sys
json.dump(dict(argv=sys.argv[1:], env=sorted(os.environ), cwd=sorted(os.listdir('.')),
               diff=open('review.diff').read()), open({str(self.seen)!r}, 'w'))
sys.stdout.write({stdout!r})
sys.exit({exit_code})
''')
        path.chmod(0o755)
        return str(path)

    def result(self, structured, **extra):
        return json.dumps(dict(type='result', subtype='success', is_error=False,
                               structured_output=structured, **extra))

    def pull(self, number, head):
        return dict(number=number, state='open', head=dict(sha=head), base=dict(ref='main'))

    def run_review(self, stdout, head=None, pulls=None, source=None, exit_code=0, summary_path=None):
        head = head or self.v['good']
        pulls = [self.pull(1, head)] if pulls is None else pulls
        fake = FakeGitHub(pulls, {'main': self.v['base']}); self.addCleanup(fake.close)
        printed = io.StringIO()
        try:
            with contextlib.redirect_stdout(printed), contextlib.redirect_stderr(printed):
                code = module(source).publish(api=fake.api, token='github-token', repository=REPO, head=head,
                                              event_pulls=[p['number'] for p in pulls], clone=str(self.tmp / 'clone'),
                                              model='claude-opus-5-5', secret=SECRET, summary_path=summary_path,
                                              claude=self.fake_claude(stdout, exit_code))
        except Exception:
            code = 'raised'
        self.printed = printed.getvalue()
        return code, [(st, d) for s, st, d, c in fake.statuses() if c == CONTEXT and s == head], fake


class Publisher(Base):
    def test_pass_is_success_on_exactly_that_head(self):
        code, statuses, fake = self.run_review(self.result(answer('pass', 'minor')))
        self.assertEqual([st for st, d in statuses], ['pending', 'success'])
        self.assertEqual({p for m, p in fake.writes()}, {f'/repos/{REPO}/statuses/{self.v["good"]}'})
        self.assertEqual(code, 0)

    def test_the_reviewer_sees_only_the_export_the_diff_and_its_credential(self):
        self.run_review(self.result(answer('pass')))
        seen = json.loads(self.seen.read_text())
        self.assertEqual(seen['cwd'], ['head', 'review.diff'])
        os_added = {'LC_CTYPE', '__CF_USER_TEXT_ENCODING'}   # macOS adds these to every process
        self.assertEqual(sorted(set(seen['env']) - os_added), ['CLAUDE_CODE_OAUTH_TOKEN', 'HOME', 'PATH'])
        argv = seen['argv']
        self.assertEqual(argv[argv.index('--tools') + 1], 'Read,Grep,Glob')
        self.assertEqual(argv[argv.index('--model') + 1], 'claude-opus-5-5')
        self.assertNotIn('--allowedTools', argv)
        self.assertNotIn('--dangerously-skip-permissions', argv)
        self.assertIn('model.json', seen['diff'])        # the fixture's change, base...head

    def test_hold_and_deny_are_failure(self):
        for verdict, findings in (('hold', ('major',)), ('deny', ('blocker',))):
            with self.subTest(verdict):
                code, statuses, _ = self.run_review(self.result(answer(verdict, *findings)))
                self.assertEqual((statuses[-1][0], code), ('failure', 2))
                self.assertIn(verdict, statuses[-1][1])

    def test_inadmissible_answers_are_errors_never_success(self):
        cases = {
            'pass with a blocker': self.result(answer('pass', 'blocker')),
            'pass with a major': self.result(answer('pass', 'major')),
            'deny without a blocker': self.result(answer('deny', 'major')),
            'unknown verdict': self.result(answer('maybe')),
            'extra field': self.result(dict(answer('pass'), approve=True)),
            'no structured output': self.result(None),
            'empty claim': self.result(dict(answer('pass'), findings=[dict(severity='minor', location='x', claim=' ')])),
            'api error': json.dumps(dict(subtype='success', is_error=True, api_error='credits_required')),
            'not json': 'pass',
        }
        for name, stdout in cases.items():
            with self.subTest(name):
                code, statuses, _ = self.run_review(stdout)
                self.assertEqual(statuses[-1][0], 'error')
                self.assertNotIn('success', [st for st, d in statuses])
                self.assertNotEqual(code, 0)

    def test_an_answer_that_carries_the_credential_is_an_error_and_is_not_repeated(self):
        code, statuses, fake = self.run_review(self.result(answer('pass', summary='token ' + SECRET)))
        self.assertEqual(statuses[-1][0], 'error')
        self.assertFalse(any(SECRET in json.dumps(body) for m, p, body in fake.requests if body))

    def test_a_failed_process_is_an_error_even_with_a_valid_pass_on_stdout(self):
        """Review of #107: exit 7 after printing a valid pass was published as success."""
        code, statuses, _ = self.run_review(self.result(answer('pass')), exit_code=7)
        self.assertEqual(statuses[-1][0], 'error')
        self.assertIn('exited 7', statuses[-1][1])
        self.assertNotEqual(code, 0)

    def test_an_escaped_credential_is_caught_after_decoding_and_never_published(self):
        """Review of #107: a \\uXXXX-escaped credential passed the raw-text check."""
        escaped = ''.join(f'\\u{ord(c):04x}' for c in SECRET)
        stdouts = {
            'in the summary': self.result(answer('pass')).replace('"summary": "s"', f'"summary": "{escaped}"'),
            'in an error message': json.dumps(dict(subtype='success', is_error=True)).replace(
                '"is_error": true', f'"is_error": true, "result": "{escaped}"'),
        }
        for name, stdout in stdouts.items():
            with self.subTest(name):
                self.assertNotIn(SECRET, stdout)
                summary = self.tmp / 'summary.md'
                code, statuses, fake = self.run_review(stdout, summary_path=str(summary))
                self.assertEqual(statuses[-1][0], 'error')
                self.assertFalse(any(SECRET in json.dumps(body) for m, p, body in fake.requests if body))
                self.assertFalse(summary.exists() and SECRET in summary.read_text())
                self.assertNotIn(SECRET, self.printed)

    def test_unbound_or_moved_heads_write_nothing(self):
        for pulls in ([], [self.pull(1, self.v['bad'])], [self.pull(1, self.v['good']), self.pull(2, self.v['good'])]):
            with self.subTest(len(pulls)):
                code, _, fake = self.run_review(self.result(answer('pass')), pulls=pulls)
                self.assertEqual((fake.writes(), code != 0), ([], True))
                self.assertFalse(self.seen.exists())

    def test_an_oversized_diff_holds_without_asking_the_reviewer(self):
        source = REVIEW.read_text().replace('MAX_DIFF = 400_000', 'MAX_DIFF = 10')
        code, statuses, _ = self.run_review(self.result(answer('pass')), source=source)
        self.assertEqual(statuses[-1][0], 'failure')
        self.assertFalse(self.seen.exists())


class Control(Base):
    SITE = "    if verdict == 'pass' and worst & {'blocker', 'major'}:\n"

    def test_without_the_consistency_rule_a_pass_with_a_blocker_succeeds(self):
        source = REVIEW.read_text()
        self.assertIn(self.SITE, source, 'mutation site not found: the control would prove nothing')
        mutant = source.replace(self.SITE, "    if False:\n")
        code, statuses, _ = self.run_review(self.result(answer('pass', 'blocker')), source=mutant)
        self.assertEqual(statuses[-1][0], 'success')


class Workflow(unittest.TestCase):
    def test_the_trusted_half_runs_from_the_default_branch_and_the_request_has_no_permissions(self):
        trusted = (ROOT / '.github/workflows/agent-review.yml').read_text()
        request = (ROOT / '.github/workflows/agent-review-request.yml').read_text()
        self.assertIn('workflow_run:', trusted)
        self.assertIn('workflows: [Agent review request]', trusted)
        self.assertNotIn('ref:', trusted)              # checkout of the default branch only
        self.assertIn('python3 -I -S tools/agent_review.py', trusted)
        self.assertIn('@anthropic-ai/claude-code@2.1.286', trusted)
        self.assertIn('permissions: {}', request)
        self.assertNotIn('secrets.', request)


if __name__ == '__main__':
    unittest.main()
