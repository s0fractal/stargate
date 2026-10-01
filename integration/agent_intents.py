"""Retained local agent intent with conservative attempt budgets and cancellation.

Shares the trusted toy actuator database. No daemon or external effect is started.
"""
import importlib.util
import json
from pathlib import Path
import tempfile

spec = importlib.util.spec_from_file_location('intent_store', Path(__file__).with_name('shared_action_store.py'))
store = importlib.util.module_from_spec(spec)
spec.loader.exec_module(store)


def idle(connection):
    if connection.isolation_level is not None or connection.in_transaction:
        raise ValueError('intent journal requires an idle autocommit connection')


def initialize(connection):
    idle(connection)
    connection.executescript('''
        CREATE TABLE intent (
            operation TEXT PRIMARY KEY,
            revision INTEGER NOT NULL CHECK(typeof(revision)='integer' AND revision>=0),
            payload TEXT NOT NULL,
            request TEXT NOT NULL,
            limit_attempts INTEGER NOT NULL CHECK(typeof(limit_attempts)='integer' AND limit_attempts BETWEEN 1 AND 1000),
            attempts INTEGER NOT NULL DEFAULT 0 CHECK(typeof(attempts)='integer' AND attempts BETWEEN 0 AND limit_attempts),
            status TEXT NOT NULL DEFAULT 'pending' CHECK(status IN ('pending','completed','cancelled','conflict'))
        );
        CREATE TRIGGER intent_binding BEFORE UPDATE ON intent
        WHEN NEW.operation!=OLD.operation OR NEW.revision!=OLD.revision OR NEW.payload!=OLD.payload
          OR NEW.request!=OLD.request OR NEW.limit_attempts!=OLD.limit_attempts
          OR NEW.attempts<OLD.attempts OR NEW.attempts>OLD.attempts+1
          OR (OLD.status!='pending' AND (NEW.status!=OLD.status OR NEW.attempts!=OLD.attempts))
        BEGIN SELECT RAISE(ABORT, 'immutable intent or invalid transition'); END;
        CREATE TRIGGER retain_intent BEFORE DELETE ON intent
        BEGIN SELECT RAISE(ABORT, 'intent history is retained'); END;
    ''')


def encode(payload):
    store.shared.exact(payload, ('world', 'candidate', 'contracts', 'proofs'))
    result = {}
    for field in ('world', 'candidate'):
        if type(payload[field]) is not bytes:
            raise ValueError('immutable payload bytes required')
        result[field] = payload[field].hex()
    for field in ('contracts', 'proofs'):
        store.shared.exact(payload[field], store.shared.ROLES)
        if any(type(raw) is not bytes for raw in payload[field].values()):
            raise ValueError('immutable payload bytes required')
        result[field] = {role: raw.hex() for role, raw in payload[field].items()}
    return json.dumps(result, sort_keys=True)


def decode(raw):
    doc = json.loads(raw)
    return dict(world=bytes.fromhex(doc['world']), candidate=bytes.fromhex(doc['candidate']),
                contracts={k: bytes.fromhex(v) for k, v in doc['contracts'].items()},
                proofs={k: bytes.fromhex(v) for k, v in doc['proofs'].items()})


def enroll(connection, operation, revision, payload, limit_attempts):
    """Operator-selected inputs and finite budget; re-enrolment cannot reset them."""
    idle(connection)
    if (type(operation) is not str or not 1 <= len(operation) <= 128 or not operation.isascii()
            or not all(c.isalnum() or c in '-_.' for c in operation)):
        raise ValueError('invalid operation identifier')
    if type(revision) is not int or not 0 <= revision < 2**63:
        raise ValueError('invalid revision')
    if type(limit_attempts) is not int or not 1 <= limit_attempts <= 1000:
        raise ValueError('invalid attempt limit')
    raw = encode(payload)
    frozen = decode(raw)
    request = store.request_identity(**frozen, expected_revision=revision)
    connection.execute('BEGIN IMMEDIATE')
    try:
        if connection.execute('SELECT 1 FROM receipt WHERE operation=?', (operation,)).fetchone():
            raise ValueError('operation already has a receipt')
        connection.execute('INSERT INTO intent(operation,revision,payload,request,limit_attempts) VALUES (?,?,?,?,?)',
                           (operation, revision, raw, request, limit_attempts))
        connection.commit()
    except BaseException:
        connection.rollback()
        raise
    return inspect(connection, operation)


def inspect(connection, operation):
    row = connection.execute('SELECT revision,payload,request,limit_attempts,attempts,status '
                             'FROM intent WHERE operation=?', (operation,)).fetchone()
    if row is None:
        raise ValueError('unknown intent')
    return dict(operation=operation, revision=row[0], payload=decode(row[1]), request=row[2],
                limit_attempts=row[3], attempts=row[4], status=row[5])


def wire(intent):
    """The existing Sokol-receipt fixture request, unchanged across reservations."""
    return store.certificate.canon(dict(operation=intent['operation'], revision=intent['revision']))


def _reconcile(connection, intent):
    previous = store.recorded(connection, intent['operation'], intent['request'])
    if previous is not None and intent['status'] == 'pending':
        status = 'completed' if previous['status'] == 'already_applied' else 'conflict'
        connection.execute('UPDATE intent SET status=? WHERE operation=?', (status, intent['operation']))
        intent['status'] = status
    return previous


def transition(connection, operation, action):
    """Serialize receipt reconciliation, reservation and local cancellation."""
    idle(connection)
    connection.execute('BEGIN IMMEDIATE')
    try:
        intent = inspect(connection, operation)
        receipt = _reconcile(connection, intent)
        status = intent['status']
        if status == 'pending' and action == 'cancel':
            # Invalidate a checked-but-not-committed release, without modifying a
            # newer generation. The actuator's existing revision CAS enforces it.
            if store.snapshot(connection)['revision'] == intent['revision']:
                store.revise(connection)
            connection.execute("UPDATE intent SET status='cancelled' WHERE operation=?", (operation,))
            status = 'cancelled'
            intent['status'] = status
        elif status == 'pending' and action == 'reserve':
            if intent['attempts'] >= intent['limit_attempts']:
                status = 'budget_exhausted'
            else:
                connection.execute('UPDATE intent SET attempts=attempts+1 WHERE operation=?', (operation,))
                intent['attempts'] += 1
                status = 'reserved'
        connection.commit()
        return dict(status=status, attempts=intent['attempts'], receipt=receipt,
                    authority='observation_only', intent=intent)
    except BaseException:
        connection.rollback()
        raise


def reserve(connection, operation):
    return transition(connection, operation, 'reserve')


def cancel(connection, operation):
    return transition(connection, operation, 'cancel')


def reconcile(connection, operation):
    return transition(connection, operation, 'reconcile')


def attempt(connection, operation, *, max_steps=store.certificate.MAX_STEPS):
    reservation = reserve(connection, operation)
    if reservation['status'] != 'reserved':
        return reservation
    intent = reservation['intent']
    # Reservation is committed before any checker/effect work; a crash consumes
    # this slot conservatively. Missing receipts never refund or renew a budget.
    outcome = store.release(connection, intent['payload'], intent['revision'], operation=operation,
                            max_steps=max_steps)
    result = reconcile(connection, operation)
    result['outcome'] = outcome
    return result


def run():
    selection, payload = store.fixture()
    with tempfile.TemporaryDirectory(prefix='stargate-intent-') as tmp:
        path = Path(tmp)/'state.sqlite'
        connection = store.connect(path)
        store.initialize(connection, selection)
        initialize(connection)
        revision = store.revise(connection, ack=True)['revision']
        enroll(connection, 'agent.1', revision, payload, 1)
        reserved = reserve(connection, 'agent.1')
        if reserved['status'] != 'reserved':
            raise ValueError('reservation failed')
        store.release(connection, reserved['intent']['payload'], revision, operation='agent.1')
        connection.close()  # sender did not retain the result
        connection = store.connect(path)
        try:
            recovered = attempt(connection, 'agent.1')
            if recovered['status'] != 'completed' or recovered['attempts'] != 1:
                raise ValueError('intent recovery failed')
            return dict(status='passed', scope='local_retained_intent', attempts=recovered['attempts'],
                        recovered=recovered['status'], authority='observation_only')
        finally:
            connection.close()


if __name__ == '__main__':
    print(json.dumps(run(), sort_keys=True))
