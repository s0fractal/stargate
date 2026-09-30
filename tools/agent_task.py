"""Check an agent's own finite model and retain an existing-format offline proof.

This convenience producer is outside the checker. Reports confer no action authority.
"""
import argparse
import hashlib
import json
from pathlib import Path
import sys

from stargate import certificate, evidence, lab, machine, transport
from stargate.canonical import decode, record_hash


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('duplicate specification field: ' + key)
        result[key] = value
    return result


def run(spec_path, expected_spec, expected_checker, output, *, max_edges=256,
        max_steps=certificate.MAX_STEPS):
    record_hash(expected_spec)
    record_hash(expected_checker)
    output = Path(output)
    if output.exists():
        raise ValueError('output already exists; never overwrite a handoff')
    if certificate.checker_id() != expected_checker:
        return dict(status='checker_unavailable', checker=expected_checker), 3
    with Path(spec_path).open('rb') as stream:
        spec = stream.read(certificate.MAX_BYTES + 1)
    if len(spec) > certificate.MAX_BYTES:
        raise ValueError('specification exceeds 1 MiB')
    if hashlib.sha256(spec).hexdigest() != expected_spec:
        raise ValueError('specification differs from the selected input hash')
    raw = machine.create(json.loads(spec, object_pairs_hook=unique_object))
    machine_id = lab.identity(raw)
    model_id = certificate.identity(certificate.model_from_machine(decode(raw)))
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

    # Use the existing offline proof format and exclusive-directory materializer.
    exported = transport.unpack_certificate(proof, output, license_text=lab.LICENSE)
    filename = 'certificate.json' if status == 'verified_certificate' else 'refutation.json'
    replay = ['python', '-I', '-S', 'replay.py', filename]
    if status == 'verified_refutation':
        replay.append('--refutation')
    replay += ['--expect-model', model_id, '--expect-checker', expected_checker,
               '--max-steps', str(max_steps)]
    report.update(status=status, check=checked, proof_sha256=hashlib.sha256(proof).hexdigest(),
                  replay_digest=exported['replay_digest'], replay_argv=replay)
    # A report is complete only after its inputs have been retained successfully.
    for name, data in (('input-spec.json', spec), ('input.machine', raw),
                       ('task-report.json', (json.dumps(report, sort_keys=True, indent=2)+'\n').encode())):
        with (output / name).open('xb') as stream:
            stream.write(data)
    return report, certificate.exit_code(checked)


def main():
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument('spec', type=Path)
    parser.add_argument('--expect-spec', required=True)
    parser.add_argument('--expect-checker', required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--max-edges', type=int, default=256)
    parser.add_argument('--max-steps', type=int, default=certificate.MAX_STEPS)
    args = parser.parse_args()
    try:
        report, code = run(args.spec, args.expect_spec, args.expect_checker, args.output,
                           max_edges=args.max_edges, max_steps=args.max_steps)
    except (ValueError, TypeError, RecursionError) as error:
        report, code = dict(status='invalid', error=str(error)), 2
    except (OSError, certificate.CheckerError) as error:
        report, code = dict(status='operation_error', error=str(error)), 1
    print(json.dumps(report, sort_keys=True))
    return code


if __name__ == '__main__':
    sys.exit(main())
