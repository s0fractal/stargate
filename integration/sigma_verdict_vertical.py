"""The sigma-glyph verdict vertical: a named review verdict is immutable within a round.

    python integration/sigma_verdict_vertical.py            # run, compare with results.json
    python integration/sigma_verdict_vertical.py --write    # run, rewrite results.json and specs/

Every step is an `sg` command in a fresh directory; this script only composes their
inputs and reads their reports. Expectations are pre-registered in
examples/sigma-verdict/REGISTRY.md and are not adjusted here: a disagreement is printed
and the exit status is 1.
"""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parent.parent
HERE = ROOT / 'examples' / 'sigma-verdict'
SPECS = ('buggy', 'fixed')


def sha(data):
    return hashlib.sha256(data).hexdigest()


class Run:
    def __init__(self, directory):
        self.directory = Path(directory)
        self.failures = []

    def sg(self, *args):
        result = subprocess.run([sys.executable, '-m', 'stargate', *map(str, args)],
                                cwd=self.directory, capture_output=True, text=True)
        try:
            report = json.loads(result.stdout)
        except ValueError:
            report = dict(stdout=result.stdout, stderr=result.stderr)
        return result.returncode, report

    def expect(self, label, actual, expected):
        if actual != expected:
            self.failures.append(dict(outcome=label, expected=expected, actual=actual))
        return actual

    def path(self, name):
        return self.directory / name


def rule(names, expression):
    return ''.join('fact ' + n + ': bool\n' for n in sorted(names)) + 'check ' + expression + '\n'


def spec(model, variant, world=True):
    names = model['state'] + model['events']
    rules = dict(model['monitor'], **model['variants'][variant])
    doc = dict(state=model['state'], events=model['events'], initial=model['initial'],
               invariant=rule(model['state'], model['invariant']),
               next={n: rule(names, rules[n]) for n in model['state']},
               goals=model['goals'], max_atp=model['max_atp'])
    if world:
        doc['world'] = model['world']
    return doc


def spec_texts(model):
    return {name: json.dumps(spec(model, name), indent=2, sort_keys=True) + '\n' for name in SPECS}


def run():
    model = json.loads((HERE / 'verdict.json').read_text())
    with tempfile.TemporaryDirectory() as tmp:
        r = Run(tmp)
        from stargate import certificate
        checker = certificate.checker_id()
        builds = [(v, v, True) for v in model['variants']] + [(v + '.nw', v, False) for v in ('buggy', 'C3b')]
        machines = {}
        for name, variant, world in builds:
            r.path(name + '.spec.json').write_text(json.dumps(spec(model, variant, world)))
            code, report = r.sg('machine-create', name + '.spec.json', '--output', name + '.machine')
            r.expect('machine-create ' + name, code, 0)
            machines[name] = sha(r.path(name + '.machine').read_bytes()) if code == 0 else None
        out = dict(machines=machines, checker=checker)

        def evidence(name):
            code, report = r.sg('machine-evidence', name + '.machine', '--expect-machine', machines[name],
                                '--output', name + '.proof')
            proof = json.loads(r.path(name + '.proof').read_text()) if r.path(name + '.proof').exists() else {}
            return code, report.get('check', report), proof

        def trace_of(proof):
            claim = proof.get('claim', {})
            if 'trace' not in claim:
                return None
            return [{e: step['event'][e] for e in model['events']} for step in claim['trace']['steps']]

        # 1. buggy (sigma-glyph master 40a9bff): refuted in two steps.
        code, report, proof = evidence('buggy')
        out['buggy'] = dict(exit=code, status=report.get('status'), claim=proof.get('claim', {}).get('kind'),
                            trace=trace_of(proof), endpoint=report.get('endpoint'))
        r.expect('buggy refuted', (code, out['buggy']['status']), (4, 'verified_refutation'))
        r.expect('buggy trace is 2 steps', len(out['buggy']['trace'] or []), 2)
        # 2. fixed: certified, 3 reachable states, both goals reachable in one step.
        code, report, proof = evidence('fixed')
        out['fixed'] = dict(exit=code, status=report.get('status'), states=len(proof.get('states', [])),
                            goal_witnesses=[len(w['steps']) if isinstance(w, dict) and 'steps' in w else w
                                            for w in proof.get('goal_witnesses', [])])
        r.expect('fixed certifies', (code, out['fixed']['status']), (0, 'verified_certificate'))
        r.expect('fixed has 3 reachable states', out['fixed']['states'], 3)
        # 3. controls as models.
        predicted = dict(C1='verified_refutation', C2='verified_refutation', C3='goal_unreachable',
                         C3b='verified_certificate')
        out['controls'] = {}
        for name, status in predicted.items():
            code, report, proof = evidence(name)
            out['controls'][name] = dict(exit=code, status=report.get('status'),
                                         unreached_goals=len(report.get('unreached_goals', [])) or None)
            r.expect('control ' + name, out['controls'][name]['status'], status)
        # 4. fixed as a hand repair of buggy.
        parent = certificate.identity(json.loads(r.path('buggy.proof').read_text())['model'])

        def repair(parent_name, candidate_name, parent_model):
            code, report = r.sg('certificate-repair-pack', parent_name + '.proof', candidate_name + '.proof',
                                '--output', candidate_name + '.repair')
            if code != 0:
                return dict(stage='pack', exit=code, status=report.get('status'), error=report.get('error'))
            code, report = r.sg('certificate-repair-check', candidate_name + '.repair', '--expect-model',
                                parent_model, '--expect-checker', checker)
            return dict(stage='check', exit=code, status=report.get('status'),
                        error=report.get('error') or report.get('reason'))

        out['hand-repair'] = repair('buggy', 'fixed', parent)
        r.expect('fixed repairs buggy', out['hand-repair']['status'], 'verified_repair')
        # 5. C3b as a repair: refused with the boundary, accepted without it.
        evidence('buggy.nw'); evidence('C3b.nw')
        out['C3b-repair'] = dict(
            boundary=repair('buggy', 'C3b', parent),
            no_boundary=repair('buggy.nw', 'C3b.nw',
                               certificate.identity(json.loads(r.path('buggy.nw.proof').read_text())['model'])))
        r.expect('C3b refused as a repair with the boundary',
                 'repair alters world rule' in str(out['C3b-repair']['boundary'].get('error')), True)
        r.expect('C3b accepted as a repair without the boundary',
                 out['C3b-repair']['no_boundary']['status'], 'verified_repair')
        # 6. repair-search on buggy: no repair, no candidate on a monitor rule.
        parent_rules = json.loads(r.path('buggy.machine').read_text())['next']
        for strategy in ('one-edit', 'trace'):
            code, report = r.sg('repair-search', 'buggy.machine', '--expect-machine', machines['buggy'],
                                '--max-candidates', 256, '--strategy', strategy, '--output', strategy + '.repair')
            entry = dict(exit=code, status=report.get('status'), attempted=report.get('attempted'))
            if report.get('status') == 'found':
                candidate = json.loads(r.path(strategy + '.repair').read_text())['candidate']['model']['next']
                entry['edited'] = sorted(n for n in candidate if candidate[n] != parent_rules[n])
            out['search-' + strategy] = entry
            r.expect('search ' + strategy + ' finds no repair', entry['status'] in
                     ('neighborhood_exhausted', 'candidate_limit'), True)
            r.expect('search ' + strategy + ' edits no monitor rule',
                     [n for n in entry.get('edited', []) if n in model['world']], [])
        return out, r.failures


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('--write', action='store_true')
    arguments = parser.parse_args(argv)
    out, failures = run()
    results = HERE / 'results.json'
    text = json.dumps(out, indent=2, sort_keys=True) + '\n'
    specs = spec_texts(json.loads((HERE / 'verdict.json').read_text()))
    if arguments.write:
        results.write_text(text)
        (HERE / 'specs').mkdir(exist_ok=True)
        for name, body in specs.items():
            (HERE / 'specs' / (name + '.json')).write_text(body)
    else:
        if not results.exists() or results.read_text() != text:
            failures.append(dict(outcome='results.json is current', expected='committed bytes', actual='differs'))
        for name, body in specs.items():
            path = HERE / 'specs' / (name + '.json')
            if not path.exists() or path.read_text() != body:
                failures.append(dict(outcome='specs/' + name + '.json is current', expected='committed bytes',
                                     actual='differs'))
    print(text, end='')
    for failure in failures:
        print('MISMATCH', json.dumps(failure, sort_keys=True), file=sys.stderr)
    return 1 if failures else 0


if __name__ == '__main__':
    sys.exit(main())
