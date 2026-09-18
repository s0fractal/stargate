"""Bounded, counterexample-guided WPL neighborhood search.

Search is a proposal generator; only lab.verify_transition admits a successor.
Inspired by CEGIS and evidence replay in neighboring projects; original MIT code.
"""
from . import boolean, compiler, kernel, lab
from .canonical import canon, decode, exact, InvalidRecord


def _render(node):
    tag = node[0]
    if tag == 'const': return 'true' if node[1] else 'false'
    if tag == 'fact': return node[1]
    if tag == 'not': return '!(' + _render(node[1]) + ')'
    return '(' + _render(node[1]) + (' && ' if tag == 'and' else ' || ') + _render(node[2]) + ')'


def _mutations(node):
    # Deliberately include potentially wrong changes: they are proposals.
    yield ('not', node)
    if node[0] in ('and', 'or'):
        yield ('or' if node[0] == 'and' else 'and', node[1], node[2])
        yield (node[0], node[2], node[1])
        if node[1] == node[2]: yield node[1]
    if node[0] == 'not' and node[1][0] == 'not': yield node[1][1]
    if node[0] == 'not':
        for child in _mutations(node[1]): yield ('not', child)
    elif node[0] in ('and', 'or'):
        for child in _mutations(node[1]): yield (node[0], child, node[2])
        for child in _mutations(node[2]): yield (node[0], node[1], child)


def candidates(doc):
    """Finite one-edit neighborhood, preorder; not a complete synthesis grammar."""
    expr, _ = compiler.parse(doc['rule'], dict.fromkeys(doc['inputs'], False))
    declarations = ''.join('fact ' + name + ': bool\n' for name in doc['inputs'])
    for node in _mutations(expr):
        yield declarations + 'check ' + _render(node)


def _probe(doc, candidate, facts):
    """A recomputed single-row witness, never equivalence or admission."""
    row = dict(input=facts)
    try:
        for name, source in [('parent', doc['rule']), ('candidate', candidate)]:
            code = boolean.program(source, doc['inputs'])
            result = compiler.compile_source(source, facts=facts, max_atp=doc['max_atp'])
            if result.value != boolean.evaluate(code, facts):
                return dict(status='checker_error', reason='independent oracle disagreement'), None
            row[name] = dict(value=result.value, atp=result.atp_spent, term=result.check['term'])
    except compiler.CompilerBug as exc:
        return dict(status='checker_error', reason=str(exc)), None
    except (compiler.CompileIncomplete, kernel.ResourceFault, kernel.AdmissionRefused) as exc:
        return dict(status='incomplete', reason=str(exc)), None
    return None, row


def search(raw, *, max_candidates=32, experience=None):
    if type(max_candidates) is not int or not 1 <= max_candidates <= 256:
        raise InvalidRecord('search candidate limit must be an integer from 1 to 256')
    doc = lab.inspect_world(raw)
    parent = lab.identity(raw)
    runtime = lab.runtime_digest(doc['sources'])
    memory = dict(parent=parent, runtime_digest=runtime, counterexamples=[])
    report = dict(status='search_incomplete', parent=parent, runtime_digest=runtime,
                  attempted=0, full_checks=0, screened=0, incomplete_candidates=0,
                  attempts=[], experience=memory)
    if experience is not None:
        incoming = decode(canon(experience))
        exact(incoming, ('parent', 'runtime_digest', 'counterexamples'))
        if incoming['parent'] != parent or incoming['runtime_digest'] != runtime:
            raise InvalidRecord('experience belongs to another parent or runtime')
        examples = incoming['counterexamples']
        if not isinstance(examples, list) or len(examples) > 256:
            raise InvalidRecord('experience must contain at most 256 counterexamples')
        for example in examples:
            exact(example, ('candidate', 'input'))
            facts = example['input']
            if (not isinstance(facts, dict) or set(facts) != set(doc['inputs']) or
                    any(type(v) is not bool for v in facts.values())):
                raise InvalidRecord('counterexample input must exactly match the boolean domain')
            lab._program(example['candidate'], doc['inputs'])
            refusal, row = _probe(doc, example['candidate'], facts)
            if refusal:
                report.update(status=refusal['status'], reason='experience replay: ' + refusal['reason'])
                return report, None
            if row['parent']['value'] == row['candidate']['value']:
                raise InvalidRecord('claimed counterexample does not reproduce')
            if not any(e['input'] == facts for e in memory['counterexamples']):
                memory['counterexamples'].append(example)

    seen = set()
    stream = iter(candidates(doc))
    for _ in range(max_candidates):
        try:
            candidate = next(stream)
        except StopIteration:
            if report['incomplete_candidates']:
                report.update(status='search_incomplete', reason='incomplete_candidates')
            else:
                report.update(status='neighborhood_exhausted')
            return report, None
        report['attempted'] += 1
        attempt = dict(candidate=candidate)
        report['attempts'].append(attempt)
        if candidate in seen:
            attempt['status'] = 'duplicate'
            continue
        seen.add(candidate)
        try:
            lab._program(candidate, doc['inputs'])
        except (compiler.PolicyError, boolean.BooleanSyntax) as exc:
            attempt.update(status='invalid', reason=str(exc))
            continue
        blocked = False
        for example in memory['counterexamples']:
            refusal, row = _probe(doc, candidate, example['input'])
            if refusal:
                attempt.update(refusal)
                if refusal['status'] == 'checker_error':
                    report.update(status='checker_error', reason=refusal['reason'])
                    return report, None
                report['incomplete_candidates'] += 1
                blocked = True
                break
            if row['parent']['value'] != row['candidate']['value']:
                attempt.update(status='screened', witness=row)
                report['screened'] += 1
                blocked = True
                break
        if blocked: continue
        report['full_checks'] += 1
        verified, successor = lab.verify_transition(raw, dict(parent=parent, candidate=candidate))
        attempt.update(status=verified['status'], verification=verified)
        if verified.get('admitted'):
            report.update(status='found', proposal=dict(parent=parent, candidate=candidate),
                          successor=lab.identity(successor))
            return report, successor
        if verified['status'] == 'counterexample':
            facts = verified['input']
            if not any(e['input'] == facts for e in memory['counterexamples']):
                memory['counterexamples'].append(dict(candidate=candidate, input=facts))
        elif verified['status'] == 'incomplete':
            report['incomplete_candidates'] += 1
        elif verified['status'] == 'checker_error':
            report.update(status=verified['status'], reason=verified.get('reason'))
            return report, None
    report['reason'] = 'candidate_limit'
    return report, None
