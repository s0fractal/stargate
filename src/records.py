"""One signed check format; re-execution does not imply trust in the author.

Canonical encoding and signature patterns adapted from Warrant (MIT).
No Warrant version registry or historical evaluator is loaded.
"""
import hashlib

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey

from . import KELVIN, __version__
from . import kernel
from .store import StoreError
from .canonical import canon, decode, exact, record_hash, InvalidRecord
from .checks import validate_check, Outcome, BoundEnvironment, capture_environment, run_check, fingerprint

DOMAIN = b"stargate-record:"


def public_key(key):
    return key.public_key().public_bytes(serialization.Encoding.Raw,
                                         serialization.PublicFormat.Raw).hex()


def record_id(body):
    return hashlib.sha256(canon(body)).hexdigest()


def validate_body(body):
    exact(body, ("stargate", "build", "key", "check", "decision", "policy", "subject"))
    if type(body["stargate"]) is not int or body["stargate"] != KELVIN:
        raise InvalidRecord("unsupported Stargate temperature")
    if not isinstance(body["build"], str) or not body["build"].isascii() or not body["build"].isdigit():
        raise InvalidRecord("build must be a decimal string")
    record_hash(body["key"])
    validate_check(body["check"])
    if body["subject"] is not None:
        record_hash(body["subject"])
    if body["policy"] is not None:
        exact(body["policy"], ("rule", "facts"))
        record_hash(body["policy"]["rule"])
        record_hash(body["policy"]["facts"])
    if body["decision"] not in ("accept", "reject"):
        raise InvalidRecord("unknown decision")


def create_record(check, store, key, *, limits=None, policy=None, subject=None):
    # Snapshot caller-owned data before evaluation and signing.
    check = decode(canon(check))
    outcome = run_check(check, store, limits=limits)
    body = dict(stargate=KELVIN, build=__version__, key=public_key(key), check=check,
                decision="accept" if outcome.verdict == "pass" else "reject", policy=decode(canon(policy)), subject=subject)
    validate_body(body)
    verify_policy(body, store, limits=limits)
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
    provenance = verify_policy(body, store, limits=limits)
    outcome = run_check(body["check"], store, limits=limits)
    decision = "accept" if outcome.verdict == "pass" else "reject"
    if body["decision"] != decision:
        raise InvalidRecord("signed decision disagrees with re-execution")
    return dict(status="verified", record=rid, decision=decision, key=body["key"],
                verifier_build=__version__, stargate=KELVIN,
                outcome=outcome.as_dict(), fingerprint=list(fingerprint(body["check"], outcome)),
                policy=provenance, subject=body["subject"])


def verify_policy(body, store, *, limits=None):
    """Authenticate source bytes and reproduce their entire compiled check.

    Called only after signature/trust on verification; before signing on creation.
    Missing material is local unverified, never a policy decision.
    """
    if body['policy'] is None:
        return None
    from .compiler import compile_source, PolicyError, CompilerBug
    policy_limits = dict(kernel.VERIFIER_LIMITS)
    if limits is not None:
        policy_limits.update(limits)
    kernel.admit(body['check']['atp'], policy_limits)
    binding = body['policy']
    def read(h):
        raw = store.get(bytes.fromhex(h))
        if raw is None:
            raise StoreError('policy material missing: ' + h)
        if not isinstance(raw, bytes) or hashlib.sha256(raw).hexdigest() != h:
            raise StoreError('policy material hash mismatch: ' + h)
        return raw
    rule_raw, facts_raw = read(binding['rule']), read(binding['facts'])
    try:
        source = rule_raw.decode('utf-8')
        facts = decode(facts_raw)
        if not isinstance(facts, dict):
            raise InvalidRecord('policy facts must be an object')
        compiled = compile_source(source, facts=facts, max_atp=body['check']['atp'], limits=limits)
    except (UnicodeError, PolicyError) as exc:
        raise InvalidRecord('invalid policy provenance: ' + str(exc)) from exc
    except CompilerBug as exc:
        raise kernel.ResourceFault('compiler disagreement') from exc
    if compiled.check != body['check']:
        raise InvalidRecord('signed check does not match rule and facts')
    return dict(rule=binding['rule'], facts=binding['facts'], source=source, inputs=facts)
