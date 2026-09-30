"""Replay bounded production Outbox traces against the existing certified table.

Use an authorized --sokol-root checkout. No private source is copied into the repository.
This checks a single subject over retry/reconnect; it is not full queue refinement.
"""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile

from sokol_delivery import models

ROOT = Path(__file__).resolve().parents[1]
TRACES = {
    'unknown_duplicate': ('unknown', 'duplicate', 'empty'),
    'partial_applied': ('partial', 'applied', 'empty'),
    'eof_recorded': ('eof', 'recorded', 'empty'),
    'two_failures_duplicate': ('unknown', 'eof', 'duplicate', 'empty'),
    'applied_empty': ('applied', 'empty'),
}
KNOWN = {'duplicate', 'applied', 'recorded'}


def observe(source, probe):
    with tempfile.TemporaryDirectory(prefix='sg-sokol-traces-') as folder:
        folder = Path(folder)
        (folder / 'delivery.rs').write_text(source)
        (folder / 'probe.rs').write_text(probe)
        build = subprocess.run(['rustc', '--edition=2021', str(folder / 'probe.rs'),
                                '-o', str(folder / 'probe')], capture_output=True, text=True, timeout=120)
        if build.returncode:
            raise RuntimeError('Rust build failed, not a semantic disagreement: ' + build.stderr)
        process = subprocess.run([str(folder / 'probe')], capture_output=True, text=True, timeout=60)
        if process.returncode:
            raise RuntimeError('Rust trace probe failed: ' + process.stderr)
        rows = {name: [] for name in TRACES}
        for line in process.stdout.splitlines():
            name, step, event, pending, total, lost, error, identity = line.split('\t')
            if name not in rows or int(step) != len(rows[name]):
                raise ValueError('unexpected trace name/order')
            if error not in ('true', 'false') or identity not in ('true', 'false'):
                raise ValueError('invalid boolean observation')
            rows[name].append(dict(event=event, pending=int(pending), total=int(total), lost=int(lost),
                                   error=error == 'true', identity=identity == 'true'))
        if any(tuple(row['event'] for row in rows[name]) != events for name, events in TRACES.items()):
            raise ValueError('missing or changed trace events')
        return rows


def mismatches(rows, table):
    failures = []
    if set(rows) != set(TRACES):
        raise ValueError('missing or additional traces')
    for name, events in TRACES.items():
        if tuple(row['event'] for row in rows[name]) != events:
            raise ValueError('missing or changed trace events')
        state = dict(ack=False, queued=True, settled=False)
        for step, row in enumerate(rows[name]):
            event = row['event']
            state = table.step(state, dict(known=event in KNOWN, reply=event not in ('eof', 'empty')))
            expected = dict(event=event, pending=int(state['queued']), total=int(state['settled']),
                            lost=0, error=event not in KNOWN and event != 'empty', identity=True)
            if row != expected:
                failures.append(f'{name}:{step}')
    return failures


def run(root):
    report, table = models()
    source = (root / 'orchestrator/src/delivery.rs').read_text()
    probe = (ROOT / 'integration/sokol_trace_probe.rs').read_text()
    rows = observe(source, probe)
    failed = mismatches(rows, table)
    if failed:
        raise AssertionError('actual trace disagrees: ' + ', '.join(failed))
    mutations = {
        'consume_unknown': ('reply.and_then(|text| Outcome::parse(&text))',
                            'reply.map(|text| Outcome::parse(&text).unwrap_or(Outcome::Recorded))', 'unknown_duplicate:0'),
        'accept_partial': (" || !reply.ends_with('\\n')", '', 'partial_applied:0'),
        'drop_on_error': ('                Err(e) => {',
                          '                Err(e) => {\n                    self.queue.pop_front();', 'eof_recorded:0'),
        'retain_after_ack': ('                    self.queue.pop_front();',
                             '                    // mutant retains acknowledged subject', 'applied_empty:1'),
    }
    controls = {}
    for name, (old, new, witness) in mutations.items():
        if source.count(old) != 1:
            raise AssertionError('mutation site changed: ' + name)
        failed = mismatches(observe(source.replace(old, new), probe), table)
        if witness not in failed:
            raise AssertionError('mutant survived: ' + name)
        controls[name] = failed
    return dict(status='bounded_traces_conform', model=report,
                source_sha256=hashlib.sha256(source.encode()).hexdigest(),
                probe_sha256=hashlib.sha256(probe.encode()).hexdigest(), traces=rows, controls=controls,
                prefix_count=sum(map(len, rows.values())), independent_demand=False)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--sokol-root', type=Path, required=True)
    parser.add_argument('--expect-results', type=Path)
    args = parser.parse_args()
    result = json.dumps(run(args.sokol_root.resolve()), sort_keys=True, indent=2) + '\n'
    if args.expect_results and args.expect_results.read_text() != result:
        raise SystemExit('results differ from the pinned trace experiment')
    print(result, end='')
