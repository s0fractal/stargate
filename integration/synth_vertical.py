"""Safety synthesis on the two live verticals (PR-85, docs/SYNTH_REGISTRY.md).

    python integration/synth_vertical.py            # run, compare with docs/synth-results.json
    python integration/synth_vertical.py --write    # run, rewrite docs/synth-results.json

Each case is `sg repair-search --strategy synth` in a fresh directory, over the committed
spec of the refuted parent with its world declared. Expectations are the registered hand
predictions and are not adjusted here: a disagreement is printed and the exit status is 1.
"""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parent.parent
RESULTS = ROOT / 'docs' / 'synth-results.json'
CASES = {
    'sigma': dict(spec=ROOT / 'examples' / 'sigma-verdict' / 'specs' / 'buggy.json', world=None,
                  expect=dict(winning_states=6, changed_rows=6, changed_owned_rules=['named', 'reject'],
                              total_owned_hamming_delta=8, final_checker_status='verified_repair'),
                  status='found'),
    'warrant': dict(spec=ROOT / 'examples' / 'mcp-proxy' / 'specs' / 'current.json',
                    world=['calls.one', 'calls.two'],
                    expect=dict(winning_states=9, changed_rows=1, changed_owned_rules=['ambiguous'],
                                total_owned_hamming_delta=1, final_checker_status='verified_refutation',
                                candidate_claim='trap'),
                    status='not_certified'),
}
MEASURED = ('winning_states', 'changed_rows', 'changed_owned_rules', 'total_owned_hamming_delta',
            'emitted_rule_bytes', 'final_checker_status', 'candidate_claim')


def run():
    failures, out = [], {}
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        for name, case in CASES.items():
            spec = json.loads(case['spec'].read_text())
            if case['world'] is not None:
                spec['world'] = case['world']
            (tmp / (name + '.spec.json')).write_text(json.dumps(spec))
            sg = lambda *a: subprocess.run([sys.executable, '-m', 'stargate', *map(str, a)], cwd=tmp,
                                           capture_output=True, text=True)
            created = sg('machine-create', name + '.spec.json', '--output', name + '.machine')
            if created.returncode != 0:
                failures.append(dict(case=name, outcome='machine-create', actual=created.stderr[-300:]))
                continue
            digest = hashlib.sha256((tmp / (name + '.machine')).read_bytes()).hexdigest()
            result = sg('repair-search', name + '.machine', '--expect-machine', digest, '--strategy', 'synth',
                        '--output', name + '.repair')
            try:
                report = json.loads(result.stdout)
            except ValueError:
                failures.append(dict(case=name, outcome='report', actual=(result.stdout + result.stderr)[-500:]))
                continue
            synthesis = report.get('synthesis', {})
            entry = dict(exit=result.returncode, status=report.get('status'), reason=report.get('reason'),
                         parent=report.get('parent', {}).get('status'),
                         **{k: synthesis.get(k) for k in MEASURED})
            if (tmp / (name + '.repair')).exists():
                packet = json.loads((tmp / (name + '.repair')).read_text())
                parent_next, candidate = spec['next'], packet['candidate']['model']['next']
                entry['world_bytes_unchanged'] = all(candidate[w] == parent_next[w]
                                                     for w in spec.get('world', []))
                entry['candidate_rules'] = {n: candidate[n] for n in sorted(candidate) if candidate[n] != parent_next[n]}
            out[name] = entry
            if entry['status'] != case['status']:
                failures.append(dict(case=name, outcome='status', expected=case['status'], actual=entry['status']))
            for key, value in case['expect'].items():
                if entry.get(key) != value:
                    failures.append(dict(case=name, outcome=key, expected=value, actual=entry.get(key)))
    return out, failures


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('--write', action='store_true')
    arguments = parser.parse_args(argv)
    out, failures = run()
    text = json.dumps(out, indent=2, sort_keys=True) + '\n'
    if arguments.write:
        RESULTS.write_text(text)
    elif not RESULTS.exists() or RESULTS.read_text() != text:
        failures.append(dict(outcome='docs/synth-results.json is current', expected='committed bytes', actual='differs'))
    print(text, end='')
    for failure in failures:
        print('MISMATCH', json.dumps(failure, sort_keys=True), file=sys.stderr)
    return 1 if failures else 0


if __name__ == '__main__':
    sys.exit(main())
