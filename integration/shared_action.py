"""Two selected contracts over the same resource-release candidate.

Synthetic, serialized model experiment. Does not release a real resource or grant
execution authority. Uses the existing proof checker, without a new proof format.
"""
import argparse
import hashlib
import json
from pathlib import Path
import shutil

from stargate import certificate, evidence, lab, machine
from stargate.canonical import decode, exact, record_hash

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT/'examples/shared-action'
ROLES = ('custodian', 'reclaimer')


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def document(raw):
    def unique(pairs):
        result = {}
        for name, value in pairs:
            if name in result:
                raise ValueError('duplicate field: ' + name)
            result[name] = value
        return result
    if not isinstance(raw, bytes) or len(raw) > certificate.MAX_BYTES:
        raise ValueError('input exceeds 1 MiB or is not bytes')
    return json.loads(raw, object_pairs_hook=unique)


def materialize(world, candidate, contract):
    shared, proposal, policy = map(document, (world, candidate, contract))
    exact(shared, ('state', 'events', 'initial', 'world', 'next', 'max_atp'))
    exact(proposal, ('next',))
    exact(policy, ('invariant', 'goals', 'live_goals'))
    # Only the resource-release rule is proposed. The acknowledgement is external.
    exact(shared['next'], ('ack',))
    exact(proposal['next'], ('held',))
    spec = dict(shared, **policy, next=dict(shared['next'], **proposal['next']))
    if not spec['live_goals']:
        del spec['live_goals']
    spec_bytes = (json.dumps(spec, sort_keys=True, indent=2)+'\n').encode()
    raw = machine.create(spec)
    model = certificate.identity(certificate.model_from_machine(decode(raw)))
    return spec_bytes, raw, model


def check(world, candidate, contracts, proofs, *, expected_world, expected_candidate,
          expected_contracts, expected_checker, max_steps=certificate.MAX_STEPS):
    """Read-only joint decision; expected identities are selected outside proposals."""
    exact(contracts, ROLES)
    exact(proofs, ROLES)
    exact(expected_contracts, ROLES)
    for raw, expected in [(world, expected_world), (candidate, expected_candidate),
                          *((contracts[role], expected_contracts[role]) for role in ROLES)]:
        record_hash(expected)
        if digest(raw) != expected:
            raise ValueError('input differs from recipient selection')
    record_hash(expected_checker)
    report = dict(authority='observation_only', admitted=False, world=expected_world,
                  candidate=expected_candidate, contracts=dict(expected_contracts),
                  checker=expected_checker, max_steps=max_steps, checks={})
    if certificate.checker_id() != expected_checker:
        return dict(report, status='checker_unavailable')
    for role in ROLES:
        _, _, model = materialize(world, candidate, contracts[role])
        checked = evidence.verify(proofs[role], model, expected_checker, max_steps=max_steps)
        report['checks'][role] = dict(model=model, proof_sha256=digest(proofs[role]), check=checked)
    statuses = [report['checks'][role]['check']['status'] for role in ROLES]
    if all(status == 'verified_certificate' for status in statuses):
        return dict(report, status='admissible', admitted=True)
    # Retain all per-party observations. No partial result establishes joint admission.
    if any(status not in ('verified_certificate', 'verified_refutation') for status in statuses):
        return dict(report, status='undetermined')
    return dict(report, status='candidate_refuted')


def run():
    selections = document(certificate.read(FIXTURES/'selections.json'))
    world = certificate.read(FIXTURES/'world.json')
    contracts = {role: certificate.read(FIXTURES/(role+'.json')) for role in ROLES}
    anchors = dict(expected_world=selections['world'], expected_contracts=selections['contracts'],
                   expected_checker=selections['checker'])
    artifacts = {'world.json': world, 'selections.json': (FIXTURES/'selections.json').read_bytes()}
    artifacts.update({role+'.json': raw for role, raw in contracts.items()})
    cases, packets, candidates = {}, {}, {}
    expected = {'premature': ('verified_refutation', 'verified_certificate'),
                'hoard': ('verified_certificate', 'verified_refutation'),
                'guarded': ('verified_certificate', 'verified_certificate')}
    for name, outcomes in expected.items():
        candidate = candidates[name] = certificate.read(FIXTURES/(name+'.json'))
        artifacts[name+'/candidate.json'] = candidate
        proofs = packets[name] = {}
        for role in ROLES:
            spec, raw, _ = materialize(world, candidate, contracts[role])
            _, proof = evidence.produce(raw, lab.identity(raw))
            if proof is None:
                raise ValueError('producer did not supply evidence')
            proofs[role] = proof
            prefix = name+'/'+role+'/'
            artifacts[prefix+'input-spec.json'] = spec
            artifacts[prefix+'input.machine'] = raw
            artifacts[prefix+evidence.kind(proof)+'.json'] = proof
        result = check(world, candidate, contracts, proofs, **anchors,
                       expected_candidate=selections['candidates'][name])
        actual = tuple(result['checks'][role]['check']['status'] for role in ROLES)
        if actual != outcomes or result['admitted'] != (name == 'guarded'):
            raise ValueError('unexpected joint decision: ' + name)
        cases[name] = result
    kwargs = dict(anchors, expected_candidate=selections['candidates']['guarded'])
    controls = {}
    weakened = document(contracts['custodian'])
    weakened['invariant'] = weakened['invariant'].replace('held || ack', 'true')
    weakened_bytes = (json.dumps(weakened, sort_keys=True)+'\n').encode()
    mutations = {
        'candidate_substitution': (candidates['premature'], contracts, packets['guarded']),
        'stale_proof': (candidates['guarded'], contracts,
                        dict(packets['guarded'], custodian=packets['hoard']['custodian'])),
        'weakened_contract': (candidates['guarded'], dict(contracts, custodian=weakened_bytes), packets['guarded']),
        'missing_party': (candidates['guarded'], contracts, {'custodian': packets['guarded']['custodian']}),
    }
    for name, (candidate, policies, proofs) in mutations.items():
        try:
            check(world, candidate, policies, proofs, **kwargs)
        except ValueError:
            controls[name] = 'rejected'
        else:
            raise ValueError('mutation accepted: ' + name)
    limited = check(world, candidates['guarded'], contracts, packets['guarded'], max_steps=0, **kwargs)
    if limited['admitted'] or limited['status'] != 'undetermined':
        raise ValueError('incomplete check admitted a candidate')
    controls['incomplete'] = limited
    objections = {name: {role: decode(packets[name][role])['claim']
                         for role, status in zip(ROLES, expected[name]) if status == 'verified_refutation'}
                  for name in ('premature', 'hoard')}
    report = dict(status='passed', scope='synthetic_shared_action', authority='observation_only',
                  cases=cases, objections=objections, controls=controls,
                  global_incompatibility='not_established')
    return report, artifacts


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, help='new directory for evidence, never overwrite')
    args = parser.parse_args()
    report, artifacts = run()
    rendered = json.dumps(report, sort_keys=True, indent=2)+'\n'
    if args.output:
        args.output.mkdir(mode=0o700)
        try:
            for name, raw in artifacts.items():
                path = args.output/name
                path.parent.mkdir(parents=True, exist_ok=True)
                with path.open('xb') as stream:
                    stream.write(raw)
            with (args.output/'report.json').open('x') as stream:
                stream.write(rendered)
        except BaseException as error:
            try:
                shutil.rmtree(args.output)
            except OSError as cleanup_error:
                error.add_note('experiment cleanup failed: ' + str(cleanup_error))
            raise
    print(rendered, end='')


if __name__ == '__main__':
    main()
