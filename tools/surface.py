"""Inventory of the command surface: what exists, and what mentions it.

Outside every checked closure. It counts references; it does not judge. The
judgement is in SURFACE.md, written by a person and reviewed by a person.

    python tools/surface.py            # rewrite SURFACE.md's table
    python tools/surface.py --check    # 0 when the committed table is current, 4 when stale
"""
import argparse
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parent.parent
SURFACE = ROOT / 'SURFACE.md'
BEGIN, END = '<!-- inventory: generated -->', '<!-- inventory: end -->'
SOURCES = {'tests': ROOT / 'tests', 'docs': None, 'examples': ROOT / 'examples',
           'integration': ROOT / 'integration'}
DOCS = ('README.md', 'VISION.md', 'SPEC.md', 'ANCHORS.md')


def commands():
    from stargate import cli
    parser = cli.parser()
    for action in parser._subparsers._group_actions:
        for name, sub in action.choices.items():
            yield name, (sub.description or _help(action, name) or '').strip()


def _help(action, name):
    for choice in action._choices_actions:
        if choice.dest == name:
            return choice.help
    return ''


def mentions(name, paths, *, quoted):
    """Count invocations, not the English word: `'verify'` in code, `sg verify` in prose."""
    pattern = (re.compile(r'[\'"]' + re.escape(name) + r'[\'"]') if quoted
               else re.compile(r'(?<![\w-])sg\s+' + re.escape(name) + r'(?![\w-])'
                               + r'|`' + re.escape(name) + r'`'))
    total = 0
    for path in paths:
        try:
            total += len(pattern.findall(path.read_text()))
        except (OSError, UnicodeDecodeError):
            continue
    return total


def inventory():
    trees = {'tests': sorted((ROOT / 'tests').rglob('*.py')),
             'docs': [ROOT / name for name in DOCS],
             'examples': sorted((ROOT / 'examples').rglob('*')),
             'integration': sorted((ROOT / 'integration').rglob('*.py'))}
    rows = []
    for name, help_text in sorted(commands()):
        counts = {label: mentions(name, paths, quoted=label != 'docs')
                  for label, paths in trees.items()}
        rows.append(dict(command=name, help=help_text, **counts))
    return rows


def table(rows):
    lines = ['| command | what it does | tests | docs | examples | integration |',
             '| --- | --- | ---: | ---: | ---: | ---: |']
    for row in rows:
        lines.append('| `{command}` | {help} | {tests} | {docs} | {examples} | {integration} |'.format(**row))
    lines.append('')
    lines.append('{} commands. `tests`, `examples` and `integration` count the quoted '
                 'command name in those files; `docs` counts `sg NAME` or `NAME` in '
                 'backticks across README, VISION, SPEC and ANCHORS. These are mentions, '
                 'not coverage.'.format(len(rows)))
    return '\n'.join(lines)


def rewrite(text, block):
    head, _, rest = text.partition(BEGIN)
    _, _, tail = rest.partition(END)
    return head + BEGIN + '\n\n' + block + '\n\n' + END + tail


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', action='store_true')
    arguments = parser.parse_args(argv)
    block = table(inventory())
    try:
        text = SURFACE.read_text()
    except OSError as exc:
        if arguments.check:
            print('invalid: ' + str(exc)); return 2
        text = '# Command surface\n\n' + BEGIN + '\n\n' + END + '\n'
    updated = rewrite(text, block)
    if arguments.check:
        if updated != text:
            print('refused: SURFACE.md does not match the current command surface')
            return 4
        print('established: {} commands, table is current'.format(len(inventory())))
        return 0
    SURFACE.write_text(updated)
    print(block)
    return 0


if __name__ == '__main__':
    sys.exit(main())
