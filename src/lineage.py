"""Anchored finite-world histories; proposals are data, every transition replays."""
import os
from pathlib import Path
import shutil

from . import lab
from .canonical import canon, decode, exact, record_hash, InvalidRecord

MAX_STEPS = 32
MAX_LINEAGE = 4 * 1024 * 1024


def inspect(raw):
    if not isinstance(raw, bytes) or len(raw) > MAX_LINEAGE:
        raise InvalidRecord('lineage exceeds size limit or is not bytes')
    doc = decode(raw)
    exact(doc, ('stargate_lineage', 'root', 'proposals'))
    if type(doc['stargate_lineage']) is not int or doc['stargate_lineage'] != 32:
        raise InvalidRecord('unsupported lineage contract')
    root = canon(doc['root'])
    lab.inspect_world(root)
    if not isinstance(doc['proposals'], list) or len(doc['proposals']) > MAX_STEPS:
        raise InvalidRecord('lineage must contain at most 32 proposals')
    for proposal in doc['proposals']:
        exact(proposal, ('parent', 'candidate'))
        record_hash(proposal['parent'])
        if len(canon(proposal)) > lab.MAX_PROPOSAL:
            raise InvalidRecord('lineage proposal exceeds size limit')
        lab._program(proposal['candidate'], doc['root']['inputs'])
    return doc


def create(root):
    lab.inspect_world(root)
    return canon(dict(stargate_lineage=32, root=decode(root), proposals=[]))


def verify(raw, expected_root):
    record_hash(expected_root)
    doc = inspect(raw)
    current = canon(doc['root'])
    if lab.identity(current) != expected_root:
        raise InvalidRecord('lineage root does not match recipient anchor')
    report = dict(status='verified_lineage', lineage_id=lab.identity(raw), root=expected_root,
                  runtime_digest=lab.runtime_digest(doc['root']['sources']),
                  total_steps=len(doc['proposals']), checked_steps=0, transitions=[])
    for index, proposal in enumerate(doc['proposals']):
        # verify_transition checks the parent against the freshly reconstructed world.
        result, successor = lab.verify_transition(current, proposal)
        report['transitions'].append(result)
        report['checked_steps'] += 1
        if not result['admitted']:
            status = result['status'] if result['status'] in ('incomplete', 'checker_error') else 'not_admitted'
            report.update(status=status, failed_step=index)
            return report, None
        if successor is None:
            report.update(status='checker_error', reason='admitted transition lacks successor', failed_step=index)
            return report, None
        current = successor
    if report['checked_steps'] != report['total_steps']:
        report.update(status='checker_error', reason='lineage replay incomplete')
        return report, None
    report['tip'] = lab.identity(current)
    return report, current


def append(raw, proposal, expected_root):
    # Snapshot both inputs before evaluation; validate/replay the resulting history.
    doc = inspect(raw)
    proposal = decode(canon(proposal))
    candidate = canon(dict(doc, proposals=doc['proposals'] + [proposal]))
    report, tip = verify(candidate, expected_root)
    return report, candidate if tip is not None else None


def read(path):
    with open(path, 'rb') as stream:
        raw = stream.read(MAX_LINEAGE + 1)
    if len(raw) > MAX_LINEAGE:
        raise InvalidRecord('lineage exceeds size limit')
    return raw


def unpack(raw, output):
    doc = inspect(raw)  # Materialization validates shape/runtime, not transitions.
    output = Path(output)
    result = lab.unpack_world(canon(doc['root']), output)
    # unpack_world owns a newly created directory; never remove an existing one.
    try:
        fd = os.open(output / 'lineage.json', os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, 'wb') as stream:
            stream.write(raw)
    except BaseException:
        shutil.rmtree(output)
        raise
    return dict(result, lineage_id=lab.identity(raw), total_steps=len(doc['proposals']))
