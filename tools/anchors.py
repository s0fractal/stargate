"""Check that ANCHORS.md describes this source, and name a snapshot after everything it anchors.

Outside every checked closure. It compares a table in this repository with source
in the same repository, so it catches a table that was not updated, or updated
inconsistently, and nothing else. An independently obtained snapshot is still the
only thing that makes an anchor worth anything.

    python tools/anchors.py --check     # 0 matched, 4 refused, 2 invalid input
    python tools/anchors.py --tag       # the tag name this source may carry
    python tools/anchors.py --check-tag NAME

A snapshot is named `snapshot-` plus the first twelve hex of the SHA-256 of the
canonical JSON object mapping each anchored closure, and "Offline launcher", to its
digest. A change to any one of them is a new name. Every `snapshot-` label in the
table must be the composite of its own rows; `build-37` and `build-38` are history.

Exit codes follow the repository: 0 established, 1 error, 2 invalid input,
4 checked and refused.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parent.parent
CLOSURES = ('Machine proof checker', 'Boolean lab runtime', 'Experiment controller', 'Projection checker')
ROW = re.compile(r'^\|\s*`([^`]+)`\s*\|\s*([^|]+?)\s*\|\s*`([0-9a-f]{64})`\s*\|\s*`([0-9a-f]{64})`\s*\|$')


def current():
    """Recomputed from the installed package, never read from the table."""
    from stargate import certificate, experiment, lab, projection_check
    return {'Machine proof checker': certificate.checker_id(),
            'Boolean lab runtime': lab.runtime_digest(lab.runtime_sources()),
            'Experiment controller': experiment.controller_id(),
            'Projection checker': projection_check.projection_checker_id()}


def launcher():
    return hashlib.sha256((ROOT / 'src' / 'replay.py').read_bytes()).hexdigest()


def snapshots(text):
    table = {}
    for line in text.splitlines():
        match = ROW.match(line.strip())
        if match is None:
            continue
        label, closure, source, launched = match.groups()
        if closure not in CLOSURES:
            raise ValueError('unknown closure in the table: ' + closure)
        rows = table.setdefault(label, {})
        if closure in rows:
            raise ValueError('snapshot ' + label + ' names ' + closure + ' twice')
        rows[closure] = (source, launched)
    return table


def match(table, digests, launched):
    """Labels that describe exactly this source, and why the others do not."""
    matched, reasons = [], {}
    for label, rows in sorted(table.items()):
        missing = [closure for closure in CLOSURES if closure not in rows]
        if missing:
            reasons[label] = 'no row for ' + ', '.join(missing)
            continue
        wrong = [closure for closure in CLOSURES if rows[closure][0] != digests[closure]]
        if any(rows[closure][1] != launched for closure in CLOSURES):
            wrong.append('offline launcher')
        if wrong:
            reasons[label] = 'differs in ' + ', '.join(wrong)
        else:
            matched.append(label)
    return matched, reasons


def snapshot_label(digests, launched):
    body = dict(digests, **{'Offline launcher': launched})
    canonical = json.dumps(body, sort_keys=True, separators=(',', ':'), ensure_ascii=False)
    return 'snapshot-' + hashlib.sha256(canonical.encode()).hexdigest()[:12]


def inconsistent(table):
    """snapshot- labels that are not the composite of their own rows."""
    wrong = []
    for label, rows in sorted(table.items()):
        if not label.startswith('snapshot-'):
            continue
        launchers = {launched for _, launched in rows.values()}
        if set(rows) != set(CLOSURES) or len(launchers) != 1 or snapshot_label(
                {closure: source for closure, (source, _) in rows.items()}, launchers.pop()) != label:
            wrong.append(label)
    return wrong


def report(**fields):
    print(json.dumps(fields, sort_keys=True))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--anchors', type=Path, default=ROOT / 'ANCHORS.md')
    parser.add_argument('--check', action='store_true')
    parser.add_argument('--tag', action='store_true')
    parser.add_argument('--check-tag')
    arguments = parser.parse_args(argv)
    if not (arguments.check or arguments.tag or arguments.check_tag):
        parser.error('choose --check, --tag or --check-tag')
    digests = current()
    expected = snapshot_label(digests, launcher())
    if arguments.tag and not (arguments.check or arguments.check_tag):
        print(expected)
        return 0
    try:
        table = snapshots(arguments.anchors.read_text())
    except OSError as exc:
        report(status='invalid', error=str(exc)); return 2
    except ValueError as exc:
        report(status='invalid', error=str(exc)); return 2
    if arguments.check_tag is not None and arguments.check_tag != expected:
        report(status='refused', reason='tag_not_derived_from_snapshot',
               tag=arguments.check_tag, expected=expected); return 4
    wrong = inconsistent(table)
    if wrong:
        report(status='refused', reason='snapshot_label_not_derived_from_its_rows',
               snapshots=wrong); return 4
    matched, reasons = match(table, digests, launcher())
    if not matched:
        report(status='refused', reason='no_snapshot_describes_this_source',
               expected_tag=expected, rejected=reasons); return 4
    if len(matched) > 1:
        report(status='refused', reason='several_snapshots_claim_this_source',
               snapshots=matched); return 4
    label = matched[0]
    if label != expected:
        report(status='refused', reason='snapshot_label_not_derived_from_digests',
               snapshot=label, expected=expected); return 4
    report(status='established', snapshot=label, tag=expected, rejected=reasons)
    return 0


if __name__ == '__main__':
    sys.exit(main())
