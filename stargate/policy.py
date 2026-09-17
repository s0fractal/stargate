"""Small boolean WPL authoring subset, lowered to the existing SKI kernel.

Church boolean lowering adapted from Warrant impl/ski_policy.py (MIT,
Copyright 2025–2026 s0fractal). No policy runtime is added to verification.
"""
import re
from dataclasses import dataclass

from . import kernel as k
from .records import canon, decode, run_check, create_record, record_id

MAX_SOURCE_BYTES = 8192
MAX_TOKENS = 256
DEFAULT_MAX_ATP = 100_000
TOKEN = re.compile(r'\s+|#[^\n]*|&&|\|\||[!():=]|[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)*')
RESERVED = {'fact', 'check', 'bool', 'true', 'false'}


class PolicyError(ValueError):
    """Unsupported or invalid author input; no record should be emitted."""


class CompilerBug(RuntimeError):
    """Compiler output disagrees with the source interpreter or emission gate."""


def parse(source):
    if not isinstance(source, str):
        raise PolicyError('source must be text')
    try:
        if len(source.encode('utf-8')) > MAX_SOURCE_BYTES:
            raise PolicyError('source exceeds 8192 bytes')
    except UnicodeError as exc:
        raise PolicyError('source contains invalid Unicode') from exc
    tokens, pos = [], 0
    while pos < len(source):
        m = TOKEN.match(source, pos)
        if not m:
            raise PolicyError(f'unsupported token at character {pos}')
        text = m.group()
        if not text.isspace() and not text.startswith('#'):
            tokens.append(text)
        pos = m.end()
    if len(tokens) > MAX_TOKENS:
        raise PolicyError('policy exceeds 256 tokens')
    cursor = 0
    facts, used = {}, set()
    def peek():
        return tokens[cursor] if cursor < len(tokens) else None
    def take(expected=None):
        nonlocal cursor
        token = peek()
        if token is None or (expected is not None and token != expected):
            raise PolicyError(f'expected {expected or "expression"}, got {token!r}')
        cursor += 1
        return token
    while peek() == 'fact':
        take('fact'); name = take()
        if name in RESERVED or re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)*', name) is None:
            raise PolicyError('invalid fact name')
        if name in facts:
            raise PolicyError('duplicate fact: ' + name)
        take(':'); take('bool'); take('=')
        value = take()
        if value not in ('true', 'false'):
            raise PolicyError('boolean facts require true or false')
        facts[name] = value == 'true'
    take('check')
    def atom(depth):
        if depth > 32:
            raise PolicyError('expression nesting exceeds 32')
        if peek() == '!':
            take('!')
            return ('not', atom(depth + 1))
        if peek() == '(':
            take('('); result = disjunction(depth + 1); take(')')
            return result
        name = take()
        if name in ('true', 'false'):
            return ('const', name == 'true')
        if name not in facts:
            raise PolicyError('unknown fact: ' + name)
        used.add(name)
        return ('fact', name)
    def conjunction(depth):
        expr = atom(depth)
        while peek() == '&&':
            take('&&'); expr = ('and', expr, atom(depth))
        return expr
    def disjunction(depth):
        expr = conjunction(depth)
        while peek() == '||':
            take('||'); expr = ('or', expr, conjunction(depth))
        return expr
    expression = disjunction(0)
    if peek() is not None:
        raise PolicyError('expected exactly one check and no trailing tokens')
    if used != set(facts):
        raise PolicyError('unused facts: ' + ', '.join(sorted(set(facts) - used)))
    return expression, facts


def interpret(expr, facts):
    tag = expr[0]
    if tag == 'const': return expr[1]
    if tag == 'fact': return facts[expr[1]]
    if tag == 'not': return not interpret(expr[1], facts)
    if tag == 'and': return interpret(expr[1], facts) and interpret(expr[2], facts)
    if tag == 'or': return interpret(expr[1], facts) or interpret(expr[2], facts)
    raise CompilerBug('unknown expression')


def lower(expr, facts):
    true, false = ('thunk', k.K_H), ('thunk', k.FALSE_H)
    def apply(f, a, b): return ('app', ('app', f, a), b)
    tag = expr[0]
    if tag == 'const': return true if expr[1] else false
    if tag == 'fact': return true if facts[expr[1]] else false
    if tag == 'not': return apply(lower(expr[1], facts), false, true)
    if tag == 'and': return apply(lower(expr[1], facts), lower(expr[2], facts), false)
    if tag == 'or': return apply(lower(expr[1], facts), true, lower(expr[2], facts))
    raise CompilerBug('unknown expression')


@dataclass
class CompiledPolicy:
    check: dict
    objects: dict
    value: bool
    atp_spent: int


def compile_source(source, *, max_atp=DEFAULT_MAX_ATP):
    if type(max_atp) is not int or not 0 <= max_atp <= k.VERIFIER_LIMITS['max_atp']:
        raise PolicyError('compile limit must be an integer within the verifier ATP ceiling')
    expr, facts = parse(source)
    value = interpret(expr, facts)
    term = lower(expr, facts)
    objects = {k.FALSE_H: k.FALSE_BYTES}
    def materialize(t):
        if t[0] == 'app':
            materialize(t[1]); materialize(t[2])
            raw = k.term_bytes(t)
            objects[k.sha(raw)] = raw
    materialize(term)
    h = k.term_hash(term)
    receipt = k.eval_receipt(h, max_atp, objects, k.VERIFIER_LIMITS)
    if receipt.exit != 'normal_form':
        raise PolicyError('policy did not finish within the compile budget')
    expected_value_hash = k.K_H if value else k.FALSE_H
    if receipt.result_hash != expected_value_hash:
        raise CompilerBug('SKI result disagrees with source interpreter')
    # ALWAYS expect TRUE: compiling a false predicate must not pin FALSE and
    # thereby turn a false policy into an accepted computation claim.
    check = decode(canon(dict(term=h.hex(), atp=receipt.atp_spent,
                             expect=k.K_H.hex(), exit='normal_form',
                             environment=sorted(h.hex() for h in objects))))
    outcome = run_check(check, objects)
    if (outcome.result_hash != expected_value_hash.hex() or outcome.exit != 'normal_form'
            or outcome.atp_spent != receipt.atp_spent
            or outcome.verdict != ('pass' if value else 'fail')):
        raise CompilerBug('serialized check failed exact-budget re-execution')
    return CompiledPolicy(check, objects, value, receipt.atp_spent)


def author_policy(source, store, key, *, max_atp=DEFAULT_MAX_ATP):
    compiled = compile_source(source, max_atp=max_atp)
    # Sign against the same staged byte environment before emitting artifacts.
    envelope = create_record(compiled.check, compiled.objects, key)
    for raw in compiled.objects.values():
        store.put(raw)
    source_object = store.put(source.encode('utf-8'))
    envelope_object = store.put(canon(envelope))
    return dict(record=record_id(envelope['body']), object=envelope_object,
                decision=envelope['body']['decision'], source_object=source_object,
                policy_value=compiled.value, atp_spent=compiled.atp_spent,
                check=compiled.check)
