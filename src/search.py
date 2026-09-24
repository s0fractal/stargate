"""Bounded, counterexample-guided WPL neighborhood search.

Search is a proposal generator; only lab.verify_transition admits a successor.
Inspired by CEGIS and evidence replay in neighboring projects; original MIT code.
"""
from . import boolean, compiler, kernel, lab, machine
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
    expr, _ = compiler.parse(doc['rule'], dict.fromkeys(doc['inputs'], False), allow_unused=True)
    declarations = ''.join('fact ' + name + ': bool\n' for name in doc['inputs'])
    for node in _mutations(expr):
        yield declarations + 'check ' + _render(node)


def _probe(doc, candidate, facts):
    """A recomputed single-row witness, never equivalence or admission."""
    row = dict(input=facts)
    try:
        for name, source in [('parent', doc['rule']), ('candidate', candidate)]:
            code = boolean.program(source, doc['inputs'], allow_unused=True)
            result = compiler.compile_source(source, facts=facts, max_atp=doc['max_atp'], allow_unused=True)
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
    property_mode = doc['contract'] == 'boolean-properties-1'
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
        if property_mode and examples:
            raise InvalidRecord('equivalence counterexamples cannot screen a property world')
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
        if verified['status'] == 'parent_rejected':
            report.update(status='parent_rejected', reason='parent violates its property contract')
            return report, None
        if verified['status'] == 'counterexample' and not property_mode:
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


def machine_candidates(doc, *, repair=False):
    """Change one next rule at a time, in state-name order.

    A plain change may evolve any rule; a repair never proposes a world rule.
    """
    for name in doc['state']:
        if repair and name in doc.get('world', ()):
            continue                    # producer only: the world is not a repair target
        for source in candidates(dict(rule=doc['next'][name], inputs=sorted(doc['state'] + doc['events']))):
            yield dict(doc['next'], **{name: source})


def search_machine(raw, expected_parent, *, max_candidates=32, max_edges=256, experience=None):
    if type(max_candidates) is not int or not 1 <= max_candidates <= 256:
        raise InvalidRecord('search candidate limit must be an integer from 1 to 256')
    doc = machine.inspect(raw)
    parent = lab.identity(raw)
    # Establish the parent before screening could conceal an unsafe root.
    checked = machine.verify(raw, expected_parent, max_edges=max_edges)
    runtime = lab.runtime_digest(doc['sources'])
    memory = dict(parent=parent, runtime_digest=runtime, counterexamples=[])
    report = dict(status='search_incomplete', parent=parent, parent_check=checked,
                  attempted=0, full_checks=0, trace_checks=0, screened=0,
                  incomplete_candidates=0, attempts=[], experience=memory)
    if checked['status'] != 'established':
        report['status'] = 'parent_rejected' if checked['status'] in machine.REFUSED else checked['status']
        return report, None
    if experience is not None:
        incoming = decode(canon(experience))
        exact(incoming, ('parent', 'runtime_digest', 'counterexamples'))
        if incoming['parent'] != parent or incoming['runtime_digest'] != runtime:
            raise InvalidRecord('experience belongs to another parent or runtime')
        examples = incoming['counterexamples']
        if type(examples) is not list or len(examples) > 256:
            raise InvalidRecord('experience must contain at most 256 counterexamples')
        for example in examples:
            exact(example, ('next', 'trace'))
            packet = canon(dict(doc, next=example['next']))
            report['trace_checks'] += 1
            result = machine.replay_trace(packet, example['trace'])
            if result['status'] in ('incomplete', 'checker_error'):
                report.update(status=result['status'], reason='experience replay: ' + result['reason'])
                return report, None
            if result['status'] != 'counterexample' or result['trace'] != example['trace']:
                raise InvalidRecord('claimed machine counterexample does not reproduce')
            if example not in memory['counterexamples']: memory['counterexamples'].append(example)
    seen = {canon(doc['next'])}
    stream = iter(machine_candidates(doc))
    for _ in range(max_candidates):
        try: rules = next(stream)
        except StopIteration:
            report['status'] = 'search_incomplete' if report['incomplete_candidates'] else 'neighborhood_exhausted'
            return report, None
        rules = decode(canon(rules))
        attempt = dict(next=rules)
        report['attempted'] += 1; report['attempts'].append(attempt)
        key = canon(rules)
        if key in seen:
            attempt['status'] = 'duplicate'
            continue
        seen.add(key)
        candidate = canon(dict(doc, next=rules))
        try: machine.inspect(candidate)
        except (InvalidRecord, compiler.PolicyError, boolean.BooleanSyntax) as exc:
            attempt.update(status='invalid', reason=str(exc))
            continue
        blocked = False
        for example in memory['counterexamples']:
            report['trace_checks'] += 1
            result = machine.replay_trace(candidate, example['trace'])
            if result['status'] == 'checker_error':
                attempt.update(result); report.update(status='checker_error', reason=result['reason'])
                return report, None
            if result['status'] == 'incomplete':
                attempt.update(result); report['incomplete_candidates'] += 1
                blocked = True; break
            if result['status'] == 'counterexample':
                attempt.update(status='screened', witness=result['trace'])
                report['screened'] += 1; blocked = True; break
        if blocked: continue
        report['full_checks'] += 1
        proposal = dict(parent=parent, next=rules)
        result, successor = machine.verify_change(raw, proposal, expected_parent, max_edges=max_edges)
        attempt.update(status=result['status'], verification=result)
        if result['admitted']:
            report.update(status='found', proposal=proposal, successor=lab.identity(successor))
            return report, successor
        if result['status'] in ('checker_error', 'parent_rejected'):
            report.update(status=result['status']); return report, None
        if result['status'] == 'incomplete': report['incomplete_candidates'] += 1
        elif result['status'] == 'counterexample':
            example = dict(next=rules, trace=result['checks']['candidate']['trace'])
            if example not in memory['counterexamples'] and len(memory['counterexamples']) < 256:
                memory['counterexamples'].append(example)
    report['reason'] = 'candidate_limit'
    return report, None


def _support(node, facts):
    """Value and sufficient dynamic input support; a ranking heuristic only."""
    tag = node[0]
    if tag == 'fact': return facts[node[1]], {node[1]}
    if tag == 'const': return node[1], set()
    if tag == 'not':
        value, names = _support(node[1], facts)
        return not value, names
    left, a = _support(node[1], facts)
    right, b = _support(node[2], facts)
    value = (left and right) if tag == 'and' else (left or right)
    # Include every determining operand, not merely the first short-circuit branch.
    deciding = False if tag == 'and' else True
    if left == deciding or right == deciding:
        return value, (a if left == deciding else set()) | (b if right == deciding else set())
    return value, a | b


def trace_order(doc, trace):
    """Backward slice across the whole trace, with all other rules retained.

    Upstream state absent from the invariant is ranked first, then slice frequency,
    then state name. This is neither fault attribution nor a necessary repair set.
    """
    if trace is None: return list(doc['state'])
    names = sorted(doc['state'] + doc['events'])
    def parse(source, inputs):
        return compiler.parse(source, dict.fromkeys(inputs, False), allow_unused=True)[0]
    invariant = parse(doc['invariant'], doc['state'])
    rules = {n:parse(source, names) for n, source in doc['next'].items()}
    direct = {n for n in boolean.program(doc['invariant'],doc['state'],allow_unused=True) if n in doc['state']}
    states = [trace['initial']] + [step['state'] for step in trace['steps']]
    _, needed = _support(invariant, states[-1])
    counts = dict.fromkeys(doc['state'], 0)
    for index in range(len(trace['steps']) - 1, -1, -1):
        facts = dict(states[index], **trace['steps'][index]['event'])
        previous = set()
        for name in sorted(needed & set(doc['state'])):
            counts[name] += 1
            _, dependencies = _support(rules[name], facts)
            previous.update(dependencies)
        needed = previous
    return sorted(doc['state'], key=lambda n:(not (counts[n] and n not in direct), -counts[n], n))


def _binary_nodes(node, path=()):
    if node[0] in ('and','or'): yield path, node
    for index in range(1,len(node)):
        if isinstance(node[index],tuple): yield from _binary_nodes(node[index],path+(index,))


def _shape(node):
    if node[0] == 'not': return _shape(node[1])
    if node[0] in ('fact','const'): return ('leaf',)
    return node[0], _shape(node[1]), _shape(node[2])


def _leaves(node):
    if node[0] in ('fact','const'): return 1
    return sum(_leaves(x) for x in node[1:] if isinstance(x,tuple))


def _exchange(node, a, b, left, right, path=()):
    if path == a: return right
    if path == b: return left
    return tuple(_exchange(x,a,b,left,right,path+(i,)) if isinstance(x,tuple) else x
                 for i,x in enumerate(node))


def repair_candidates(doc, order):
    """At most eight compatible compound exchanges per rule, then old neighborhood.

    Non-overlapping subtrees have the same binary shape ignoring NOT/name/constant.
    Larger pairs first, then preorder paths. No rule is excluded by the slice.
    """
    if sorted(order) != list(doc['state']): raise InvalidRecord('rule order must be a permutation')
    names = sorted(doc['state'] + doc['events'])
    declarations = ''.join('fact '+n+': bool\n' for n in names)
    for name in order:
        if name in doc.get('world', ()):
            continue                    # producer only: the world is not a repair target
        tree, _ = compiler.parse(doc['next'][name],dict.fromkeys(names,False),allow_unused=True)
        nodes = list(_binary_nodes(tree)); pairs = []
        for index,(a,left) in enumerate(nodes):
            for b,right in nodes[index+1:]:
                if a == b[:len(a)] or b == a[:len(b)] or left == right: continue
                if _shape(left) == _shape(right): pairs.append((a,b,left,right))
        pairs.sort(key=lambda pair:(-_leaves(pair[2]),pair[0],pair[1]))
        for a,b,left,right in pairs[:8]:
            source = declarations+'check '+_render(_exchange(tree,a,b,left,right))
            yield dict(doc['next'], **{name:source})
    yield from machine_candidates(doc, repair=True)
