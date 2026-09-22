"""projection-1: a machine's full transition table as canonical data.

`project` is a producer and asserts nothing about its output. It evaluates every
(state, event) pair of the full Boolean domain — reachable or not, safe or not —
with the machine's compiled rules and the independent Boolean oracle, the same way
machine.verify does, and writes the table. Whether a projection matches a model is
decided elsewhere, against a checked certificate; `inspect` checks structure only.
"""
import hashlib
import itertools

from . import boolean, certificate, compiler, kernel, lab, machine
from .canonical import canon, decode, exact, record_hash, InvalidRecord



def _ceiling():
    """The largest canonical projection any valid machine can have, in bytes.

    Names are bounded only by the WPL source limit: every next rule declares all
    k = |state| + |events| names, the shortest declaration is `fact N:bool ` (len + 11
    bytes) and the shortest tail `check!b` (7), so the name lengths sum to at most
    MAX_SOURCE_BYTES - 7 - 11k. Bytes are linear in name lengths — a state name occurs
    2R + 1 times, an event name R + 1 — so one long state name with every value
    `false` bounds each shape. Derived, never tightened: see vertical/projection_REGISTRY.md.
    """
    def assignment(lengths):
        return 2 if not lengths else 1 + sum(n + 9 for n in lengths)    # {"n":false,...}
    def names(lengths):
        return 2 + sum(n + 2 for n in lengths) + max(len(lengths) - 1, 0)  # ["n",...]
    best = 0
    for s in range(1, 7):
        for e in range(3):
            spare = compiler.MAX_SOURCE_BYTES - 7 - 11 * (s + e)
            events, state = [1] * e, [spare - e - (s - 1)] + [1] * (s - 1)
            rows = 2 ** (s + e)
            row = len('{"event":,"next":,"state":}') + assignment(events) + 2 * assignment(state)
            total = (len('{"events":,"model":"","projection":1,"rows":[],"state":}') + 64
                     + names(events) + names(state) + rows * row + rows - 1)
            best = max(best, total)
    return best


MAX_PROJECTION = _ceiling()
FIELDS = ('projection', 'model', 'state', 'events', 'rows')


def domain(state, events):
    """Every (state, event) pair in canonical order: states outer, events inner."""
    return [(dict(zip(state, s)), dict(zip(events, e)))
            for s in itertools.product((False, True), repeat=len(state))
            for e in itertools.product((False, True), repeat=len(events))]


def project(raw, expected_machine):
    record_hash(expected_machine)
    doc = machine.inspect(raw)
    if lab.identity(raw) != expected_machine:
        raise InvalidRecord('machine does not match recipient anchor')
    state, events = doc['state'], doc['events']
    names = sorted(state + events)
    codes = {name: lab._program(source, names) for name, source in doc['next'].items()}
    model = certificate.identity(certificate.model_from_machine(doc))
    rows = []
    try:
        for current, event in domain(state, events):
            facts = dict(current, **event)
            target = {}
            for name in state:
                value = compiler.compile_source(doc['next'][name], facts=facts, max_atp=doc['max_atp'],
                                                allow_unused=True).value
                if value != boolean.evaluate(codes[name], facts):
                    raise compiler.CompilerBug('projection independent oracle disagreement')
                target[name] = value
            rows.append(dict(state=current, event=event, next=target))
    except (compiler.CompileIncomplete, kernel.ResourceFault, kernel.AdmissionRefused) as exc:
        return dict(status='incomplete', model=model, reason=str(exc)), None
    packet = canon(dict(projection=1, model=model, state=state, events=events, rows=rows))
    inspect(packet)
    return dict(status='projected', model=model, rows=len(rows),
                projection_id=hashlib.sha256(packet).hexdigest()), packet


def _assignment(value, names, what):
    if type(value) is not dict or set(value) != set(names) or any(type(v) is not bool for v in value.values()):
        raise InvalidRecord(what + ' must give every named bit as a Boolean')
    return tuple(value[n] for n in names)


def inspect(raw):
    """Structure only: a projection that passes says nothing about any model."""
    if not isinstance(raw, bytes) or len(raw) > MAX_PROJECTION:
        raise InvalidRecord('projection must be bytes within ' + str(MAX_PROJECTION))
    doc = decode(raw)
    exact(doc, FIELDS)
    if type(doc['projection']) is not int or doc['projection'] != 1:
        raise InvalidRecord('unsupported projection')
    record_hash(doc['model'])
    state, events = doc['state'], doc['events']
    lab._inputs(state); lab._inputs(events)
    if not 1 <= len(state) <= 6 or len(events) > 2 or set(state) & set(events):
        raise InvalidRecord('projection requires 1..6 state bits and 0..2 disjoint event bits')
    if type(doc['rows']) is not list:
        raise InvalidRecord('rows must be a list')
    keys = []
    for row in doc['rows']:
        exact(row, ('state', 'event', 'next'))
        keys.append((_assignment(row['state'], state, 'row state'),
                     _assignment(row['event'], events, 'row event')))
        _assignment(row['next'], state, 'row next')
    if len(set(keys)) != len(keys):
        raise InvalidRecord('duplicate row')
    expected = [(tuple(s[n] for n in state), tuple(e[n] for n in events)) for s, e in domain(state, events)]
    if len(keys) != len(expected):
        raise InvalidRecord('missing row')
    if keys != expected:
        raise InvalidRecord('rows are not in canonical order')
    return doc
