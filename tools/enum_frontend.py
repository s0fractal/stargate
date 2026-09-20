"""Write a model over named values; get boolean-machine-1 rules back.

This front-end is outside every checked closure. It emits text for
`sg machine-create` and decodes what comes back into names again. It proves
nothing: if it emits the wrong model, the checker will faithfully certify the
wrong model. Read tools/REGISTRY.md for what was and was not established.

A spec is a plain dict:

    enums        {name: [value, ...]}      each takes ceil(log2 k) bits
    flags        [name, ...]               ordinary one-bit state
    events       [name, ...]               0..2 event bits, as everywhere
    initial      {name: value or bool}
    invariant    WPL over `name:value` tokens and flags
    goals        [{name: value or bool}, ...]
    transitions  {enum: [(guard, target value), ...]}   first match wins
    flag_rules   {flag: WPL expression}
    max_atp      int

Codes that name no value are excluded in the invariant, always. An unused code is
not a state of the model, so a model that can enter one is not a model of anything
-- and a repair search is free to park a machine there unless it is forbidden.

    python tools/enum_frontend.py SPEC.json --output machine-spec.json
"""
import argparse
import itertools
import json
from pathlib import Path
import re
import sys

TOKEN = re.compile(r'\b([A-Za-z_][A-Za-z0-9_]*):([A-Za-z_][A-Za-z0-9_]*)\b')


def width(values):
    if len(values) < 2 or len(set(values)) != len(values):
        raise ValueError('an enum needs at least two distinct values')
    return max(1, (len(values) - 1).bit_length())


def bits(name, values):
    """Least significant bit first, so `a_0` is the low bit of `a`."""
    return [name + '_' + str(index) for index in range(width(values))]


def assignment(name, values, value):
    if value not in values:
        raise ValueError('unknown value ' + repr(value) + ' for ' + name)
    code = values.index(value)
    return {bit: bool(code >> index & 1) for index, bit in enumerate(bits(name, values))}


def term(name, values, value):
    return '(' + ' && '.join(bit if held else '!' + bit
                             for bit, held in assignment(name, values, value).items()) + ')'


def code_term(name, values, code):
    return '(' + ' && '.join(bit if code >> index & 1 else '!' + bit
                             for index, bit in enumerate(bits(name, values))) + ')'


def expand(expression, enums):
    """Replace every `name:value` token with the conjunction of its bits."""
    def replace(match):
        name, value = match.group(1), match.group(2)
        if name not in enums:
            raise ValueError('no enum named ' + name)
        return term(name, enums[name], value)
    return TOKEN.sub(replace, expression)


def unused(enums):
    """One exclusion per code that names nothing. Empty when every code is used."""
    clauses = []
    for name, values in sorted(enums.items()):
        for code in range(len(values), 2 ** width(values)):
            clauses.append('!' + code_term(name, values, code))
    return clauses


def state_names(spec):
    names = list(spec.get('flags', []))
    for name, values in spec['enums'].items():
        names.extend(bits(name, values))
    return sorted(names)


def flatten(spec, row):
    out = {}
    for name, value in row.items():
        if name in spec['enums']:
            out.update(assignment(name, spec['enums'][name], value))
        else:
            if type(value) is not bool:
                raise ValueError('flag ' + name + ' takes a boolean')
            out[name] = value
    if set(out) != set(state_names(spec)):
        raise ValueError('a state must give every enum and flag exactly once')
    return out


def rules(spec):
    """First match wins: guard j applies only where no earlier guard does."""
    enums, out = spec['enums'], {}
    for name, values in enums.items():
        moves = spec['transitions'].get(name, [])
        guards = [expand(guard, enums) for guard, _ in moves]
        earlier = []
        effective = []
        for guard in guards:
            effective.append(guard if not earlier else
                             '(' + guard + ') && !(' + ' || '.join(earlier) + ')')
            earlier.append('(' + guard + ')')
        stay = ('!(' + ' || '.join(earlier) + ')') if earlier else 'true'
        for index, bit in enumerate(bits(name, values)):
            taken = ['(' + guard + ')' for guard, (_, target) in zip(effective, moves)
                     if values.index(target) >> index & 1]
            parts = taken + ['(' + stay + ' && ' + bit + ')']
            out[bit] = ' || '.join(parts)
    for flag, source in spec.get('flag_rules', {}).items():
        out[flag] = expand(source, enums)
    if set(out) != set(state_names(spec)):
        raise ValueError('every enum and flag needs a rule')
    return out


def compile_spec(spec):
    """The machine spec `sg machine-create` takes, with unused codes excluded."""
    names = state_names(spec)
    declared = ''.join('fact ' + name + ': bool\n' for name in sorted(names + list(spec['events'])))
    state_only = ''.join('fact ' + name + ': bool\n' for name in names)
    invariant = ' && '.join(['(' + expand(spec['invariant'], spec['enums']) + ')'] + unused(spec['enums']))
    return dict(
        state=names, events=sorted(spec['events']),
        initial=[flatten(spec, spec['initial'])],
        goals=[flatten(spec, goal) for goal in spec['goals']],
        invariant=state_only + 'check ' + invariant + '\n',
        next={bit: declared + 'check ' + source + '\n' for bit, source in rules(spec).items()},
        max_atp=spec['max_atp'])


class UnusedCode(ValueError):
    """A state that names no value. The checker refuses these; this only reads."""


def decode_state(state, spec):
    out = {}
    for name, values in spec['enums'].items():
        code = sum(bool(state[bit]) << index for index, bit in enumerate(bits(name, values)))
        if code >= len(values):
            raise UnusedCode('code ' + format(code, 'b') + ' names no value of ' + name)
        out[name] = values[code]
    for flag in spec.get('flags', []):
        out[flag] = bool(state[flag])
    return out


def decode_trace(trace, spec):
    """A refutation trace as named values; an unused code is reported, not hidden."""
    def safely(state):
        try:
            return decode_state(state, spec)
        except UnusedCode as exc:
            return dict(unused_code=str(exc))
    return [dict(event=None, state=safely(trace['initial']))] + [
        dict(event=step['event'], state=safely(step['state'])) for step in trace['steps']]


def main(argv=None):
    parser = argparse.ArgumentParser(description='Compile an enum spec into a machine spec.')
    parser.add_argument('spec', type=Path)
    parser.add_argument('--output', type=Path)
    arguments = parser.parse_args(argv)
    compiled = compile_spec(json.loads(arguments.spec.read_text()))
    text = json.dumps(compiled, indent=2, sort_keys=True) + '\n'
    if arguments.output:
        arguments.output.write_text(text)
    else:
        sys.stdout.write(text)
    return 0


if __name__ == '__main__':
    sys.exit(main())
