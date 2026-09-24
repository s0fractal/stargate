"""Ownership-safe safety synthesis for repair (producer only; docs/SYNTH_REGISTRY.md).

A repair of a machine with declared world rules is a safety game: the world bits' next
values are the environment's move, the owned bits' next values are the system's, chosen
after the event. The greatest fixed point of the states from which every event leaves
some owned choice inside the invariant is the winning region. A minimal-Hamming strategy
inside it is emitted as ordinary WPL rules. Nothing here is a verdict: the candidate goes
through the same producer, repair packet and repair checker as any other.
"""
from itertools import product

from . import boolean, compiler, kernel

class Unrepresentable(Exception):
    """The chosen table exists but no representation here states it within the machine's limits."""

    def __init__(self, reason, detail=None):
        super().__init__(reason if detail is None else reason + ': ' + detail)
        self.reason, self.detail = reason, detail


class EmitterError(Exception):
    """A representation parsed but does not compute the chosen table: a producer defect."""


def _rows(names):
    """Every valuation of names, in binary order with the first name most significant."""
    n = len(names)
    for row in range(2 ** n):
        yield {name: bool(row >> (n - 1 - i) & 1) for i, name in enumerate(names)}


def _dnf(table, inputs, value):
    return ' || '.join('(' + ' && '.join(n if row[n] else '!' + n for n in inputs) + ')'
                       for row, cell in zip(_rows(inputs), table) if cell == value)


def emit(table, inputs):
    """The truth table as a full-minterm WPL rule; no validity check (see represent)."""
    inputs = sorted(inputs)
    declarations = ''.join('fact ' + name + ': bool\n' for name in inputs)
    if all(table) or not any(table):
        return declarations + 'check ' + ('true' if all(table) else 'false') + '\n'
    positive, negative = _dnf(table, inputs, True), '!(' + _dnf(table, inputs, False) + ')'
    return declarations + 'check ' + (positive if len(positive) <= len(negative) else negative) + '\n'


def table_of(source, inputs):
    """The rule's value on every row, by the independent Boolean oracle."""
    inputs = sorted(inputs)
    code = boolean.program(source, inputs, allow_unused=True)
    return [boolean.evaluate(code, row) for row in _rows(inputs)]


def _expression(source):
    """The parent rule's expression, when the rule is fact declarations and one check."""
    lines = [line for line in source.split('\n') if line.strip()]
    if not lines or not lines[-1].startswith('check ') or not all(
            line.startswith('fact ') and line.endswith(': bool') for line in lines[:-1]):
        return None
    return lines[-1][len('check '):]


def _forms(table, inputs, parent_source):
    """Candidate expressions, in tie-break order."""
    if all(table) or not any(table):
        yield 'true' if all(table) else 'false'
        return
    parent = _expression(parent_source)
    if parent is not None:
        flipped = [a != b for a, b in zip(table, table_of(parent_source, inputs))]
        changed = _dnf(flipped, inputs, True)
        yield '((' + parent + ') && !(' + changed + ')) || (!(' + parent + ') && (' + changed + '))'
    yield _dnf(table, inputs, True)
    yield '!(' + _dnf(table, inputs, False) + ')'


def _within_budget(source, inputs, max_atp):
    for row in _rows(inputs):
        try:
            compiler.compile_source(source, facts=row, max_atp=max_atp, allow_unused=True)
        except (compiler.CompileIncomplete, kernel.ResourceFault, kernel.AdmissionRefused) as exc:
            return str(exc) or type(exc).__name__
    return None


def represent(table, inputs, parent_source, max_atp):
    """The shortest representation the current compiler accepts that computes the table."""
    inputs = sorted(inputs)
    declarations = ''.join('fact ' + name + ': bool\n' for name in inputs)
    valid, refusals = [], []
    for order, expression in enumerate(_forms(table, inputs, parent_source)):
        source = declarations + 'check ' + expression + '\n'
        try:
            compiler.parse(source, dict.fromkeys(inputs, False), allow_unused=True)
        except compiler.PolicyError as exc:
            refusals.append(('rule_wpl', str(exc)))
            continue
        over = _within_budget(source, inputs, max_atp)
        if over is not None:
            refusals.append(('rule_atp', over))
            continue
        if table_of(source, inputs) != table:
            raise EmitterError('representation ' + str(order) + ' does not compute the chosen table')
        valid.append((len(source.encode('utf-8')), order, source))
    if valid:
        return min(valid)[2]
    reason = 'rule_atp' if any(kind == 'rule_atp' for kind, _ in refusals) else 'rule_wpl'
    raise Unrepresentable(reason, '; '.join(sorted({detail for _, detail in refusals})))


def synthesize(doc):
    """Winning region, strategy and emitted rules for an inspected machine document."""
    state, events = list(doc['state']), list(doc['events'])
    world = list(doc.get('world', ()))
    owned = [name for name in state if name not in world]
    choosable = owned
    inputs = sorted(state + events)
    programs = {name: boolean.program(doc['next'][name], inputs, allow_unused=True) for name in state}
    invariant = boolean.program(doc['invariant'], state, allow_unused=True)

    def key(values):
        return tuple(values[name] for name in state)

    states = {key(s): s for s in _rows(state)}
    valuations = list(_rows(events))
    vectors = list(product((False, True), repeat=len(choosable)))

    def world_next(s, e):
        facts = dict(s, **e)
        return {name: boolean.evaluate(programs[name], facts) for name in world}

    def parent(s, e):
        facts = dict(s, **e)
        return tuple(boolean.evaluate(programs[name], facts) for name in choosable)

    def combine(moved, choice):
        values = dict(moved)
        values.update(zip(choosable, choice))
        return key(values)

    region = {k for k, s in states.items() if boolean.evaluate(invariant, s)}
    while True:
        smaller = {k for k in region
                   if all(any(combine(world_next(states[k], e), o) in region for o in vectors)
                          for e in valuations)}
        if smaller == region:
            break
        region = smaller
    metrics = dict(winning_states=len(region))
    for initial in doc['initial']:
        if key(initial) not in region:
            return dict(status='unrealizable', metrics=dict(metrics, first_initial_outside=initial))

    # For a state in the region an admissible choice exists by construction; the parent's
    # fallback is only reachable in a mutant of the fixed point above.
    choice, changed_rows, delta, changed = {}, 0, 0, set()
    for k, s in states.items():
        for e in valuations:
            old = parent(s, e)
            new = old
            if k in region and combine(world_next(s, e), old) not in region:
                admissible = [o for o in vectors if combine(world_next(s, e), o) in region]
                if admissible:
                    new = min(admissible, key=lambda o: (sum(a != b for a, b in zip(o, old)), o))
            if new != old:
                changed_rows += 1
                delta += sum(a != b for a, b in zip(new, old))
                changed.update(name for name, a, b in zip(choosable, new, old) if a != b)
            choice[k, tuple(e[n] for n in events)] = new
    metrics.update(changed_rows=changed_rows, total_owned_hamming_delta=delta,
                   changed_owned_rules=sorted(changed))

    rules, sizes = dict(doc['next']), {}
    for index, name in enumerate(choosable):
        table = [choice[key(row), tuple(row[n] for n in events)][index] for row in _rows(inputs)]
        if table == table_of(doc['next'][name], inputs):
            source = doc['next'][name]              # unchanged function: the parent's bytes
        else:
            try:
                source = represent(table, inputs, doc['next'][name], doc['max_atp'])
            except EmitterError as exc:
                return dict(status='producer_error', reason=name + ': ' + str(exc), metrics=metrics)
            except Unrepresentable as exc:
                return dict(status='search_incomplete', reason=exc.reason + ': ' + name + ': ' + str(exc.detail),
                            metrics=metrics)
        rules[name] = source
        sizes[name] = len(source.encode('utf-8'))
    metrics['emitted_rule_bytes'] = sizes
    return dict(status='realizable', next=rules, metrics=metrics)

