"""The interlock shadow experiment, from a clean checkout (PR-10-shadow).

    python integration/interlock_shadow.py            # run, compare with results.json
    python integration/interlock_shadow.py --write    # run, rewrite results.json

Every step is an `sg` command in a fresh directory. Expectations are pre-registered in
examples/interlock/REGISTRY.md and are not adjusted here: a disagreement is printed and
the exit status is 1. Nothing from bagowix/interlock is read or vendored; see
examples/interlock/upstream.json for the identities that motivated the models.
"""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parent.parent
HERE = ROOT / 'examples' / 'interlock'
MODELS = {'too-weak': 'lifecycle-too-weak.json', 'lifecycle': 'lifecycle.json'}
MUTATIONS = ('bad-round-closes', 'trip-ignored', 'open-skips-half-open', 'half-open-stuck')
# Registered outcomes 1-4: (status, reachable states or claim kind, trace length or None).
EXPECTED = {
    ('too-weak', None): ('verified_certificate', 3),
    ('too-weak', 'bad-round-closes'): ('verified_certificate',),
    ('too-weak', 'trip-ignored'): ('verified_certificate',),
    ('too-weak', 'open-skips-half-open'): ('verified_certificate',),
    ('too-weak', 'half-open-stuck'): ('verified_refutation', 'trap'),
    ('lifecycle', None): ('verified_certificate', 5),
    ('lifecycle', 'bad-round-closes'): ('verified_refutation', 'unsafe', 3),
    ('lifecycle', 'trip-ignored'): ('verified_refutation', 'unsafe', 1),
    ('lifecycle', 'open-skips-half-open'): ('verified_refutation', 'unsafe', 2),
    ('lifecycle', 'half-open-stuck'): ('verified_refutation', 'trap'),
}


def rule(names, expression):
    return ''.join('fact ' + n + ': bool\n' for n in sorted(names)) + 'check ' + expression + '\n'


def spec(model, overrides=None):
    names = model['state'] + model['events']
    rules = dict(model['next'], **(overrides or {}))
    return dict(state=model['state'], events=model['events'], initial=model['initial'],
                invariant=rule(model['state'], model['invariant']),
                next={n: rule(names, rules[n]) for n in model['state']},
                goals=model['goals'], live_goals=model['live_goals'], max_atp=model['max_atp'])


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('--write', action='store_true')
    arguments = parser.parse_args(argv)
    failures, out = [], {}
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)

        def sg(*args):
            result = subprocess.run([sys.executable, '-m', 'stargate', *map(str, args)], cwd=tmp,
                                    capture_output=True, text=True)
            try:
                return result.returncode, json.loads(result.stdout)
            except ValueError:
                return result.returncode, dict(stdout=result.stdout, stderr=result.stderr)

        def expect(label, actual, expected):
            if actual != expected:
                failures.append(dict(outcome=label, expected=expected, actual=actual))

        for kind, filename in MODELS.items():
            model = json.loads((HERE / filename).read_text())
            for mutation in (None,) + MUTATIONS:
                overrides = (json.loads((HERE / 'mutations' / (mutation + '.json')).read_text())['overrides']
                             if mutation else None)
                name = kind + '.' + (mutation or 'as-is')
                (tmp / (name + '.spec.json')).write_text(json.dumps(spec(model, overrides)))
                sg('machine-create', name + '.spec.json', '--output', name + '.machine')
                machine_id = hashlib.sha256((tmp / (name + '.machine')).read_bytes()).hexdigest()
                code, report = sg('machine-evidence', name + '.machine', '--expect-machine', machine_id,
                                  '--output', name + '.proof')
                proof = json.loads((tmp / (name + '.proof')).read_text()) if (tmp / (name + '.proof')).exists() else {}
                status = report.get('check', report).get('status')
                if status == 'verified_certificate':
                    measured = (status, len(proof['states']))
                else:
                    claim = proof.get('claim', {})
                    steps = len(claim.get('trace', {}).get('steps', [])) if claim.get('kind') == 'unsafe' else None
                    measured = (status, claim.get('kind')) + ((steps,) if steps is not None else ())
                expected = EXPECTED[(kind, mutation)]
                # A registered certificate for a mutant names no state count; compare only what was registered.
                expect(name, list(measured[:len(expected)]), list(expected))
                out[name] = dict(exit=code, machine=machine_id, measured=list(measured))
        # Outcomes 5-6: the 4-bit model's projection, checked, then one flipped cell.
        code, report = sg('model-project', 'lifecycle.as-is.machine', '--expect-machine', out['lifecycle.as-is']['machine'],
                          '--output', 'projection.json')
        model_id = report.get('model')
        _, checker = sg('certificate-checker')
        _, pchecker = sg('projection-checker')
        code, check = sg('projection-check', 'projection.json', 'lifecycle.as-is.proof', '--expect-model', model_id,
                         '--expect-checker', checker['checker'], '--expect-projection-checker', pchecker['projection_checker'])
        expect('projection rows', report.get('rows'), 64)
        expect('projection conforms', (code, check.get('status')), (0, 'conforms'))
        table = json.loads((tmp / 'projection.json').read_text())
        table['rows'][37]['next']['open'] = not table['rows'][37]['next']['open']
        from stargate.canonical import canon
        (tmp / 'flipped.json').write_bytes(canon(table))
        code, flipped = sg('projection-check', 'flipped.json', 'lifecycle.as-is.proof', '--expect-model', model_id,
                           '--expect-checker', checker['checker'], '--expect-projection-checker', pchecker['projection_checker'])
        expect('flipped cell is a mismatch', (code, flipped.get('status')), (4, 'mismatch'))
        from stargate import projection_runtime
        row = table['rows'][37]
        expect('the runtime executes the flipped cell',
               projection_runtime.ProjectionMachine.from_bytes(canon(table)).step(row['state'], row['event']), row['next'])
        out['projection'] = dict(rows=report.get('rows'), model=model_id, projection=report.get('projection_id'),
                                 conforms=check.get('status'), flipped=flipped.get('status'))
    out['upstream'] = json.loads((HERE / 'upstream.json').read_text())
    text = json.dumps(out, indent=2, sort_keys=True) + '\n'
    results = HERE / 'results.json'
    if arguments.write:
        results.write_text(text)
    elif not results.exists() or results.read_text() != text:
        failures.append(dict(outcome='results.json is current', expected='committed bytes', actual='differs'))
    for failure in failures:
        print('MISMATCH', json.dumps(failure, sort_keys=True), file=sys.stderr)
    print(json.dumps({k: v.get('measured', v.get('conforms')) for k, v in out.items() if k != 'upstream'}, indent=1))
    return 1 if failures else 0


if __name__ == '__main__':
    sys.exit(main())
