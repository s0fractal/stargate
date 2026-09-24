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

MAX_RULE_BYTES = 8192


class Unrepresentable(Exception):
    """The chosen table exists but this emitter cannot state it within the machine's limits."""

    def __init__(self, reason):
        super().__init__(reason)
        self.reason = reason


def _rows(names):
    """Every valuation of names, in binary order with the first name most significant."""
    n = len(names)
    for row in range(2 ** n):
        yield {name: bool(row >> (n - 1 - i) & 1) for i, name in enumerate(names)}


def emit(table, inputs):
    """The truth table as WPL: a constant, the true-row DNF or the negated false-row DNF."""
    inputs = sorted(inputs)
    declarations = ''.join('fact ' + name + ': bool\n' for name in inputs)
    if all(table):
        expression = 'true'
    elif not any(table):
        expression = 'false'
    else:
        rows = list(_rows(inputs))

        def dnf(value):
            return ' || '.join('(' + ' && '.join(n if row[n] else '!' + n for n in inputs) + ')'
                               for row, cell in zip(rows, table) if cell == value)
        positive, negative = dnf(True), '!(' + dnf(False) + ')'
        expression = positive if len(positive) <= len(negative) else negative
    if len((declarations + 'check ' + expression + '\n').encode('utf-8')) > MAX_RULE_BYTES:
        raise Unrepresentable('rule_size')
    return declarations + 'check ' + expression + '\n'


def table_of(source, inputs):
    """The rule's value on every row, by the independent Boolean oracle."""
    inputs = sorted(inputs)
    code = boolean.program(source, inputs, allow_unused=True)
    return [boolean.evaluate(code, row) for row in _rows(inputs)]


def _within_budget(source, inputs, max_atp):
    for row in _rows(sorted(inputs)):
        try:
            compiler.compile_source(source, facts=row, max_atp=max_atp, allow_unused=True)
        except (compiler.CompileIncomplete, kernel.ResourceFault, kernel.AdmissionRefused):
            raise Unrepresentable('rule_atp')


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
        try:
            source = emit(table, inputs)
            if table_of(source, inputs) != table:
                return dict(status='producer_error', reason='emitted rule for ' + name + ' differs from the strategy',
                            metrics=metrics)
            _within_budget(source, inputs, doc['max_atp'])
        except Unrepresentable as exc:
            return dict(status='search_incomplete', reason=exc.reason + ': ' + name, metrics=metrics)
        rules[name] = source
        sizes[name] = len(source.encode('utf-8'))
    metrics['emitted_rule_bytes'] = sizes
    return dict(status='realizable', next=rules, metrics=metrics)
