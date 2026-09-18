"""Recipient-selected, deterministic byte predicates; no plugins or code loading."""
import codecs
import re

from .records import canon, decode, InvalidRecord
from .policy import PolicyError, RESERVED


class FactDeriver:
    def __init__(self, profile):
        try:
            profile = decode(canon(profile))  # snapshot caller-owned configuration
        except InvalidRecord as exc:
            raise PolicyError('invalid derivation profile: ' + str(exc)) from exc
        if not isinstance(profile, dict) or not 1 <= len(profile) <= 32:
            raise PolicyError('derivation profile must contain 1 to 32 facts')
        for name, predicate in profile.items():
            if name in RESERVED or re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)*', name) is None:
                raise PolicyError('invalid derived fact name')
            if not isinstance(predicate, dict) or len(predicate) != 1:
                raise PolicyError('each fact must specify exactly one byte predicate')
            op, value = next(iter(predicate.items()))
            if op == 'utf8':
                if value is not True:
                    raise PolicyError('utf8 predicate must be true')
            elif op in ('size_at_least', 'size_at_most'):
                if type(value) is not int or not 0 <= value < 2**53:
                    raise PolicyError('size threshold must be a nonnegative safe integer')
            else:
                raise PolicyError('unknown byte predicate: ' + op)
        self.profile = profile
        self.size = 0
        self.valid_utf8 = True
        self.decoder = (codecs.getincrementaldecoder('utf-8')('strict')
                        if any('utf8' in p for p in profile.values()) else None)

    def update(self, chunk):
        self.size += len(chunk)
        if self.decoder is not None and self.valid_utf8:
            try:
                self.decoder.decode(chunk, final=False)
            except UnicodeDecodeError:
                self.valid_utf8 = False

    def finish(self):
        if self.decoder is not None and self.valid_utf8:
            try:
                self.decoder.decode(b'', final=True)
            except UnicodeDecodeError:
                self.valid_utf8 = False
        facts = {}
        for name, predicate in self.profile.items():
            op, value = next(iter(predicate.items()))
            if op == 'utf8':
                facts[name] = self.valid_utf8
            elif op == 'size_at_least':
                facts[name] = self.size >= value
            else:
                facts[name] = self.size <= value
        return facts
