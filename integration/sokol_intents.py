"""Retained local intents driving one actual Sokol Outbox flush per reservation.

The receiver and sender share the trusted toy database. No production node is used.
"""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import threading


def load(name, filename):
    spec = importlib.util.spec_from_file_location(name, Path(__file__).with_name(filename))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


intents = load('sender_intents', 'agent_intents.py')
receipts = load('sender_receipts', 'sokol_receipts.py')
store = intents.store
DRIVER = r'''
#[path = "delivery.rs"] mod delivery;
use std::{env, path::Path};
fn main() {
    let args: Vec<String> = env::args().collect();
    let mut out = delivery::Outbox::new(Path::new(&args[1]), 1);
    out.push(&args[2]);
    let (done, error) = out.flush(1);
    println!("{}\t{}\t{}\t{}", out.pending(), done.len(), out.lost, error.is_some());
}
'''


def send_once(connection, operation, binary, endpoint, *, timeout=10):
    """Reserve before transport; only the local receipt establishes completion.

    binary and endpoint are trusted operator-selected inputs, never wire fields.
    The supplied binary must implement DRIVER's one-flush contract.
    """
    reservation = intents.reserve(connection, operation)
    if reservation['status'] != 'reserved':
        return reservation
    request = intents.wire(reservation['intent']).decode()
    try:
        process = subprocess.run([str(binary), str(endpoint), request], capture_output=True,
                                 text=True, timeout=timeout)
        transport = dict(status='exited', returncode=process.returncode)
    except subprocess.TimeoutExpired:
        transport = dict(status='timeout')
    except OSError:
        transport = dict(status='launch_error')
    # Neither exit 0, stdout nor an ACK creates a completed intent. Even after a
    # timeout the receiver may still commit: retain uncertainty and reconcile later.
    result = intents.reconcile(connection, operation)
    result['transport'] = transport
    return result


def dispatch(connection, raw, *, max_steps=store.certificate.MAX_STEPS):
    request = store.decode(raw)
    store.shared.exact(request, ('operation', 'revision'))
    retained = intents.inspect(connection, request['operation'])
    if type(request['revision']) is not int or request['revision'] != retained['revision']:
        raise ValueError('wire revision does not match retained intent')
    # Cancellation races are still fenced by the actuator revision CAS, including
    # cancellation after this lookup. Payload comes exclusively from enrolment.
    return receipts.dispatch(connection, retained['payload'], raw, max_steps=max_steps)


def build(sokol_root, target):
    source = (Path(sokol_root)/'orchestrator/src/delivery.rs').read_bytes()
    (target/'delivery.rs').write_bytes(source)
    (target/'main.rs').write_text(DRIVER)
    result = subprocess.run(['rustc', '--edition=2021', str(target/'main.rs'), '-o', str(target/'sender')],
                            capture_output=True, text=True, timeout=60)
    if result.returncode:
        raise RuntimeError(result.stderr)
    return target/'sender', hashlib.sha256(source).hexdigest()


# Fault injection is confined to the experiment worker. It exits the Python
# sender after the committed reservation, before or after the actual Rust child.
WORKER = r'''
import importlib.util, os, sys
spec=importlib.util.spec_from_file_location('worker',sys.argv[1])
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
c=m.store.connect(sys.argv[2]); original=m.subprocess.run
phase=sys.argv[5]
def interrupted(*args,**kwargs):
 if phase=='before': os._exit(73)
 result=original(*args,**kwargs)
 if phase=='after': os._exit(73)
 return result
m.subprocess.run=interrupted
m.send_once(c,'job',sys.argv[3],sys.argv[4]);c.close()
'''


def exercise(binary, mode):
    selection, payload = store.fixture()
    with tempfile.TemporaryDirectory(prefix='sg-i-', dir='/tmp') as tmp:
        root = Path(tmp)
        database, endpoint = root/'state.sqlite', root/'ipc'
        connection = store.connect(database)
        store.initialize(connection, selection)
        intents.initialize(connection)
        revision = store.revise(connection, ack=True)['revision']
        limit = 1 if mode in ('exhausted', 'lost', 'false_ack', 'cancelled') else 2
        intents.enroll(connection, 'job', revision, payload, limit)
        connection.close()
        listener = socket.socket(socket.AF_UNIX)
        listener.bind(str(endpoint)); listener.listen(4); listener.settimeout(0.1)
        stopped = threading.Event()
        seen, errors = [], []

        def serve():
            c = store.connect(database)
            try:
                while not stopped.is_set():
                    try:
                        stream, _ = listener.accept()
                    except socket.timeout:
                        continue
                    with stream:
                        stream.settimeout(5)
                        with stream.makefile('rb') as incoming:
                            if incoming.readline(4096) != b'ACK\n':
                                raise ValueError('missing handshake')
                            stream.sendall(b'OK ack\n')
                            raw = incoming.readline(4096)
                            if raw != intents.wire(intents.inspect(c, 'job'))+b'\n':
                                raise ValueError('request changed across restart')
                            if mode == 'cancelled':
                                intents.cancel(c, 'job')
                            budget = 0 if mode in ('incomplete', 'false_ack') and not seen else store.certificate.MAX_STEPS
                            result = dispatch(c, raw[:-1], max_steps=budget)
                            seen.append(result['status'])
                            reply = receipts.acknowledge(result)
                            if mode == 'lost':
                                reply = None
                            elif mode == 'false_ack':
                                reply = b'OK applied\n'  # untrusted transport success
                            if reply is not None:
                                stream.sendall(reply)
            except BaseException as error:
                errors.append(error)
            finally:
                c.close()

        thread = threading.Thread(target=serve)
        thread.start()
        try:
            phase = 'before' if mode in ('before', 'exhausted') else 'after'
            first = subprocess.run([sys.executable, '-c', WORKER, str(Path(__file__).resolve()),
                                    str(database), str(binary), str(endpoint), phase],
                                   capture_output=True, text=True, timeout=20)
            if first.returncode != 73:
                raise ValueError('worker did not reach fault boundary: '+first.stderr)
            # A different Python process resumes with no in-memory queue or payload.
            second = subprocess.run([sys.executable, '-c', WORKER, str(Path(__file__).resolve()),
                                     str(database), str(binary), str(endpoint), 'resume'],
                                    capture_output=True, text=True, timeout=20)
            if second.returncode:
                raise ValueError('resume failed: '+second.stderr)
        finally:
            stopped.set(); thread.join(timeout=6); listener.close()
        if thread.is_alive() or errors:
            raise RuntimeError('receiver failed: '+repr(errors))
        c = store.connect(database)
        try:
            result = intents.reserve(c, 'job')  # must reconcile or refuse; never another slot
            final = store.snapshot(c)
            count = c.execute('SELECT COUNT(*) FROM receipt').fetchone()[0]
        finally:
            c.close()
        expected = {
            'before': ('completed', 2, ['applied'], 1),
            'exhausted': ('budget_exhausted', 1, [], 0),
            'lost': ('completed', 1, ['applied'], 1),
            'incomplete': ('completed', 2, ['not_admitted', 'applied'], 1),
            'false_ack': ('budget_exhausted', 1, ['not_admitted'], 0),
            'cancelled': ('cancelled', 1, ['stale_revision'], 0),
        }[mode]
        observed = (result['status'], result['attempts'], seen, count)
        if observed != expected or final['state']['held'] != (count == 0):
            raise ValueError(f'wrong {mode} outcome: {observed}, {final}')
        return dict(status=result['status'], attempts=result['attempts'], receiver=seen,
                    receipts=count, state=final['state'], revision=final['revision'])


def run(sokol_root):
    with tempfile.TemporaryDirectory(prefix='sg-intent-build-') as tmp:
        binary, digest = build(sokol_root, Path(tmp))
        cases = {mode: exercise(binary, mode) for mode in
                 ('before', 'exhausted', 'lost', 'incomplete', 'false_ack', 'cancelled')}
    return dict(status='passed', scope='actual_outbox_retained_local_intent', authority='observation_only',
                delivery_sha256=digest, driver_sha256=hashlib.sha256(DRIVER.encode()).hexdigest(),
                adapter_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                intent_sha256=hashlib.sha256(Path(intents.__file__).read_bytes()).hexdigest(),
                actuator_sha256=hashlib.sha256(Path(store.__file__).read_bytes()).hexdigest(),
                receiver_sha256=hashlib.sha256(Path(receipts.__file__).read_bytes()).hexdigest(), cases=cases)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--sokol-root', type=Path, required=True)
    parser.add_argument('--expect-results', type=Path)
    args = parser.parse_args()
    result = (json.dumps(run(args.sokol_root), sort_keys=True, indent=2)+'\n').encode()
    if args.expect_results and result != args.expect_results.read_bytes():
        raise ValueError('retained sender results differ from expected bytes')
    sys.stdout.buffer.write(result)
