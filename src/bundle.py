"""Portable signed checks with only the objects actually fetched at export.

No extraction, implicit key trust, local-store fallback or evaluator loading.
"""
import hashlib
import os
from pathlib import Path
import tempfile

from . import KELVIN
from .records import canon, decode, exact, record_hash, validate_body, verify_record, InvalidRecord
from .store import StoreError

MAX_BUNDLE_BYTES = 16 * 1024 * 1024  # local operational cap, not a semantic version


def export_bundle(envelope_raw, store, trusted_keys):
    fetched = {}
    size = 0
    class Capture:
        def get(self, h):
            nonlocal size
            if h not in fetched:
                raw = store.get(h)
                if raw is None:
                    return None
                size += len(raw) * 2 + 70
                if size > MAX_BUNDLE_BYTES:
                    raise StoreError('bundle exceeds local size limit')
                fetched[h] = raw
            return fetched[h]
    # Explicit trust, signature and successful re-execution BEFORE exporting.
    report = verify_record(envelope_raw, Capture(), trusted_keys)
    doc = dict(stargate_bundle=KELVIN, envelope=decode(envelope_raw),
               objects={h.hex(): raw.hex() for h, raw in fetched.items()})
    raw = canon(doc)
    if len(raw) > MAX_BUNDLE_BYTES:
        raise StoreError('bundle exceeds local size limit')
    return raw, report


def verify_bundle(raw, trusted_keys):
    if len(raw) > MAX_BUNDLE_BYTES:
        raise StoreError('bundle exceeds local size limit')
    doc = decode(raw)
    exact(doc, ('stargate_bundle', 'envelope', 'objects'))
    if type(doc['stargate_bundle']) is not int or doc['stargate_bundle'] != KELVIN:
        raise InvalidRecord('unsupported bundle temperature')
    exact(doc['envelope'], ('body', 'signature'))
    validate_body(doc['envelope']['body'])
    domain = set(doc['envelope']['body']['check']['environment'])
    policy = doc['envelope']['body']['policy']
    if policy is not None:
        domain.update(policy.values())
    if not isinstance(doc['objects'], dict):
        raise InvalidRecord('bundle objects must be a hash-to-hex mapping')
    objects = {}
    for h, encoded in doc['objects'].items():
        record_hash(h)
        if h not in domain:
            raise InvalidRecord('bundle object outside signed environment')
        if (not isinstance(encoded, str) or len(encoded) % 2
                or any(c not in '0123456789abcdef' for c in encoded)):
            raise InvalidRecord('bundle object must be lowercase hexadecimal bytes')
        value = bytes.fromhex(encoded)
        if hashlib.sha256(value).hexdigest() != h:
            raise InvalidRecord('bundle object hash mismatch: ' + h)
        objects[bytes.fromhex(h)] = value
    # A missing demanded member is unverified; unused missing members are fine.
    # This dictionary is the ONLY byte source, regardless of caller cwd/store.
    return verify_record(canon(doc['envelope']), objects, trusted_keys)


def read_bundle(path):
    with Path(path).open('rb') as f:
        raw = f.read(MAX_BUNDLE_BYTES + 1)
    if len(raw) > MAX_BUNDLE_BYTES:
        raise StoreError('bundle exceeds local size limit')
    return raw


def write_bundle(path, raw):
    """Publish a complete bundle without replacing an existing path."""
    path = Path(path)
    fd, tmp = tempfile.mkstemp(prefix='.sg-export-', dir=path.parent)
    try:
        with os.fdopen(fd, 'wb') as f:
            f.write(raw)
        os.link(tmp, path)  # exclusive publication, no overwrite or symlink following
    finally:
        Path(tmp).unlink(missing_ok=True)


def require_bundle(raw, trusted_keys, *, rule, facts, subject=None):
    """Verify transport and require the recipient's exact rule and boolean facts.

    Returns satisfied/unsatisfied for verified records only. Verification failures
    retain their existing exceptions; they never become an unsatisfied verdict.
    """
    from .policy import parse, PolicyError
    if not isinstance(rule, str):
        raise PolicyError('expected rule must be text')
    if not isinstance(facts, dict) or not all(
            isinstance(n, str) and type(v) is bool for n, v in facts.items()):
        raise PolicyError('expected facts must be an object of boolean values')
    if subject is not None:
        record_hash(subject)
    facts_raw = canon(facts)
    parse(rule, decode(facts_raw))  # validate the recipient's request independently
    expected = dict(rule=hashlib.sha256(rule.encode('utf-8')).hexdigest(),
                    facts=hashlib.sha256(facts_raw).hexdigest(), subject=subject)
    report = verify_bundle(raw, set(trusted_keys))
    policy = report['policy']
    if policy is None:
        reason = 'policy_missing'
    elif policy['rule'] != expected['rule']:
        reason = 'rule_mismatch'
    elif policy['facts'] != expected['facts']:
        reason = 'facts_mismatch'
    elif report['subject'] != expected['subject']:
        reason = 'subject_mismatch'
    elif report['decision'] != 'accept':
        reason = 'decision_reject'
    else:
        reason = None
    return dict(status='satisfied' if reason is None else 'unsatisfied',
                reason=reason, expected=expected, verification=report)
