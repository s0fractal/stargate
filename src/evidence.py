"""Untrusted proof production; only the independent certificate checker concludes."""
import hashlib

from . import certificate, machine
from .canonical import InvalidRecord, canon, decode, record_hash


def kind(raw):
    if not isinstance(raw, bytes) or len(raw) > certificate.MAX_BYTES:
        raise InvalidRecord('evidence must be bytes within 1 MiB')
    doc = decode(raw)
    if type(doc) is not dict:
        raise InvalidRecord('evidence must be an object')
    if 'certificate' in doc and 'refutation' not in doc:
        certificate.inspect(raw)
        return 'certificate'
    if 'refutation' in doc and 'certificate' not in doc:
        certificate.inspect_refutation(raw)
        return 'refutation'
    raise InvalidRecord('expected exactly one certificate or refutation')


def verify(raw, expected_model, expected_checker, *, max_steps=certificate.MAX_STEPS):
    check = certificate.verify if kind(raw) == 'certificate' else certificate.verify_refutation
    return check(raw, expected_model, expected_checker, max_steps=max_steps)


def produce(raw, expected_machine, *, max_edges=256, max_steps=certificate.MAX_STEPS):
    record_hash(expected_machine)
    if hashlib.sha256(raw).hexdigest() != expected_machine:
        raise InvalidRecord('machine does not match recipient anchor')
    if type(max_steps) is not int or not 0 <= max_steps <= certificate.MAX_STEPS:
        raise InvalidRecord('step quota must be 0..4288')
    model = certificate.model_from_machine(machine.inspect(raw))
    model_id = certificate.identity(model)
    producer = machine.verify(raw, expected_machine, max_edges=max_edges)
    report = dict(machine_id=expected_machine, model_id=model_id, producer=producer)
    if type(producer) is not dict:
        return dict(report, status='checker_error', phase='producer', reason='invalid producer report'), None
    status = producer.get('status')
    if status in ('incomplete', 'checker_error'):
        return dict(report, status=status, phase='producer'), None
    if status not in ('established', 'counterexample', 'goal_unreachable'):
        return dict(report, status='checker_error', phase='producer', reason='unknown producer status'), None
    try:
        checker = certificate.checker_id()
        if status == 'established':
            packet = canon(dict(certificate=1, checker=checker, model=model,
                                states=producer['reachable'], paths=producer['goal_witnesses']))
            expected = 'verified_certificate'
        else:
            claim = (dict(kind='unsafe', trace=producer['trace']) if status == 'counterexample' else
                     dict(kind='unreachable_goal', goal=producer['unreached_goals'][0], states=producer['reachable']))
            packet = canon(dict(refutation=1, checker=checker, model=model, claim=claim))
            expected = 'verified_refutation'
        # Never inherit a producer verdict. Anchor checking to the INPUT model,
        # not any replacement model, ID or verdict in the producer report.
        checked = verify(packet, model_id, checker, max_steps=max_steps)
    except (ValueError, TypeError, KeyError, IndexError, RecursionError) as exc:
        return dict(report, status='checker_error', phase='evidence',
                    reason='producer evidence rejected: ' + str(exc)), None
    report.update(check=checked, phase='evidence')
    if checked['status'] == expected:
        return dict(report, status=expected), packet
    if checked['status'] in ('incomplete', 'checker_unavailable', 'checker_error'):
        return dict(report, status=checked['status']), None
    return dict(report, status='checker_error', reason='unexpected evidence checker status'), None
