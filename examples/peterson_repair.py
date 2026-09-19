"""Peterson's mutual exclusion as a Stargate repair edge (written against build 37).

Five state bits, one scheduler event. The 'broken' model makes each process claim
the turn for itself; the repair makes it yield to the other. Initial state, events,
safety invariant and both goals are identical, so only `next` changes.

Run inside an environment where `stargate` is installed, in an empty directory:
    python examples/peterson_repair.py peterson-demo
In that new directory writes broken.json (refutation), peterson.json (certificate), broken-id (ModelID).
Also writes broken-world.json and peterson-world.json for repeatable search.
Then: sg certificate-repair-pack broken.json peterson.json --output repair.json
"""
from pathlib import Path
from stargate import evidence, lab, machine

STATE, EVENTS = ['a0', 'a1', 'b0', 'b1', 't'], ['s']   # pc0=(a1,a0) pc1=(b1,b0) turn; s = who moves
ALL = ''.join(f'fact {n}: bool\n' for n in sorted(STATE + EVENTS))
ONLY_STATE = ''.join(f'fact {n}: bool\n' for n in STATE)
# pc encoding: 00 idle, 01 want, 10 wait, 11 critical


def process(p, move, may_enter):
    hi, lo = p + '1', p + '0'
    step_hi = f'({hi} && !{lo}) || (!{hi} && {lo})'
    step_lo = f'(!{hi} && !{lo}) || ({hi} && !{lo} && ({may_enter}))'
    return {hi: f'({move} && ({step_hi})) || (!({move}) && {hi})',
            lo: f'({move} && ({step_lo})) || (!({move}) && {lo})'}


def model(yield_turn):
    rules = {}
    rules.update(process('a', '!s', '(!b1 && !b0) || !t'))   # enter if other idle or turn is mine
    rules.update(process('b', 's', '(!a1 && !a0) || t'))
    p0_sets, p1_sets = '!s && !a1 && a0', 's && !b1 && b0'   # the want -> wait step writes turn
    rules['t'] = (f'({p0_sets}) || (t && !({p1_sets}))' if yield_turn      # turn := other
                  else f'({p1_sets}) || (t && !({p0_sets}))')              # turn := self (the slip)
    return dict(
        state=STATE, events=EVENTS, max_atp=4000,
        initial=[dict.fromkeys(STATE, False)],
        next={k: ALL + 'check ' + v for k, v in rules.items()},
        invariant=ONLY_STATE + 'check !(a1 && a0 && b1 && b0)',
        goals=[dict(a0=True, a1=True, b0=False, b1=False, t=True),      # P0 alone in critical
               dict(a0=False, a1=False, b0=True, b1=True, t=False)])    # P1 alone in critical


def main():
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument('output', type=Path, help='new directory for the two proofs')
    output = p.parse_args().output
    output.mkdir(mode=0o700)
    for name, yield_turn, expected in [('broken', False, 'verified_refutation'),
                                       ('peterson', True, 'verified_certificate')]:
        raw = machine.create(model(yield_turn))
        report, proof = evidence.produce(raw, lab.identity(raw))
        (output / (name + '-world.json')).write_bytes(raw)
        assert report['status'] == expected, report
        (output / (name + '.json')).write_bytes(proof)
        (output / (name + '-id')).write_text(report['model_id'])
        print(name, report['status'], report['model_id'])


if __name__ == '__main__':
    main()
