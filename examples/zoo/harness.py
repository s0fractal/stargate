"""Run every zoo system through the same pipeline and write one table.

Each system file holds two rule sets over the same state, events, initial state,
invariant and goals. The harness declares the facts, builds both machines, asks
`evidence.produce` for a proof, and runs both repair strategies on the broken one.

    python examples/zoo/harness.py                 # rewrite examples/zoo/results.json
    python examples/zoo/harness.py --print         # the README table, to stdout

The numbers are measurements. Expectations live in REGISTRY.md and are never
adjusted to them; where they disagree, the row is listed in `mismatches`.
"""
import argparse
import json
from pathlib import Path
import re
import sys

HERE = Path(__file__).resolve().parent
STRATEGIES = ('one-edit', 'trace')
REGISTRY_KEYS = {'philosophers': ('philosophers (honest)', 'philosophers (broken)')}


def load(directory=None):
    directory = Path(directory or HERE / 'systems')
    return [json.loads(path.read_text()) for path in sorted(directory.glob('*.json'))]


def model(system, which):
    names = sorted(system['state'] + system['events'])
    facts = ''.join('fact ' + name + ': bool\n' for name in names)
    state_facts = ''.join('fact ' + name + ': bool\n' for name in sorted(system['state']))
    return dict(state=sorted(system['state']), events=sorted(system['events']),
                initial=system['initial'], goals=system['goals'],
                max_atp=system['max_atp'],
                invariant=state_facts + 'check ' + system['invariant'] + '\n',
                next={name: facts + 'check ' + system[which][name] + '\n'
                      for name in system['state']})


def registered(text):
    """Parse the pre-registered table of REGISTRY.md into per-system cells."""
    rows = {}
    for line in text.splitlines():
        cells = [cell.strip() for cell in line.strip().strip('|').split('|')]
        if len(cells) == 6 and cells[0] not in ('system', '---'):
            rows[re.sub(r'\*\*', '', cells[0])] = [re.sub(r'\*\*', '', c) for c in cells[1:]]
    return rows


def expectation(rows, name):
    keys = REGISTRY_KEYS.get(name, (name,))
    cells = [None] * 5
    for key in keys:
        for index, cell in enumerate(rows.get(key, [])):
            if cell not in ('—', 'measure', 'none') and cells[index] is None:
                cells[index] = cell
    evidence = {'broken': cells[1], 'correct': cells[2] and cells[2].split(' (')[0]}
    search = {}
    for strategy, cell in zip(STRATEGIES, cells[3:5]):
        match = re.fullmatch(r'(\w+) at (\d+)', cell or '')
        search[strategy] = match and dict(status=match.group(1), attempted=int(match.group(2)))
    if evidence['broken'] is None and evidence['correct'] is None and not any(search.values()):
        return None
    return dict(evidence=evidence, search=search)


def measure(systems):
    from stargate import evidence, lab, machine
    from stargate.canonical import decode
    rows = []
    registry = {}
    for path in sorted(HERE.glob('REGISTRY*.md')):
        registry.update(registered(path.read_text()))
    for system in systems:
        row = dict(name=system['name'], title=system['title'],
                   state_bits=len(system['state']), event_bits=len(system['events']))
        proofs = {}
        for which in ('correct', 'broken'):
            raw = machine.create(model(system, which))
            report, packet = evidence.produce(raw, lab.identity(raw))
            proofs[which] = (raw, report, packet)
        measured = dict(evidence={which: proofs[which][1]['status'] for which in proofs}, search={})
        packet = proofs['broken'][2]
        row['refutation'] = None
        if packet is not None and 'refutation' in decode(packet):
            claim = decode(packet)['claim']
            row['refutation'] = dict(kind=claim['kind'],
                                     trace_steps=len(claim['trace']['steps']) if claim['kind'] == 'unsafe' else None,
                                     excluded_states=len(claim['states']) if claim['kind'] == 'unreachable_goal' else None,
                                     bytes=len(packet))
        certificate = proofs['correct'][2]
        row['certificate'] = (None if certificate is None or 'certificate' not in decode(certificate)
                              else dict(states=len(decode(certificate)['states']), bytes=len(certificate)))
        raw, _, _ = proofs['broken']
        for strategy in STRATEGIES:
            report, _ = evidence.repair_search(raw, lab.identity(raw), strategy=strategy,
                                               max_candidates=system['max_candidates'])
            status = report['status']
            if status == 'search_incomplete':
                status = report.get('reason') or status
            measured['search'][strategy] = dict(status=status, attempted=report['attempted'])
        row['measured'] = measured
        want = expectation(registry, system['name'])
        row['registered'] = want and dict(
            evidence={k: v for k, v in want['evidence'].items() if v is not None},
            search={k: v for k, v in want['search'].items() if v is not None})
        rows.append(row)
    return rows


def disagrees(row):
    want, got = row['registered'], row['measured']
    if want is None:
        return False
    for which, status in want['evidence'].items():
        if got['evidence'][which] != status:
            return True
    for strategy, cell in want['search'].items():
        if got['search'][strategy] != cell:
            return True
    return False


def table(rows):
    header = ('| system | bits (state/event) | refutation | trace | certificate | '
              'one-edit | trace search |\n| --- | --- | --- | --- | --- | --- | --- |')
    lines = [header]
    for row in rows:
        refutation = row['refutation']
        search = row['measured']['search']
        lines.append('| `{name}` | {s}/{e} | {kind} | {trace} | {cert} | {one} | {tr} |'.format(
            name=row['name'], s=row['state_bits'], e=row['event_bits'],
            kind='—' if refutation is None else refutation['kind'],
            trace=('—' if refutation is None else
                   '{} steps'.format(refutation['trace_steps']) if refutation['kind'] == 'unsafe'
                   else '{} states excluded'.format(refutation['excluded_states'])),
            cert=('—' if row['certificate'] is None else
                  '{} states, {} B'.format(row['certificate']['states'], row['certificate']['bytes'])),
            one='{status} at {attempted}'.format(**search['one-edit']),
            tr='{status} at {attempted}'.format(**search['trace'])))
    return '\n'.join(lines)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--print', dest='show', action='store_true', help='print the table, write nothing')
    parser.add_argument('--output', type=Path, default=HERE / 'results.json')
    arguments = parser.parse_args(argv)
    rows = measure(load())
    if arguments.show:
        print(table(rows))
        return 0
    document = dict(rows=rows, mismatches=sorted(row['name'] for row in rows if disagrees(row)))
    arguments.output.write_text(json.dumps(document, indent=2, sort_keys=True) + '\n')
    print(table(rows))
    print('mismatches with REGISTRY.md:', ', '.join(document['mismatches']) or 'none')
    return 0


if __name__ == '__main__':
    sys.exit(main())
