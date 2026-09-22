"""Check that the machine proof checker is still the one the vertical was built on.

Outside every checked closure. `vertical/baseline.json` names the machine proof
checker digest and the temperature the projection vertical starts from; this gate
recomputes both from the installed package and refuses any difference. The build
number may rise during the vertical, never fall below the baseline.

    python tools/vertical_baseline.py --check    # 0 established, 4 refused, 2 invalid input

It compares this repository with a file in this repository. It catches a closure
edit nobody meant to make; a deliberate re-baseline edits the file in its own PR.
It is not ANCHORS.md and says nothing about which snapshot a digest belongs to.
"""
import argparse
import json
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parent.parent
BASELINE = ROOT / 'vertical' / 'baseline.json'
FIELDS = ('build', 'machine_checker', 'temperature')


class Invalid(ValueError):
    pass


def validate(baseline):
    if type(baseline) is not dict or set(baseline) != set(FIELDS):
        raise Invalid('baseline must have exactly the fields ' + ', '.join(FIELDS))
    if type(baseline['build']) is not str or re.fullmatch(r'[1-9][0-9]*', baseline['build']) is None:
        raise Invalid('build must be a decimal build number as text')
    if type(baseline['machine_checker']) is not str or re.fullmatch(r'[0-9a-f]{64}', baseline['machine_checker']) is None:
        raise Invalid('machine_checker must be 64 lower-case hex digits')
    if type(baseline['temperature']) is not int:
        raise Invalid('temperature must be an integer')
    return baseline


def check(baseline, sources=None):
    """Return (exit code, report). `sources` replaces the installed checker closure."""
    from stargate import certificate, KELVIN
    from stargate.build import __version__
    try:
        validate(baseline)
    except Invalid as exc:
        return 2, dict(status='invalid', error=str(exc))
    current = dict(build=__version__, temperature=KELVIN,
                   machine_checker=certificate.identity(sources) if sources is not None
                   else certificate.checker_id())
    report = dict(baseline=baseline, current=current)
    if current['machine_checker'] != baseline['machine_checker']:
        return 4, dict(report, status='refused', reason='machine_checker_changed')
    if current['temperature'] != baseline['temperature']:
        return 4, dict(report, status='refused', reason='temperature_changed')
    if int(current['build']) < int(baseline['build']):
        return 4, dict(report, status='refused', reason='build_older_than_baseline')
    return 0, dict(report, status='established')


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('--check', action='store_true', required=True)
    parser.add_argument('--baseline', type=Path, default=BASELINE)
    arguments = parser.parse_args(argv)
    try:
        baseline = json.loads(arguments.baseline.read_text())
    except (OSError, ValueError) as exc:
        print(json.dumps(dict(status='invalid', error=str(exc))))
        return 2
    code, report = check(baseline)
    print(json.dumps(report, sort_keys=True))
    return code


if __name__ == '__main__':
    sys.exit(main())
