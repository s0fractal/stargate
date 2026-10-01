"""Publish an agent reviewer's verdict as a commit status on exactly one head commit.

Outside every checked closure. Run by .github/workflows/agent-review.yml on `workflow_run`
(from the default branch, so this file, its prompt and its pins cannot come from a pull
request). Binding follows tools/pr_gate_publish.py: exactly one open pull request whose API
head is `workflow_run.head_sha`, rechecked before the final status.

The head is exported as plain files (`git archive`) and the diff is computed against the
merge base with the current base tip; nothing from the head is executed. The reviewer is
the Claude Code CLI in print mode with read-only tools (Read, Grep, Glob), confined to a
scratch directory holding only that export and the diff. Its environment carries the model
credential and nothing else: the status-writing token never reaches it. Its answer must
match SCHEMA and be self-consistent; anything else is an `error` status, never a pass.

    pass -> success      hold/deny -> failure      anything else -> error

SHADOW: the context `stargate/agent-review` is published with the GitHub Actions token and
is not a required check. A pull request's own workflow could publish the same context, so
it must not be made required before it is published by a dedicated App (as model-gate is).
A pass is one model's opinion of one diff; it certifies nothing.

    python tools/agent_review.py            # reads the environment the workflow sets
"""
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

CONTEXT = 'stargate/agent-review'
TOOLS = Path(__file__).resolve().parent
PROMPT = TOOLS / 'agent_review_prompt.md'
MAX_DIFF = 400_000
VERDICTS = {'pass': 'success', 'hold': 'failure', 'deny': 'failure'}
SEVERITIES = ('blocker', 'major', 'minor')
SCHEMA = {
    'type': 'object', 'additionalProperties': False,
    'required': ['verdict', 'summary', 'findings'],
    'properties': {
        'verdict': {'enum': sorted(VERDICTS)},
        'summary': {'type': 'string'},
        'findings': {'type': 'array', 'items': {
            'type': 'object', 'additionalProperties': False,
            'required': ['severity', 'location', 'claim'],
            'properties': {'severity': {'enum': list(SEVERITIES)},
                           'location': {'type': 'string'}, 'claim': {'type': 'string'}}}},
    },
}


def _publisher():
    spec = importlib.util.spec_from_file_location('pr_gate_publish', TOOLS / 'pr_gate_publish.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class ReviewError(Exception):
    """The reviewer produced no admissible verdict."""


def validate(answer):
    """The verdict, checked against SCHEMA and for consistency; ReviewError otherwise."""
    if not isinstance(answer, dict) or set(answer) != {'verdict', 'summary', 'findings'}:
        raise ReviewError('answer is not exactly {verdict, summary, findings}')
    verdict, summary, findings = answer['verdict'], answer['summary'], answer['findings']
    if verdict not in VERDICTS or not isinstance(summary, str) or not isinstance(findings, list):
        raise ReviewError('verdict, summary or findings has the wrong type')
    for finding in findings:
        if (not isinstance(finding, dict) or set(finding) != {'severity', 'location', 'claim'}
                or finding['severity'] not in SEVERITIES
                or not all(isinstance(finding[k], str) and finding[k].strip() for k in ('location', 'claim'))):
            raise ReviewError('malformed finding')
    worst = {f['severity'] for f in findings}
    # A verdict that its own findings contradict is not a verdict.
    if verdict == 'pass' and worst & {'blocker', 'major'}:
        raise ReviewError('pass with a blocker or major finding')
    if verdict == 'deny' and 'blocker' not in worst:
        raise ReviewError('deny without a blocker finding')
    return answer


def parse(stdout, secret):
    """The validated verdict from the CLI's JSON output."""
    if secret and secret in stdout:
        raise ReviewError('reviewer output contains the model credential')
    try:
        result = json.loads(stdout)
    except ValueError:
        raise ReviewError('reviewer output is not JSON') from None
    if not isinstance(result, dict):
        raise ReviewError('reviewer output is not an object')
    if result.get('is_error') or result.get('subtype') != 'success':
        raise ReviewError('reviewer run failed: ' + str(result.get('api_error') or result.get('result')
                                                         or result.get('subtype'))[:100])
    return validate(result.get('structured_output'))


def review(clone, base, head, *, claude='claude', model, secret, timeout=1500):
    """Run the reviewer on base...head of `clone`; returns the validated verdict."""
    merge_base = subprocess.run(['git', '-C', clone, 'merge-base', base, head], check=True,
                                capture_output=True, text=True).stdout.strip()
    diff = subprocess.run(['git', '-C', clone, 'diff', '--no-ext-diff', '--no-textconv', '--no-color',
                           merge_base, head], check=True, capture_output=True).stdout
    if len(diff) > MAX_DIFF:
        return dict(verdict='hold', summary=f'diff is {len(diff)} bytes, over the {MAX_DIFF} review limit',
                    findings=[dict(severity='major', location='(whole diff)',
                                   claim='too large for one review; split the pull request')])
    with tempfile.TemporaryDirectory(prefix='agent-review-') as tmp:
        work = Path(tmp) / 'work'
        (work / 'head').mkdir(parents=True)
        home = Path(tmp) / 'home'
        home.mkdir()
        archive = subprocess.run(['git', '-C', clone, 'archive', '--format=tar', head],
                                 check=True, capture_output=True).stdout
        subprocess.run(['tar', '-x', '-C', str(work / 'head')], input=archive, check=True)
        (work / 'review.diff').write_bytes(diff)
        prompt = PROMPT.read_text().replace('{base}', merge_base).replace('{head}', head)
        settings = {'permissions': {'deny': ['Read(//proc/**)', 'Read(//sys/**)', 'Read(//etc/**)']}}
        env = {'PATH': os.environ.get('PATH', '/usr/bin:/bin'), 'HOME': str(home),
               'CLAUDE_CODE_OAUTH_TOKEN': secret}
        run = subprocess.run([claude, '-p', '--model', model, '--output-format', 'json',
                              '--tools', 'Read,Grep,Glob', '--settings', json.dumps(settings),
                              '--json-schema', json.dumps(SCHEMA), prompt],
                             cwd=work, env=env, capture_output=True, text=True, timeout=timeout)
    if run.returncode and not run.stdout:
        raise ReviewError(f'reviewer exited {run.returncode}')
    return parse(run.stdout, secret)


def report_markdown(verdict, pr, base, head):
    lines = [f'## Agent review (shadow): `{verdict["verdict"]}`', '',
             f'PR #{pr}, head `{head}`, merge base `{base}`.', '', verdict['summary'], '']
    for f in verdict['findings']:
        lines.append(f'- **{f["severity"]}** `{f["location"]}`: {f["claim"]}')
    return '\n'.join(lines) + '\n'


def publish(*, api, token, repository, head, event_pulls, clone, model, secret, claude='claude',
            target_url=None, summary_path=None):
    gate = _publisher()
    github = gate.Api(api, token, repository)
    github_status = lambda state, text: github.call('POST', f'statuses/{head}', dict(
        state=state, context=CONTEXT, description=text[:140], **({'target_url': target_url} if target_url else {})))
    pr = gate.pull_request(github, head, event_pulls)
    if pr is None:
        print(json.dumps(dict(status='unbound', head=head, event_pulls=event_pulls)), file=sys.stderr)
        return 1
    github_status('pending', 'agent-review (shadow): reviewing')
    try:
        base = github.call('GET', f'git/ref/heads/{pr["base"]["ref"]}')['object']['sha']
        subprocess.run(['git', '-C', clone, 'fetch', '--quiet', '--no-tags', 'origin', head, base],
                       check=True, capture_output=True)
        try:
            verdict = review(clone, base, head, claude=claude, model=model, secret=secret)
        except (ReviewError, subprocess.TimeoutExpired) as exc:
            github_status('error', 'agent-review (shadow): ' + str(exc))
            print(json.dumps(dict(status='error', error=str(exc), pull_request=pr['number'], head=head)))
            return 1
        current = gate.pull_request(github, head, event_pulls)
        if current is None or current['number'] != pr['number'] or current['base']['ref'] != pr['base']['ref']:
            github_status('error', 'agent-review (shadow): binding changed during review')
            return 4
    except Exception as exc:  # anything unexpected is an error status, never a pass
        github_status('error', 'agent-review (shadow): ' + type(exc).__name__)
        raise
    blockers = sum(f['severity'] == 'blocker' for f in verdict['findings'])
    github_status(VERDICTS[verdict['verdict']],
                  f'agent-review (shadow): {verdict["verdict"]}, {len(verdict["findings"])} findings, {blockers} blockers')
    if summary_path:
        with open(summary_path, 'a') as handle:
            handle.write(report_markdown(verdict, pr['number'], base, head))
    print(json.dumps(dict(verdict, pull_request=pr['number'], base=base, head=head), sort_keys=True))
    return 0 if verdict['verdict'] == 'pass' else 2


def main():
    event = json.loads(Path(os.environ['GITHUB_EVENT_PATH']).read_text())['workflow_run']
    return publish(api=os.environ['GITHUB_API_URL'], token=os.environ['GITHUB_TOKEN'],
                   repository=os.environ['GITHUB_REPOSITORY'], head=event['head_sha'],
                   event_pulls=[p['number'] for p in event.get('pull_requests') or []],
                   clone=os.environ.get('GITHUB_WORKSPACE', '.'), model=os.environ['REVIEW_MODEL'],
                   secret=os.environ['CLAUDE_CODE_OAUTH_TOKEN'],
                   summary_path=os.environ.get('GITHUB_STEP_SUMMARY'),
                   target_url=f'{os.environ.get("GITHUB_SERVER_URL", "")}/{os.environ["GITHUB_REPOSITORY"]}'
                              f'/actions/runs/{os.environ.get("GITHUB_RUN_ID", "")}')


if __name__ == '__main__':
    sys.exit(main())
