"""One signed check format; re-execution does not imply trust in the author.

Canonical encoding and signature patterns adapted from Warrant (MIT).
No Warrant version registry or historical evaluator is loaded.
"""
import hashlib
import json
from dataclasses import dataclass

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey

from . import KELVIN, __version__
from . import kernel
from .store import hex_hash, StoreError

DOMAIN = b"stargate-record:"
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


def public_key(key):
    return key.public_key().public_bytes(serialization.Encoding.Raw,
                                         serialization.PublicFormat.Raw).hex()


def record_id(body):
    return hashlib.sha256(canon(body)).hexdigest()


def validate_body(body):
    exact(body, ("stargate", "build", "key", "check", "decision"))
    if type(body["stargate"]) is not int or body["stargate"] != KELVIN:
        raise InvalidRecord("unsupported Stargate temperature")
    if not isinstance(body["build"], str) or not body["build"].isascii() or not body["build"].isdigit():
        raise InvalidRecord("build must be a decimal string")
    record_hash(body["key"])
    validate_check(body["check"])
    if body["decision"] not in ("accept", "reject"):
        raise InvalidRecord("unknown decision")


def create_record(check, store, key, *, limits=None):
    # Snapshot caller-owned data before evaluation and signing.
    check = decode(canon(check))
    outcome = run_check(check, store, limits=limits)
    body = dict(stargate=KELVIN, build=__version__, key=public_key(key), check=check,
                decision="accept" if outcome.verdict == "pass" else "reject")
    rid = record_id(body)
    return dict(body=body, signature=key.sign(DOMAIN + bytes.fromhex(rid)).hex())


_ED25519_P = (1 << 255) - 19
_ED25519_SMALL_ORDER = {bytes.fromhex(h) for h in (
    "0100000000000000000000000000000000000000000000000000000000000000",
    "c7176a703d4dd84fba3c0b760d10670f2a2053fa2c39ccc64ec7fd7792ac037a",
    "0000000000000000000000000000000000000000000000000000000000000080",
    "26e8958fc2b227b045c3f489f2ef98f0d5dfac05d3c63339b13802886d53fc05",
    "ecffffffffffffffffffffffffffffffffffffffffffffffffffffffffffff7f",
    "26e8958fc2b227b045c3f489f2ef98f0d5dfac05d3c63339b13802886d53fc85",
    "0000000000000000000000000000000000000000000000000000000000000000",
    "c7176a703d4dd84fba3c0b760d10670f2a2053fa2c39ccc64ec7fd7792ac03fa",
    # non-canonical sign-bit variants of the x=0 torsion points (y=1, y=p-1):
    # current libs reject these at decode; blocklisted as defense-in-depth so a
    # lenient third implementation cannot accept them (Gemini 3.1 Pro audit).
    "0100000000000000000000000000000000000000000000000000000000000080",
    "ecffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffff",
)}


def weak_ed25519_pubkey(raw):
    """True if `raw` (32 bytes) is a small-order or non-canonically-encoded
    Ed25519 public key that a conforming verifier MUST reject (SPEC §5)."""
    if len(raw) != 32 or raw in _ED25519_SMALL_ORDER:
        return True
    y = int.from_bytes(raw, "little") & ((1 << 255) - 1)   # drop the sign bit
    return y >= _ED25519_P                                  # non-canonical y



def verify_record(raw, store, trusted_keys, *, limits=None):
    """Verify canonical bytes, explicit key trust, signature, then re-execute.

    A verified reject is a valid signed decision, not an invalid signature.
    Local faults propagate; they never produce pass/fail or accept/reject.
    """
    envelope = decode(raw)
    exact(envelope, ("body", "signature"))
    body = envelope["body"]
    validate_body(body)
    if weak_ed25519_pubkey(bytes.fromhex(body["key"])):
        raise InvalidRecord("weak or noncanonical signing key")
    if body["key"] not in trusted_keys:
        raise InvalidRecord("signer is not explicitly trusted")
    sig = envelope["signature"]
    if not isinstance(sig, str) or len(sig) != 128 or any(c not in "0123456789abcdef" for c in sig):
        raise InvalidRecord("invalid signature encoding")
    rid = record_id(body)
    try:
        Ed25519PublicKey.from_public_bytes(bytes.fromhex(body["key"])).verify(
            bytes.fromhex(sig), DOMAIN + bytes.fromhex(rid))
    except (InvalidSignature, ValueError) as exc:
        raise InvalidRecord("signature does not verify") from exc
    outcome = run_check(body["check"], store, limits=limits)
    decision = "accept" if outcome.verdict == "pass" else "reject"
    if body["decision"] != decision:
        raise InvalidRecord("signed decision disagrees with re-execution")
    return dict(status="verified", record=rid, decision=decision, key=body["key"],
                verifier_build=__version__, stargate=KELVIN,
                outcome=outcome.as_dict(), fingerprint=list(fingerprint(body["check"], outcome)))
