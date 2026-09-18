"""Hash local artifacts and publish only the staged bytes that satisfied a request."""
from contextlib import closing
import hashlib
import os
from pathlib import Path
import stat
import tempfile

from .bundle import require_bundle
from .store import StoreError
from .facts import FactDeriver


def _subject_chunks(path):
    # Nonblocking open lets us reject FIFOs rather than waiting for a writer.
    fd = os.open(path, os.O_RDONLY | os.O_NONBLOCK)
    try:
        before = os.fstat(fd)
        if not stat.S_ISREG(before.st_mode):
            raise ValueError('subject must be a regular file')
        with os.fdopen(fd, 'rb', closefd=False) as stream:
            while chunk := stream.read(1024 * 1024):
                yield chunk
            after = os.fstat(fd)
        if (before.st_size, before.st_mtime_ns, before.st_ctime_ns) != (
                after.st_size, after.st_mtime_ns, after.st_ctime_ns):
            raise OSError('subject changed while hashing')
    finally:
        os.close(fd)


def subject_hash(path):
    if path is None:
        return None
    digest = hashlib.sha256()
    with closing(_subject_chunks(path)) as chunks:
        for chunk in chunks:
            digest.update(chunk)
    return digest.hexdigest()


def measure_subject(path, profile):
    """Hash and derive facts from one read of the same regular-file bytes."""
    if path is None:
        raise ValueError('derived facts require a subject file')
    deriver = FactDeriver(profile)
    digest = hashlib.sha256()
    with closing(_subject_chunks(path)) as chunks:
        for chunk in chunks:
            digest.update(chunk)
            deriver.update(chunk)
    return dict(subject=digest.hexdigest(), facts=deriver.finish(), profile=deriver.profile)


def admit_bundle(raw, trusted_keys, *, rule, subject, output, facts=None, derive=None):
    """Stage, require, then exclusively publish the same bytes (mode 0600).

    Source read failures are unverified; output failures are OSError. An
    unsatisfied request returns without publishing. No existing path is replaced.
    The caller must control the output directory; this is not a filesystem sandbox.
    """
    request = dict(name='requirement', bundle=raw, trust=list(trusted_keys), rule=rule)
    request['derive' if derive is not None else 'facts'] = derive if derive is not None else facts
    if (facts is None) == (derive is None):
        raise ValueError('provide exactly one of facts or derive')
    result = admit_all([request], subject=subject, output=output)
    report = result['requirements'][0]['report']
    if result['status'] != 'admitted':
        return dict(report, artifact=None)
    return dict(status='admitted', artifact=result['artifact'], requirement=report)


def admit_all(requirements, *, subject, output):
    """Require every named request against one staged subject, then publish.

    Requests are recipient configuration, not signed claims. Each carries its
    own trust set, bundle bytes, rule and exactly one of facts/derive. Reports
    are ordered; an unsatisfied request stops the run, and exceptions propagate.
    No partial success publishes. The output directory must be caller-controlled.
    """
    from .records import canon, decode
    from .policy import parse
    from .store import hex_hash

    if not isinstance(requirements, (list, tuple)) or not 1 <= len(requirements) <= 32:
        raise ValueError('provide 1 to 32 requirements')
    prepared, names = [], set()
    for req in requirements:
        if not isinstance(req, dict):
            raise ValueError('requirement must be an object')
        fields = set(req)
        if fields not in ({'name', 'bundle', 'trust', 'rule', 'facts'},
                          {'name', 'bundle', 'trust', 'rule', 'derive'}):
            raise ValueError('requirement needs name, bundle, trust, rule and exactly one of facts/derive')
        name = req['name']
        if not isinstance(name, str) or not name or len(name) > 64 or name in names:
            raise ValueError('requirement names must be unique nonempty strings of at most 64 characters')
        names.add(name)
        if not isinstance(req['bundle'], bytes):
            raise ValueError('requirement bundle must be bytes')
        trust = req['trust']
        if not isinstance(trust, (list, tuple, set, frozenset)) or not trust:
            raise ValueError('each requirement needs its own nonempty trust set')
        trust = frozenset(hex_hash(key) for key in trust)
        deriver = FactDeriver(req['derive']) if 'derive' in req else None
        facts = decode(canon(req['facts'])) if deriver is None else None
        if deriver is None and (not isinstance(facts, dict) or
                not all(isinstance(k, str) and type(v) is bool for k, v in facts.items())):
            raise ValueError('expected facts must be an object of boolean values')
        rule = req['rule']
        if not isinstance(rule, str):
            raise ValueError('expected rule must be text')
        parse(rule, facts if deriver is None else {k: False for k in deriver.profile})
        prepared.append((name, req['bundle'], trust, rule, facts, deriver))

    output = Path(output)
    fd, tmp = tempfile.mkstemp(prefix='.sg-admit-', dir=output.parent)
    try:
        digest = hashlib.sha256()
        with os.fdopen(fd, 'wb') as staged:
            with closing(_subject_chunks(subject)) as chunks:
                while True:
                    try:
                        chunk = next(chunks)
                    except StopIteration:
                        break
                    except OSError as exc:
                        raise StoreError('cannot read subject: ' + str(exc)) from exc
                    staged.write(chunk)
                    digest.update(chunk)
                    for _, _, _, _, _, deriver in prepared:
                        if deriver is not None:
                            deriver.update(chunk)
        h = digest.hexdigest()
        reports = []
        for name, raw, trust, rule, facts, deriver in prepared:
            if deriver is not None:
                facts = deriver.finish()
            report = require_bundle(raw, trust, rule=rule, facts=facts, subject=h)
            if deriver is not None:
                report['derivation'] = dict(profile=deriver.profile, facts=facts, subject=h)
            reports.append(dict(name=name, report=report))
            if report['status'] != 'satisfied':
                return dict(status='unsatisfied', failed=name, requirements=reports, artifact=None)
        os.link(tmp, output)
        return dict(status='admitted', artifact=dict(path=str(output), sha256=h),
                    requirements=reports)
    finally:
        Path(tmp).unlink(missing_ok=True)
