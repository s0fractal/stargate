"""Inductive finite-state certificates, checked without compiler or producer code."""
import hashlib
import itertools
import os
from pathlib import Path
import re

from . import boolean
from .canonical import canon, decode, exact, record_hash, InvalidRecord

MODEL_FIELDS = ('state', 'events', 'initial', 'next', 'invariant', 'goals')
SOURCES = ('__init__.py', 'store.py', 'canonical.py', 'boolean.py', 'certificate.py')
MAX_BYTES = 1024 * 1024
MAX_STEPS = 4288  # 64 * 4 closure edges + 64 * 63 path steps.


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
    exact(doc, ('language',) + MODEL_FIELDS)
    if doc['language'] != 'boolean-machine-1': raise InvalidRecord('unsupported model language')
    _names(doc['state'], 6); _names(doc['events'], 2)
    if not doc['state'] or set(doc['state']) & set(doc['events']):
        raise InvalidRecord('state must be nonempty and disjoint from events')
    _assignments(doc['initial'], doc['state'], nonempty=True)
    _assignments(doc['goals'], doc['state'])
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
    exact(doc, ('certificate', 'checker', 'model', 'states', 'paths'))
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
        raise InvalidRecord('step quota must be 0..4288')
    report = describe(raw)
    report.update(checked_states=0, checked_edges=0, checked_path_steps=0, max_steps=max_steps)
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
            if report['checked_edges'] + report['checked_path_steps'] >= max_steps:
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
            if report['checked_edges'] + report['checked_path_steps'] >= max_steps:
                return dict(report, status='incomplete', reason='step_quota')
            event = _assignment(step['event'], event_names)
            target = _assignment(step['state'], state_names)
            if transitions[(current, event)] != target:
                raise InvalidRecord('goal path transition does not reproduce')
            current = target
            report['checked_path_steps'] += 1
        if current != _assignment(entry['goal'], state_names):
            raise InvalidRecord('path does not reach its goal')
    return dict(report, status='verified_certificate')


def create(model, states, paths):
    """Construct data, then independently check it before returning any bytes."""
    raw = canon(dict(certificate=1, checker=checker_id(), model=model, states=states, paths=paths))
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
    for field in ('language', 'state', 'events', 'initial', 'invariant', 'goals'):
        if parent[field] != candidate[field]:
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


def verify_refutation(raw, expected_model, expected_checker, *, max_steps=MAX_STEPS):
    doc = inspect_refutation(raw)
    record_hash(expected_model); record_hash(expected_checker)
    if identity(doc['model']) != expected_model:
        raise InvalidRecord('model does not match recipient anchor')
    if type(max_steps) is not int or not 0 <= max_steps <= MAX_STEPS:
        raise InvalidRecord('step quota must be 0..4288')
    report = dict(describe_refutation(raw), checked_steps=0, max_steps=max_steps)
    if doc['checker'] != expected_checker or checker_id() != expected_checker:
        return dict(report, status='checker_unavailable')
    model, claim = doc['model'], doc['claim']
    invariant, codes = _model(model, programs=True)
    names = model['state']
    if claim['kind'] == 'unsafe':
        trace = claim['trace']
        if trace['initial'] not in model['initial']:
            raise InvalidRecord('unsafe path does not start in an initial state')
        current = trace['initial']
        for step in trace['steps']:
            if report['checked_steps'] >= max_steps:
                return dict(report, status='incomplete', reason='step_quota')
            facts = dict(current, **step['event'])
            target = {n: boolean.evaluate(codes[n], facts) for n in names}
            if target != step['state']:
                raise InvalidRecord('unsafe path transition does not reproduce')
            current = target
            report['checked_steps'] += 1
        if boolean.evaluate(invariant, current):
            raise InvalidRecord('path endpoint does not violate invariant')
        return dict(report, status='verified_refutation', endpoint=current)
    # A closed set containing all initials and excluding the goal proves absence.
    # Its states need not satisfy the safety invariant.
    if claim['goal'] not in model['goals']:
        raise InvalidRecord('target is not a required goal')
    keys = {_assignment(state, names) for state in claim['states']}
    if any(_assignment(state, names) not in keys for state in model['initial']):
        raise InvalidRecord('refutation omits an initial state')
    if _assignment(claim['goal'], names) in keys:
        raise InvalidRecord('refutation set contains the goal')
    events = list(itertools.product((False, True), repeat=len(model['events'])))
    covered = set()
    for state in claim['states']:
        for bits in events:
            if report['checked_steps'] >= max_steps:
                return dict(report, status='incomplete', reason='step_quota')
            facts = dict(state, **dict(zip(model['events'], bits)))
            target = {n: boolean.evaluate(codes[n], facts) for n in names}
            if _assignment(target, names) not in keys:
                raise InvalidRecord('refutation set is not closed under transitions')
            report['checked_steps'] += 1
            covered.add((_assignment(state, names), bits))
    if len(covered) != len(keys) * (2 ** len(model['events'])) or report['checked_steps'] != len(covered):
        return dict(report, status='checker_error', reason='closure coverage mismatch')
    return dict(report, status='verified_refutation', goal=claim['goal'])


def create_refutation(model, claim):
    raw = canon(dict(refutation=1, checker=checker_id(), model=model, claim=claim))
    result = verify_refutation(raw, identity(model), checker_id())
    if result['status'] != 'verified_refutation':
        raise CheckerError('refutation did not complete independent checking: ' + result['status'])
    return raw


def read(path):
    with Path(path).open('rb') as stream: raw = stream.read(MAX_BYTES + 1)
    if len(raw) > MAX_BYTES: raise InvalidRecord('certificate exceeds size limit')
    return raw


def exit_code(report):
    return {'verified_refutation': 4, 'verified_history': 0, 'verified_change': 0, 'verified_certificate': 0, 'incomplete': 3, 'checker_unavailable': 3, 'checker_error': 1}[report['status']]


REPLAY = r'''"""Authenticate this launcher independently. No producer code is loaded."""
import sys
if not sys.flags.isolated or not sys.flags.no_site:
    raise SystemExit('requires python -I -S')
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
p = argparse.ArgumentParser(allow_abbrev=False)
p.add_argument('certificate', type=Path)
p.add_argument('--expect-model', required=True)
p.add_argument('--expect-checker', required=True)
p.add_argument('--max-steps', type=int, default=4288)
mode = p.add_mutually_exclusive_group()
mode.add_argument('--change', action='store_true')
mode.add_argument('--history', action='store_true')
mode.add_argument('--refutation', action='store_true')
p.add_argument('--output', type=Path)
a = p.parse_args()
if a.output and not (a.change or a.history): p.error('--output requires --change or --history')
names = ('__init__.py', 'store.py', 'canonical.py', 'boolean.py', 'certificate.py')
root = Path(__file__).resolve().parent
try:
    with (root / 'checker.json').open('rb') as stream: raw = stream.read(1024 * 1024 + 1)
    if len(raw) > 1024 * 1024: raise ValueError('checker exceeds size limit')
    texts = json.loads(raw)
    if type(texts) is not dict or set(texts) != set(names) or any(type(t) is not str for t in texts.values()):
        raise ValueError('invalid checker source map')
    id = hashlib.sha256(json.dumps(texts, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
except OSError as exc:
    print(json.dumps(dict(status='unverified', error=str(exc))))
    raise SystemExit(3)
except (ValueError, TypeError, RecursionError) as exc:
    print(json.dumps(dict(status='invalid', error=str(exc))))
    raise SystemExit(2)
if id != a.expect_checker:
    print(json.dumps(dict(status='checker_unavailable', checker=id)))
    raise SystemExit(3)
class Loader:
    def get_data(self, path):
        name = Path(path).name
        if path != '/__stargate_certificate__/' + name or name not in texts:
            raise OSError('outside checked source snapshot')
        return texts[name].encode('utf-8')
    def create_module(self, spec): return None
    def exec_module(self, module):
        exec(compile(self.get_data(module.__file__), module.__file__, 'exec'), module.__dict__)
loader = Loader()
for name in names:
    fullname = 'stargate' if name == '__init__.py' else 'stargate.' + name[:-3]
    if fullname in sys.modules: raise SystemExit('unexpected preloaded module')
    spec = importlib.util.spec_from_loader(fullname, loader, is_package=name == '__init__.py')
    module = importlib.util.module_from_spec(spec)
    module.__file__ = '/__stargate_certificate__/' + name
    sys.modules[fullname] = module
    loader.exec_module(module)
    if name != '__init__.py': setattr(sys.modules['stargate'], name[:-3], module)
from stargate import certificate
try:
    if a.refutation:
        report = certificate.verify_refutation(certificate.read(a.certificate), a.expect_model, a.expect_checker, max_steps=a.max_steps)
    elif a.history:
        report, successor = certificate.verify_history(certificate.read(a.certificate), a.expect_model, a.expect_checker, max_steps=a.max_steps)
    elif a.change:
        report, successor = certificate.verify_change(certificate.read(a.certificate), a.expect_model, a.expect_checker, max_steps=a.max_steps)
    else:
        report = certificate.verify(certificate.read(a.certificate), a.expect_model, a.expect_checker, max_steps=a.max_steps)
except (ValueError, TypeError, RecursionError) as exc:
    print(json.dumps(dict(status='invalid', error=str(exc))))
    raise SystemExit(2)
except OSError as exc:
    print(json.dumps(dict(status='unverified', error=str(exc))))
    raise SystemExit(3)
if (a.change or a.history) and a.output and successor is not None:
    try:
        with a.output.open('xb') as stream: stream.write(successor)
    except OSError as exc:
        print(json.dumps(dict(status='operation_error', error=str(exc))))
        raise SystemExit(1)
print(json.dumps(report, sort_keys=True))
raise SystemExit(certificate.exit_code(report))
'''


def unpack(raw, destination, *, license_text, change=False, history=False, refutation=False):
    if sum((change, history, refutation)) > 1: raise InvalidRecord('choose one packet mode')
    if refutation:
        report = describe_refutation(raw)
        if report['checker'] != checker_id(): raise InvalidRecord('cannot export another checker')
    elif history:
        doc = inspect_history(raw)
        certs = [doc['root']] + [step['certificate'] for step in doc['steps']]
        if any(cert['checker'] != checker_id() for cert in certs):
            raise InvalidRecord('cannot export another checker')
        report = dict(status='unchecked_history', history_id=identity(doc), checker=checker_id())
    elif change:
        doc = inspect_change(raw)
        if any(doc[role]['checker'] != checker_id() for role in ('parent', 'candidate')):
            raise InvalidRecord('cannot export another checker')
        report = dict(status='unchecked_change', change_id=identity(doc), checker=checker_id())
    else:
        report = describe(raw)
        if report['checker'] != checker_id(): raise InvalidRecord('cannot export another checker')
    files = {('refutation.json' if refutation else 'history.json' if history else 'change.json' if change else 'certificate.json'): raw, 'checker.json': canon(sources()),
             'replay.py': REPLAY.encode(), 'LICENSE': license_text.encode(),
             'README.txt': GUIDE.encode()}
    out = Path(destination); out.mkdir(mode=0o700)
    try:
        for name, data in files.items():
            fd = os.open(out / name, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(fd, 'wb') as stream: stream.write(data)
    except BaseException:
        for name in files: (out / name).unlink(missing_ok=True)
        out.rmdir()
        raise
    report['replay_digest'] = hashlib.sha256(REPLAY.encode()).hexdigest()
    return report


GUIDE = '''Finite Boolean machine certificate. No producer implementation is included.
The claimed state set must contain all initials, preserve the invariant, and be
closed under every event. Every goal needs a valid path from an initial state.
The set may overapproximate reachability; paths need not be shortest. Nothing here
proves SKI execution, ATP costs, Python behavior, liveness or inevitability.
To contribute, propose a corrected state set or goal paths as data, not a verdict.
The recipient chooses the model ID independently; replacing the invariant changes it.
Authenticate replay.py and the checker ID independently before running:
python -I -S replay.py certificate.json --expect-model MODEL --expect-checker CHECKER
For a certified change packet, add --change and use change.json. --expect-model
anchors the parent. Both certificates are rechecked; only next may change. Optional
--output writes the verified candidate certificate without overwrite. The step
quota applies separately to each certificate. A no-op change is permitted. No
claim of behavioral equivalence, improvement, or SKI runtime admission is made.
For history.json use --history; --expect-model anchors the root. The root and
every step are checked once; a failed tail gives no tip. --output writes the tip
certificate only on success. At most 32 changes, with quota per certificate.
This proves a contract-preserving path, not who made it, when, completeness of
history or selection of the latest/best branch. No-op steps remain legal.
For refutation.json use --refutation: exit 4 proves a reachable unsafe endpoint
or an unreachable required goal. A closed exclusion set need not be safe. Invalid
evidence (2) proves neither safety nor unsafety; incomplete remains 3. No output
option is accepted for refutations, and no admission or successor is produced.
Exit 0 verifies these finite obligations; 3 means incomplete/unavailable; 2 means
invalid data/certificate, not proof that the model itself is unsafe; 1 checker error.
Python, stdlib, the host and the selected checker remain trusted. Included checker
sources are authenticated code, not authority derived from the certificate itself.
'''
