"""Inductive finite-state certificates, checked without compiler or producer code."""
import hashlib
import itertools
from pathlib import Path
import re

from . import boolean
from .canonical import canon, decode, exact, record_hash, InvalidRecord

MODEL_FIELDS = ('state', 'events', 'initial', 'next', 'invariant', 'goals')
SOURCES = ('__init__.py', 'store.py', 'canonical.py', 'boolean.py', 'certificate.py')
MAX_BYTES = 1024 * 1024
MAX_STEPS = 8384  # 64 * 4 closure edges + 64 * 63 path steps + 64 * 64 rank rows.


class CheckerError(RuntimeError):
    """The local certificate checker failed, not a refutation of evidence."""


def identity(value):
    return hashlib.sha256(canon(value)).hexdigest()


def sources():
    root = Path(__file__).resolve().parent
    return {n: __loader__.get_data(str(root / n)).decode('utf-8') for n in SOURCES}


def checker_id():
    return identity(sources())


def model_from_machine(doc):
    """An explicit projection: no claim about the discarded ATP/runtime fields."""
    result = dict(language='boolean-machine-1', **{k: doc[k] for k in MODEL_FIELDS})
    if 'live_goals' in doc: result['live_goals'] = doc['live_goals']
    if 'world' in doc: result['world'] = doc['world']
    return decode(canon(result))


def _names(names, maximum):
    if (type(names) is not list or len(names) > maximum or
            any(type(n) is not str or re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)*', n) is None or
                n in ('fact', 'check', 'bool', 'true', 'false') for n in names) or names != sorted(set(names))):
        raise InvalidRecord('expected sorted unique Boolean names')


def _assignment(value, names):
    if type(value) is not dict or set(value) != set(names) or any(type(v) is not bool for v in value.values()):
        raise InvalidRecord('assignment must give every named bit as a Boolean')
    return tuple(value[n] for n in names)


def _assignments(values, names, *, nonempty=False):
    if type(values) is not list or len(values) > 2 ** len(names) or (nonempty and not values):
        raise InvalidRecord('invalid bounded assignment set')
    keys = [_assignment(v, names) for v in values]
    if len(set(keys)) != len(keys): raise InvalidRecord('duplicate assignment')
    return keys


def _model(doc, *, programs):
    fields = ('language',) + MODEL_FIELDS
    exact(doc, fields + tuple(f for f in ('live_goals', 'world') if f in doc))
    if doc['language'] != 'boolean-machine-1': raise InvalidRecord('unsupported model language')
    _names(doc['state'], 6); _names(doc['events'], 2)
    if not doc['state'] or set(doc['state']) & set(doc['events']):
        raise InvalidRecord('state must be nonempty and disjoint from events')
    _assignments(doc['initial'], doc['state'], nonempty=True)
    goals = _assignments(doc['goals'], doc['state'])
    if 'live_goals' in doc:
        # A live goal is a declared goal with a stronger obligation, never a new target.
        # An empty list would be a field that demands nothing while changing identity.
        if any(key not in goals for key in _assignments(doc['live_goals'], doc['state'], nonempty=True)):
            raise InvalidRecord('every live goal must also be a declared goal')
    if 'world' in doc:
        # World bits: rules of the environment, which a repair may not change. Empty is
        # refused for the same reason as empty live_goals.
        _names(doc['world'], 6)
        if not doc['world'] or any(bit not in doc['state'] for bit in doc['world']):
            raise InvalidRecord('world must be a nonempty sorted list of distinct state bits')
    exact(doc['next'], doc['state'])
    for source in [doc['invariant'], *doc['next'].values()]:
        if type(source) is not str or len(source.encode('utf-8')) > 8192:
            raise InvalidRecord('rule must be text within 8192 bytes')
    if programs:
        names = sorted(doc['state'] + doc['events'])
        return (boolean.program(doc['invariant'], doc['state'], allow_unused=True),
                {n: boolean.program(s, names, allow_unused=True) for n, s in doc['next'].items()})


def _trace(trace, model):
    exact(trace, ('initial', 'steps'))
    _assignment(trace['initial'], model['state'])
    if type(trace['steps']) is not list or len(trace['steps']) > 63:
        raise InvalidRecord('path must have at most 63 steps')
    for step in trace['steps']:
        exact(step, ('event', 'state'))
        _assignment(step['event'], model['events'])
        _assignment(step['state'], model['state'])


def inspect(raw):
    if not isinstance(raw, bytes) or len(raw) > MAX_BYTES:
        raise InvalidRecord('certificate must be bytes within 1 MiB')
    doc = decode(raw)
    fields = ('certificate', 'checker', 'model', 'states', 'paths')
    exact(doc, fields + ('ranks',) if 'ranks' in doc else fields)
    if type(doc['certificate']) is not int or doc['certificate'] != 1:
        raise InvalidRecord('unsupported certificate')
    record_hash(doc['checker'])
    model = doc['model']; _model(model, programs=False)
    _assignments(doc['states'], model['state'], nonempty=True)
    if type(doc['paths']) is not list or len(doc['paths']) != len(model['goals']):
        raise InvalidRecord('exactly one path is required per goal, in goal order')
    for entry, goal in zip(doc['paths'], model['goals']):
        exact(entry, ('goal', 'trace'))
        _assignment(entry['goal'], model['state'])
        if entry['goal'] != goal: raise InvalidRecord('goal path order mismatch')
        _trace(entry['trace'], model)
    live = model.get('live_goals') or []
    if bool(live) != ('ranks' in doc):
        raise InvalidRecord('a model with live goals needs exactly one rank map per live goal')
    if live:
        if type(doc['ranks']) is not list or len(doc['ranks']) != len(live):
            raise InvalidRecord('exactly one rank map is required per live goal, in order')
        for entry, goal in zip(doc['ranks'], live):
            exact(entry, ('goal', 'ranks'))
            _assignment(entry['goal'], model['state'])
            if entry['goal'] != goal: raise InvalidRecord('rank map order mismatch')
            if type(entry['ranks']) is not list or len(entry['ranks']) != len(doc['states']):
                raise InvalidRecord('a rank map covers exactly the certified states')
            for row in entry['ranks']:
                exact(row, ('state', 'rank'))
                _assignment(row['state'], model['state'])
                if type(row['rank']) is not int or not 0 <= row['rank'] < len(doc['states']):
                    raise InvalidRecord('rank must be a bounded non-negative integer')
    return doc


def describe(raw):
    doc = inspect(raw)
    return dict(status='unchecked_certificate', certificate_id=identity(doc),
                model_id=identity(doc['model']), checker=doc['checker'],
                states=len(doc['states']), goals=len(doc['paths']))


def verify(raw, expected_model, expected_checker, *, max_steps=MAX_STEPS):
    doc = inspect(raw)
    record_hash(expected_model); record_hash(expected_checker)
    if identity(doc['model']) != expected_model:
        raise InvalidRecord('model does not match recipient anchor')
    if type(max_steps) is not int or not 0 <= max_steps <= MAX_STEPS:
        raise InvalidRecord('step quota must be 0..' + str(MAX_STEPS))
    report = describe(raw)
    report.update(checked_states=0, checked_edges=0, checked_path_steps=0, checked_ranks=0,
                  max_steps=max_steps)
    if doc['checker'] != expected_checker or checker_id() != expected_checker:
        return dict(report, status='checker_unavailable')
    model = doc['model']
    invariant, codes = _model(model, programs=True)
    state_names, event_names = model['state'], model['events']
    keys = {_assignment(s, state_names) for s in doc['states']}
    if any(_assignment(s, state_names) not in keys for s in model['initial']):
        raise InvalidRecord('certificate omits an initial state')
    for state in doc['states']:
        if not boolean.evaluate(invariant, state):
            raise InvalidRecord('certificate state violates invariant')
        report['checked_states'] += 1
    # An inductive set suffices: initial subset + transition closure + invariant.
    # No producer BFS, reachability ordering or declared verdict is trusted.
    transitions = {}
    events = list(itertools.product((False, True), repeat=len(event_names)))
    for state in doc['states']:
        old_key = _assignment(state, state_names)
        for bits in events:
            if report['checked_edges'] + report['checked_path_steps'] + report['checked_ranks'] >= max_steps:
                return dict(report, status='incomplete', reason='step_quota')
            facts = dict(state, **dict(zip(event_names, bits)))
            target = {n: boolean.evaluate(codes[n], facts) for n in state_names}
            target_key = _assignment(target, state_names)
            if target_key not in keys:
                raise InvalidRecord('certificate is not closed under transitions')
            transitions[(old_key, bits)] = target_key
            report['checked_edges'] += 1
    expected_edges = len(keys) * (2 ** len(event_names))
    if len(transitions) != expected_edges or report['checked_edges'] != expected_edges:
        return dict(report, status='checker_error', reason='closure coverage mismatch')
    for entry in doc['paths']:
        trace = entry['trace']
        if trace['initial'] not in model['initial']:
            raise InvalidRecord('goal path does not start in an initial state')
        current = _assignment(trace['initial'], state_names)
        for step in trace['steps']:
            if report['checked_edges'] + report['checked_path_steps'] + report['checked_ranks'] >= max_steps:
                return dict(report, status='incomplete', reason='step_quota')
            event = _assignment(step['event'], event_names)
            target = _assignment(step['state'], state_names)
            if transitions[(current, event)] != target:
                raise InvalidRecord('goal path transition does not reproduce')
            current = target
            report['checked_path_steps'] += 1
        if current != _assignment(entry['goal'], state_names):
            raise InvalidRecord('path does not reach its goal')
    # A live goal must stay reachable from EVERY certified state. The rank map is the
    # proof: zero only at the goal, and one event out of every other state lowers it.
    for entry in doc.get('ranks', ()):
        ranks = {}
        for row in entry['ranks']:
            state_key = _assignment(row['state'], state_names)
            if state_key not in keys:
                raise InvalidRecord('rank map names a state outside the certificate')
            if state_key in ranks: raise InvalidRecord('duplicate rank for a state')
            ranks[state_key] = row['rank']
        if len(ranks) != len(keys):
            raise InvalidRecord('rank map does not cover the certified set')
        goal_key = _assignment(entry['goal'], state_names)
        if ranks.get(goal_key) != 0: raise InvalidRecord('the live goal must have rank zero')
        for state_key, rank in ranks.items():
            if report['checked_edges'] + report['checked_path_steps'] + report['checked_ranks'] >= max_steps:
                return dict(report, status='incomplete', reason='step_quota')
            report['checked_ranks'] += 1
            if state_key == goal_key: continue
            if rank == 0: raise InvalidRecord('only the live goal may have rank zero')
            if not any(ranks[transitions[(state_key, bits)]] < rank for bits in events):
                raise InvalidRecord('no event lowers the rank of a certified state')
    return dict(report, status='verified_certificate')


def create(model, states, paths, ranks=None):
    """Construct data, then independently check it before returning any bytes."""
    body = dict(certificate=1, checker=checker_id(), model=model, states=states, paths=paths)
    raw = canon(dict(body, ranks=ranks) if ranks is not None else body)
    report = verify(raw, identity(model), checker_id())
    if report['status'] != 'verified_certificate':
        raise CheckerError('certificate did not complete independent checking: ' + report['status'])
    return raw


def inspect_change(raw):
    if not isinstance(raw, bytes) or len(raw) > MAX_BYTES:
        raise InvalidRecord('certified change must be bytes within 1 MiB')
    doc = decode(raw)
    exact(doc, ('certified_change', 'parent', 'candidate'))
    if type(doc['certified_change']) is not int or doc['certified_change'] != 1:
        raise InvalidRecord('unsupported certified change')
    for role in ('parent', 'candidate'):
        inspect(canon(doc[role]))
    return doc


def pack_change(parent, candidate):
    """Package untrusted evidence; no verification or admission implied."""
    raw = canon(dict(certified_change=1, parent=inspect(parent), candidate=inspect(candidate)))
    inspect_change(raw)
    return raw


def _preserves_contract(parent, candidate):
    # Structural identity is meaningful without executing either grammar.
    for field in ('language', 'state', 'events', 'initial', 'invariant', 'goals', 'live_goals', 'world'):
        # live_goals and world are absent in most models; dropping or adding one is still a change.
        if parent.get(field) != candidate.get(field):
            raise InvalidRecord('certified change alters protected field: ' + field)


def verify_change(raw, expected_parent, expected_checker, *, max_steps=MAX_STEPS):
    """Check both certificates and preserve every model field except next.

    The quota is per certificate, so the total bound is twice max_steps.
    Only a successful result carries successor bytes (a reusable certificate).
    """
    doc = inspect_change(raw)
    record_hash(expected_parent); record_hash(expected_checker)
    parent, candidate = doc['parent']['model'], doc['candidate']['model']
    if identity(parent) != expected_parent:
        raise InvalidRecord('parent model does not match recipient anchor')
    _preserves_contract(parent, candidate)
    report = dict(status='unchecked_change', change_id=identity(doc),
                  parent_model=expected_parent, checker=expected_checker, checks=[])
    for role in ('parent', 'candidate'):
        cert = canon(doc[role])
        checked = verify(cert, identity(doc[role]['model']), expected_checker, max_steps=max_steps)
        report['checks'].append(dict(role=role, report=checked))
        if checked['status'] != 'verified_certificate':
            return dict(report, status=checked['status'], failed=role), None
    return dict(report, status='verified_change', successor_model=identity(candidate),
                successor_certificate=identity(doc['candidate'])), canon(doc['candidate'])


def inspect_history(raw):
    if not isinstance(raw, bytes) or len(raw) > MAX_BYTES:
        raise InvalidRecord('certificate history must be bytes within 1 MiB')
    doc = decode(raw)
    exact(doc, ('certificate_history', 'root', 'steps'))
    if type(doc['certificate_history']) is not int or doc['certificate_history'] != 1:
        raise InvalidRecord('unsupported certificate history')
    inspect(canon(doc['root']))
    if type(doc['steps']) is not list or len(doc['steps']) > 32:
        raise InvalidRecord('history needs at most 32 steps')
    for step in doc['steps']:
        exact(step, ('parent', 'certificate'))
        record_hash(step['parent'])
        inspect(canon(step['certificate']))
    return doc


def start_history(root):
    raw = canon(dict(certificate_history=1, root=inspect(root), steps=[]))
    inspect_history(raw)
    return raw


def verify_history(raw, expected_root, expected_checker, *, max_steps=MAX_STEPS):
    doc = inspect_history(raw)
    record_hash(expected_root); record_hash(expected_checker)
    current = doc['root']
    if identity(current['model']) != expected_root:
        raise InvalidRecord('history root does not match recipient anchor')
    report = dict(status='unchecked_history', history_id=identity(doc),
                  root_model=expected_root, checker=expected_checker, checks=[])
    # Check the root even for an empty history. Each proof is checked once.
    certificates = [current] + [step['certificate'] for step in doc['steps']]
    for index, cert in enumerate(certificates):
        if index:
            if doc['steps'][index - 1]['parent'] != identity(current['model']):
                raise InvalidRecord('history parent link does not match previous model')
            _preserves_contract(current['model'], cert['model'])
        checked = verify(canon(cert), identity(cert['model']), expected_checker, max_steps=max_steps)
        report['checks'].append(dict(index=index, report=checked))
        if checked['status'] != 'verified_certificate':
            return dict(report, status=checked['status'], failed=index), None
        current = cert
    return dict(report, status='verified_history', transitions=len(doc['steps']),
                tip_model=identity(current['model']), tip_certificate=identity(current)), canon(current)


def append_history(raw, candidate, expected_root, expected_checker, *, max_steps=MAX_STEPS):
    doc = inspect_history(raw)
    previous = doc['steps'][-1]['certificate'] if doc['steps'] else doc['root']
    doc['steps'].append(dict(parent=identity(previous['model']), certificate=inspect(candidate)))
    proposed = canon(doc)
    report, tip = verify_history(proposed, expected_root, expected_checker, max_steps=max_steps)
    return report, proposed if tip is not None else None


def inspect_refutation(raw):
    if not isinstance(raw, bytes) or len(raw) > MAX_BYTES:
        raise InvalidRecord('refutation must be bytes within 1 MiB')
    doc = decode(raw)
    exact(doc, ('refutation', 'checker', 'model', 'claim'))
    if type(doc['refutation']) is not int or doc['refutation'] != 1:
        raise InvalidRecord('unsupported refutation')
    record_hash(doc['checker']); _model(doc['model'], programs=False)
    claim, model = doc['claim'], doc['model']
    if type(claim) is not dict: raise InvalidRecord('claim must be an object')
    if claim.get('kind') == 'unsafe':
        exact(claim, ('kind', 'trace')); _trace(claim['trace'], model)
    elif claim.get('kind') == 'trap':
        exact(claim, ('kind', 'goal', 'states', 'trace'))
        _assignment(claim['goal'], model['state'])
        _assignments(claim['states'], model['state'], nonempty=True)
        _trace(claim['trace'], model)
    elif claim.get('kind') == 'unreachable_goal':
        exact(claim, ('kind', 'goal', 'states'))
        _assignment(claim['goal'], model['state'])
        _assignments(claim['states'], model['state'], nonempty=True)
    else:
        raise InvalidRecord('unsupported refutation claim')
    return doc


def describe_refutation(raw):
    doc = inspect_refutation(raw)
    return dict(status='unchecked_refutation', refutation_id=identity(doc),
                model_id=identity(doc['model']), checker=doc['checker'], claim=doc['claim']['kind'])


def _replay(trace, codes, names, model, report, max_steps, what):
    """Re-derive every state of a claimed path; the claim's own states prove nothing."""
    if trace['initial'] not in model['initial']:
        raise InvalidRecord(what + ' does not start in an initial state')
    current = trace['initial']
    for step in trace['steps']:
        if report['checked_steps'] >= max_steps:
            return None, dict(report, status='incomplete', reason='step_quota')
        target = {n: boolean.evaluate(codes[n], dict(current, **step['event'])) for n in names}
        if target != step['state']:
            raise InvalidRecord(what + ' transition does not reproduce')
        current = target
        report['checked_steps'] += 1
    return current, None


def _closed_set(states, keys, codes, names, model, report, max_steps):
    """Every event out of every listed state lands back inside the set."""
    base = report['checked_steps']
    events = list(itertools.product((False, True), repeat=len(model['events'])))
    covered = set()
    for state in states:
        for bits in events:
            if report['checked_steps'] >= max_steps:
                return dict(report, status='incomplete', reason='step_quota')
            facts = dict(state, **dict(zip(model['events'], bits)))
            target = {n: boolean.evaluate(codes[n], facts) for n in names}
            if _assignment(target, names) not in keys:
                raise InvalidRecord('refutation set is not closed under transitions')
            report['checked_steps'] += 1
            covered.add((_assignment(state, names), bits))
    if len(covered) != len(keys) * (2 ** len(model['events'])) or report['checked_steps'] - base != len(covered):
        return dict(report, status='checker_error', reason='closure coverage mismatch')
    return None


def verify_refutation(raw, expected_model, expected_checker, *, max_steps=MAX_STEPS):
    doc = inspect_refutation(raw)
    record_hash(expected_model); record_hash(expected_checker)
    if identity(doc['model']) != expected_model:
        raise InvalidRecord('model does not match recipient anchor')
    if type(max_steps) is not int or not 0 <= max_steps <= MAX_STEPS:
        raise InvalidRecord('step quota must be 0..' + str(MAX_STEPS))
    report = dict(describe_refutation(raw), checked_steps=0, max_steps=max_steps)
    if doc['checker'] != expected_checker or checker_id() != expected_checker:
        return dict(report, status='checker_unavailable')
    model, claim = doc['model'], doc['claim']
    invariant, codes = _model(model, programs=True)
    names = model['state']
    if claim['kind'] == 'unsafe':
        current, incomplete = _replay(claim['trace'], codes, names, model, report, max_steps, 'unsafe path')
        if incomplete is not None: return incomplete
        if boolean.evaluate(invariant, current):
            raise InvalidRecord('path endpoint does not violate invariant')
        return dict(report, status='verified_refutation', endpoint=current)
    if claim['kind'] == 'trap':
        # A live goal is refuted by a reachable set that is closed and excludes it.
        if claim['goal'] not in (model.get('live_goals') or []):
            raise InvalidRecord('target is not a live goal')
        keys = {_assignment(state, names) for state in claim['states']}
        if _assignment(claim['goal'], names) in keys:
            raise InvalidRecord('trap contains the goal')
        current, incomplete = _replay(claim['trace'], codes, names, model, report, max_steps, 'trap path')
        if incomplete is not None: return incomplete
        if _assignment(current, names) not in keys:
            raise InvalidRecord('trap path does not end inside the trap')
        refused = _closed_set(claim['states'], keys, codes, names, model, report, max_steps)
        if refused is not None: return refused
        return dict(report, status='verified_refutation', goal=claim['goal'], trap=len(keys))
    # A closed set containing all initials and excluding the goal proves absence.
    # Its states need not satisfy the safety invariant.
    if claim['goal'] not in model['goals']:
        raise InvalidRecord('target is not a required goal')
    keys = {_assignment(state, names) for state in claim['states']}
    if any(_assignment(state, names) not in keys for state in model['initial']):
        raise InvalidRecord('refutation omits an initial state')
    if _assignment(claim['goal'], names) in keys:
        raise InvalidRecord('refutation set contains the goal')
    refused = _closed_set(claim['states'], keys, codes, names, model, report, max_steps)
    if refused is not None: return refused
    return dict(report, status='verified_refutation', goal=claim['goal'])


def create_refutation(model, claim):
    raw = canon(dict(refutation=1, checker=checker_id(), model=model, claim=claim))
    result = verify_refutation(raw, identity(model), checker_id())
    if result['status'] != 'verified_refutation':
        raise CheckerError('refutation did not complete independent checking: ' + result['status'])
    return raw


def inspect_repair(raw):
    if not isinstance(raw, bytes) or len(raw) > MAX_BYTES:
        raise InvalidRecord('certified repair must be bytes within 1 MiB')
    doc = decode(raw)
    exact(doc, ('certified_repair', 'refutation', 'candidate'))
    if type(doc['certified_repair']) is not int or doc['certified_repair'] != 1:
        raise InvalidRecord('unsupported certified repair')
    inspect_refutation(canon(doc['refutation']))
    inspect(canon(doc['candidate']))
    return doc


def pack_repair(refutation, candidate):
    """Package a claimed defect and repair; packing establishes neither."""
    raw = canon(dict(certified_repair=1, refutation=inspect_refutation(refutation),
                     candidate=inspect(candidate)))
    inspect_repair(raw)
    return raw


def verify_repair(raw, expected_model, expected_checker, *, max_steps=MAX_STEPS):
    """Prove a parent defect and the full inherited contract of a replacement.

    This is a repair edge, not admission from a safe parent. The quota is per
    proof (at most twice max_steps); no candidate bytes escape on either failure.
    """
    doc = inspect_repair(raw)
    record_hash(expected_model); record_hash(expected_checker)
    parent, candidate = doc['refutation']['model'], doc['candidate']['model']
    if identity(parent) != expected_model:
        raise InvalidRecord('repair parent model does not match recipient anchor')
    _preserves_contract(parent, candidate)
    # An automatic repair changes the system, never the world it has to survive.
    for bit in parent.get('world', ()):
        if candidate['next'][bit] != parent['next'][bit]:
            raise InvalidRecord('repair alters world rule: ' + bit)
    report = dict(status='unchecked_repair', repair_id=identity(doc),
                  parent_model=expected_model, refutation_id=identity(doc['refutation']),
                  checker=expected_checker, checks=[])
    for role, check, expected in (('refutation', verify_refutation, 'verified_refutation'),
                                  ('candidate', verify, 'verified_certificate')):
        checked = check(canon(doc[role]), identity(doc[role]['model']), expected_checker,
                        max_steps=max_steps)
        report['checks'].append(dict(role=role, report=checked))
        if checked['status'] != expected:
            return dict(report, status=checked['status'], failed=role), None
    return dict(report, status='verified_repair', successor_model=identity(candidate),
                successor_certificate=identity(doc['candidate'])), canon(doc['candidate'])


def read(path):
    with Path(path).open('rb') as stream: raw = stream.read(MAX_BYTES + 1)
    if len(raw) > MAX_BYTES: raise InvalidRecord('certificate exceeds size limit')
    return raw


def exit_code(report):
    return {'verified_repair': 0, 'verified_refutation': 4, 'verified_history': 0, 'verified_change': 0, 'verified_certificate': 0, 'incomplete': 3, 'checker_unavailable': 3, 'checker_error': 1}[report['status']]
