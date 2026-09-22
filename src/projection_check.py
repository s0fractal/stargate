"""Check a projection-1 table against a verified machine certificate.

Its own trust domain: PROJECTION_SOURCES is the machine proof checker closure plus
this file, and ProjectionCheckerID is the identity of those sources. Nothing from
the compiler, kernel, lab, machine, search or the projector is imported; the
structural reader below is this closure's own, not projection.py's.

The certificate is verified first, with identities the recipient supplies; then
every row's `next` is recomputed from the certified model's rules with the
independent Boolean evaluator. Only a complete row-by-row match is `conforms`.
Conformance is to the model's rules over the full Boolean domain; the certificate
is what makes that model a checked one, and says nothing about rows outside its
inductive set.
"""
import hashlib
import itertools
from pathlib import Path

from . import boolean, certificate
from .canonical import decode, exact, record_hash, InvalidRecord

PROJECTION_SOURCES = certificate.SOURCES + ('projection_check.py',)
# boolean.program and certificate._model both refuse a rule longer than this.
RULE_BYTES = 8192


def _ceiling():
    """Largest canonical projection of any model the closure accepts, in bytes.

    Every rule declares every one of the k names; the shortest declaration is
    `fact N:bool ` (len + 11) and the shortest tail `check!b` (7), so the names sum to
    at most RULE_BYTES - 7 - 11k. A state name occurs 2R + 1 times, an event name
    R + 1; every value is counted as `false`. Derived independently of projection.py.
    """
    def assignment(lengths):
        return 2 if not lengths else 1 + sum(n + 9 for n in lengths)
    def names(lengths):
        return 2 + sum(n + 2 for n in lengths) + max(len(lengths) - 1, 0)
    best = 0
    for s in range(1, 7):
        for e in range(3):
            spare = RULE_BYTES - 7 - 11 * (s + e)
            events, state = [1] * e, [spare - e - (s - 1)] + [1] * (s - 1)
            rows = 2 ** (s + e)
            row = len('{"event":,"next":,"state":}') + assignment(events) + 2 * assignment(state)
            total = (len('{"events":,"model":"","projection":1,"rows":[],"state":}') + 64
                     + names(events) + names(state) + rows * row + rows - 1)
            best = max(best, total)
    return best


MAX_PROJECTION = _ceiling()
FIELDS = ('projection', 'model', 'state', 'events', 'rows')
EXIT = {'conforms': 0, 'mismatch': 4, 'projection_checker_unavailable': 3,
        'checker_unavailable': 3, 'incomplete': 3, 'checker_error': 1}


def sources():
    root = Path(__file__).resolve().parent
    return {n: __loader__.get_data(str(root / n)).decode('utf-8') for n in PROJECTION_SOURCES}


def projection_checker_id():
    return certificate.identity(sources())


def _domain(state, events):
    return [(s, e) for s in itertools.product((False, True), repeat=len(state))
            for e in itertools.product((False, True), repeat=len(events))]


def inspect(raw):
    """Structure only, with this closure's own reader."""
    if not isinstance(raw, bytes) or len(raw) > MAX_PROJECTION:
        raise InvalidRecord('projection must be bytes within ' + str(MAX_PROJECTION))
    doc = decode(raw)
    exact(doc, FIELDS)
    if type(doc['projection']) is not int or doc['projection'] != 1:
        raise InvalidRecord('unsupported projection')
    record_hash(doc['model'])
    state, events = doc['state'], doc['events']
    certificate._names(state, 6); certificate._names(events, 2)
    if not state or set(state) & set(events):
        raise InvalidRecord('projection requires 1..6 state bits and 0..2 disjoint event bits')
    if type(doc['rows']) is not list:
        raise InvalidRecord('rows must be a list')
    keys = []
    for row in doc['rows']:
        exact(row, ('state', 'event', 'next'))
        keys.append((certificate._assignment(row['state'], state), certificate._assignment(row['event'], events)))
        certificate._assignment(row['next'], state)
    if len(set(keys)) != len(keys):
        raise InvalidRecord('duplicate row')
    expected = _domain(state, events)
    if len(keys) != len(expected):
        raise InvalidRecord('missing row')
    if keys != expected:
        raise InvalidRecord('rows are not in canonical order')
    return doc


def check(projection_raw, certificate_raw, expected_model, expected_checker, expected_projection_checker):
    doc = inspect(projection_raw)
    record_hash(expected_model); record_hash(expected_checker); record_hash(expected_projection_checker)
    report = dict(model=expected_model, projection=hashlib.sha256(projection_raw).hexdigest(),
                  projection_checker=expected_projection_checker, checked_rows=0)
    if projection_checker_id() != expected_projection_checker:
        return dict(report, status='projection_checker_unavailable')
    if doc['model'] != expected_model:
        raise InvalidRecord('projection names another model than the recipient anchor')
    proof = certificate.verify(certificate_raw, expected_model, expected_checker)
    if proof['status'] != 'verified_certificate':
        return dict(report, status=proof['status'], certificate=proof)
    model = decode(certificate_raw)['model']
    if doc['state'] != model['state'] or doc['events'] != model['events']:
        raise InvalidRecord('projection names differ from the certified model')
    _, codes = certificate._model(model, programs=True)
    for row in doc['rows']:
        facts = dict(row['state'], **row['event'])
        expected = {name: boolean.evaluate(codes[name], facts) for name in model['state']}
        actual = row['next']
        report['checked_rows'] += 1
        if actual != expected:
            return dict(report, status='mismatch', witness=dict(
                state=row['state'], event=row['event'], expected=expected, actual=actual))
    if report['checked_rows'] != 2 ** (len(model['state']) + len(model['events'])):
        return dict(report, status='checker_error', reason='row coverage mismatch')
    return dict(report, status='conforms')


def exit_code(report):
    return EXIT[report['status']]
