"""Canonical data and address validation, independent of records and policy."""
import json
from .store import hex_hash

MAX_INT = 2**53 - 1


class InvalidRecord(ValueError):
    """Invalid input or unsupported contract, not a canonical check failure."""


def canon(value):
    """Integer-domain JCS: UTF-16 key ordering, no floats or surrogate strings."""
    def render(x):
        if x is None:
            return "null"
        if type(x) is bool:
            return "true" if x else "false"
        if type(x) is int and -MAX_INT <= x <= MAX_INT:
            return str(x)
        if isinstance(x, str):
            x.encode("utf-8", errors="strict")
            return json.dumps(x, ensure_ascii=False, separators=(",", ":"))
        if isinstance(x, list):
            return "[" + ",".join(render(v) for v in x) + "]"
        if isinstance(x, dict) and all(isinstance(k, str) for k in x):
            keys = sorted(x, key=lambda k: k.encode("utf-16-be"))
            return "{" + ",".join(render(k) + ":" + render(x[k]) for k in keys) + "}"
        raise InvalidRecord("unsupported canonical JSON value")
    try:
        return render(value).encode("utf-8")
    except (UnicodeError, RecursionError) as exc:
        raise InvalidRecord("invalid JSON string or nesting") from exc


def decode(raw):
    def unique(pairs):
        result = {}
        for k, v in pairs:
            if k in result:
                raise InvalidRecord("duplicate JSON key")
            result[k] = v
        return result
    try:
        doc = json.loads(raw, object_pairs_hook=unique)
        if canon(doc) != raw:
            raise InvalidRecord("record must be canonical JSON bytes")
        return doc
    except (ValueError, UnicodeError, RecursionError) as exc:
        raise InvalidRecord(str(exc)) from exc


def exact(doc, keys):
    if not isinstance(doc, dict) or set(doc) != set(keys):
        raise InvalidRecord("unexpected fields; expected " + ", ".join(keys))


def record_hash(value):
    try:
        return hex_hash(value)
    except ValueError as exc:
        raise InvalidRecord(str(exc)) from exc


