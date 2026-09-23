"""A read-only pull-request gate: one verdict about one base commit and one head commit.

Outside every checked closure. The workflow owner pins the paths and the two checker
IDs; the event supplies the
base and head commit IDs; the pull request supplies only bytes at those paths in its
head commit. Nothing from the head is executed: blobs are read by commit ID through
Git with hooks, replacement objects, inherited GIT_* variables and global/system
configuration disabled (stargate.apply._Git). Refs, the index and the working tree are
never changed and no byte from the head is executed; a caller's `git fetch` does add
objects and FETCH_HEAD, the gate itself only reads.

    python tools/pr_gate.py --repository . --base SHA --head SHA \\
        --model-path model.json --projection-path projection.json \\
        --evidence-path .stargate/evidence.json \\
        --expect-checker ID --expect-projection-checker ID

Exit codes: 0 verified or untouched; 1 checker or operation error; 2 invalid input;
3 unverified, incomplete or unavailable; 4 refused (stale base, a head model that is
not the verified successor, a projection that does not match). Registered in
docs/PR_GATE_REGISTRY.md.
"""
import argparse
import importlib.util
import json
import os
from pathlib import Path
import re
import subprocess
import sys


def _bootstrap():
    """Use an installed stargate if there is one; otherwise the source next to this file.

    The action runs `python3 -I -S` with nothing installed, so the code that decides is
    exactly the action's own pinned source: no pip, no network, no site-packages.
    """
    try:
        import stargate  # noqa: F401
        return
    except ImportError:
        pass
    source = Path(__file__).resolve().parent.parent / 'src'
    spec = importlib.util.spec_from_file_location('stargate', source / '__init__.py',
                                                  submodule_search_locations=[str(source)])
    module = importlib.util.module_from_spec(spec)
    sys.modules['stargate'] = module
    spec.loader.exec_module(module)


_bootstrap()
from stargate import certificate, projection_check  # noqa: E402
from stargate.apply import _Git, GitError  # noqa: E402
from stargate.canonical import decode, InvalidRecord  # noqa: E402

COMMIT = re.compile(r'(?:[0-9a-f]{40}|[0-9a-f]{64})')
SEGMENT = r'\.?[A-Za-z0-9_][A-Za-z0-9_.-]*'
PATH = re.compile(SEGMENT + '(?:/' + SEGMENT + ')*')
EXIT = {'verified': 0, 'untouched': 0, 'checker_error': 1, 'invalid': 2, 'unverified': 3,
        'incomplete': 3, 'checker_unavailable': 3, 'projection_checker_unavailable': 3,
        'stale_base': 4, 'model_not_successor': 4, 'projection_mismatch': 4}


class Repository:
    def __init__(self, path):
        top = Path(path).resolve()
        if (top / '.git').is_file():             # a worktree or submodule: ask Git where its directory is
            clean = _Git(top).env                # the same sanitised environment: no GIT_*, no global/system config
            found = subprocess.run(['git', '-c', 'core.hooksPath=' + os.devnull, '-c', 'core.fsmonitor=false',
                                    '-C', str(top), 'rev-parse', '--absolute-git-dir'],
                                   capture_output=True, text=True, env=clean)
            if found.returncode:
                raise InvalidRecord('not a Git checkout: ' + str(top))
            self.git = _Git(found.stdout.strip())
        else:
            self.git = _Git(top / '.git' if (top / '.git').is_dir() else top)

    def commit(self, sha):
        if not isinstance(sha, str) or not COMMIT.fullmatch(sha):
            raise InvalidRecord('expected a full commit ID')
        if self.git.run('cat-file', '-e', sha + '^{commit}', optional=True).returncode:
            raise InvalidRecord('commit not in the repository: ' + sha)
        return sha

    def ancestor(self, base, head):
        return self.git.run('merge-base', '--is-ancestor', base, head, optional=True).returncode == 0

    def blob(self, sha, path, limit):
        """The regular file at path in commit sha, or None when it is absent."""
        listed = self.git.read('ls-tree', '-z', sha, '--', path).split(b'\0')[0]
        if not listed:
            return None
        meta, _, name = listed.partition(b'\t')
        mode, kind, obj = meta.split(b' ')
        if name.decode() != path or mode != b'100644' or kind != b'blob':
            raise InvalidRecord(path + ' is not a regular file in ' + sha)
        if int(self.git.read('cat-file', '-s', obj.decode())) > limit:
            raise InvalidRecord(path + ' exceeds its size limit')
        return self.git.read('cat-file', 'blob', obj.decode())


def admission(raw):
    """(machine checker, projection checker) from an admission record, or InvalidRecord."""
    if raw is None:
        raise InvalidRecord('no admission record at the base commit')
    record = decode(raw)
    if not isinstance(record, dict) or set(record) != {'admission', 'machine_checker', 'projection_checker'}:
        raise InvalidRecord('an admission record has exactly admission, machine_checker, projection_checker')
    if type(record['admission']) is not int or record['admission'] != 1:
        raise InvalidRecord('unsupported admission record')
    for key in ('machine_checker', 'projection_checker'):
        if not isinstance(record[key], str) or not re.fullmatch(r'[0-9a-f]{64}', record[key]):
            raise InvalidRecord(key + ' must be one lowercase SHA-256')
    return record['machine_checker'], record['projection_checker']


def gate(repository, base, head, *, model_path, projection_path, evidence_path,
         expect_checker=None, expect_projection_checker=None, admission_path=None):
    """(exit code, report). Raises InvalidRecord for invalid input (exit 2)."""
    if (admission_path is None) == (expect_checker is None or expect_projection_checker is None):
        raise InvalidRecord('give either both pinned checker IDs or an admission record, not both')
    for path in (model_path, projection_path, evidence_path) + ((admission_path,) if admission_path else ()):
        if not isinstance(path, str) or not PATH.fullmatch(path) or '..' in path.split('/'):
            raise InvalidRecord('paths must be relative and ..-free')
    repo = Repository(repository)
    base, head = repo.commit(base), repo.commit(head)
    if admission_path is not None:
        # Current authority is a record on the base commit: never the head's, never
        # ANCHORS.md (history), never the code that happens to be running.
        admitted = admission(repo.blob(base, admission_path, 4096))
        expect_checker, expect_projection_checker = admitted
    report = dict(base=base, head=head, model_path=model_path, projection_path=projection_path,
                  evidence_path=evidence_path, checker=expect_checker,
                  projection_checker=expect_projection_checker,
                  admission=admission_path if admission_path else 'pinned')
    def done(status, **fields):
        return EXIT[status], dict(report, status=status, **fields)
    if not repo.ancestor(base, head):
        return done('stale_base')
    base_model = repo.blob(base, model_path, certificate.MAX_BYTES)
    if base_model is None:
        raise InvalidRecord('no guarded model at the base commit')
    parent = decode(base_model)
    certificate._model(parent, programs=True)
    parent_id = certificate.identity(parent)
    head_model = repo.blob(head, model_path, certificate.MAX_BYTES)
    base_projection = repo.blob(base, projection_path, projection_check.MAX_PROJECTION)
    head_projection = repo.blob(head, projection_path, projection_check.MAX_PROJECTION)
    if head_model == base_model and head_projection == base_projection:
        return done('untouched', model=parent_id)
    packet = repo.blob(head, evidence_path, certificate.MAX_BYTES)
    if packet is None:
        return done('unverified', reason='the guarded files changed and there is no evidence')
    doc = decode(packet)
    tags = [t for t in ('certified_change', 'certified_repair') if type(doc.get(t) if isinstance(doc, dict) else None) is int]
    if len(tags) != 1:
        raise InvalidRecord('evidence must be one certified_change or certified_repair')
    verify = certificate.verify_change if tags[0] == 'certified_change' else certificate.verify_repair
    proof, successor = verify(packet, parent_id, expect_checker)
    if successor is None:
        status = proof['status'] if proof['status'] in EXIT else 'checker_error'
        return done(status, evidence=proof)
    successor_model = decode(successor)['model']
    if head_model is None:
        return done('unverified', reason='the guarded model is gone at head')
    head_model = decode(head_model)
    if successor_model != head_model:
        return done('model_not_successor', evidence=dict(status=proof['status']))
    if head_projection is None:
        return done('unverified', reason='the guarded model changed and there is no projection')
    checked = projection_check.check(head_projection, successor, certificate.identity(head_model),
                                     expect_checker, expect_projection_checker)
    status = {'conforms': 'verified', 'mismatch': 'projection_mismatch'}.get(checked['status'], checked['status'])
    return done(status if status in EXIT else 'checker_error', evidence=dict(status=proof['status']),
                projection=checked)


def finish(code, report_text):
    """The step's exit code: the gate's, only if its report parses, names a known status,
    and that status's code is the gate's code. Anything else is 1 — never a pass."""
    try:
        status = json.loads(report_text)['status']
    except (ValueError, TypeError, KeyError):
        return 1
    if not isinstance(status, str) or EXIT.get(status) != code:
        return 1
    return code


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument('--github', action='store_true',
                   help='also write status/exit-code to $GITHUB_OUTPUT and the report to $GITHUB_STEP_SUMMARY')
    for name in ('repository', 'base', 'head', 'model-path', 'projection-path', 'evidence-path',
                 'expect-checker', 'expect-projection-checker'):
        p.add_argument('--' + name, required=True)
    a = p.parse_args(argv)
    try:
        code, report = gate(a.repository, a.base, a.head, model_path=a.model_path,
                            projection_path=a.projection_path, evidence_path=a.evidence_path,
                            expect_checker=a.expect_checker,
                            expect_projection_checker=a.expect_projection_checker)
    except (InvalidRecord, ValueError, TypeError) as exc:
        code, report = 2, dict(status='invalid', error=str(exc), base=a.base, head=a.head)
    except GitError as exc:
        code, report = 1, dict(status='operation_error', error=str(exc), base=a.base, head=a.head)
    text = json.dumps(report, sort_keys=True)
    print(text)
    final = finish(code, text)
    if a.github:
        status = report.get('status', 'invalid_report') if final == code else 'invalid_report'
        with open(os.environ['GITHUB_OUTPUT'], 'a') as out:
            out.write('status=' + status + '\nexit-code=' + str(final) + '\n')
        with open(os.environ['GITHUB_STEP_SUMMARY'], 'a') as summary:
            summary.write('### Stargate model gate: `' + status + '` (exit ' + str(final) + ')\n\n```json\n'
                          + json.dumps(report, indent=2, sort_keys=True) + '\n```\n')
    return final


if __name__ == '__main__':
    sys.exit(main())
