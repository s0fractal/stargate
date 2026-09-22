"""RED STUB: the table runtime does not exist yet."""
import json

RUNTIME_ID = 'python-table-1'
MAX_PROJECTION = 1024 * 1024


class ProjectionMachine:
    def __init__(self, doc):
        self.doc = doc

    @classmethod
    def from_bytes(cls, raw):
        return cls(json.loads(raw))

    @classmethod
    def load(cls, path):
        with open(path, 'rb') as stream:
            return cls.from_bytes(stream.read())

    def step(self, state, event):
        return dict(state)
