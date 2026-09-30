"""Shadow contract pilot: model proof + actual Rust/socket observations + semantic mutants.

Run with --sokol-root PATH. No network, writes to source trees or production effects.
The source-root argument authorizes compiling that checkout; it is not untrusted evidence.
Compiler/process failure is an error, never a detected mutant. Results are deterministic;
source digests identify the exact code examined. No model/code equivalence is claimed.
"""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile

from stargate import boolean, certificate, evidence, lab, machine, projection, projection_check
from stargate.canonical import decode
from stargate.projection_runtime import ProjectionMachine

ROOT = Path(__file__).resolve().parents[1]
CASES = ('applied', 'pending', 'recorded', 'duplicate', 'refused', 'rejected',
         'retract_before', 'retract_nothing', 'retract_held', 'retract_lifted', 'retract_shortened',
         'unknown', 'blank', 'err_prefix', 'refused_prefix', 'missing_reason', 'partial', 'eof')
KNOWN = set(CASES[:11])


def models():
    packets, proofs, reports = {}, {}, {}
    for name in ('current', 'fixed'):
        raw = machine.create(json.loads((ROOT / 'examples/sokol-delivery' / (name + '.json')).read_text()))
        report, proof = evidence.produce(raw, lab.identity(raw))
        expected = 'verified_refutation' if name == 'current' else 'verified_certificate'
        if report['status'] != expected:
            raise AssertionError((name, report))
        packets[name], proofs[name] = raw, proof
        reports[name] = dict(status=report['status'], model=certificate.identity(decode(proof)['model']))
    repair = certificate.pack_repair(proofs['current'], proofs['fixed'])
    verdict, successor = certificate.verify_repair(repair, reports['current']['model'], certificate.checker_id())
    if verdict['status'] != 'verified_repair' or successor is None:
        raise AssertionError(verdict)
    reports['hand_repair'] = verdict['status']
    synth_model = None
    for strategy in ('one-edit', 'synth'):
        report, packet = evidence.repair_search(packets['current'], lab.identity(packets['current']),
                                               strategy=strategy)
        reports[strategy] = {key: report[key] for key in ('status', 'attempted', 'synthesis') if key in report}
        if packet is not None:
            checked, tip = certificate.verify_repair(packet, reports['current']['model'], certificate.checker_id())
            if checked['status'] != 'verified_repair' or tip is None:
                raise AssertionError(checked)
            if strategy == 'synth':
                synth_model = decode(tip)['model']
    report, table = projection.project(packets['fixed'], lab.identity(packets['fixed']))
    if table is None:
        raise AssertionError(report)
    checked = projection_check.check(table, proofs['fixed'], reports['fixed']['model'],
                                     certificate.checker_id(), projection_check.projection_checker_id())
    if checked['status'] != 'conforms':
        raise AssertionError(checked)
    runtime = ProjectionMachine.from_bytes(table)
    if synth_model is not None:
        names = sorted(synth_model['state'] + synth_model['events'])
        rules = {bit: boolean.program(text, names, allow_unused=True)
                 for bit, text in synth_model['next'].items()}
        rows = decode(table)['rows']
        reachable = {tuple(sorted(decode(proofs['fixed'])['model']['initial'][0].items()))}
        while True:
            expanded = reachable | {tuple(sorted(row['next'].items())) for row in rows
                                    if tuple(sorted(row['state'].items())) in reachable}
            if expanded == reachable:
                break
            reachable = expanded
        disagree = [row for row in rows if {bit: boolean.evaluate(code, dict(row['state'], **row['event']))
                                            for bit, code in rules.items()} != row['next']]
        reports['comparison'] = dict(total_rows=len(rows), unequal_rows=len(disagree),
            reachable_states=len(reachable), unequal_reachable_rows=sum(
                tuple(sorted(row['state'].items())) in reachable for row in disagree),
            independent_agent_arm=False, labor_savings_measured=False)
    return reports, runtime


def observe(source, probe):
    with tempfile.TemporaryDirectory(prefix='sg-sokol-') as tmp:
        tmp = Path(tmp)
        (tmp / 'delivery.rs').write_text(source)
        marker = '#[path = "../orchestrator/src/delivery.rs"]'
        if probe.count(marker) != 1:
            raise AssertionError('probe module binding changed')
        (tmp / 'probe.rs').write_text(probe.replace(marker, '#[path = "delivery.rs"]'))
        built = subprocess.run(['rustc', '--edition=2021', str(tmp / 'probe.rs'), '-o', str(tmp / 'probe')],
                               capture_output=True, text=True, timeout=120)
        if built.returncode:
            raise RuntimeError('Rust build failed (not a contract refusal): ' + built.stderr)
        run = subprocess.run([str(tmp / 'probe')], capture_output=True, text=True, timeout=30)
        if run.returncode:
            raise RuntimeError('Rust probe failed: ' + run.stderr)
        rows = {}
        for line in run.stdout.splitlines():
            name, pending, done, lost, error = line.split('\t')
            if name in rows or error not in ('true', 'false'):
                raise AssertionError('invalid probe output')
            rows[name] = dict(pending=int(pending), done=int(done), lost=int(lost), error=error == 'true')
        if set(rows) != set(CASES):
            raise AssertionError('probe cases incomplete')
        return rows


def mismatches(rows, table):
    failures = []
    for name in CASES:
        event = dict(known=name in KNOWN, reply=name != 'eof')
        state = table.step(dict(ack=False, queued=True, settled=False), event)
        expected = dict(pending=int(state['queued']), done=int(state['settled']), lost=0,
                        error=name not in KNOWN)
        if rows[name] != expected:
            failures.append(name)
    return failures


def run(root):
    report, table = models()
    source = (root / 'orchestrator/src/delivery.rs').read_text()
    probe = (root / 'scripts/stargate_delivery_probe.rs').read_text()
    rows = observe(source, probe)
    failures = mismatches(rows, table)
    if failures:
        raise AssertionError('actual adapter disagrees: ' + ', '.join(failures))
    mutations = {
        'consume_unknown': ('reply.and_then(|text| Outcome::parse(&text))',
                            'reply.map(|text| Outcome::parse(&text).unwrap_or(Outcome::Recorded))', 'unknown'),
        'err_prefix': ('.strip_prefix("ERR ")', '.strip_prefix("ERR")', 'err_prefix'),
        'partial_line': (" || !reply.ends_with('\\n')", '', 'partial'),
        'lose_on_error': ('                Err(e) => {',
                          '                Err(e) => {\n                    self.queue.pop_front();', 'eof'),
    }
    controls = {}
    for name, (old, new, witness) in mutations.items():
        if source.count(old) != 1:
            raise AssertionError('mutation site changed: ' + name)
        failed = mismatches(observe(source.replace(old, new), probe), table)
        if witness not in failed:
            raise AssertionError('mutant survived: ' + name)
        controls[name] = failed
    return dict(model=report, source_sha256=hashlib.sha256(source.encode()).hexdigest(),
                probe_sha256=hashlib.sha256(probe.encode()).hexdigest(), cases=rows, controls=controls,
                status='shadow_conforms', independent_demand=False)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--sokol-root', type=Path, required=True)
    parser.add_argument('--expect-results', type=Path)
    args = parser.parse_args()
    result = json.dumps(run(args.sokol_root.resolve()), sort_keys=True, indent=2) + '\n'
    if args.expect_results and args.expect_results.read_text() != result:
        raise SystemExit('results differ from the pinned experiment')
    print(result, end='')
