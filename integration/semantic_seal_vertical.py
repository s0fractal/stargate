"""The black-heart semantic-seal vertical: an authenticated semantic counterexample seals
re-admission of its (candidate, evaluator, requirement).

    python integration/semantic_seal_vertical.py            # run, compare with results.json
    python integration/semantic_seal_vertical.py --write    # run, rewrite results.json and specs/

Every step is an `sg` command in a fresh directory; this script only composes their
inputs and reads their reports. Expectations are pre-registered in
examples/semantic-seal/REGISTRY.md and are not adjusted here: a disagreement is printed and
the exit status is 1.
"""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parent.parent
HERE = ROOT / 'examples' / 'semantic-seal'
SPECS = ('buggy', 'fixed')


def sha(data):
    return hashlib.sha256(data).hexdigest()


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


class Run:
    def __init__(self, directory):
        self.directory = Path(directory)
        self.failures = []

    def sg(self, *args):
        result = subprocess.run([sys.executable, '-m', 'stargate', *map(str, args)],
                                cwd=self.directory, capture_output=True, text=True)
        for stream in (result.stdout, result.stderr):   # refusals are reported on stderr
            try:
                return result.returncode, json.loads(stream)
            except ValueError:
                pass
        return result.returncode, dict(stdout=result.stdout[-300:], stderr=result.stderr[-300:])

    def expect(self, label, actual, expected):
        if actual != expected:
            self.failures.append(dict(outcome=label, expected=expected, actual=actual))

    def path(self, name):
        return self.directory / name


def run():
    model = json.loads((HERE / 'seal.json').read_text())
    with tempfile.TemporaryDirectory() as tmp:
        r = Run(tmp)
        from stargate import certificate
        checker = certificate.checker_id()
        machines = {}
        builds = [(v, v, True) for v in model['variants']] + [('C1', 'buggy', False)]
        for name, variant, world in builds:
            r.path(name + '.spec.json').write_text(json.dumps(spec(model, variant, world)))
            code, _ = r.sg('machine-create', name + '.spec.json', '--output', name + '.machine')
            r.expect('machine-create ' + name, code, 0)
            machines[name] = sha(r.path(name + '.machine').read_bytes()) if code == 0 else None
        out = dict(machines=machines, checker=checker)

        def evidence(name):
            code, report = r.sg('machine-evidence', name + '.machine', '--expect-machine', machines[name],
                                '--output', name + '.proof')
            proof = json.loads(r.path(name + '.proof').read_text()) if r.path(name + '.proof').exists() else {}
            return code, report.get('check', report), proof

        # 1. buggy (black-heart 3893fad): unsafe in two steps from I1.
        code, report, proof = evidence('buggy')
        claim = proof.get('claim', {})
        trace = claim.get('trace', {})
        out['buggy'] = dict(exit=code, status=report.get('status'), claim=claim.get('kind'),
                            initial=trace.get('initial'),
                            trace=[{e: step['event'][e] for e in model['events']} for step in trace.get('steps', [])])
        r.expect('buggy refuted unsafe', (out['buggy']['status'], out['buggy']['claim']), ('verified_refutation', 'unsafe'))
        r.expect('buggy: 2 steps', len(out['buggy']['trace']), 2)
        r.expect('buggy: from I1', out['buggy']['initial'], model['initial'][1])
        # 2. fixed: certified, 5 states, both goals.
        code, report, proof = evidence('fixed')
        out['fixed'] = dict(exit=code, status=report.get('status'), states=len(proof.get('states', [])),
                            goals=report.get('goals'))
        r.expect('fixed certifies', (out['fixed']['status'], out['fixed']['states'], out['fixed']['goals']),
                 ('verified_certificate', 5, 2))
        # 3. fixed as a hand repair of buggy.
        parent = certificate.identity(json.loads(r.path('buggy.proof').read_text())['model'])

        def repair(parent_name, candidate_name):
            code, report = r.sg('certificate-repair-pack', parent_name + '.proof', candidate_name + '.proof',
                                '--output', candidate_name + '.repair')
            if code != 0:
                return dict(stage='pack', exit=code, status=report.get('status'), error=report.get('error'))
            code, report = r.sg('certificate-repair-check', candidate_name + '.repair', '--expect-model', parent,
                                '--expect-checker', checker)
            return dict(stage='check', exit=code, status=report.get('status'), error=report.get('error'))

        out['hand-repair'] = repair('buggy', 'fixed')
        r.expect('fixed repairs buggy', out['hand-repair']['status'], 'verified_repair')
        # 4-5. repair-search: one-edit and trace find nothing; synth finds the guard.
        parent_rules = json.loads(r.path('buggy.machine').read_text())['next']
        for strategy in ('one-edit', 'trace', 'synth'):
            code, report = r.sg('repair-search', 'buggy.machine', '--expect-machine', machines['buggy'],
                                '--max-candidates', 256, '--strategy', strategy, '--output', strategy + '.repair')
            entry = dict(exit=code, status=report.get('status'), attempted=report.get('attempted'))
            if strategy == 'synth':
                entry.update({k: report.get('synthesis', {}).get(k) for k in (
                    'winning_states', 'changed_rows', 'changed_owned_rules', 'total_owned_hamming_delta',
                    'emitted_rule_bytes', 'final_checker_status')})
            if r.path(strategy + '.repair').exists():
                candidate = json.loads(r.path(strategy + '.repair').read_text())['candidate']['model']['next']
                entry['edited'] = sorted(n for n in candidate if candidate[n] != parent_rules[n])
                if strategy == 'synth':
                    entry['admitted_rule'] = candidate['admitted']
            out['search-' + strategy] = entry
            r.expect('search ' + strategy + ' edits no monitor rule',
                     [n for n in entry.get('edited', []) if n in model['world']], [])
        for strategy in ('one-edit', 'trace'):
            r.expect('search ' + strategy + ': no repair', out['search-' + strategy]['status'] != 'found', True)
        s = out['search-synth']
        r.expect('synth', (s['status'], s['winning_states'], s['changed_rows'], s['changed_owned_rules'],
                           s['total_owned_hamming_delta'], s['final_checker_status']),
                 ('found', 6, 2, ['admitted'], 2, 'verified_repair'))
        # Controls.
        code, report = r.sg('repair-search', 'C1.machine', '--expect-machine', machines['C1'], '--strategy', 'synth')
        out['C1'] = dict(exit=code, status=report.get('status'))
        r.expect('C1 not applicable', out['C1']['status'], 'not_applicable')
        for name, goal in (('C2', model['goals'][1]), ('C3', model['goals'][0])):
            code, report, proof = evidence(name)
            claim = proof.get('claim', {})
            out[name] = dict(exit=code, status=report.get('status'), claim=claim.get('kind'), goal=claim.get('goal'))
            r.expect(name + ' unreachable goal', (out[name]['status'], out[name]['claim'], out[name]['goal']),
                     ('verified_refutation', 'unreachable_goal', goal))
        out['C2']['as_repair'] = repair('buggy', 'C2')
        r.expect('C2 not packable as a repair', out['C2']['as_repair']['stage'], 'pack')
        return out, r.failures


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('--write', action='store_true')
    arguments = parser.parse_args(argv)
    out, failures = run()
    results = HERE / 'results.json'
    text = json.dumps(out, indent=2, sort_keys=True) + '\n'
    specs = spec_texts(json.loads((HERE / 'seal.json').read_text()))
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
