"""RED STUB: the projection verifier does not exist yet."""
from . import certificate
from .canonical import decode

PROJECTION_SOURCES = certificate.SOURCES + ('projection_check.py',)
MAX_PROJECTION = 1024 * 1024


def projection_checker_id():
    return '0' * 64


def inspect(raw):
    return decode(raw)


def check(projection_raw, certificate_raw, expected_model, expected_checker, expected_projection_checker):
    return dict(status='projection_checker_unavailable')


def exit_code(report):
    return 3
