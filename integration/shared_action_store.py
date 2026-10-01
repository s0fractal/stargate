"""SQLite actuator experiment for the two-contract resource model.

The only effect is updating a toy database row. No real resource is deleted.
The operator chooses the database and its selections; proofs grant no permissions.
"""
import argparse
import importlib.util
import json
from pathlib import Path
import sqlite3
import tempfile
from unittest.mock import patch

from stargate import certificate, lab, projection, projection_check
from stargate.canonical import decode
from stargate.projection_runtime import ProjectionMachine

spec = importlib.util.spec_from_file_location('shared_action', Path(__file__).with_name('shared_action.py'))
shared = importlib.util.module_from_spec(spec)
spec.loader.exec_module(shared)


def connect(path):
    return sqlite3.connect(path, isolation_level=None, timeout=10)


def initialize(connection, selection):
    connection.executescript('''
        CREATE TABLE resource (
            id INTEGER PRIMARY KEY CHECK(id=1),
            revision INTEGER NOT NULL CHECK(typeof(revision)='integer' AND revision>=0),
            held INTEGER NOT NULL CHECK(held IN (0,1)),
            ack INTEGER NOT NULL CHECK(ack IN (0,1)),
            selection TEXT NOT NULL
        );
        CREATE TRIGGER advance_revision BEFORE UPDATE ON resource
        WHEN NEW.revision != OLD.revision + 1 OR typeof(NEW.revision) != 'integer'
        BEGIN SELECT RAISE(ABORT, 'revision must advance exactly once'); END;
    ''')
    connection.execute('INSERT INTO resource VALUES (1,0,1,0,?)', (json.dumps(selection, sort_keys=True),))


def snapshot(connection):
    row = connection.execute('SELECT revision,held,ack,selection FROM resource WHERE id=1').fetchone()
    if row is None:
        raise ValueError('missing selected resource')
    return dict(revision=row[0], state=dict(held=bool(row[1]), ack=bool(row[2])), selection=json.loads(row[3]))


def revise(connection, *, held=None, ack=None, selection=None):
    """Trusted fixture/operator mutation, including starting a new handoff generation."""
    before = snapshot(connection)
    state = before['state']
    for key, value in (('held', held), ('ack', ack)):
        if value is not None:
            if type(value) is not bool:
                raise ValueError('state values must be Boolean')
            state[key] = value
    selected = before['selection'] if selection is None else selection
    cursor = connection.execute('UPDATE resource SET revision=revision+1,held=?,ack=?,selection=? '
                                'WHERE id=1 AND revision=?',
                                (int(state['held']), int(state['ack']), json.dumps(selected, sort_keys=True),
                                 before['revision']))
    if cursor.rowcount != 1:
        raise ValueError('concurrent operator mutation')
    return snapshot(connection)


def release(connection, payload, expected_revision, *, max_steps=certificate.MAX_STEPS):
    if type(expected_revision) is not int or expected_revision < 0:
        raise ValueError('expected revision must be a nonnegative integer')
    if connection.isolation_level is not None or connection.in_transaction:
        raise ValueError('actuator requires an idle autocommit connection')
    before = snapshot(connection)
    result = dict(applied=False, revision=expected_revision, authority='observation_only')
    if before['revision'] != expected_revision:
        return dict(result, status='stale_revision')
    # Freeze the mappings; proof/specification values must be immutable bytes.
    shared.exact(payload, ('world', 'candidate', 'contracts', 'proofs'))
    world, candidate = payload['world'], payload['candidate']
    contracts, proofs = dict(payload['contracts']), dict(payload['proofs'])
    if not all(type(raw) is bytes for raw in (world, candidate, *contracts.values(), *proofs.values())):
        raise ValueError('actuator inputs must be immutable bytes')
    selected = dict(before['selection'])
    projection_anchor = selected.pop('expected_projection_checker')
    checked = shared.check(world, candidate, contracts, proofs, **selected, max_steps=max_steps)
    result['joint_check'] = checked
    if checked['status'] != 'admissible' or checked['admitted'] is not True:
        return dict(result, status='not_admitted')
    # A global policy proof does not establish that the live state belongs to its
    # certified inductive set. Require that separately for both obligations.
    state = before['state']
    if any(state not in decode(proofs[role])['states'] for role in shared.ROLES):
        return dict(result, status='state_not_certified')
    _, raw, model = shared.materialize(world, candidate, contracts['custodian'])
    projected, table = projection.project(raw, lab.identity(raw))
    if projected['status'] != 'projected' or table is None:
        return dict(result, status='projection_incomplete')
    conformance = projection_check.check(table, proofs['custodian'], model,
                                         selected['expected_checker'], projection_anchor)
    result['projection_check'] = conformance
    if conformance['status'] != 'conforms':
        return dict(result, status='projection_refused')
    target = ProjectionMachine.from_bytes(table).step(state, dict(a=False, b=True))
    if not state['held'] or target['held']:
        return dict(result, status='no_release')
    # One SQLite statement is the only effect. Every relevant operator mutation
    # advances this revision, including an ABA return to identical field values.
    cursor = connection.execute('UPDATE resource SET revision=revision+1,held=?,ack=? '
                                'WHERE id=1 AND revision=?',
                                (int(target['held']), int(target['ack']), expected_revision))
    if cursor.rowcount != 1:
        return dict(result, status='stale_revision')
    return dict(result, status='applied', applied=True, successor_revision=expected_revision+1,
                state=target, projection=projected)


def fixture():
    report, artifacts = shared.run()
    choices = json.loads(artifacts['selections.json'])
    selection = dict(expected_world=choices['world'], expected_candidate=choices['candidates']['guarded'],
                     expected_contracts=choices['contracts'], expected_checker=choices['checker'],
                     expected_projection_checker='80a23b477b853dea066ce1cc40eec5f37ed74388fc42ddfbc3e82e01dfa0c6d7')
    payload = dict(world=artifacts['world.json'], candidate=artifacts['guarded/candidate.json'],
                   contracts={role: artifacts[role+'.json'] for role in shared.ROLES},
                   proofs={role: artifacts['guarded/'+role+'/certificate.json'] for role in shared.ROLES})
    return selection, payload


def run():
    selection, payload = fixture()
    results = {}
    with tempfile.TemporaryDirectory(prefix='stargate-shared-store-') as tmp:
        connection = connect(Path(tmp)/'resource.sqlite')
        try:
            initialize(connection, selection)
            results['unacknowledged'] = release(connection, payload, 0)
            current = revise(connection, ack=True)
            results['incomplete'] = release(connection, payload, current['revision'], max_steps=0)
            results['applied'] = release(connection, payload, current['revision'])
            results['replayed'] = release(connection, payload, current['revision'])
            current = revise(connection, held=True, ack=True)
            original = shared.check
            def intervening_handoff(*args, **kwargs):
                checked = original(*args, **kwargs)
                revise(connection, held=True, ack=False)
                return checked
            with patch.object(shared, 'check', intervening_handoff):
                results['changed_during_check'] = release(connection, payload, current['revision'])
            final = snapshot(connection)
            expected = dict(unacknowledged='no_release', incomplete='not_admitted', applied='applied',
                            replayed='stale_revision', changed_during_check='stale_revision')
            if ({name: result['status'] for name, result in results.items()} != expected or
                    final['state'] != dict(held=True, ack=False)):
                raise ValueError('unexpected actuator outcome')
        finally:
            connection.close()
    return dict(status='passed', scope='toy_sqlite_actuator', authority='observation_only',
                cases=results, final=final)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args()
    print(json.dumps(run(), sort_keys=True, indent=2))


if __name__ == '__main__':
    main()
