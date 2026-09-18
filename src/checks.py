"""Bounded checks and their declared content environment; no signatures or policies."""
import hashlib
from dataclasses import dataclass
from . import KELVIN, kernel
from .canonical import canon, decode, exact, record_hash, InvalidRecord
from .store import StoreError

def validate_check(check):
    exact(check, ("term", "atp", "expect", "exit", "environment"))
    record_hash(check["term"])
    record_hash(check["expect"])
    env = check["environment"]
    if not isinstance(env, list):
        raise InvalidRecord("environment must be a sorted unique list of hashes")
    for h in env:
        record_hash(h)
    if env != sorted(set(env)):
        raise InvalidRecord("environment must be sorted and unique")
    if type(check["atp"]) is not int or not 0 <= check["atp"] <= kernel.UINT32_MAX:
        raise InvalidRecord("atp must be uint32")
    if check["exit"] not in kernel.EXITS:
        raise InvalidRecord("unknown expected exit")


@dataclass(frozen=True)
class Outcome:
    verdict: str
    result_hash: str
    exit: str
    atp_spent: int

    def as_dict(self):
        return dict(verdict=self.verdict, result_hash=self.result_hash,
                    exit=self.exit, atp_spent=self.atp_spent)


class BoundEnvironment:
    """A signed domain: extra local objects are invisible, missing members fault."""
    def __init__(self, store, addresses):
        self.store = store
        self.addresses = frozenset(bytes.fromhex(h) for h in addresses)
        self.cache = {}

    def get(self, h):
        if h not in self.addresses:
            return None
        if h not in self.cache:
            raw = self.store.get(h)
            if raw is None:
                raise StoreError("declared object missing: " + h.hex())
            if not isinstance(raw, bytes) or hashlib.sha256(raw).digest() != h:
                raise StoreError("CAS key mismatch: " + h.hex())
            self.cache[h] = raw
        return self.cache[h]


def capture_environment(term, atp, store):
    """CLI authoring convenience: discover demanded objects, never infer absence.

    Missing demanded bytes abort authoring. Intentional unresolved outcomes
    require an explicit signed domain, including an explicitly empty list.
    """
    seen = {}
    class Capture:
        def get(self, h):
            if h not in seen:
                raw = store.get(h)
                if raw is None:
                    raise StoreError("cannot capture missing object: " + h.hex())
                if not isinstance(raw, bytes) or hashlib.sha256(raw).digest() != h:
                    raise StoreError("CAS key mismatch: " + h.hex())
                seen[h] = raw
            return seen[h]
    kernel.eval_receipt(bytes.fromhex(record_hash(term)), atp, Capture(), kernel.VERIFIER_LIMITS)
    return sorted(h.hex() for h in seen)


def run_check(check, store, *, limits=None):
    check = decode(canon(check))
    validate_check(check)
    policy = dict(kernel.VERIFIER_LIMITS)
    if limits is not None:
        policy.update(limits)
    receipt = kernel.eval_receipt(bytes.fromhex(check["term"]), check["atp"],
                                  BoundEnvironment(store, check["environment"]), policy)
    result = receipt.result_hash.hex()
    verdict = "pass" if (result == check["expect"] and receipt.exit == check["exit"]) else "fail"
    return Outcome(verdict, result, receipt.exit, receipt.atp_spent)


def fingerprint(check, outcome):
    """Outcome identity, deliberately excluding budget and spent work."""
    validate_check(check)
    return ("stargate", KELVIN, tuple(check["environment"]), check["term"], check["expect"], check["exit"],
            outcome.verdict, outcome.result_hash, outcome.exit)


