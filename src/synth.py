"""Ownership-safe safety synthesis for repair (producer only).

Stub: the registration (docs/SYNTH_REGISTRY.md) is committed; the synthesis is not.
"""


def synthesize(doc):
    return dict(status='not_implemented')


class Unrepresentable(Exception):
    def __init__(self, reason):
        super().__init__(reason)
        self.reason = reason


def emit(table, inputs):
    return 'check false\n'


def table_of(source, inputs):
    return []
