"""Portable lab work requests. Imported progress is a claim, always recomputed."""
from pathlib import Path

from . import lab
from .canonical import canon, decode, exact, record_hash, InvalidRecord

MAX_TASK = 4 * 1024 * 1024


def identity(world, proposal):
    """Stable task anchor independent of claimed progress; not authorization."""
    return lab.identity(canon(dict(world=lab.identity(world), proposal=proposal)))


def inspect(raw):
    if not isinstance(raw, bytes) or len(raw) > MAX_TASK:
        raise InvalidRecord('lab task exceeds size limit or is not bytes')
    doc = decode(raw)
    exact(doc, ('stargate_task', 'world', 'proposal', 'prefix'))
    if type(doc['stargate_task']) is not int or doc['stargate_task'] != 32:
        raise InvalidRecord('unsupported lab task contract')
    world = canon(doc['world'])
    lab.inspect_world(world)
    if len(canon(doc['proposal'])) > lab.MAX_PROPOSAL:
        raise InvalidRecord('task proposal exceeds size limit')
    # Eager validation, no evaluation. Also binds proposal.parent to this world.
    lab.start_transition(world, doc['proposal'])
    prefix = doc['prefix']
    names = doc['world']['inputs']
    if not isinstance(prefix, list) or len(prefix) >= 2**len(names):
        raise InvalidRecord('task prefix must be a proper prefix of the input table')
    for index, row in enumerate(prefix):
        exact(row, ('input', 'parent', 'candidate'))
        facts = row['input']
        expected = {name: bool(index & (1 << (len(names)-position-1)))
                    for position, name in enumerate(names)}
        if (not isinstance(facts, dict) or set(facts) != set(names) or
                any(type(value) is not bool for value in facts.values()) or facts != expected):
            raise InvalidRecord('task prefix input order or domain mismatch')
        for role in ('parent', 'candidate'):
            result = row[role]
            exact(result, ('value', 'atp', 'term'))
            if type(result['value']) is not bool or type(result['atp']) is not int or not 0 <= result['atp'] <= doc['world']['max_atp']:
                raise InvalidRecord('invalid task prefix result')
            record_hash(result['term'])
    return doc


def describe(raw):
    doc = inspect(raw)
    return dict(status='unverified_progress', task_id=identity(canon(doc['world']), doc['proposal']),
                packet_id=lab.identity(raw), claimed_rows=len(doc['prefix']),
                total_rows=2**len(doc['world']['inputs']),
                runtime_digest=lab.runtime_digest(doc['world']['sources']))


def _result(doc, state, replayed, advanced):
    verification = state.report
    report = dict(status=state.status, task_id=identity(canon(doc['world']), doc['proposal']),
                  replayed_rows=replayed, new_rows=advanced, verification=verification,
                  admitted=verification['admitted'], output_kind=None)
    output = state.successor
    if state.status == 'suspended':
        output = canon(dict(doc, prefix=verification['rows']))
        if len(output) > MAX_TASK:
            raise InvalidRecord('lab task exceeds size limit')
        report.update(output_kind='task', packet_id=lab.identity(output))
    elif output is not None:
        report['output_kind'] = 'world'
    return report, output


def start(world, proposal, *, rows=0):
    lab._row_quota(rows)
    doc = inspect(canon(dict(stargate_task=32, world=decode(world), proposal=proposal, prefix=[])))
    state = lab.start_transition(canon(doc['world']), doc['proposal'], rows=rows)
    return _result(doc, state, 0, len(state.report['rows']))


def resume(raw, expected_task, *, rows):
    lab._row_quota(rows)
    record_hash(expected_task)
    doc = inspect(raw)
    world = canon(doc['world'])
    if identity(world, doc['proposal']) != expected_task:
        raise InvalidRecord('lab task does not match recipient anchor')
    count = len(doc['prefix'])
    state = lab.start_transition(world, doc['proposal'], rows=count)
    replayed = len(state.report['rows'])
    # A completed-prefix claim contradicts deterministic world-budget exhaustion.
    if state.status == 'incomplete' and state.report.get('incomplete_kind') == 'world_budget':
        raise InvalidRecord('claimed lab prefix does not reproduce: world budget exhausted')
    # Local inability to recheck is not evidence that the sender lied.
    if state.status in ('incomplete', 'checker_error'):
        return _result(doc, state, replayed, 0)
    if state.status != 'suspended' or state.report['rows'] != doc['prefix']:
        raise InvalidRecord('claimed lab prefix does not reproduce')
    lab.resume_transition(state, rows=rows)
    return _result(doc, state, replayed, len(state.report['rows'])-replayed)


def read(path):
    with open(path, 'rb') as stream:
        raw = stream.read(MAX_TASK+1)
    if len(raw) > MAX_TASK:
        raise InvalidRecord('lab task exceeds size limit')
    return raw
