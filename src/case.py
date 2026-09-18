"""Portable counterexample evidence. Integrity is not truth or code authority."""
import hashlib
import os
from pathlib import Path
import re
import shutil

from . import KELVIN
from .records import canon, decode, exact, InvalidRecord
from .store import StoreError

MAX_CASE_BYTES = 16 * 1024 * 1024
MAX_FILES = 64


def _path(name):
    if (not isinstance(name, str) or len(name) > 240 or
            not re.fullmatch(r'[A-Za-z0-9_.-]+(?:/[A-Za-z0-9_.-]+)*', name) or
            any(p in ('.', '..') for p in name.split('/'))):
        raise InvalidRecord('unsafe case file path')
    return name


def _manifest(doc):
    exact(doc, ('title', 'claim', 'scope', 'limits', 'source', 'entrypoint', 'expected'))
    for field in ('title', 'claim', 'scope', 'expected'):
        if not isinstance(doc[field], str) or not doc[field].strip():
            raise InvalidRecord('case ' + field + ' must be nonempty text')
    if not isinstance(doc['limits'], list) or not doc['limits'] or not all(
            isinstance(v, str) and v.strip() for v in doc['limits']):
        raise InvalidRecord('case limits must be a nonempty text list')
    exact(doc['source'], ('repository', 'commit'))
    if not isinstance(doc['source']['repository'], str) or not doc['source']['repository']:
        raise InvalidRecord('case repository must be text')
    if not isinstance(doc['source']['commit'], str) or not re.fullmatch(
            r'[0-9a-f]{40}', doc['source']['commit']):
        raise InvalidRecord('case source commit must be a full Git SHA-1')
    _path(doc['entrypoint'])


def inspect_case(raw):
    """Return checked metadata and bytes; never import, execute or fetch them."""
    if len(raw) > MAX_CASE_BYTES:
        raise StoreError('case exceeds local size limit')
    doc = decode(raw)
    exact(doc, ('stargate_case', 'manifest', 'files'))
    if type(doc['stargate_case']) is not int or doc['stargate_case'] != KELVIN:
        raise InvalidRecord('unsupported case temperature')
    _manifest(doc['manifest'])
    files = doc['files']
    if not isinstance(files, dict) or not 1 <= len(files) <= MAX_FILES:
        raise InvalidRecord('case must contain 1 to 64 files')
    names = set()
    payload = {}
    for name, entry in files.items():
        _path(name)
        # Reject case-fold collisions for recipients on case-insensitive disks.
        folded = name.casefold()
        if folded in names:
            raise InvalidRecord('case file names collide')
        names.add(folded)
        exact(entry, ('sha256', 'hex'))
        encoded = entry['hex']
        if not isinstance(encoded, str) or len(encoded) % 2 or not re.fullmatch(r'[0-9a-f]*', encoded):
            raise InvalidRecord('case file must be lowercase hex bytes')
        value = bytes.fromhex(encoded)
        if hashlib.sha256(value).hexdigest() != entry['sha256']:
            raise InvalidRecord('case file digest mismatch: ' + name)
        payload[name] = value
    for name in names:
        parts = name.split('/')
        if any('/'.join(parts[:i]) in names for i in range(1, len(parts))):
            raise InvalidRecord('case file conflicts with directory')
    if doc['manifest']['entrypoint'] not in files:
        raise InvalidRecord('case entrypoint is missing')
    return dict(status='intact', case_id=hashlib.sha256(raw).hexdigest(),
                manifest=doc['manifest'], files={n: e['sha256'] for n, e in files.items()}), payload


def pack_case(manifest, files):
    """Files are a logical-name to bytes map. No source revision is authenticated."""
    if not isinstance(files, dict) or not all(isinstance(v, bytes) for v in files.values()):
        raise InvalidRecord('case files must map names to bytes')
    raw = canon(dict(stargate_case=KELVIN, manifest=manifest,
                     files={n: dict(sha256=hashlib.sha256(v).hexdigest(), hex=v.hex())
                            for n, v in files.items()}))
    inspect_case(raw)
    return raw


def read_case(path):
    try:
        with Path(path).open('rb') as stream:
            raw = stream.read(MAX_CASE_BYTES + 1)
    except OSError as exc:
        raise StoreError('cannot read case: ' + str(exc)) from exc
    if len(raw) > MAX_CASE_BYTES:
        raise StoreError('case exceeds local size limit')
    return raw


def unpack_case(raw, output):
    """Materialize data into an exclusively created directory; never run it.

    Caller controls the parent directory. Publication of multiple files is not
    atomic; exceptions clean this call's newly created directory. Process death
    may leave a partial directory, which must not be mistaken for completion.
    """
    report, files = inspect_case(raw)  # validate everything before creating output
    output = Path(output)
    output.mkdir(mode=0o700)  # outside try: never remove a preexisting destination
    try:
        for name, value in files.items():
            path = output / name
            path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(fd, 'wb') as stream:
                stream.write(value)
    except BaseException:
        shutil.rmtree(output)
        raise
    return dict(report, status='materialized', output=str(output), executed=False)
