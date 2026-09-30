"""Reproduce the consumer pilot and emit an observation report, never admission authority.

No downloads, source edits or production effects. The full profile executes only explicitly
provided, trusted source roots after checking the frozen input hashes. Reports are unsigned.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import platform
import shutil
import subprocess
import sys
import time

from stargate import certificate
import sokol_delivery
import sokol_queue
import sokol_traces
import warrant_adapter

ROOT = Path(__file__).resolve().parents[1]
ARTIFACTS = {
    'delivery': 'examples/sokol-delivery/results-v2.json',
    'traces': 'examples/sokol-delivery/trace-results.json',
    'queue': 'examples/sokol-queue/results.json',
    'warrant': 'examples/warrant-adapter/results.json',
}
FULL_STAGES = ('warrant_adapter', 'sokol_delivery', 'sokol_traces', 'sokol_queue')


def digest(data):
    return hashlib.sha256(data).hexdigest()


def require(condition, message):
    if not condition:
        raise ValueError(message)


def public_evidence():
    """Recompute the public model/observation binding, without executing private source."""
    data = {key: json.loads((ROOT / path).read_text()) for key, path in ARTIFACTS.items()}
    report, table = sokol_delivery.models()
    delivery, traces, queue = (data[key] for key in ('delivery', 'traces', 'queue'))
    require(delivery['model'] == report and traces['model'] == report, 'delivery model identity/report drift')
    require(delivery['status'] == 'shadow_conforms', 'delivery status drift')
    require(set(delivery['cases']) == set(sokol_delivery.CASES), 'delivery case coverage drift')
    require(not sokol_delivery.mismatches(delivery['cases'], table), 'delivery observations disagree')
    require(traces['status'] == 'bounded_traces_conform', 'trace status drift')
    require(traces['prefix_count'] == sum(map(len, sokol_traces.TRACES.values())), 'trace count drift')
    require(not sokol_traces.mismatches(traces['traces'], table), 'trace observations disagree')
    report, table = sokol_queue.model()
    require(queue['model'] == report, 'queue model identity/report drift')
    require(queue['status'] == 'bounded_queue_conforms', 'queue status drift')
    require(queue['prefix_count'] == sum(map(len, sokol_queue.PLANS.values())), 'queue count drift')
    require(not sokol_queue.mismatches(queue['traces'], sokol_queue.expected(table)), 'queue observations disagree')
    for key, probe in (('traces', 'sokol_trace_probe.rs'), ('queue', 'sokol_queue_probe.rs')):
        require(data[key]['source_sha256'] == delivery['source_sha256'], 'source identity drift')
        require(data[key]['probe_sha256'] == digest((ROOT / 'integration' / probe).read_bytes()),
                key + ' probe identity drift')
    return dict(delivery_cases=len(delivery['cases']), retry_prefixes=traces['prefix_count'],
                queue_prefixes=queue['prefix_count'], queue_reference_transitions=report['reference_transitions'],
                artifacts={key: digest((ROOT / path).read_bytes()) for key, path in ARTIFACTS.items()})


def preflight(warrant_root, sokol_root):
    require(warrant_root is not None and sokol_root is not None,
            'full profile requires both --warrant-root and --sokol-root; no partial fallback')
    require(shutil.which('rustc') is not None, 'full profile requires rustc on PATH')
    for name, expected in warrant_adapter.PINS.items():
        require(digest((warrant_root / 'impl' / name).read_bytes()) == expected, 'Warrant source pin mismatch: ' + name)
    frozen = json.loads((ROOT / ARTIFACTS['delivery']).read_text())
    for rel, key in (('orchestrator/src/delivery.rs', 'source_sha256'),
                     ('scripts/stargate_delivery_probe.rs', 'probe_sha256')):
        require(digest((sokol_root / rel).read_bytes()) == frozen[key], 'Sokol source pin mismatch: ' + rel)
    version = subprocess.run(['rustc', '--version'], capture_output=True, text=True, timeout=10, check=True)
    return version.stdout.strip()


def execute(name, root, expected_path):
    flag = '--warrant-root' if name == 'warrant_adapter' else '--sokol-root'
    run = subprocess.run([sys.executable, str(ROOT / 'integration' / (name + '.py')),
                          flag, str(root), '--expect-results', str(expected_path)],
                         cwd=ROOT, capture_output=True, timeout=300)
    require(run.returncode == 0, name + ' failed: ' + run.stderr.decode(errors='replace')[-3000:])
    # Independently check the bytes even if a harness accidentally ignores --expect-results.
    require(run.stdout == expected_path.read_bytes(), name + ' output differs from frozen evidence')
    return dict(result_sha256=digest(run.stdout))


def source_manifest():
    paths = {p for folder, pattern in (('src', '*.py'), ('integration', '*.py'), ('integration', '*.rs'), ('examples', '*.json'))
             for p in (ROOT / folder).rglob(pattern) if p.is_file() and '__pycache__' not in p.parts}
    return {str(path.relative_to(ROOT)): digest(path.read_bytes()) for path in sorted(paths)}


def runtime_binding():
    actual_root = Path(certificate.__file__).resolve().parent
    def inventory(folder):
        return {str(p.relative_to(folder)): digest(p.read_bytes()) for p in sorted(folder.rglob('*.py'))}
    actual = inventory(actual_root)
    require(actual == inventory(ROOT / 'src'),
            'installed Stargate differs from this checkout; reinstall with python -m pip install .')
    return digest(json.dumps(actual, sort_keys=True).encode())


def reproduce(profile, warrant_root=None, sokol_root=None):
    started = time.monotonic()
    expected = ['public_models'] + (list(FULL_STAGES) if profile == 'full' else [])
    report = dict(schema='stargate.consumer-replay.v1', authority='observation_only', profile=profile,
                  status='failed', started_utc=datetime.now(timezone.utc).isoformat(),
                  python=platform.python_version(), platform=platform.system(),
                  checker=certificate.checker_id(), expected_stages=expected, stages=[],
                  independent_participant=False, production_qualification=False)
    try:
        require(profile in ('public', 'full'), 'unknown profile')
        report['runtime_source_sha256'] = runtime_binding()
        if profile == 'full':
            report['rustc'] = preflight(warrant_root, sokol_root)
        report['source_manifest'] = source_manifest()
        for name in expected:
            mark = time.monotonic()
            stage = dict(name=name, status='failed')
            report['stages'].append(stage)
            try:
                if name == 'public_models':
                    stage['evidence'] = public_evidence()
                    require(stage['evidence'] == dict(
                        delivery_cases=len(sokol_delivery.CASES),
                        retry_prefixes=sum(map(len, sokol_traces.TRACES.values())),
                        queue_prefixes=sum(map(len, sokol_queue.PLANS.values())),
                        queue_reference_transitions=56,
                        artifacts={key: digest((ROOT / path).read_bytes()) for key, path in ARTIFACTS.items()}),
                        'public stage did not return the complete evidence inventory')
                else:
                    key = {'warrant_adapter': 'warrant', 'sokol_delivery': 'delivery',
                           'sokol_traces': 'traces', 'sokol_queue': 'queue'}[name]
                    root = warrant_root if name == 'warrant_adapter' else sokol_root
                    stage['evidence'] = execute(name, root, ROOT / ARTIFACTS[key])
                    require(stage['evidence'] == dict(result_sha256=digest((ROOT / ARTIFACTS[key]).read_bytes())),
                            name + ' did not return the expected evidence identity')
                stage['status'] = 'passed'
            finally:
                stage['elapsed_seconds'] = round(time.monotonic() - mark, 3)
        report['status'] = 'passed'
    except (ValueError, KeyError, OSError, RuntimeError, AssertionError, subprocess.SubprocessError) as error:
        report['error'] = str(error)
    report['elapsed_seconds'] = round(time.monotonic() - started, 3)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--profile', choices=('public', 'full'), required=True)
    parser.add_argument('--warrant-root', type=Path)
    parser.add_argument('--sokol-root', type=Path)
    parser.add_argument('--output', type=Path, help='new report file; existing reports are never overwritten')
    args = parser.parse_args()
    if args.output and args.output.exists():
        parser.error('refusing to overwrite an existing report')
    report = reproduce(args.profile,
                       args.warrant_root.resolve() if args.warrant_root else None,
                       args.sokol_root.resolve() if args.sokol_root else None)
    raw = json.dumps(report, sort_keys=True, indent=2) + '\n'
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with args.output.open('x') as out:
            out.write(raw)
    print(raw, end='')
    return 0 if report['status'] == 'passed' else 1


if __name__ == '__main__':
    raise SystemExit(main())
