"""The MCP sealing proxy vertical, end to end, from a clean checkout.

    python integration/mcp_proxy_vertical.py                    # run, compare with results.json
    python integration/mcp_proxy_vertical.py --write            # run, rewrite results.json and specs/
    python integration/mcp_proxy_vertical.py --vendor DIR       # also write the chosen table for warrant

Every step is an `sg` command in a fresh directory; this script only composes their
inputs and reads their reports. Expectations are pre-registered in
examples/mcp-proxy/REGISTRY.md and are not adjusted here: a disagreement is printed and
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
HERE = ROOT / 'examples' / 'mcp-proxy'
CALL, RESPONSE, REQUEST, END = (True, False), (False, True), (False, False), (True, True)
# Registration outcome 6: the successor warrant runs. This constant was typed before
# the first run; the measured search result is what justifies it — both strategies
# repair the model by editing `calls.one`, the server's side, which a proxy cannot
# implement. See examples/mcp-proxy/RESULTS.md.
CHOSEN = 'fixed'


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


def spec(model, variant):
    names = model['state'] + model['events']
    rules = dict(model['world'], **model['variants'][variant])
    return dict(state=model['state'], events=model['events'], initial=model['initial'],
                invariant=rule(model['state'], model['invariant']),
                next={n: rule(names, rules[n]) for n in model['state']},
                goals=model['goals'], live_goals=model['live_goals'], max_atp=model['max_atp'])


def events_of(trace, names):
    return [tuple(step['event'][n] for n in names) for step in trace['steps']]


SPECS = ('current', 'historic', 'fixed')    # what README.md's walkthrough feeds to sg machine-create


def spec_texts(model):
    return {name: json.dumps(spec(model, name), indent=2, sort_keys=True) + '\n' for name in SPECS}


def run(vendor=None):
    model = json.loads((HERE / 'proxy.json').read_text())
    with tempfile.TemporaryDirectory() as tmp:
        r = Run(tmp)
        from stargate import certificate
        checker = certificate.checker_id()
        machines = {}
        for variant in model['variants']:
            r.path(variant + '.spec.json').write_text(json.dumps(spec(model, variant)))
            code, _ = r.sg('machine-create', variant + '.spec.json', '--output', variant + '.machine')
            r.expect('machine-create ' + variant, code, 0)
            machines[variant] = sha(r.path(variant + '.machine').read_bytes())
        out = dict(machines=machines, checker=checker)

        def evidence(variant):
            return r.sg('machine-evidence', variant + '.machine', '--expect-machine', machines[variant],
                        '--output', variant + '.proof')

        # 1-2. current and historic are refuted for safety, with the registered traces.
        for variant, second, endpoint in (
                ('current', CALL, {'ambiguous': False, 'calls.one': True, 'calls.two': True, 'pending': True}),
                ('historic', REQUEST, {'ambiguous': False, 'calls.one': True, 'calls.two': False, 'pending': False})):
            code, report = evidence(variant)
            claim = json.loads(r.path(variant + '.proof').read_text())['claim'] if code == 4 else {}
            out[variant] = dict(status=report.get('check', report).get('status'), exit=code,
                                claim=claim.get('kind'),
                                trace=[list(e) for e in events_of(claim['trace'], model['events'])] if claim else None,
                                endpoint=report.get('check', {}).get('endpoint'))
            r.expect(variant + ' refuted', (code, out[variant]['status'], claim.get('kind')), (4, 'verified_refutation', 'unsafe'))
            r.expect(variant + ' trace', out[variant]['trace'], [list(CALL), list(second)])
            r.expect(variant + ' endpoint', out[variant]['endpoint'], endpoint)
        # 3. the naive fix is the same model as today's code.
        r.expect('naive-fix is model-identical to current', machines['naive-fix'], machines['current'])
        # 4. the hand-written fix certifies with idle live.
        code, report = evidence('fixed')
        cert = json.loads(r.path('fixed.proof').read_text()) if code == 0 else {}
        out['fixed'] = dict(status=report.get('check', report).get('status'), exit=code,
                            states=len(cert.get('states', [])), live_ranks=len(cert.get('ranks', [])))
        r.expect('fixed certifies', (code, out['fixed']['status']), (0, 'verified_certificate'))
        r.expect('fixed states', out['fixed']['states'], 5)
        r.expect('fixed idle is live', out['fixed']['live_ranks'], 1)
        # 5. repair search on current (measured), and the hand repair checked against the refutation.
        parent_model = certificate.identity(certificate.model_from_machine(
            json.loads(r.path('current.machine').read_text())))
        parent_next = json.loads(r.path('current.machine').read_text())['next']
        successors = {}
        for strategy in ('one-edit', 'trace'):
            code, report = r.sg('repair-search', 'current.machine', '--expect-machine', machines['current'],
                                '--max-candidates', 256, '--strategy', strategy, '--output', strategy + '.repair')
            entry = dict(status=report.get('status'), attempted=report.get('attempted'), exit=code)
            if report.get('status') == 'found':
                packet = json.loads(r.path(strategy + '.repair').read_text())
                candidate = packet['candidate']['model']['next']
                entry['edited'] = sorted(n for n in candidate if candidate[n] != parent_next[n])
                entry['edit'] = {n: candidate[n].split('check ', 1)[1].strip() for n in entry['edited']}
                code, check = r.sg('certificate-repair-check', strategy + '.repair', '--expect-model', parent_model,
                                   '--expect-checker', checker, '--output', strategy + '.successor')
                entry['repair_check'] = check.get('status')
                r.expect('search ' + strategy + ' repair checks', (code, check.get('status')), (0, 'verified_repair'))
                successors['search-' + strategy] = candidate
            out['search-' + strategy] = entry
        code, _ = r.sg('certificate-repair-pack', 'current.proof', 'fixed.proof', '--output', 'hand.repair')
        r.expect('hand repair packs', code, 0)
        code, check = r.sg('certificate-repair-check', 'hand.repair', '--expect-model', parent_model,
                           '--expect-checker', checker, '--output', 'hand.successor')
        out['hand-repair'] = check.get('status')
        r.expect('hand repair checks', (code, check.get('status')), (0, 'verified_repair'))
        successors['fixed'] = json.loads(r.path('fixed.machine').read_text())['next']
        # 6. every certified successor: machine, certificate, projection, projection-check.
        base = json.loads(r.path('current.machine').read_text())
        out['successors'] = {}
        for name, rules in sorted(successors.items()):
            doc = dict(base, next=rules)
            from stargate import machine as machine_module
            raw = machine_module.create({k: doc[k] for k in ('state', 'events', 'initial', 'next', 'invariant',
                                                              'max_atp', 'goals', 'live_goals')})
            r.path(name + '.succ.machine').write_bytes(raw)
            mid = sha(raw)
            code, _ = r.sg('machine-evidence', name + '.succ.machine', '--expect-machine', mid, '--output', name + '.succ.cert')
            r.expect(name + ' successor certifies', code, 0)
            code, report = r.sg('model-project', name + '.succ.machine', '--expect-machine', mid, '--output', name + '.projection.json')
            model_id = report.get('model')
            r.expect(name + ' projection rows', (code, report.get('rows')), (0, 64))
            code, pid = r.sg('projection-checker')
            code, check = r.sg('projection-check', name + '.projection.json', name + '.succ.cert', '--expect-model', model_id,
                               '--expect-checker', checker, '--expect-projection-checker', pid['projection_checker'])
            r.expect(name + ' conforms', (code, check.get('status')), (0, 'conforms'))
            out['successors'][name] = dict(machine=mid, model=model_id, projection=report.get('projection_id'),
                                           conforms=check.get('status'))
        # 7. flip one cell of the chosen projection: the verifier refuses it, the runtime runs it.
        chosen = r.path(CHOSEN + '.projection.json').read_bytes()
        from stargate.canonical import canon, decode
        flipped = decode(chosen); flipped['rows'][9]['next']['pending'] = not flipped['rows'][9]['next']['pending']
        r.path('flipped.json').write_bytes(canon(flipped))
        code, check = r.sg('projection-check', 'flipped.json', CHOSEN + '.succ.cert', '--expect-model',
                           out['successors'][CHOSEN]['model'], '--expect-checker', checker,
                           '--expect-projection-checker', pid['projection_checker'])
        r.expect('flipped cell is a mismatch', (code, check.get('status')), (4, 'mismatch'))
        from stargate import projection_runtime
        row = flipped['rows'][9]
        r.expect('the runtime executes the flipped cell',
                 projection_runtime.ProjectionMachine.from_bytes(canon(flipped)).step(row['state'], row['event']), row['next'])
        code, manifest = r.sg('projection-materialize', CHOSEN + '.projection.json', '--lang', 'python', '--output', 'app')
        r.expect('materialize', code, 0)
        out['chosen'] = dict(successor=CHOSEN, projection=manifest.get('projection'),
                             runtime_digest=manifest.get('runtime_digest'), model=manifest.get('model'))
        if vendor is not None:
            vendor = Path(vendor); vendor.mkdir(parents=True, exist_ok=False)
            for name in ('projection.json', 'runtime.py'):
                (vendor / name).write_bytes((r.directory / 'app' / name).read_bytes())
        return out, r.failures


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('--write', action='store_true')
    parser.add_argument('--vendor', type=Path)
    arguments = parser.parse_args(argv)
    out, failures = run(arguments.vendor)
    results = HERE / 'results.json'
    text = json.dumps(out, indent=2, sort_keys=True) + '\n'
    specs = spec_texts(json.loads((HERE / 'proxy.json').read_text()))
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
                failures.append(dict(outcome='specs/' + name + '.json is current', expected='committed bytes', actual='differs'))
    print(text, end='')
    for failure in failures:
        print('MISMATCH', json.dumps(failure, sort_keys=True), file=sys.stderr)
    return 1 if failures else 0


if __name__ == '__main__':
    sys.exit(main())
