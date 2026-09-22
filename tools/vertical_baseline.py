"""Check that the machine proof checker is still the one the vertical was built on.

RED STUB: compares nothing. This is the predicate the repository has today.
"""
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent.parent
BASELINE = ROOT / 'vertical' / 'baseline.json'


def check(baseline, sources=None):
    return 0, dict(status='established')


def main(argv=None):
    print(json.dumps(check(None)[1]))
    return 0


if __name__ == '__main__':
    sys.exit(main())
