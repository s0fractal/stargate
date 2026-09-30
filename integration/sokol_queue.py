"""Capacity-two queue correspondence: certified representation + bounded real traces.

The authorized source checkout is compiled locally. No private source is vendored.
FIFO/overflow reference transitions, exact loss counts and occurrence identity are
separate from the model's representation-safety certificate. No crash durability claim.
"""
import argparse
import hashlib
import itertools
import json
from pathlib import Path
import subprocess
import tempfile

from stargate import certificate, evidence, lab, machine, projection, projection_check
from stargate.canonical import decode
from stargate.projection_runtime import ProjectionMachine

ROOT = Path(__file__).resolve().parents[1]
PLANS = {
    'fifo_limit': ('push:A1', 'push:B1', 'flush:0', 'flush:1', 'push:A2', 'flush:8', 'flush:8'),
    'partial_retry': ('push:A1', 'push:B1', 'flush:2', 'push:A2', 'retry:2', 'flush:8'),
    'overflow': ('push:A1', 'push:B1', 'push:A2', 'flush:8', 'flush:8'),
    'repeated_overflow': ('push:A1', 'push:B1', 'push:A2', 'push:B2', 'flush:1', 'flush:8'),
}
EVENTS = {'A': dict(x=False, y=False), 'B': dict(x=False, y=True),
          'ack': dict(x=True, y=False), 'idle': dict(x=True, y=True)}


def encode(queue, dropped):
    return dict(front=bool(queue), rear=len(queue) == 2,
                front_b=bool(queue) and queue[0].startswith('B'),
                rear_b=len(queue) == 2 and queue[1].startswith('B'), dropped=dropped)


def check_reference(table):
    """Exhaust the valid representation against a list specification, not Boolean rules."""
    checked = 0
    for size in range(3):
        for values in itertools.product('AB', repeat=size):
            for dropped in (False, True):
                state = encode(values, dropped)
                for operation, event in EVENTS.items():
                    queue = list(values)
                    lost = dropped
                    if operation in ('A', 'B'):
                        if len(queue) == 2:
                            queue = queue[1:]
                            lost = True
                        queue.append(operation)
                    elif operation == 'ack' and queue:
                        queue = queue[1:]
                    if table.step(state, event) != encode(queue, lost):
                        raise AssertionError('model disagrees with list reference: ' + str((values, dropped, operation)))
                    checked += 1
    return checked


def model():
    spec = json.loads((ROOT / 'examples/sokol-queue/model.json').read_text())
    raw = machine.create(spec)
    report, proof = evidence.produce(raw, lab.identity(raw))
    if report['status'] != 'verified_certificate':
        raise AssertionError(report)
    model_id = certificate.identity(decode(proof)['model'])
    projected, table = projection.project(raw, lab.identity(raw))
    if table is None:
        raise AssertionError(projected)
    checked = projection_check.check(table, proof, model_id, certificate.checker_id(),
                                     projection_check.projection_checker_id())
    if checked['status'] != 'conforms':
        raise AssertionError(checked)
    runtime = ProjectionMachine.from_bytes(table)
    return dict(status=report['status'], model=model_id, checker=certificate.checker_id(),
                reference_transitions=check_reference(runtime)), runtime


def expected(table):
    rows = {}
    for name, operations in PLANS.items():
        queue, requests, timeline = [], [], []
        lost, pushed, completed = 0, 0, 0
        failed_b = False
        state = encode([], False)
        for op in operations:
            kind, value = op.split(':')
            done, error = [], False
            if kind == 'push':
                pushed += 1
                if len(queue) == 2:
                    queue = queue[1:]
                    lost += 1
                queue.append(value)
                state = table.step(state, EVENTS[value[0]])
            else:
                for _ in range(min(int(value), len(queue))):
                    subject = queue[0]
                    requests.append(subject)
                    if name == 'partial_retry' and subject == 'B1' and not failed_b:
                        failed_b, error = True, True
                        state = table.step(state, EVENTS['idle'])
                        break
                    done.append(queue.pop(0))
                    completed += 1
                    state = table.step(state, EVENTS['ack'])
            if state != encode(queue, lost > 0) or pushed != len(queue) + completed + lost:
                raise AssertionError('reference conservation/model mismatch')
            timeline.append(dict(op=op, pending=len(queue), lost=lost, done=done,
                                 requests=list(requests), error=error))
        rows[name] = timeline
    return rows


def observe(source, probe):
    with tempfile.TemporaryDirectory(prefix='sg-queue-') as folder:
        folder = Path(folder)
        (folder / 'delivery.rs').write_text(source)
        (folder / 'probe.rs').write_text(probe)
        build = subprocess.run(['rustc', '--edition=2021', str(folder / 'probe.rs'), '-o', str(folder / 'probe')],
                               capture_output=True, text=True, timeout=120)
        if build.returncode:
            raise RuntimeError('Rust compilation failed, not a mutant kill: ' + build.stderr)
        process = subprocess.run([str(folder / 'probe')], capture_output=True, text=True, timeout=60)
        if process.returncode:
            raise RuntimeError('Rust queue probe failed: ' + process.stderr)
        rows = {name: [] for name in PLANS}
        for line in process.stdout.splitlines():
            name, step, op, pending, lost, done, requests, error = line.split('\t')
            if name not in rows or int(step) != len(rows[name]) or error not in ('true', 'false'):
                raise ValueError('invalid queue trace')
            rows[name].append(dict(op=op, pending=int(pending), lost=int(lost),
                                   done=done.split(',') if done else [],
                                   requests=requests.split(',') if requests else [], error=error == 'true'))
        return rows


def mismatches(rows, reference):
    if set(rows) != set(PLANS):
        raise ValueError('missing/additional queue cases')
    failures = []
    for name, operations in PLANS.items():
        if tuple(row['op'] for row in rows[name]) != operations:
            raise ValueError('missing/reordered queue operations')
        for step, (actual, wanted) in enumerate(zip(rows[name], reference[name])):
            if actual != wanted:
                failures.append(f'{name}:{step}')
    return failures


def run(root):
    report, table = model()
    reference = expected(table)
    source = (root / 'orchestrator/src/delivery.rs').read_text()
    probe = (ROOT / 'integration/sokol_queue_probe.rs').read_text()
    rows = observe(source, probe)
    failed = mismatches(rows, reference)
    if failed:
        raise AssertionError('queue disagrees: ' + ', '.join(failed))
    mutations = {
        'evict_newest': ('            self.queue.pop_front();', '            self.queue.pop_back();', 'overflow:3'),
        'omit_loss': ('            self.lost += 1;', '            // omitted loss', 'overflow:2'),
        'reverse_insert': ('self.queue.push_back(line.trim_end().to_string());',
                           'self.queue.push_front(line.trim_end().to_string());', 'fifo_limit:3'),
        'remove_newest_on_ack': ('                    self.queue.pop_front();',
                                 '                    self.queue.pop_back();', 'fifo_limit:5'),
        'flush_extra': ('while done.len() < max {', 'while done.len() <= max {', 'fifo_limit:2'),
        'drop_on_error': ('                Err(e) => {',
                          '                Err(e) => {\n                    self.queue.pop_front();', 'partial_retry:2'),
    }
    controls = {}
    for name, (old, new, witness) in mutations.items():
        # Anchor whole lines so indentation cannot accidentally match another pop site.
        if source.splitlines().count(old) == 1:
            mutated = '\n'.join(new if line == old else line for line in source.split('\n'))
        elif source.count(old) == 1:
            mutated = source.replace(old, new)
        else:
            raise AssertionError('mutation site changed: ' + name)
        failed = mismatches(observe(mutated, probe), reference)
        if witness not in failed:
            raise AssertionError('mutant survived: ' + name)
        controls[name] = failed
    return dict(status='bounded_queue_conforms', model=report,
                source_sha256=hashlib.sha256(source.encode()).hexdigest(),
                probe_sha256=hashlib.sha256(probe.encode()).hexdigest(),
                traces=rows, prefix_count=sum(map(len, rows.values())), controls=controls,
                independent_demand=False)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--sokol-root', type=Path, required=True)
    parser.add_argument('--expect-results', type=Path)
    args = parser.parse_args()
    result = json.dumps(run(args.sokol_root.resolve()), sort_keys=True, indent=2) + '\n'
    if args.expect_results and args.expect_results.read_text() != result:
        raise SystemExit('queue results differ from the frozen experiment')
    print(result, end='')
