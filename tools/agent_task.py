"""Check an agent's own finite model and retain an existing-format offline proof.

This convenience producer is outside the checker. Reports confer no action authority.
"""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import sys

from stargate import certificate, evidence, lab, machine, transport
from stargate.canonical import canon, decode, record_hash


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('duplicate specification field: ' + key)
        result[key] = value
    return result


def run(spec_path, expected_spec, expected_checker, output, *, max_edges=256,
        max_steps=certificate.MAX_STEPS, repair_parent=None, expected_parent=None,
        search=None, max_candidates=None):
    if search is not None:
        if search not in ('one-edit', 'trace', 'synth') or max_candidates is None:
            raise ValueError('search requires an explicit strategy and candidate quota')
        if repair_parent is not None or expected_parent is not None:
            raise ValueError('search takes a defective input spec, not a separate repair parent')
    elif max_candidates is not None:
        raise ValueError('candidate quota requires search mode')
    if (repair_parent is None) != (expected_parent is None):
        raise ValueError('repair requires both parent evidence and the selected parent model')
    if expected_parent is not None:
        record_hash(expected_parent)
    record_hash(expected_spec)
    record_hash(expected_checker)
    output = Path(output)
    if output.exists():
        raise ValueError('output already exists; never overwrite a handoff')
    if certificate.checker_id() != expected_checker:
        return dict(status='checker_unavailable', checker=expected_checker), 3
    parent = None
    if repair_parent is not None:
        parent = certificate.read(repair_parent)
        parent_check = certificate.verify_refutation(parent, expected_parent, expected_checker, max_steps=max_steps)
        if parent_check['status'] != 'verified_refutation':
            return dict(status=parent_check['status'], parent_check=parent_check), certificate.exit_code(parent_check)
    with Path(spec_path).open('rb') as stream:
        spec = stream.read(certificate.MAX_BYTES + 1)
    if len(spec) > certificate.MAX_BYTES:
        raise ValueError('specification exceeds 1 MiB')
    if hashlib.sha256(spec).hexdigest() != expected_spec:
        raise ValueError('specification differs from the selected input hash')
    raw = machine.create(json.loads(spec, object_pairs_hook=unique_object))
    machine_id = lab.identity(raw)
    model_id = certificate.identity(certificate.model_from_machine(decode(raw)))
    if search is not None:
        return search_task(spec, raw, model_id, expected_checker, output,
                           search, max_candidates, max_edges, max_steps)
    produced, proof = evidence.produce(raw, machine_id, max_edges=max_edges, max_steps=max_steps)
    report = dict(authority='observation_only', spec_sha256=expected_spec,
                  machine_id=machine_id, model_id=model_id, checker=expected_checker,
                  budget=dict(max_edges=max_edges, max_steps=max_steps), producer=produced)
    status = produced.get('status')
    if status not in ('verified_certificate', 'verified_refutation'):
        if status not in ('incomplete', 'checker_unavailable', 'checker_error'):
            status = 'checker_error'
        return dict(report, status=status), certificate.exit_code(dict(status=status))
    if proof is None:
        return dict(report, status='checker_error', error='producer omitted evidence'), 1
    checked = evidence.verify(proof, model_id, expected_checker, max_steps=max_steps)
    if checked.get('status') != status:
        return dict(report, status='checker_error', check=checked, error='recipient check disagrees'), 1

    successor = None
    replay_model = model_id
    filename = 'certificate.json' if status == 'verified_certificate' else 'refutation.json'
    mode = [] if status == 'verified_certificate' else ['--refutation']
    if parent is not None:
        report.update(parent_model=expected_parent, parent_check=parent_check)
        if status != 'verified_certificate':
            return dict(report, status='not_repaired', candidate_check=checked), 4
        proof = certificate.pack_repair(parent, proof)
        checked, successor = certificate.verify_repair(proof, expected_parent, expected_checker, max_steps=max_steps)
        status = checked.get('status')
        if status != 'verified_repair':
            if status not in ('incomplete', 'checker_unavailable', 'checker_error'):
                status = 'checker_error'
            return dict(report, status=status, check=checked), certificate.exit_code(dict(status=status))
        if successor is None:
            return dict(report, status='checker_error', error='verified repair omitted successor'), 1
        # Bind the returned successor to the independently checked candidate, not a report label.
        successor_check = certificate.verify(successor, model_id, expected_checker, max_steps=max_steps)
        if successor_check.get('status') != 'verified_certificate':
            return dict(report, status='checker_error', check=successor_check), 1
        report['successor_model'] = model_id
        replay_model, filename, mode = expected_parent, 'repair.json', ['--repair']

    report.update(status=status, check=checked)
    return export_task(output, report, proof, spec, raw, filename, mode, replay_model, successor)


def export_task(output, report, proof, spec, raw, filename, mode, replay_model, successor=None, extra=None):
    # Existing offline proof format, exported only after all checks succeed.
    exported = transport.unpack_certificate(proof, output, license_text=lab.LICENSE)
    # unpack owns cleanup until it returns. Never remove a destination whose
    # exclusive creation failed (another writer may have created it).
    try:
        replay = ['python', '-I', '-S', 'replay.py', filename, *mode,
                  '--expect-model', replay_model, '--expect-checker', report['checker'],
                  '--max-steps', str(report['budget']['max_steps'])]
        report.update(proof_sha256=hashlib.sha256(proof).hexdigest(),
                      replay_digest=exported['replay_digest'], replay_argv=replay)
        files = {'input-spec.json': spec, 'input.machine': raw}
        if successor is not None:
            files['successor.json'] = successor
        files.update(extra or {})
        # The report is written last; partial filesystem failure is never success.
        files['task-report.json'] = (json.dumps(report, sort_keys=True, indent=2)+'\n').encode()
        for name, data in files.items():
            with (output / name).open('xb') as stream:
                stream.write(data)
        return report, certificate.exit_code(report)
    except BaseException as error:
        # Includes an ordinary KeyboardInterrupt, but cannot recover from SIGKILL
        # or machine failure. The caller must control the destination's parent.
        try:
            shutil.rmtree(output)
        except OSError as cleanup_error:
            error.add_note('handoff cleanup failed: ' + str(cleanup_error))
        raise


def search_task(spec, raw, parent_model, checker, output, strategy, quota, max_edges, max_steps):
    produced, proof = evidence.repair_search(raw, lab.identity(raw), strategy=strategy,
        max_candidates=quota, max_edges=max_edges, max_steps=max_steps)
    report = dict(authority='observation_only', spec_sha256=hashlib.sha256(spec).hexdigest(),
        machine_id=lab.identity(raw), model_id=parent_model, parent_model=parent_model, checker=checker,
        budget=dict(max_edges=max_edges, max_steps=max_steps, max_candidates=quota), search=produced)
    status = produced.get('status') if isinstance(produced, dict) else None
    if status != 'found':
        known = ('not_needed', 'neighborhood_exhausted', 'not_applicable', 'unrealizable',
                 'not_certified', 'repair_refused', 'search_incomplete', 'incomplete',
                 'checker_unavailable', 'checker_error')
        report['status'] = status if status in known else 'checker_error'
        return report, evidence.repair_exit_code(report)
    if proof is None:
        return dict(report, status='checker_error', error='search omitted repair evidence'), 1
    checked, successor = certificate.verify_repair(proof, parent_model, checker, max_steps=max_steps)
    if checked.get('status') != 'verified_repair':
        status = checked.get('status')
        if status not in ('incomplete', 'checker_unavailable', 'checker_error'):
            status = 'checker_error'
        return dict(report, status=status, check=checked), certificate.exit_code(dict(status=status))
    candidate = certificate.inspect_repair(proof)['candidate']
    if successor is None or successor != canon(candidate):
        return dict(report, status='checker_error', error='repair successor differs from candidate evidence'), 1
    candidate_id = certificate.identity(candidate['model'])
    candidate_check = certificate.verify(successor, candidate_id, checker, max_steps=max_steps)
    if candidate_check.get('status') != 'verified_certificate':
        return dict(report, status='checker_error', check=candidate_check), 1
    # Keep an editable candidate using the original specification's non-proof fields.
    candidate_spec = dict(json.loads(spec, object_pairs_hook=unique_object), next=candidate['model']['next'])
    candidate_raw = machine.create(candidate_spec)
    if certificate.identity(certificate.model_from_machine(decode(candidate_raw))) != candidate_id:
        raise ValueError('materialized candidate does not match the checked successor')
    candidate_bytes = (json.dumps(candidate_spec, sort_keys=True, indent=2)+'\n').encode()
    report.update(status='verified_repair', check=checked, successor_model=candidate_id,
                  candidate_spec_sha256=hashlib.sha256(candidate_bytes).hexdigest())
    return export_task(output, report, proof, spec, raw, 'repair.json', ['--repair'], parent_model,
                       successor, {'candidate-spec.json': candidate_bytes})


def check_handoff(directory, expected_spec, expected_checker, *, expected_parent=None,
                  max_steps=certificate.MAX_STEPS):
    """Recheck saved data with the installed checker; never execute packet code."""
    record_hash(expected_spec)
    record_hash(expected_checker)
    if expected_parent is not None:
        record_hash(expected_parent)
    if certificate.checker_id() != expected_checker:
        return dict(status='checker_unavailable', checker=expected_checker), 3
    directory = Path(directory)
    spec = certificate.read(directory/'input-spec.json')
    if hashlib.sha256(spec).hexdigest() != expected_spec:
        raise ValueError('specification differs from the selected input hash')
    raw = machine.create(json.loads(spec, object_pairs_hook=unique_object))
    if certificate.read(directory/'input.machine') != raw:
        raise ValueError('saved machine differs from the selected specification')
    model_id = certificate.identity(certificate.model_from_machine(decode(raw)))
    names = [name for name in ('certificate.json', 'refutation.json', 'repair.json')
             if (directory/name).exists() or (directory/name).is_symlink()]
    if len(names) != 1:
        raise ValueError('handoff must contain exactly one evidence file')
    name = names[0]
    proof = certificate.read(directory/name)
    report = dict(authority='observation_only', spec_sha256=expected_spec,
                  machine_id=lab.identity(raw), model_id=model_id, checker=expected_checker,
                  proof_sha256=hashlib.sha256(proof).hexdigest(),
                  budget=dict(max_steps=max_steps))
    if name != 'repair.json':
        if expected_parent is not None:
            raise ValueError('selected repair parent requires repair evidence')
        if evidence.kind(proof) + '.json' != name:
            raise ValueError('evidence kind differs from its filename')
        checked = evidence.verify(proof, model_id, expected_checker, max_steps=max_steps)
    else:
        if expected_parent is None:
            raise ValueError('repair handoff requires an independently selected parent')
        checked, successor = certificate.verify_repair(
            proof, expected_parent, expected_checker, max_steps=max_steps)
        if checked.get('status') == 'verified_repair':
            candidate = certificate.inspect_repair(proof)['candidate']
            candidate_id = certificate.identity(candidate['model'])
            if successor is None or successor != canon(candidate):
                raise ValueError('repair checker omitted the exact candidate successor')
            if certificate.read(directory/'successor.json') != successor:
                raise ValueError('saved successor differs from the verified repair')
            if model_id not in (expected_parent, candidate_id):
                raise ValueError('selected input is neither repair parent nor candidate')
            role = 'parent' if model_id == expected_parent else 'candidate'
            candidate_path = directory/'candidate-spec.json'
            if role == 'parent' or candidate_path.exists() or candidate_path.is_symlink():
                candidate_spec = certificate.read(candidate_path)
                candidate_raw = machine.create(json.loads(candidate_spec, object_pairs_hook=unique_object))
                if certificate.identity(certificate.model_from_machine(decode(candidate_raw))) != candidate_id:
                    raise ValueError('saved candidate specification differs from the verified successor')
                report['candidate_spec_sha256'] = hashlib.sha256(candidate_spec).hexdigest()
            report.update(parent_model=expected_parent, successor_model=candidate_id, input_role=role)
    report.update(status=checked['status'], check=checked)
    return report, certificate.exit_code(report)


def main():
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument('spec', type=Path, help='input specification, or directory with --check-handoff')
    parser.add_argument('--expect-spec', required=True)
    parser.add_argument('--expect-checker', required=True)
    parser.add_argument('--output', type=Path)
    parser.add_argument('--check-handoff', action='store_true',
                        help='recheck the positional handoff directory using the installed checker')
    parser.add_argument('--repair-parent', type=Path)
    parser.add_argument('--expect-parent')
    parser.add_argument('--search', choices=('one-edit', 'trace', 'synth'))
    parser.add_argument('--max-candidates', type=int)
    parser.add_argument('--max-edges', type=int, default=256)
    parser.add_argument('--max-steps', type=int, default=certificate.MAX_STEPS)
    args = parser.parse_args()
    try:
        if args.check_handoff:
            if (args.output is not None or args.repair_parent is not None or
                    args.search is not None or args.max_candidates is not None or args.max_edges != 256):
                raise ValueError('handoff checking does not accept production options')
            report, code = check_handoff(args.spec, args.expect_spec, args.expect_checker,
                                        expected_parent=args.expect_parent, max_steps=args.max_steps)
        else:
            if args.output is None:
                raise ValueError('production requires an output directory')
            report, code = run(args.spec, args.expect_spec, args.expect_checker, args.output,
                               max_edges=args.max_edges, max_steps=args.max_steps,
                               repair_parent=args.repair_parent, expected_parent=args.expect_parent,
                               search=args.search, max_candidates=args.max_candidates)
    except (ValueError, TypeError, RecursionError) as error:
        report, code = dict(status='invalid', error=str(error)), 2
    except (OSError, certificate.CheckerError) as error:
        report, code = dict(status='operation_error', error=str(error)), 1
    print(json.dumps(report, sort_keys=True))
    return code


if __name__ == '__main__':
    sys.exit(main())
