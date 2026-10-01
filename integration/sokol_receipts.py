"""Exercise Sokol's actual outbox against the local Stargate receipt actuator.

Explicit private source is required. Only a temporary Unix socket and toy database
are used; this is not a Sokol node endpoint or a production authorization protocol.
"""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import socket
import subprocess
import tempfile
import threading

spec = importlib.util.spec_from_file_location('receipt_store', Path(__file__).with_name('shared_action_store.py'))
store = importlib.util.module_from_spec(spec)
spec.loader.exec_module(store)

DRIVER = r'''
#[path = "delivery.rs"] mod delivery;
use std::{env, path::Path, thread, time::Duration};
fn main() {
    let args: Vec<String> = env::args().collect();
    let mut out = delivery::Outbox::new(Path::new(&args[1]), 2);
    out.push(&args[2]);
    for phase in 0..2 {
        if phase == 1 { thread::sleep(Duration::from_millis(550)); }
        let (done, error) = out.flush(1);
        let outcome = match done.first().map(|v| &v.1) {
            None => "none",
            Some(delivery::Outcome::Applied) => "applied",
            Some(delivery::Outcome::Duplicate) => "duplicate",
            Some(delivery::Outcome::Refused(_)) => "refused",
            Some(_) => "other",
        };
        println!("{}\t{}\t{}\t{}\t{}\t{}", phase, out.pending(), done.len(), out.lost, error.is_some(), outcome);
    }
}
'''


def acknowledge(result):
    """Only a committed effect or its matching receipt permits a success reply."""
    status = result.get('status')
    if status == 'applied' and result.get('applied') is True:
        return b'OK applied\n'
    if status == 'already_applied' and result.get('applied') is False:
        receipt = result.get('receipt', {})
        if receipt.get('status') == 'applied' and receipt.get('applied') is True:
            return b'OK duplicate\n'
    if status in ('operation_conflict', 'stale_revision', 'no_release', 'state_not_certified'):
        if result.get('applied') is False:
            return ('OK refused '+status+'\n').encode()
    # Incomplete/unknown/error is not Applied, Recorded, Pending or final refusal.
    return None


def dispatch(connection, payload, raw, *, max_steps=store.certificate.MAX_STEPS):
    request = store.decode(raw)
    store.shared.exact(request, ('operation', 'revision'))
    if request['operation'] is None:
        raise ValueError('an operation identity is required')
    return store.release(connection, payload, request['revision'], operation=request['operation'],
                         max_steps=max_steps)


def exercise(binary, mode, *, responder=None):
    selection, payload = store.fixture()
    # Keep the socket path short enough on macOS; no user socket is opened.
    with tempfile.TemporaryDirectory(prefix='sg-r-', dir='/tmp') as tmp:
        path = Path(tmp)
        database = path/'state.sqlite'
        connection = store.connect(database)
        store.initialize(connection, selection)
        revision = store.revise(connection, ack=True)['revision']
        if mode == 'conflict':
            store.release(connection, payload, revision, operation='release.1')
            revision += 1
        connection.close()
        request = store.certificate.canon(dict(operation='release.1', revision=revision)).decode()
        observations, errors = [], []
        listener = socket.socket(socket.AF_UNIX)
        listener.bind(str(path/'ipc'))
        listener.listen(2)
        listener.settimeout(0.2)
        stopped = threading.Event()

        def serve():
            connection = store.connect(database)
            try:
                for attempt in range(1 if mode == 'conflict' else 2):
                    while not stopped.is_set():
                        try:
                            stream, _ = listener.accept()
                            break
                        except socket.timeout:
                            continue
                    else:
                        return
                    with stream:
                        stream.settimeout(5)
                        with stream.makefile('rb') as incoming:
                            if incoming.readline(4096) != b'ACK\n':
                                raise ValueError('missing ACK handshake')
                            stream.sendall(b'OK ack\n')
                            raw = incoming.readline(4096)
                            if not raw.endswith(b'\n') or raw.decode().rstrip('\n') != request:
                                raise ValueError('outbox changed the submitted request')
                            budget = 0 if attempt == 0 and mode in ('incomplete', 'revoked') else store.certificate.MAX_STEPS
                            result = dispatch(connection, payload, raw[:-1], max_steps=budget)
                            observations.append(result['status'])
                            reply = (responder or acknowledge)(result)
                            if attempt == 0:
                                if mode == 'lost':
                                    reply = None
                                elif mode == 'partial':
                                    reply = b'OK applied'
                                elif mode == 'unknown':
                                    reply = b'OK unknown\n'
                                elif mode == 'revoked':
                                    store.revise(connection, ack=False)
                            if reply is not None:
                                stream.sendall(reply)
            except BaseException as error:
                errors.append(error)
            finally:
                connection.close()

        server = threading.Thread(target=serve)
        server.start()
        try:
            process = subprocess.run([str(binary), str(path/'ipc'), request], capture_output=True,
                                     text=True, timeout=15)
        finally:
            stopped.set()
            server.join(timeout=12)
            listener.close()
        if server.is_alive():
            raise RuntimeError('receiver did not terminate')
        if errors:
            raise RuntimeError('receiver failed') from errors[0]
        if process.returncode:
            raise RuntimeError(process.stderr)
        rows = [line.split('\t') for line in process.stdout.splitlines()]
        connection = store.connect(database)
        try:
            final = store.snapshot(connection)
            receipts = connection.execute('SELECT COUNT(*) FROM receipt').fetchone()[0]
        finally:
            connection.close()
        expected_outcome = 'refused' if mode in ('conflict', 'revoked') else ('applied' if mode == 'incomplete' else 'duplicate')
        expected_rows = ([['0', '0', '1', '0', 'false', 'refused'], ['1', '0', '0', '0', 'false', 'none']]
                         if mode == 'conflict' else
                         [['0', '1', '0', '0', 'true', 'none'], ['1', '0', '1', '0', 'false', expected_outcome]])
        expected_observations = (['operation_conflict'] if mode == 'conflict' else
                                 ['not_admitted', 'stale_revision'] if mode == 'revoked' else
                                 ['not_admitted', 'applied'] if mode == 'incomplete' else
                                 ['applied', 'already_applied'])
        expected_state = dict(held=True, ack=False) if mode == 'revoked' else dict(held=False, ack=True)
        if (rows != expected_rows or observations != expected_observations or final['revision'] != 2
                or final['state'] != expected_state or receipts != (0 if mode == 'revoked' else 1)):
            raise ValueError(f'wrong {mode} outcome: {rows}, {observations}, {final}, receipts={receipts}')
        return dict(delivery=rows, receiver=observations, final=final['state'],
                    revision=final['revision'], receipts=receipts)


def run(sokol_root):
    source = (Path(sokol_root)/'orchestrator/src/delivery.rs').read_bytes()
    with tempfile.TemporaryDirectory(prefix='sg-receipt-build-') as tmp:
        root = Path(tmp)
        # Compile exactly the bytes whose digest is reported, not a mutable path.
        (root/'delivery.rs').write_bytes(source)
        (root/'main.rs').write_text(DRIVER)
        compiled = subprocess.run(['rustc', '--edition=2021', str(root/'main.rs'), '-o', str(root/'probe')],
                                  capture_output=True, text=True, timeout=60)
        if compiled.returncode:
            raise RuntimeError(compiled.stderr)
        cases = {mode: exercise(root/'probe', mode)
                 for mode in ('lost', 'partial', 'unknown', 'incomplete', 'revoked', 'conflict')}
        controls = {}
        marker = b'self.failing = true;'
        if source.count(marker) != 1:
            raise ValueError('cannot apply dropped-request mutation to this source')
        (root/'delivery.rs').write_bytes(source.replace(marker, b'self.queue.pop_front(); '+marker))
        mutated = subprocess.run(['rustc', '--edition=2021', str(root/'main.rs'), '-o', str(root/'mutant')],
                                 capture_output=True, text=True, timeout=60)
        if mutated.returncode:
            raise RuntimeError(mutated.stderr)
        original = acknowledge
        def false_success(result):
            return b'OK applied\n' if result.get('status') == 'not_admitted' else original(result)
        for name, binary, mode, reply in (
                ('drop_uncertain_request', root/'mutant', 'lost', original),
                ('ack_incomplete_verification', root/'probe', 'incomplete', false_success)):
            try:
                exercise(binary, mode, responder=reply)
            except ValueError as error:
                if not str(error).startswith('wrong '):
                    raise
                controls[name] = 'detected_observation_mismatch'
            else:
                raise ValueError('semantic mutant survived: '+name)

    return dict(status='passed', authority='observation_only', scope='actual_outbox_toy_receiver',
                delivery_sha256=hashlib.sha256(source).hexdigest(),
                adapter_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                actuator_sha256=hashlib.sha256(Path(store.__file__).read_bytes()).hexdigest(),
                driver_sha256=hashlib.sha256(DRIVER.encode()).hexdigest(), cases=cases,
                mutation_controls=controls)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--sokol-root', required=True, type=Path)
    args = parser.parse_args()
    print(json.dumps(run(args.sokol_root), sort_keys=True, indent=2))


if __name__ == '__main__':
    main()
