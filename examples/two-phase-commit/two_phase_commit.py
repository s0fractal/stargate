"""A truncated two-phase commit, written twice over the same rules.

Six state bits hold a coordinator and two participants. The environment has three
independent inputs -- A votes, B votes, the coordinator times out -- and any
combination can happen in one step, including a vote arriving exactly as the
coordinator gives up. Three independent inputs are eight combinations; two event
bits offer four, so `simultaneous()` cannot be submitted today.

`serialized()` carries the same three actions on two bits by allowing at most one
per step. The rules are identical: only what may happen at once differs.

    python examples/two-phase-commit/two_phase_commit.py

prints the refusal, both verdicts, and the comparison of what each one reaches.
This file is outside every checked closure and proves nothing by itself.
"""
import itertools
import sys

STATE = ['a0', 'a1', 'b0', 'b1', 'c0', 'c1']
# participant: 00 idle, 01 yes, 10 no  (11 names nothing and the invariant forbids it)
# coordinator: 00 init, 01 wait, 10 commit, 11 abort
IDLE = '(!{p}1 && !{p}0)'
YES = '(!{p}1 && {p}0)'
NO = '({p}1 && !{p}0)'
INIT, WAIT, COMMIT, ABORT = '(!c1 && !c0)', '(!c1 && c0)', '(c1 && !c0)', '(c1 && c0)'


def participant(name, votes, timeout):
    idle, yes, no = (form.format(p=name) for form in (IDLE, YES, NO))
    return {name + '0': '({idle} && {votes}) || {yes}'.format(idle=idle, votes=votes, yes=yes),
            name + '1': '({idle} && ({timeout}) && !({votes})) || {no}'.format(
                idle=idle, timeout=timeout, votes=votes, no=no)}


def coordinator(timeout, *, broken):
    both_yes = YES.format(p='a') + ' && ' + YES.format(p='b')
    any_no = '(' + NO.format(p='a') + ' || ' + NO.format(p='b') + ')'
    enough = YES.format(p='a') if broken else '(' + both_yes + ')'
    abort = '({wait} && (({timeout}) || {any_no}))'.format(wait=WAIT, timeout=timeout, any_no=any_no)
    commit = '({wait} && {enough} && !(({timeout}) || {any_no}))'.format(
        wait=WAIT, enough=enough, timeout=timeout, any_no=any_no)
    return {'c1': '{commit} || {abort} || c1'.format(commit=commit, abort=abort),
            'c0': '{init} || {abort} || (c0 && c1) || ({wait} && !{commit} && !{abort})'.format(
                init=INIT, abort=abort, wait=WAIT, commit=commit)}


def rules(votes_a, votes_b, timeout, *, broken=False):
    out = {}
    out.update(participant('a', votes_a, timeout))
    out.update(participant('b', votes_b, timeout))
    out.update(coordinator(timeout, broken=broken))
    return out


def spec(events, source, *, broken=False):
    names = sorted(STATE + events)
    declared = ''.join('fact ' + name + ': bool\n' for name in names)
    state_only = ''.join('fact ' + name + ': bool\n' for name in STATE)
    invariant = ('!{commit} || ({yes_a} && {yes_b})'.format(
        commit=COMMIT, yes_a=YES.format(p='a'), yes_b=YES.format(p='b'))
        + ' && !(a1 && a0) && !(b1 && b0)')
    return dict(
        state=STATE, events=events,
        initial=[dict.fromkeys(STATE, False)],
        goals=[dict(a0=True, a1=False, b0=True, b1=False, c0=False, c1=True),   # commit, both yes
               dict(a0=False, a1=True, b0=False, b1=True, c0=True, c1=True)],   # abort, both no
        invariant=state_only + 'check ' + invariant + '\n',
        next={name: declared + 'check ' + body + '\n' for name, body in source.items()},
        max_atp=4000)


def simultaneous(*, broken=False):
    """Three independent inputs. Refused today: events take at most two bits."""
    return spec(['to', 'ya', 'yb'], rules('ya', 'yb', 'to', broken=broken), broken=broken)


def serialized(*, broken=False):
    """The same rules, one action per step: 00 nothing, 01 A, 10 B, 11 timeout."""
    votes_a, votes_b, timeout = '(!e1 && e0)', '(e1 && !e0)', '(e1 && e0)'
    return spec(['e0', 'e1'], rules(votes_a, votes_b, timeout, broken=broken), broken=broken)


NO_RACE = ('!((!c1 && c0) && ((!a1 && a0) && (b1 && !b0) || (a1 && !a0) && (!b1 && b0)))')
"""A property that forbids exactly the race: one vote in, one timed out, still waiting."""


def name(state):
    """A reachable state as words, for reading the comparison."""
    values = dict(zip(STATE, state))
    def label(bit):
        return {(False, False): 'idle', (True, False): 'yes', (False, True): 'no',
                (True, True): '??'}[(values[bit + '0'], values[bit + '1'])]
    coordinator = {(False, False): 'init', (True, False): 'wait',
                   (False, True): 'commit', (True, True): 'abort'}[(values['c0'], values['c1'])]
    return 'A=' + label('a') + ' B=' + label('b') + ' C=' + coordinator


def value(expression, facts):
    """An evaluator of my own: the checker refuses to look at three event bits."""
    return bool(eval(expression.replace('&&', ' and ').replace('||', ' or ').replace('!', ' not '),
                     {'__builtins__': {}}, dict(facts)))


def reachable(model):
    """Every state the model can be in, as a set of tuples over STATE."""
    events = model['events']
    source = {name: text.split('check ')[1].strip() for name, text in model['next'].items()}
    start = tuple(model['initial'][0][name] for name in STATE)
    seen, queue = {start}, [start]
    while queue:
        current = queue.pop()
        for row in itertools.product([False, True], repeat=len(events)):
            facts = dict(zip(STATE, current)); facts.update(zip(events, row))
            following = tuple(value(source[name], facts) for name in STATE)
            if following not in seen:
                seen.add(following); queue.append(following)
    return seen


def main():
    from stargate import evidence, lab, machine
    from stargate.canonical import InvalidRecord
    try:
        machine.create(simultaneous())
        print('simultaneous: accepted')
    except InvalidRecord as exc:
        print('simultaneous: refused by machine-create:', exc)
    for label, broken in (('serialized', False), ('serialized, broken coordinator', True)):
        raw = machine.create(serialized(broken=broken))
        report, _ = evidence.produce(raw, lab.identity(raw))
        print(label + ':', report['status'])
    three, two = reachable(simultaneous()), reachable(serialized())
    print('states reachable with three independent inputs:', len(three))
    print('states reachable with two event bits:          ', len(two))
    print('difference:', sorted(three ^ two) or 'none')
    return 0


if __name__ == '__main__':
    sys.exit(main())
