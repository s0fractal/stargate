"""Finite Boolean safety checking: exhaustive reachable graph, concrete traces."""
import itertools
import os
from pathlib import Path
import shutil

from . import lab, compiler, boolean, kernel
from .canonical import canon, decode, exact, record_hash, InvalidRecord

MAX_MACHINE = 4 * 1024 * 1024
GUIDE = '''A finite synchronous Boolean machine. state has 1..6 bits; events 0..2.
Each next rule is WPL over ALL state and event names; invariant is WPL over ALL
state names. Every declared fact must be used (tautologies may express irrelevance).
All next bits read the SAME old state and event. Every event valuation is possible
at every reached state; initial is the complete listed initial-state set.
Check safety on every reachable state, including initial states. A counterexample
is an initial state followed by event/next-state steps, not an unreachable row.
Budget or graph-quota exhaustion is incomplete, never established. No liveness,
fairness, external environment assumptions or implicit assumptions about a real system.
Use machine-check or replay --machine --expect-machine ID --max-edges N.
To propose new behavior, send only {"parent":"COPY_MACHINE_ID","next":{NAME:WPL,...}}.
Define every next bit. Do not include state/events/initial/invariant/budget/proofs.
The change checker recomputes BOTH parent and candidate safety. A broken parent
cannot be repaired through admission; choose a new root explicitly. Safe changes
may have different reachable graphs and need not be equivalent or cheaper.
Use machine-change PARENT PROPOSAL --expect-machine ID --output CHILD; offline
replay PROPOSAL CHILD --machine-change --expect-machine ID --max-edges N.
There is no machine history proof: a proposal and its parent are needed to replay
the change. An identical rule set may be admitted with the same machine ID.
Installed machine-search proposes one-rule edits and can reuse recomputed event
traces to reject unsafe candidates. A trace that passes is NOT safety; every found
proposal must still pass machine-change. Search itself is not included offline;
its emitted proposal is checked by the existing offline change mode.
Choose machine ID and runtime/launcher digests independently. Included source
is data until explicitly executed; this is not a sandbox or self-authentication.
'''


def _view(doc):
    # Reuse current runtime/ATP/WPL envelope validation, never emit this view.
    return canon(dict(stargate_world=32, contract='boolean-exhaustive-1',
                      rule=doc['invariant'], inputs=doc['state'], max_atp=doc['max_atp'],
                      objective='equivalence', predecessor=None, sources=doc['sources'],
                      guide=lab.GUIDE, license=doc['license']))


def inspect(raw):
    if not isinstance(raw, bytes) or len(raw) > MAX_MACHINE:
        raise InvalidRecord('machine exceeds size limit or is not bytes')
    doc = decode(raw)
    exact(doc, ('stargate_machine', 'state', 'events', 'initial', 'next', 'invariant',
                'max_atp', 'sources', 'guide', 'license'))
    if type(doc['stargate_machine']) is not int or doc['stargate_machine'] != 32:
        raise InvalidRecord('unsupported machine contract')
    lab._inputs(doc['state']); lab._inputs(doc['events'])
    if not 1 <= len(doc['state']) <= 6 or len(doc['events']) > 2 or set(doc['state']) & set(doc['events']):
        raise InvalidRecord('machine requires 1..6 state bits and 0..2 disjoint event bits')
    lab.inspect_world(_view(doc))  # runtime mismatch precedes current guide matching
    if doc['guide'] != GUIDE:
        raise InvalidRecord('machine guide does not match runtime')
    if not isinstance(doc['initial'], list) or not 1 <= len(doc['initial']) <= 2**len(doc['state']):
        raise InvalidRecord('machine requires nonempty bounded initial states')
    for state in doc['initial']:
        if not isinstance(state, dict) or set(state) != set(doc['state']) or any(type(v) is not bool for v in state.values()):
            raise InvalidRecord('initial state must give every state bit as a boolean')
    if len({canon(s) for s in doc['initial']}) != len(doc['initial']):
        raise InvalidRecord('duplicate initial state')
    if not isinstance(doc['next'], dict) or set(doc['next']) != set(doc['state']):
        raise InvalidRecord('next must define exactly every state bit')
    names = sorted(doc['state'] + doc['events'])
    for source in doc['next'].values(): lab._program(source, names)
    return doc


def create(spec):
    spec = decode(canon(spec))
    exact(spec, ('state', 'events', 'initial', 'next', 'invariant', 'max_atp'))
    raw = canon(dict(spec, stargate_machine=32, sources=lab.runtime_sources(), guide=GUIDE, license=lab.LICENSE))
    inspect(raw)
    return raw


def read(path):
    with open(path, 'rb') as stream: raw = stream.read(MAX_MACHINE + 1)
    if len(raw) > MAX_MACHINE: raise InvalidRecord('machine exceeds size limit')
    return raw


def describe(raw):
    doc = inspect(raw)
    return dict(status='unchecked_machine', machine_id=lab.identity(raw),
                state_bits=len(doc['state']), event_bits=len(doc['events']),
                runtime_digest=lab.runtime_digest(doc['sources']), replay_digest=lab.identity(lab.REPLAY.encode()))


def _closed(report, states, state_names, event_names, event_rows):
    def key(state): return tuple(state[n] for n in state_names)
    expected = {(k, bits) for k in states for bits in event_rows}
    actual = {(key(e['state']), tuple(e['event'][n] for n in event_names)) for e in report['edges']}
    return (actual == expected and len(report['edges']) == len(expected) and
            report['checked_edges'] == len(expected) and report['checked_invariants'] == len(states) and
            all(key(e['next']) in states for e in report['edges']))


def _witness(target, states, parents):
    steps = []
    # A simple ancestry chain has at most N nodes, including its initial state.
    for _ in range(len(states)):
        if target not in states or target not in parents:
            raise compiler.CompilerBug('witness ancestry references an unknown state')
        if parents[target] is None:
            return dict(initial=states[target], steps=list(reversed(steps)))
        previous, event = parents[target]
        steps.append(dict(event=event, state=states[target]))
        target = previous
    raise compiler.CompilerBug('witness ancestry exceeds reachable states')


def verify(raw, expected_machine, *, max_edges=256):
    if type(max_edges) is not int or not 0 <= max_edges <= 256:
        raise InvalidRecord('edge quota must be an integer from 0 to 256')
    record_hash(expected_machine)
    doc = inspect(raw)
    if lab.identity(raw) != expected_machine:
        raise InvalidRecord('machine does not match recipient anchor')
    state_names, event_names = doc['state'], doc['events']
    names = sorted(state_names + event_names)
    invariant_code = lab._program(doc['invariant'], state_names)
    codes = {name: lab._program(source, names) for name,source in doc['next'].items()}
    report = dict(status='incomplete', machine_id=expected_machine,
                  runtime_digest=lab.runtime_digest(doc['sources']),
                  reachable=[], edges=[], checked_invariants=0, checked_edges=0)
    def key(state): return tuple(state[n] for n in state_names)
    def evaluate(source, code, facts):
        result = compiler.compile_source(source, facts=facts, max_atp=doc['max_atp'])
        if result.value != boolean.evaluate(code, facts):
            raise compiler.CompilerBug('machine independent oracle disagreement')
        return result.value
    def check_state(state):
        value = evaluate(doc['invariant'], invariant_code, state)
        report['checked_invariants'] += 1
        if not value:
            report.update(status='counterexample', trace=_witness(key(state), states, parents))
        return value
    states = {key(state):state for state in doc['initial']}
    parents = {k:None for k in states}
    queue = list(states)
    report['reachable'] = list(states.values())
    event_rows = list(itertools.product((False, True), repeat=len(event_names)))
    expected_events = [tuple(bool(i & (1 << (len(event_names)-j-1))) for j in range(len(event_names)))
                       for i in range(2**len(event_names))]
    if event_rows != expected_events:
        return dict(report, status='checker_error', reason='event domain coverage or order mismatch')
    try:
        for state in states.values():
            if not check_state(state): return report
        cursor = 0
        while cursor < len(queue):
            old_key = queue[cursor]; cursor += 1
            old = states[old_key]
            for bits in event_rows:
                if report['checked_edges'] >= max_edges:
                    return dict(report, reason='edge_quota')
                event = dict(zip(event_names, bits))
                facts = dict(old, **event)
                # Synchronous: every rule sees the same old facts, never a newly computed bit.
                target = {n:evaluate(doc['next'][n], codes[n], facts) for n in state_names}
                report['edges'].append(dict(state=old, event=event, next=target))
                report['checked_edges'] += 1
                target_key = key(target)
                if target_key not in states:
                    states[target_key] = target
                    parents[target_key] = (old_key, event)
                    queue.append(target_key)
                    report['reachable'].append(target)
                    if not check_state(target): return report
        if not _closed(report, states, state_names, event_names, expected_events):
            return dict(report, status='checker_error', reason='reachable graph is not fully checked')
    except compiler.CompilerBug as exc:
        return dict(report, status='checker_error', reason=str(exc))
    except (compiler.CompileIncomplete, kernel.ResourceFault, kernel.AdmissionRefused) as exc:
        return dict(report, reason=str(exc))
    return dict(report, status='established')


MAX_CHANGE = 64 * 1024


def read_change(path):
    with open(path, 'rb') as stream: raw = stream.read(MAX_CHANGE + 1)
    if len(raw) > MAX_CHANGE: raise InvalidRecord('machine proposal exceeds size limit')
    # Author proposals allow whitespace, never duplicate keys.
    import json
    def unique(pairs):
        out = {}
        for name, value in pairs:
            if name in out: raise InvalidRecord('duplicate machine proposal field')
            out[name] = value
        return out
    return decode(canon(json.loads(raw, object_pairs_hook=unique)))


def verify_change(raw, proposal, expected_parent, *, max_edges=256):
    """Admit only new transition rules; inherited safety contract cannot change."""
    if type(max_edges) is not int or not 0 <= max_edges <= 256:
        raise InvalidRecord('edge quota must be an integer from 0 to 256')
    record_hash(expected_parent)
    doc = inspect(raw)
    parent = lab.identity(raw)
    if parent != expected_parent:
        raise InvalidRecord('machine does not match recipient anchor')
    proposal = decode(canon(proposal))
    if len(canon(proposal)) > MAX_CHANGE:
        raise InvalidRecord('machine proposal exceeds size limit')
    exact(proposal, ('parent', 'next'))
    record_hash(proposal['parent'])
    if proposal['parent'] != parent:
        raise InvalidRecord('machine proposal parent mismatch')
    candidate = canon(dict(doc, next=proposal['next']))
    inspect(candidate)  # malformed candidate is rejected before either evaluation
    report = dict(status='incomplete', parent=parent, candidate=lab.identity(candidate),
                  admitted=False, checks={})
    for role, packet in (('parent', raw), ('candidate', candidate)):
        result = verify(packet, lab.identity(packet), max_edges=max_edges)
        report['checks'][role] = result
        if result['status'] != 'established':
            status = 'parent_rejected' if role == 'parent' and result['status'] == 'counterexample' else result['status']
            report.update(status=status, program=role)
            return report, None
    report.update(status='safety_preserved', admitted=True, successor=lab.identity(candidate))
    return report, candidate


def replay_trace(raw, trace):
    """Replay only initial + events on this machine; claimed states grant no authority.

    A passing finite trace says nothing about paths that were not replayed.
    """
    doc = inspect(raw)
    trace = decode(canon(trace))
    exact(trace, ('initial', 'steps'))
    def bits(value, names):
        if type(value) is not dict or set(value) != set(names) or any(type(x) is not bool for x in value.values()):
            raise InvalidRecord('trace must match the Boolean domain')
    bits(trace['initial'], doc['state'])
    if trace['initial'] not in doc['initial']:
        raise InvalidRecord('trace must start at an initial state')
    if type(trace['steps']) is not list or len(trace['steps']) >= 2**len(doc['state']):
        raise InvalidRecord('trace exceeds shortest-path state bound')
    for step in trace['steps']:
        exact(step, ('event', 'state'))
        bits(step['event'], doc['events']); bits(step['state'], doc['state'])
    state = trace['initial']
    actual = dict(initial=state, steps=[])
    report = dict(status='trace_passed', trace=actual, checked_steps=0)
    names = sorted(doc['state'] + doc['events'])
    invariant = lab._program(doc['invariant'], doc['state'])
    codes = {n:lab._program(source, names) for n, source in doc['next'].items()}
    def evaluate(source, code, facts):
        result = compiler.compile_source(source, facts=facts, max_atp=doc['max_atp'])
        if result.value != boolean.evaluate(code, facts):
            raise compiler.CompilerBug('trace independent oracle disagreement')
        return result.value
    try:
        for index in range(len(trace['steps']) + 1):
            if not evaluate(doc['invariant'], invariant, state):
                return dict(report, status='counterexample')
            if index == len(trace['steps']): break
            event = trace['steps'][index]['event']
            facts = dict(state, **event)
            state = {n:evaluate(doc['next'][n], codes[n], facts) for n in doc['state']}
            actual['steps'].append(dict(event=event, state=state))
            report['checked_steps'] += 1
    except compiler.CompilerBug as exc:
        return dict(report, status='checker_error', reason=str(exc))
    except (compiler.CompileIncomplete, kernel.ResourceFault, kernel.AdmissionRefused) as exc:
        return dict(report, status='incomplete', reason=str(exc))
    return report


def unpack(raw, output):
    doc = inspect(raw)
    output = Path(output)
    result = lab.unpack_world(_view(doc), output)
    try:
        fd = os.open(output/'machine.json', os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, 'wb') as stream: stream.write(raw)
        (output/'README.txt').write_text(GUIDE + '\npython -I -S replay.py machine.json --machine '
            '--expect-machine INDEPENDENT_MACHINE_ID --max-edges 256 --expect-runtime INDEPENDENT_DIGEST\n')
    except BaseException:
        shutil.rmtree(output)
        raise
    return dict(result, **describe(raw))
