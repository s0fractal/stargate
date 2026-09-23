"""Publish the model gate's verdict as a commit status on exactly one head commit.

Outside every checked closure. Run by .github/workflows/model-gate.yml on
`workflow_run` (from the default branch, so its pins cannot come from a pull request).
The head is the event's `workflow_run.head_sha` — for a pull_request source run, the pull
request's head commit (GITHUB_SHA, the merge ref, is a different field and is not read).
Nothing is written until exactly one open pull request whose API head equals that commit
is found; the base is the current tip of its base branch. The
verdict is tools/pr_gate.py's gate and finish, run in-process. The only write is
`POST /repos/{repo}/statuses/{head}` with context `stargate/model-gate`: pending, then
success (exit 0), failure (2, 3, 4) or error (1 or anything unexpected).
Registered in docs/MODEL_GATE_PUBLISHER_REGISTRY.md.

    python tools/pr_gate_publish.py            # reads the environment the workflow sets
"""
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import urllib.request

CONTEXT = 'stargate/model-gate'
TOOLS = Path(__file__).resolve().parent


def _gate_module():
    spec = importlib.util.spec_from_file_location('pr_gate', TOOLS / 'pr_gate.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class Api:
    def __init__(self, api, token, repository):
        self.base, self.token, self.repository = api.rstrip('/'), token, repository

    def call(self, method, path, body=None):
        request = urllib.request.Request(
            f'{self.base}/repos/{self.repository}/{path}', method=method,
            data=json.dumps(body).encode() if body is not None else None,
            headers={'Authorization': 'Bearer ' + self.token, 'Accept': 'application/vnd.github+json',
                     'Content-Type': 'application/json', 'X-GitHub-Api-Version': '2022-11-28'})
        with urllib.request.urlopen(request, timeout=30) as response:
            return json.loads(response.read() or b'null')

    def status(self, head, state, description, target_url=None):
        body = dict(state=state, context=CONTEXT, description=description[:140])
        if target_url:
            body['target_url'] = target_url
        return self.call('POST', f'statuses/{head}', body)


def pull_request(api, head, event_pulls):
    """The one open pull request whose head is this commit, or None."""
    candidates = [api.call('GET', f'pulls/{number}') for number in event_pulls]
    if not candidates:
        candidates = api.call('GET', f'commits/{head}/pulls') or []
    # one pull request, open, whose head is this commit: two sharing it cannot both be judged
    matching = [p for p in candidates if p.get('state') == 'open' and p.get('head', {}).get('sha') == head]
    if len(matching) != 1:
        return None
    return matching[0]


def publish(*, api, token, repository, head, event_pulls, clone, model_path, projection_path,
            evidence_path, expect_checker, expect_projection_checker, target_url=None):
    github = Api(api, token, repository)
    # Bind first: exactly one open pull request whose head, as the API reports it now, is
    # the run's head. Only then is anything written. An unbound run writes nothing and is
    # red; a pull request that has moved on is left to the run of its new head.
    pr = pull_request(github, head, event_pulls)
    if pr is None:
        print(json.dumps(dict(status='unbound', head=head, event_pulls=event_pulls)), file=sys.stderr)
        return 1
    github.status(head, 'pending', 'stargate: checking', target_url)
    try:
        base = github.call('GET', f'git/ref/heads/{pr["base"]["ref"]}')['object']['sha']
        subprocess.run(['git', '-C', clone, 'fetch', '--quiet', '--no-tags', 'origin', head, base],
                       check=True, capture_output=True)
        gate = _gate_module()
        try:
            code, report = gate.gate(clone, base, head, model_path=model_path, projection_path=projection_path,
                                     evidence_path=evidence_path, expect_checker=expect_checker,
                                     expect_projection_checker=expect_projection_checker)
        except ValueError as exc:
            code, report = 2, dict(status='invalid', error=str(exc))
        final = gate.finish(code, json.dumps(report))
        print(json.dumps(dict(report, pull_request=pr['number'], base=base, head=head), sort_keys=True))
    except Exception as exc:  # anything unexpected is an error status, never a pass
        github.status(head, 'error', 'stargate: ' + type(exc).__name__, target_url)
        raise
    state = 'success' if final == 0 else 'error' if final == 1 else 'failure'
    github.status(head, state, f'stargate: {report.get("status")} (exit {final})', target_url)
    return final


def main():
    event = json.loads(Path(os.environ['GITHUB_EVENT_PATH']).read_text())['workflow_run']
    return publish(api=os.environ['GITHUB_API_URL'], token=os.environ['GITHUB_TOKEN'],
                   repository=os.environ['GITHUB_REPOSITORY'], head=event['head_sha'],
                   event_pulls=[p['number'] for p in event.get('pull_requests') or []],
                   clone=os.environ.get('GITHUB_WORKSPACE', '.'),
                   model_path=os.environ['MODEL_PATH'], projection_path=os.environ['PROJECTION_PATH'],
                   evidence_path=os.environ['EVIDENCE_PATH'], expect_checker=os.environ['EXPECT_CHECKER'],
                   expect_projection_checker=os.environ['EXPECT_PROJECTION_CHECKER'],
                   target_url=f'{os.environ.get("GITHUB_SERVER_URL", "")}/{os.environ["GITHUB_REPOSITORY"]}'
                              f'/actions/runs/{os.environ.get("GITHUB_RUN_ID", "")}')


if __name__ == '__main__':
    sys.exit(main())
