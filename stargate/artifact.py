"""Hash local artifacts and publish only the staged bytes that satisfied a request."""
from contextlib import closing
import hashlib
import os
from pathlib import Path
import stat
import tempfile

from .bundle import require_bundle
from .store import StoreError


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


def admit_bundle(raw, trusted_keys, *, rule, facts, subject, output):
    """Stage, require, then exclusively publish the same bytes (mode 0600).

    Source read failures are unverified; output failures are OSError. An
    unsatisfied request returns without publishing. No existing path is replaced.
    The caller must control the output directory; this is not a filesystem sandbox.
    """
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
        h = digest.hexdigest()
        report = require_bundle(raw, trusted_keys, rule=rule, facts=facts, subject=h)
        if report['status'] != 'satisfied':
            return dict(report, artifact=None)
        os.link(tmp, output)  # exclusive publication of staged bytes, no reread
        return dict(status='admitted', artifact=dict(path=str(output), sha256=h),
                    requirement=report)
    finally:
        Path(tmp).unlink(missing_ok=True)
