"""The head-SHA publisher. Registered in docs/MODEL_GATE_PUBLISHER_REGISTRY.md."""
import http.server
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import threading
import unittest

ROOT = Path(__file__).resolve().parent.parent
PUBLISH = ROOT / 'tools' / 'pr_gate_publish.py'
FIXTURE = ROOT / 'tools' / 'pr_gate_fixture.py'
REPO = 'owner/repo'


def module():
    spec = importlib.util.spec_from_file_location('pr_gate_publish', PUBLISH)
    loaded = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(loaded)
    return loaded


class FakeGitHub:
    """Just enough of the REST API; every request is recorded."""

    def __init__(self, pulls, refs, fail_final=False):
        self.pulls, self.refs, self.fail_final = pulls, refs, fail_final
        self.requests = []
        fake = self

        class Handler(http.server.BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def reply(self, code, body):
                data = json.dumps(body).encode()
                self.send_response(code); self.send_header('Content-Type', 'application/json')
                self.send_header('Content-Length', str(len(data))); self.end_headers(); self.wfile.write(data)

            def do_GET(self):
                fake.requests.append(('GET', self.path, None))
                parts = self.path.strip('/').split('/')
                if parts[3:4] == ['commits'] and parts[5:6] == ['pulls']:
                    return self.reply(200, [p for p in fake.pulls if p['head']['sha'] == parts[4] and p['state'] == 'open'])
                if parts[3:4] == ['pulls']:
                    found = [p for p in fake.pulls if str(p['number']) == parts[4]]
                    return self.reply(200, found[0]) if found else self.reply(404, {})
                if parts[3:6] == ['git', 'ref', 'heads']:
                    ref = '/'.join(parts[6:])
                    return self.reply(200, {'object': {'sha': fake.refs[ref]}}) if ref in fake.refs else self.reply(404, {})
                self.reply(404, {})

            def do_POST(self):
                body = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
                fake.requests.append(('POST', self.path, body))
                if fake.fail_final and body.get('state') != 'pending':
                    return self.reply(500, {})
                self.reply(201, {})

        self.server = http.server.HTTPServer(('127.0.0.1', 0), Handler)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.api = f'http://127.0.0.1:{self.server.server_port}'

    def close(self):
        self.server.shutdown()

    def statuses(self):
        return [(path.rsplit('/', 1)[1], body['state'], body.get('description', ''), body.get('context'))
                for method, path, body in self.requests if method == 'POST']

    def writes(self):
        return [(method, path) for method, path, body in self.requests if method != 'GET']


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp()); self.addCleanup(shutil.rmtree, self.tmp)
        out = subprocess.run([sys.executable, str(FIXTURE), str(self.tmp / 'origin')],
                             capture_output=True, text=True, check=True).stdout
        self.v = dict(line.split('=', 1) for line in out.split())
        subprocess.run(['git', 'clone', '-q', str(self.tmp / 'origin'), str(self.tmp / 'clone')], check=True)

    def pull(self, number, head, base='main', state='open'):
        return dict(number=number, state=state, head=dict(sha=head), base=dict(ref=base))

    def run_publisher(self, head, pulls, refs=None, event_pulls=None, fail_final=False, **overrides):
        fake = FakeGitHub(pulls, refs if refs is not None else {'main': self.v['base']}, fail_final)
        self.addCleanup(fake.close)
        options = dict(api=fake.api, token='t', repository=REPO, head=head,
                       event_pulls=event_pulls if event_pulls is not None else [p['number'] for p in pulls],
                       clone=str(self.tmp / 'clone'), model_path='model.json', projection_path='projection.json',
                       evidence_path='.stargate/evidence.json', expect_checker=self.v['checker'],
                       expect_projection_checker=self.v['projection_checker'])
        options.update(overrides)
        try:
            code = module().publish(**options)
        except Exception:
            code = 'raised'
        return code, fake


class Publisher(Base):
    def test_1_valid_repair_is_success_on_exactly_that_head(self):
        code, fake = self.run_publisher(self.v['good'], [self.pull(1, self.v['good'])])
        self.assertEqual([(s, st, c) for s, st, d, c in fake.statuses()],
                         [(self.v['good'], 'pending', 'stargate/model-gate'), (self.v['good'], 'success', 'stargate/model-gate')])
        self.assertIn('verified', fake.statuses()[-1][2])
        self.assertEqual({p for m, p in fake.writes()}, {f'/repos/{REPO}/statuses/{self.v["good"]}'})
        self.assertEqual(code, 0)

    def test_2_flipped_cell_is_failure(self):
        code, fake = self.run_publisher(self.v['bad'], [self.pull(2, self.v['bad'])])
        final = fake.statuses()[-1]
        self.assertEqual((final[0], final[1]), (self.v['bad'], 'failure'))
        self.assertIn('projection_mismatch', final[2])

    # Outcomes 3 and 4 were registered as an `error` status. Changed after Codex's review
    # of #67: nothing is written before the head is bound to exactly one open pull request
    # whose API head equals the event's head. An unbound run writes nothing and is red.
    def test_3_no_pull_request_writes_nothing_and_the_run_is_red(self):
        code, fake = self.run_publisher(self.v['good'], [], event_pulls=[])
        self.assertEqual((fake.writes(), code != 0), ([], True))

    def test_4_two_pull_requests_with_that_head_write_nothing(self):
        code, fake = self.run_publisher(self.v['good'], [self.pull(1, self.v['good']), self.pull(3, self.v['good'])])
        self.assertEqual((fake.writes(), code != 0), ([], True))

    def test_5_the_base_is_the_branch_tip_not_an_event_value(self):
        subprocess.run(['git', '-C', str(self.tmp / 'origin'), 'checkout', '-q', 'main'], check=True)
        (self.tmp / 'origin' / 'other').write_text('main moved\n')
        subprocess.run(['git', '-C', str(self.tmp / 'origin'), 'add', '-A'], check=True)
        subprocess.run(['git', '-C', str(self.tmp / 'origin'), '-c', 'user.name=x', '-c', 'user.email=x@x',
                        'commit', '-q', '-m', 'moved'], check=True)
        moved = subprocess.run(['git', '-C', str(self.tmp / 'origin'), 'rev-parse', 'HEAD'],
                               capture_output=True, text=True).stdout.strip()
        code, fake = self.run_publisher(self.v['good'], [self.pull(1, self.v['good'])], refs={'main': moved})
        final = fake.statuses()[-1]
        self.assertEqual(final[1], 'failure')
        self.assertIn('stale_base', final[2])

    def test_6_a_crashing_gate_is_an_error(self):
        code, fake = self.run_publisher(self.v['good'], [self.pull(1, self.v['good'])], expect_checker='not-hex')
        self.assertIn(fake.statuses()[-1][1], ('error', 'failure'))
        self.assertNotIn('success', [st for s, st, d, c in fake.statuses()])

    def test_7_a_pull_request_that_moved_on_gets_nothing_from_this_run(self):
        """The event's head is no longer the PR's head: a later run owns the new head."""
        code, fake = self.run_publisher(self.v['good'], [self.pull(1, self.v['bad'])], event_pulls=[1])
        self.assertEqual((fake.writes(), code != 0), ([], True))

    def test_8_a_refused_final_post_makes_the_run_red(self):
        code, fake = self.run_publisher(self.v['good'], [self.pull(1, self.v['good'])], fail_final=True)
        self.assertNotEqual(code, 0)


class Control(Base):
    SITE = "    if len(matching) != 1:\n"

    def test_without_the_one_pull_request_check_a_shared_head_gets_a_verdict(self):
        source = PUBLISH.read_text()
        self.assertIn(self.SITE, source, 'mutation site not found: the control would prove nothing')
        namespace = {'__name__': 'publish_mutant', '__file__': str(PUBLISH)}
        exec(compile(source.replace(self.SITE, "    if not matching:\n"), 'publish_mutant', 'exec'), namespace)
        pulls = [self.pull(1, self.v['good']), self.pull(3, self.v['good'])]
        fake = FakeGitHub(pulls, {'main': self.v['base']}); self.addCleanup(fake.close)
        namespace['publish'](api=fake.api, token='t', repository=REPO, head=self.v['good'], event_pulls=[1, 3],
                             clone=str(self.tmp / 'clone'), model_path='model.json', projection_path='projection.json',
                             evidence_path='.stargate/evidence.json', expect_checker=self.v['checker'],
                             expect_projection_checker=self.v['projection_checker'])
        self.assertEqual(fake.statuses()[-1][1], 'success')


class RealPayload(Base):
    def test_the_recorded_github_run_binds_its_head(self):
        """tests/github_workflow_run_pull_request.json is a real run object of this
        repository's `Model gate request` (event pull_request, PR #67): head_sha is the
        pull request's head commit, and pull_requests[0].head.sha is the same commit."""
        run = json.loads((ROOT / 'tests' / 'github_workflow_run_pull_request.json').read_text())
        self.assertEqual(run['event'], 'pull_request')
        self.assertEqual(run['head_sha'], run['pull_requests'][0]['head']['sha'])


class Entry(Base):
    def test_the_workflow_entry_point_runs_under_isolation(self):
        """What model-gate.yml runs: python3 -I -S tools/pr_gate_publish.py, from the event file."""
        import os
        fake = FakeGitHub([self.pull(1, self.v['good'])], {'main': self.v['base']}); self.addCleanup(fake.close)
        run = json.loads((ROOT / 'tests' / 'github_workflow_run_pull_request.json').read_text())
        run['head_sha'] = self.v['good']                       # the recorded shape, with the fixture's commits
        run['pull_requests'][0].update(number=1)
        run['pull_requests'][0]['head']['sha'] = self.v['good']
        event = self.tmp / 'event.json'
        event.write_text(json.dumps({'action': 'completed', 'workflow_run': run}))
        env = dict(os.environ, GITHUB_EVENT_PATH=str(event), GITHUB_API_URL=fake.api, GITHUB_TOKEN='t',
                   GITHUB_REPOSITORY=REPO, GITHUB_WORKSPACE=str(self.tmp / 'clone'), GITHUB_RUN_ID='1',
                   GITHUB_SERVER_URL='https://github.example', MODEL_PATH='model.json',
                   PROJECTION_PATH='projection.json', EVIDENCE_PATH='.stargate/evidence.json',
                   EXPECT_CHECKER=self.v['checker'], EXPECT_PROJECTION_CHECKER=self.v['projection_checker'])
        result = subprocess.run([sys.executable, '-I', '-S', str(PUBLISH)], env=env, capture_output=True,
                                text=True, cwd='/')
        self.assertEqual(result.returncode, 0, result.stderr[-400:])
        self.assertEqual([st for s, st, d, c in fake.statuses()], ['pending', 'success'])
