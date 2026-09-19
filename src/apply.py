"""Apply certified model changes to a trusted local bare Git repository.

The caller chooses repository, branch, model path, base commit and checker.
Evidence supplies none of those permissions. No checkout, merge or candidate code.
"""
import os
from pathlib import Path
import re
import subprocess
import time
from . import certificate as c
from .canonical import canon, decode, InvalidRecord


class GitError(OSError):
    """Repository operation failed; no mathematical verdict implied."""


class _Git:
    def __init__(self, repository):
        self.repository = str(Path(repository).resolve())
        self.env = {k: v for k, v in os.environ.items() if not k.startswith('GIT_')}
        self.env.update(GIT_CONFIG_NOSYSTEM='1', GIT_CONFIG_GLOBAL=os.devnull,
                        GIT_NO_REPLACE_OBJECTS='1', GIT_TERMINAL_PROMPT='0')

    def run(self, *args, data=None, optional=False):
        result = subprocess.run(['git', '--no-pager', '-c', 'core.hooksPath='+os.devnull,
                                 '-c', 'core.fsmonitor=false', '--git-dir='+self.repository,
                                 *args], input=data, stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE, env=self.env)
        if result.returncode and not optional:
            raise GitError(result.stderr.decode('utf-8', 'replace').strip())
        return result

    def read(self, *args):
        return self.run(*args).stdout


def apply(raw, repository, ref, model_path, expected_commit, expected_checker,
          *, max_steps=c.MAX_STEPS):
    """Verify a change/repair and CAS a branch to a one-file successor commit.

    Only bare repositories and root-level regular model files are supported.
    A failed CAS can leave unreachable Git objects, but never a partial tree.
    Repository, host Git/Python and filesystem permissions are operator-trusted.
    """
    if not isinstance(raw, bytes) or len(raw) > c.MAX_BYTES:
        raise InvalidRecord('application evidence must be bytes within 1 MiB')
    if not isinstance(ref, str) or not ref.startswith('refs/heads/'):
        raise InvalidRecord('target must be a full refs/heads/ branch')
    if not isinstance(model_path, str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]*', model_path):
        raise InvalidRecord('model must be one root-level ASCII filename')
    if not isinstance(expected_commit, str) or not re.fullmatch(r'(?:[0-9a-f]{40}|[0-9a-f]{64})', expected_commit):
        raise InvalidRecord('expected commit must be a full Git object ID')
    git = _Git(repository)
    if git.run('check-ref-format', ref, optional=True).returncode:
        raise InvalidRecord('invalid target branch')
    if git.read('rev-parse', '--is-bare-repository').strip() != b'true':
        raise InvalidRecord('application requires a bare repository')
    if git.run('symbolic-ref', '-q', ref, optional=True).returncode == 0:
        raise InvalidRecord('target branch must not be symbolic')
    actual = git.read('rev-parse', '--verify', ref).decode().strip()
    if actual != expected_commit:
        return dict(status='base_changed', applied=False, expected_commit=expected_commit,
                    actual_commit=actual)
    if git.read('cat-file', '-t', expected_commit).strip() != b'commit':
        raise InvalidRecord('base is not a commit')
    entries = git.read('ls-tree', '-z', expected_commit).split(b'\0')[:-1]
    matches = [i for i, entry in enumerate(entries) if entry.split(b'\t', 1)[1] == model_path.encode()]
    if len(matches) != 1:
        raise InvalidRecord('base must contain the selected model file')
    index = matches[0]
    mode, kind, oid = entries[index].split(b'\t', 1)[0].split()
    if mode != b'100644' or kind != b'blob':
        raise InvalidRecord('model must be a regular non-executable blob')
    if int(git.read('cat-file', '-s', oid.decode())) > c.MAX_BYTES:
        raise InvalidRecord('base model exceeds size limit')
    parent = git.read('cat-file', 'blob', oid.decode())
    model = decode(parent)
    doc = decode(raw)
    if not isinstance(doc, dict):
        raise InvalidRecord('expected certified change or repair')
    if 'certified_change' in doc:
        verify = c.verify_change
    elif 'certified_repair' in doc:
        verify = c.verify_repair
    else:
        raise InvalidRecord('expected certified change or repair')
    report, successor = verify(raw, c.identity(model), expected_checker, max_steps=max_steps)
    result = dict(status=report['status'], applied=False, base=expected_commit,
                  ref=ref, model_path=model_path, evidence=c.identity(doc), check=report)
    if successor is None:
        return result
    replacement = canon(decode(successor)['model'])
    if replacement == parent:
        return dict(result, status='unchanged')
    new_blob = git.run('hash-object', '-w', '--stdin', data=replacement).stdout.strip()
    entries[index] = b'100644 blob '+new_blob+b'\t'+model_path.encode()
    tree = git.run('mktree', '-z', data=b'\0'.join(entries)+b'\0').stdout.decode().strip()
    message = ('Certified model application\n\nEvidence-SHA256: '+result['evidence']+
               '\nChecker-SHA256: '+expected_checker+'\nModel: '+model_path+'\n')
    stamp = str(int(time.time()))+' +0000'
    commit = ('tree '+tree+'\nparent '+expected_commit+
              '\nauthor Stargate <stargate@localhost> '+stamp+
              '\ncommitter Stargate <stargate@localhost> '+stamp+'\n\n'+message).encode()
    target = git.run('hash-object', '-t', 'commit', '-w', '--stdin', data=commit).stdout.decode().strip()
    update = git.run('update-ref', '--no-deref', '-m', 'certified model application',
                     ref, target, expected_commit, optional=True)
    if update.returncode:
        current = git.run('rev-parse', '--verify', ref, optional=True)
        if current.returncode or current.stdout.decode().strip() != expected_commit:
            return dict(result, status='base_changed')
        raise GitError(update.stderr.decode('utf-8', 'replace').strip())
    return dict(result, status='applied', applied=True, commit=target,
                model_sha256=c.identity(decode(replacement)))


def exit_code(report):
    if report['status'] == 'applied': return 0
    if report['status'] in ('base_changed', 'unchanged'): return 4
    return c.exit_code(report)
