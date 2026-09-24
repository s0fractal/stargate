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
        raise InvalidRecord('step quota must be 0..' + str(certificate.MAX_STEPS))
    model = certificate.model_from_machine(machine.inspect(raw))
    model_id = certificate.identity(model)
    producer = machine.verify(raw, expected_machine, max_edges=max_edges)
    report = dict(machine_id=expected_machine, model_id=model_id, producer=producer)
    if type(producer) is not dict:
        return dict(report, status='checker_error', phase='producer', reason='invalid producer report'), None
    status = producer.get('status')
    if status in ('incomplete', 'checker_error'):
        return dict(report, status=status, phase='producer'), None
    if status not in ('established', 'counterexample', 'goal_unreachable', 'goal_not_live'):
        return dict(report, status='checker_error', phase='producer', reason='unknown producer status'), None
    try:
        checker = certificate.checker_id()
        if status == 'established':
            body = dict(certificate=1, checker=checker, model=model,
                        states=producer['reachable'], paths=producer['goal_witnesses'])
            if model.get('live_goals'):
                body['ranks'] = producer['live_ranks']
            packet = canon(body)
            expected = 'verified_certificate'
        else:
            claim = (dict(kind='unsafe', trace=producer['trace']) if status == 'counterexample' else
                     dict(kind='trap', goal=producer['live_goal'], states=producer['trap'],
                          trace=producer['trace']) if status == 'goal_not_live' else
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


def repair_search(raw, expected_machine, *, max_candidates=32, max_edges=256,
                  max_steps=certificate.MAX_STEPS, strategy="one-edit"):
    """Bounded repair search producing an existing, independently checked repair.

    Exhaustion means only this syntactic neighborhood, never impossibility of repair.
    Candidate incompleteness does not stop later candidates or become refutation.
    """
    from . import search
    if strategy not in ('one-edit','trace','synth'): raise InvalidRecord('unknown repair search strategy')
    if type(max_candidates) is not int or not 1 <= max_candidates <= 256:
        raise InvalidRecord('candidate quota must be 1..256')
    parent_check, refutation = produce(raw, expected_machine, max_edges=max_edges, max_steps=max_steps)
    report = dict(status='search_incomplete', parent=parent_check, attempted=0,
                  strategy=strategy, trace_checks=0, screened=0,
                  producer_calls=1, repair_checks=0, incomplete_candidates=0, attempts=[])
    if parent_check['status'] != 'verified_refutation':
        return dict(report, status=('not_needed' if parent_check['status'] == 'verified_certificate'
                                    else parent_check['status'])), None
    doc = machine.inspect(raw)
    if strategy == 'synth':
        # docs/SYNTH_REGISTRY.md: safety only, and only over rules the model says it owns.
        from . import synth
        kind = decode(refutation)['claim']['kind']
        if kind != 'unsafe':
            return dict(report, status='not_applicable', reason='parent refutation is ' + kind), None
        if not doc.get('world') or set(doc['world']) == set(doc['state']):
            return dict(report, status='not_applicable',
                        reason='synthesis needs a declared world and at least one owned rule'), None
        synthesized = synth.synthesize(doc)
        report['synthesis'] = synthesized['metrics']
        if synthesized['status'] != 'realizable':
            return dict(report, status=synthesized['status'], reason=synthesized.get('reason')), None
    parent_model = certificate.model_from_machine(doc)
    checker = certificate.checker_id()
    # The synthesized candidate is always checked, even when it is the parent's bytes: then
    # the checker, not this producer, says that the parent is still refuted.
    seen = set() if strategy == 'synth' else {canon(doc['next'])}
    traces = []
    def remember(proof):
        claim = decode(proof)['claim']
        if claim['kind'] != 'unsafe' or len(traces) >= 16: return
        trace = claim['trace']
        def events(t): return (t['initial'], [step['event'] for step in t['steps']])
        if not any(events(t) == events(trace) for t in traces): traces.append(trace)
    remember(refutation)
    order = search.trace_order(doc, traces[0] if traces else None) if strategy == 'trace' else list(doc['state'])
    report.update(rule_order=order)
    stream = iter([synthesized['next']] if strategy == 'synth' else search.repair_candidates(doc,order)
                  if strategy == 'trace' else search.machine_candidates(doc, repair=True))
    for _ in range(max_candidates):
        try:
            rules = next(stream)
        except StopIteration:
            if strategy == 'synth':
                return dict(report, status=('search_incomplete' if report['incomplete_candidates']
                                            else 'not_certified')), None
            return dict(report, status=('search_incomplete' if report['incomplete_candidates']
                                        else 'neighborhood_exhausted'), reason='neighborhood_exhausted'), None
        report['attempted'] += 1
        attempt = dict(status='invalid_candidate')
        report['attempts'].append(attempt)
        try:
            key = canon(rules)
            if key in seen:
                attempt['status'] = 'duplicate'
                continue
            seen.add(key)
            candidate = canon(dict(doc, next=decode(key)))
            candidate_model = certificate.model_from_machine(machine.inspect(candidate))
        except (ValueError, TypeError) as exc:
            attempt['reason'] = str(exc)
            continue
        attempt['model_id'] = certificate.identity(candidate_model)
        blocked = False
        if strategy == 'trace':
            for trace in traces:
                report['trace_checks'] += 1
                replay = machine.replay_trace(candidate, trace)
                if replay['status'] == 'counterexample':
                    try:
                        witness = certificate.create_refutation(candidate_model,dict(kind='unsafe',trace=replay['trace']))
                    except (ValueError,TypeError,KeyError,certificate.CheckerError) as exc:
                        return dict(report,status='checker_error',reason=str(exc)), None
                    attempt.update(status='screened', witness=decode(witness)['claim']['trace'])
                    report['screened'] += 1
                    blocked = True
                    break
                if replay['status'] == 'incomplete':
                    attempt['status'] = 'incomplete'
                    report['incomplete_candidates'] += 1
                    blocked = True
                    break
                if replay['status'] != 'trace_passed':
                    return dict(report,status='checker_error',reason='trace replay failed'), None
        if blocked: continue
        report['producer_calls'] += 1
        checked, proof = produce(candidate, hashlib.sha256(candidate).hexdigest(),
                                 max_edges=max_edges, max_steps=max_steps)
        attempt.update(status=checked['status'], check=checked)
        if strategy == 'synth':
            report['synthesis']['final_checker_status'] = checked['status']
            if checked['status'] == 'verified_refutation':
                report['synthesis']['candidate_claim'] = decode(proof)['claim']['kind']
        if checked['status'] == 'incomplete':
            report['incomplete_candidates'] += 1
            continue
        if checked['status'] == 'verified_refutation':
            if strategy == 'trace': remember(proof)
            continue
        if checked['status'] != 'verified_certificate':
            return dict(report, status=checked['status']), None
        report['repair_checks'] += 1
        try:
            if decode(proof)['model'] != candidate_model:
                raise InvalidRecord('producer certificate names a different candidate')
            packet = certificate.pack_repair(refutation, proof)
            verdict, successor = certificate.verify_repair(packet, certificate.identity(parent_model),
                                                           checker, max_steps=max_steps)
        except InvalidRecord as exc:
            if strategy != 'synth': return dict(report, status='checker_error', reason=str(exc)), None
            report['synthesis']['final_checker_status'] = 'invalid'
            return dict(report, status='repair_refused', reason=str(exc)), None
        except (ValueError, TypeError, KeyError) as exc:
            return dict(report, status='checker_error', reason=str(exc)), None
        attempt['repair'] = verdict
        if strategy == 'synth': report['synthesis']['final_checker_status'] = verdict['status']
        if verdict['status'] == 'verified_repair' and successor is not None:
            return dict(report, status='found', repair=verdict), packet
        if verdict['status'] == 'incomplete':
            report['incomplete_candidates'] += 1
            continue
        return dict(report, status='checker_error', reason='repair check did not establish repair'), None
    return dict(report, reason='candidate_limit'), None


def repair_exit_code(report):
    if report['status'] == 'found': return 0
    if report['status'] in ('not_needed', 'neighborhood_exhausted', 'not_applicable', 'unrealizable',
                            'not_certified', 'repair_refused'): return 4
    return 3 if report['status'] in ('search_incomplete', 'incomplete', 'checker_unavailable') else 1
