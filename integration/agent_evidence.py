"""Agent task: refute stale eligibility, verify an owned repair, retain replay data.

Synthetic model exercise; does not check GitHub, grant authority or publish code.
"""
import argparse
import json
from pathlib import Path

from stargate import certificate, evidence, lab, machine
from stargate.canonical import decode

ROOT = Path(__file__).resolve().parents[1]
CHECKER = 'd425682ebb142a03021c13de63c8443dfd06c07f68ab1624a63df858e50b43fa'


def require(condition, message):
    if not condition:
        raise ValueError(message)


def run():
    artifacts, models, reports, proofs = {}, {}, {}, {}
    require(certificate.checker_id() == CHECKER, 'checker differs from the selected anchor')
    for name, expected in [('stale', 'verified_refutation'), ('fixed', 'verified_certificate')]:
        spec = json.loads((ROOT / 'examples/agent-evidence' / (name + '.json')).read_text())
        raw = machine.create(spec)
        model_id = certificate.identity(certificate.model_from_machine(decode(raw)))
        report, proof = evidence.produce(raw, lab.identity(raw))
        require(report['status'] == expected and proof is not None, name + ': incomplete or unexpected evidence')
        checked = evidence.verify(proof, model_id, CHECKER)
        require(checked['status'] == expected, name + ': recipient replay failed')
        artifacts[name + '.machine'] = raw
        artifacts[name + '.proof'] = proof
        models[name], reports[name], proofs[name] = model_id, checked, proof
    repair = certificate.pack_repair(proofs['stale'], proofs['fixed'])
    checked, successor = certificate.verify_repair(repair, models['stale'], CHECKER)
    require(checked['status'] == 'verified_repair' and successor is not None, 'repair not verified')
    artifacts['repair.json'], artifacts['successor.json'] = repair, successor

    # A valid packet for another model cannot serve as the current model's evidence.
    try:
        evidence.verify(proofs['fixed'], models['stale'], CHECKER)
    except ValueError:
        pass
    else:
        raise ValueError('wrong model anchor accepted')
    limited, unpublished = certificate.verify_repair(repair, models['stale'], CHECKER, max_steps=0)
    require(limited['status'] != 'verified_repair' and unpublished is None, 'incomplete repair exposed a successor')

    # A producer must not repair the environment by making verification permanently fresh.
    spec = json.loads((ROOT / 'examples/agent-evidence/fixed.json').read_text())
    spec['next']['fresh'] = spec['next']['fresh'].split('check ')[0] + 'check true\n'
    raw = machine.create(spec)
    produced, proof = evidence.produce(raw, lab.identity(raw))
    require(produced['status'] == 'verified_certificate' and proof is not None, 'world control did not certify')
    invalid_repair = certificate.pack_repair(proofs['stale'], proof)
    try:
        certificate.verify_repair(invalid_repair, models['stale'], CHECKER)
    except ValueError as error:
        require('world rule' in str(error), 'world control refused for an unrelated reason')
    else:
        raise ValueError('world-changing repair accepted')
    report = dict(status='passed', scope='synthetic_agent_workflow', authority='observation_only',
                  checker=CHECKER, models=models, checks=reports, repair=checked,
                  controls=dict(wrong_model='rejected', incomplete_successor='withheld', world_change='rejected'),
                  counterexample=decode(proofs['stale'])['claim'])
    return report, artifacts


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, help='new directory for portable evidence; never overwrite')
    args = parser.parse_args()
    if args.output and args.output.exists():
        parser.error('output directory already exists')
    report, artifacts = run()
    text = json.dumps(report, indent=2, sort_keys=True) + '\n'
    if args.output:
        args.output.mkdir(parents=True, exist_ok=False)
        for name, raw in artifacts.items():
            with (args.output / name).open('xb') as target:
                target.write(raw)
        with (args.output / 'report.json').open('x') as target:
            target.write(text)
    print(text, end='')


if __name__ == '__main__':
    main()
