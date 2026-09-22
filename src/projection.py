"""RED STUB: projection-1 does not exist yet."""
from .canonical import canon, decode


def project(raw, expected_machine):
    return dict(status='projected'), canon({})


def inspect(raw):
    return decode(raw)
