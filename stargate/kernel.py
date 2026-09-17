"""Stargate reduction kernel, adapted from Sigma-Glyph 0.7.0.

Copyright (c) 2025-2026 s0fractal. MIT; see LICENSE.
Provenance and modifications are recorded in README.md.
"""
import hashlib
import sys
from dataclasses import dataclass

sha = lambda b: hashlib.sha256(b).digest()

# ---------- OpCodes / Flags ----------
LITERAL, REF, APPLY, RESERVED, DISSONANCE = 0x00, 0x01, 0x02, 0x03, 0xFF
F_ATOM, F_LEFT, F_RIGHT = 0x01, 0x02, 0x04
FLAGS_REQ = {LITERAL: F_ATOM, REF: F_ATOM, APPLY: F_LEFT | F_RIGHT, DISSONANCE: F_ATOM}

# ---------- Reason hashes ----------
R_INVALID = sha(b"Invalid Object")
R_ATP     = sha(b"ATP Exhausted")
R_UNRES   = sha(b"Unresolved Reference")

# ---------- Canonical serialization ----------
def ser(op, flags, atom=None, left=None, right=None):
    b = bytes([op, flags])
    for f in (atom, left, right):
        if f is not None:
            assert len(f) == 32
            b += f
    return b

def node_hash(b): return sha(b)

def deser(buf):
    """Validate + parse. Returns dict or None (caller maps None -> Invalid Object)."""
    if len(buf) < 2: return None
    op, flags = buf[0], buf[1]
    if flags & ~0x07: return None
    if op not in FLAGS_REQ: return None            # covers RESERVED 0x03
    if flags != FLAGS_REQ[op]: return None
    exp = 2 + 32 * bin(flags & 0x07).count("1")
    if len(buf) != exp: return None
    out, off = {"op": op, "flags": flags}, 2
    for bit, name in ((F_ATOM, "atom"), (F_LEFT, "left"), (F_RIGHT, "right")):
        if flags & bit:
            out[name] = buf[off:off + 32]; off += 32
    return out

INVALID_OBJECT = ser(DISSONANCE, F_ATOM, atom=R_INVALID)

# ---------- Genesis ----------
I_BYTES = ser(LITERAL, F_ATOM, atom=sha(b"I"))
K_BYTES = ser(LITERAL, F_ATOM, atom=sha(b"K"))
S_BYTES = ser(LITERAL, F_ATOM, atom=sha(b"S"))
I_H, K_H, S_H = map(node_hash, (I_BYTES, K_BYTES, S_BYTES))
FALSE_BYTES = ser(APPLY, F_LEFT | F_RIGHT, left=K_H, right=I_H)
FALSE_H = node_hash(FALSE_BYTES)

# ---------- CAS ----------
class Store:
    def __init__(self): self.m = {}
    def put(self, b):
        h = node_hash(b); self.m[h] = b; return h
    def get(self, h): return self.m.get(h)  # None => unresolved

class ResourceFault(Exception):
    """Local, NON-canonical implementation fault (limits breached). Not a DISSONANCE."""

# ---------- Terms (hash-thunk machine, v0.5) ----------
# term := ("thunk", h)                        unresolved hash (size 1)
#       | ("lit", atom) | ("ref", h) | ("dis", reason)
#       | ("app", t, t)                       children may be thunks
GENESIS = {I_H: I_BYTES, K_H: K_BYTES, S_H: S_BYTES}   # intrinsic axioms (Book I §5.1)
UINT32_MAX = 2**32 - 1

def term_bytes(t):
    if t[0] == "lit": return ser(LITERAL, F_ATOM, atom=t[1])
    if t[0] == "ref": return ser(REF, F_ATOM, atom=t[1])
    if t[0] == "dis": return ser(DISSONANCE, F_ATOM, atom=t[1])
    return ser(APPLY, F_LEFT | F_RIGHT, left=term_hash(t[1]), right=term_hash(t[2]))

def term_hash(t):
    if t[0] == "thunk": return t[1]           # hash-transparent
    return node_hash(term_bytes(t))

def size(t):
    """Hash-leaf size model (ADR-001×003): materialized nodes count 1 each,
    an unresolved hash leaf counts exactly 1, a materialized REF counts 2
    (node + target thunk)."""
    k = t[0]
    if k == "app": return 1 + size(t[1]) + size(t[2])
    if k == "ref": return 2
    return 1                                   # thunk, lit, dis

def depth(t):
    return 1 if t[0] != "app" else 1 + max(depth(t[1]), depth(t[2]))

def is_glyph(t, gh): return term_hash(t) == gh   # Identity by Hash (general, recursive)

def glyph_eq(t, gh):
    """O(1) glyph check for redex patterns: a thunk carries its hash; a
    materialized LITERAL hashes in constant time; APPLY/REF/DISSONANCE cannot
    equal a LITERAL's NodeHash short of a SHA-256 collision (out of scope)."""
    if t[0] == "thunk": return t[1] == gh
    if t[0] == "lit":   return node_hash(ser(LITERAL, F_ATOM, atom=t[1])) == gh
    return False

# ---------- Hash-thunk stepper (v0.5: lazy left-spine, size-priced ATP) ----------
class Unresolved(Exception): pass
class BudgetExhausted(Exception): pass

def force(h, store, stats, limits):  # NOSONAR python:S8495
    """Materialize ONE node from hash h; children stay thunks. Genesis axioms
    are intrinsic — synthesized without the store (Book I §5.1). Bytes failing
    §4.1 materialize the Canonical Invalid Object (§3.5b).

    Returns a Term, which is a tagged union: ``("lit", atom)`` and ``("app", l, r)``
    have different arities on purpose (see the Term grammar above). A rule that
    wants every return of a function to be the same length is reading a sum type
    as a record, so S8495 is suppressed here by name rather than by silence."""
    stats["fetches"] += 1
    if stats["fetches"] > limits["max_store_fetches"]: raise ResourceFault("fetches")
    b = GENESIS.get(h)
    if b is None: b = store.get(h)
    if b is None: raise Unresolved()
    # A mapping lookup is not, by itself, a content-addressed store.  The
    # public evaluator accepts any object with ``get`` (tests and downstream
    # callers use plain dicts), so verify the CAS relation at the boundary
    # instead of assuming only Store.put() can reach this function.  Treat a
    # wrong key as a local storage fault: the bytes may be a perfectly valid
    # SigmaNodeV2, but evaluating them as the requested hash would violate
    # Identity by Hash and could make two conforming engines disagree.
    if not isinstance(b, bytes):
        raise ResourceFault("store returned non-bytes")
    if node_hash(b) != h:
        raise ResourceFault("CAS key mismatch")
    n = deser(b)
    if n is None: return ("dis", R_INVALID)
    op = n["op"]
    if op == LITERAL:    return ("lit", n["atom"])
    if op == REF:        return ("ref", n["atom"])
    if op == DISSONANCE: return ("dis", n["atom"])
    return ("app", ("thunk", n["left"]), ("thunk", n["right"]))

_NO_REDUCTION = object()


def _require_budget(cost, remaining):
    if cost > remaining:
        raise BudgetExhausted()


def _head_reduction(function, argument, remaining):
    """Return an I/K/S head contraction, or the private no-redex sentinel."""
    if glyph_eq(function, I_H):
        _require_budget(1, remaining)
        return argument, 1
    if function[0] != "app":
        return _NO_REDUCTION
    if glyph_eq(function[1], K_H):
        _require_budget(1, remaining)
        return function[2], 1
    if function[1][0] != "app" or not glyph_eq(function[1][1], S_H):
        return _NO_REDUCTION
    x, y, z = function[1][2], function[2], argument
    cost = 1 + size(z)
    _require_budget(cost, remaining)
    return ("app", ("app", x, z), ("app", y, z)), cost


def _step_application(t, remaining, store, stats, limits):
    function, argument = t[1], t[2]
    reduced = _head_reduction(function, argument, remaining)
    if reduced is not _NO_REDUCTION:
        return reduced
    result = step5(function, remaining, store, stats, limits)
    if result is not None:
        return ("app", result[0], argument), result[1]
    result = step5(argument, remaining, store, stats, limits)
    if result is not None:
        return ("app", function, result[0]), result[1]
    return None


def step5(t, remaining, store, stats, limits):
    """One priced action, leftmost-outermost with lazy spine resolution.
    Returns (new_term, cost) with cost <= remaining, or None (normal form).
    Raises BudgetExhausted if the demanded action is unaffordable (checked
    BEFORE the action; a minimum-cost check of 1 precedes even the fetch,
    so exhaustion at budget 0 is decided without touching the store).
    Raises Unresolved if the demanded hash is absent (not charged)."""
    kind = t[0]
    if kind == "thunk":
        if t[1] in GENESIS: return None                      # NF leaf by hash
        _require_budget(1, remaining)
        v = force(t[1], store, stats, limits)                # may raise Unresolved
        c = size(v)                                          # 1 (lit/dis) / 2 (ref) / 3 (app)
        _require_budget(c, remaining)                         # fetched bytes discarded
        return v, c
    if kind == "ref":                                        # R-R: unwrap one level
        _require_budget(1, remaining)
        return ("thunk", t[1]), 1
    if kind == "app":
        return _step_application(t, remaining, store, stats, limits)
    return None                                              # lit / dis are normal forms

DEFAULT_LIMITS = {"max_node_depth": 4096,
                  "max_materialized_nodes": 1_000_000,
                  "max_store_fetches": 1_000_000,
                  # No admission cap: this module is the conformance oracle and
                  # must be able to answer for any budget the Book permits.
                  "max_atp": None}

# What a *verifier* should use instead. `eval` is total, so a stranger's term
# always terminates -- and `size <= atp + 1` means the budget they choose is also
# their licence over the verifier's memory. A 32-bit ATP is up to 4,294,967,295
# priced actions, so "finite" and "affordable" are different words. This cap is a
# local admission decision, made BEFORE any allocation or any store access, and
# it is NOT a canonical Sigma-GLYPH outcome (Book I s3.6): it says the verifier
# declined to run the computation, not what the computation evaluates to.
VERIFIER_LIMITS = dict(DEFAULT_LIMITS, max_atp=10_000_000)


class AdmissionRefused(Exception):
    """The verifier declined to begin. Distinct from ResourceFault, which is
    breached during evaluation, and from every DISSONANCE, which is a result.

    Kept a separate type on purpose: a caller that confuses "I would not run
    this" with "this is what it evaluates to" has let the party supplying the
    term decide what the verifier reports."""

    def __init__(self, claimed, allowed):
        super().__init__(f"claimed ATP {claimed} exceeds this verifier's "
                         f"admission limit {allowed}; refused before execution")
        self.claimed, self.allowed = claimed, allowed


def admit(atp, limits=None):
    """Decide whether to begin at all. Raises before anything is touched.

    Book I's consensus domain is ``uint32``.  Python's ``bool`` is an ``int``
    subclass and floats participate in numeric comparisons, so an ordinary
    range check is not enough to keep the API on that domain.
    """
    if type(atp) is not int or not 0 <= atp <= UINT32_MAX:
        raise ValueError("atp must be a uint32 integer")
    allowed = (limits or DEFAULT_LIMITS).get("max_atp")
    if allowed is not None and atp > allowed:
        raise AdmissionRefused(atp, allowed)


def resource_check(t, limits):
    """Raise ResourceFault (local, non-canonical §3.6) if the term breaches a
    configured maximum. Called on the 256-step in-flight sample AND before any
    normal-form return, so a `max_*` control is never exceeded on a completed
    return (Codex v0.6.4 hardening audit P1)."""
    if size(t) > limits["max_materialized_nodes"]:
        raise ResourceFault("term growth")
    if depth(t) > limits["max_node_depth"]:
        raise ResourceFault("term depth")


EXITS = ("normal_form", "atp_exhausted", "unresolved_reference")


@dataclass(frozen=True)
class Receipt:
    """Canonical result; deliberately not the legacy two-value tuple."""
    term: tuple
    atp_spent: int
    exit: str

    @property
    def result_hash(self):
        return term_hash(self.term)

    def as_dict(self):
        return {"exit": self.exit, "result_hash": self.result_hash.hex(),
                "atp_spent": self.atp_spent}


def eval_receipt(h, atp, env, limits=None):
    """eval(term_hash, uint32 atp, content environment) -> Receipt (Book I §3.4).

    The three inputs the Book states. `env` is a partial map from NodeHash to
    bytes whose entries hash to their own key (§3.5); bytes under a foreign key
    are refused locally rather than executed."""
    term, spent, exit_kind = _eval_hash_raw(h, atp, env, limits)
    return Receipt(term, spent, exit_kind)


def _eval_hash_raw(h, atp, store, limits=None):
    """The machine. Returns (term, spent, exit); eval_receipt wraps it."""
    limits = limits or DEFAULT_LIMITS
    admit(atp, limits)
    if not isinstance(h, bytes) or len(h) != 32:
        raise ValueError("term_hash must be exactly 32 bytes")
    stats = {"fetches": 0}
    old_rl = sys.getrecursionlimit()
    sys.setrecursionlimit(max(old_rl, 3 * limits["max_node_depth"] + 2000))
    try:
        t = ("thunk", h)
        spent = 0
        steps = 0
        while True:
            # Memory fence guards on ACTUAL materialized size, not on `spent`.
            # The ADR-001 bound `size <= 1 + spent` is only an UPPER bound, so
            # `spent` is not a valid size proxy: a divergent term (e.g. Omega)
            # keeps its size tiny while `spent` grows without bound, so guarding
            # on `spent` would wrongly fault it instead of returning the canonical
            # DISSONANCE(ATP Exhausted) that TV-7 mandates for all n. Both size and
            # depth need a traversal — amortize them (non-canonical local faults,
            # so the check cadence is an implementation choice, s3.6).
            steps += 1
            if steps % 256 == 0:
                resource_check(t, limits)          # in-flight runaway fence
            try:
                r = step5(t, atp - spent, store, stats, limits)
            except BudgetExhausted:
                return ("dis", R_ATP), spent, "atp_exhausted"
            except Unresolved:
                return ("dis", R_UNRES), spent, "unresolved_reference"
            if r is None:
                # normal form: a `max_*` limit MUST hold on the returned term,
                # even for evaluations that finish before the 256-step sample
                # (Codex v0.6.4 hardening audit P1 — a completed return must
                # never exceed the configured maximum). DISSONANCE returns
                # above are size-1 leaves and cannot breach.
                resource_check(t, limits)
                return t, spent, "normal_form"
            t = r[0]
            spent += r[1]
    except RecursionError:
        raise ResourceFault("python recursion depth") from None
    finally:
        sys.setrecursionlimit(old_rl)



# ---------- In-process continuation ----------
class Evaluation:
    """An owned, in-process continuation; not a portable or trusted receipt.

    Use start()/resume(). A copied byte mapping fixes the content environment.
    The pending priced action is retained when its cost exceeds current credit.
    Only committed actions increase spent. No legacy evaluator is involved.
    """
    def __init__(self, h, atp, env, limits=None):
        from collections.abc import Mapping
        if not isinstance(h, bytes) or len(h) != 32:
            raise ValueError("term_hash must be exactly 32 bytes")
        self._limits = dict(VERIFIER_LIMITS)
        if limits is not None:
            self._limits.update(limits)
        admit(atp, self._limits)
        if not isinstance(env, Mapping):
            raise TypeError("start requires a mapping of hash bytes to immutable bytes")
        # Copy now, not lazily across resumes. Reject mutable values even on dead
        # branches: this API promises a fixed input snapshot, not a live store.
        self._env = dict(env)
        if any(not isinstance(k, bytes) or len(k) != 32 or not isinstance(v, bytes)
               for k, v in self._env.items()):
            raise ValueError("environment must map 32-byte hashes to immutable bytes")
        self._term = ("thunk", h)
        self._granted = atp
        self._spent = 0
        self._stats = {"fetches": 0}
        self._steps = 0
        self._pending = None
        self._receipt = None
        self._status = "suspended"
        self._drive()

    @property
    def status(self):
        return self._status

    @property
    def atp_spent(self):
        return self._spent

    @property
    def atp_remaining(self):
        return self._granted - self._spent

    @property
    def receipt(self):
        # A suspension is NOT atp_exhausted and carries no canonical receipt.
        return self._receipt

    def _drive(self):
        old_rl = sys.getrecursionlimit()
        sys.setrecursionlimit(max(old_rl, 3 * self._limits["max_node_depth"] + 2000))
        try:
            while True:
                remaining = self.atp_remaining
                if self._pending is None:
                    self._steps += 1
                    if self._steps % 256 == 0:
                        resource_check(self._term, self._limits)
                    try:
                        # Preserve zero-budget no-fetch behavior. With positive
                        # credit, prepare ONE action, caching any fetched object
                        # and computed contraction rather than repeating it.
                        step = step5(self._term, UINT32_MAX if remaining else 0,
                                     self._env, self._stats, self._limits)
                    except BudgetExhausted:
                        resource_check(self._term, self._limits)
                        return
                    except Unresolved:
                        self._receipt = Receipt(("dis", R_UNRES), self._spent,
                                                "unresolved_reference")
                        self._status = "unresolved_reference"
                        return
                    if step is None:
                        resource_check(self._term, self._limits)
                        self._receipt = Receipt(self._term, self._spent, "normal_form")
                        self._status = "normal_form"
                        return
                    self._pending = step
                next_term, cost = self._pending
                if cost > remaining:
                    # Pending work is transient and uncharged until committed;
                    # guard it too. It stays in this process, never serialized.
                    resource_check(self._term, self._limits)
                    resource_check(next_term, self._limits)
                    return
                self._term = next_term
                self._spent += cost
                self._pending = None
        except RecursionError:
            self._status = "faulted"
            raise ResourceFault("python recursion depth") from None
        except Exception:
            self._status = "faulted"
            raise
        finally:
            sys.setrecursionlimit(old_rl)


def start(h, atp, env, limits=None):
    """Start resumable reduction against a copied mapping. Returns Evaluation."""
    return Evaluation(h, atp, env, limits)


def resume(state, additional_atp):
    """Add credit and advance the SAME continuation. No copy or re-execution."""
    if not isinstance(state, Evaluation):
        raise TypeError("resume requires an Evaluation")
    if state.status != "suspended":
        raise ValueError("only a suspended evaluation can be resumed")
    admit(additional_atp, state._limits)
    admit(state._granted + additional_atp, state._limits)
    if additional_atp == 0:
        return state
    state._granted += additional_atp
    state._drive()
    return state


# ---------- Canonical Lambda->SKI Compiler, Profile C1 ----------
# lambda term := ("var", name) | ("lam", name, body) | ("lapp", f, a) | SKI term (passthrough)
IG, KG, SG = ("lit", sha(b"I")), ("lit", sha(b"K")), ("lit", sha(b"S"))

def _fv(t):
    k = t[0]
    if k == "var": return {t[1]}
    if k == "lam": return _fv(t[2]) - {t[1]}
    if k in ("lapp", "app"): return _fv(t[1]) | _fv(t[2])
    return set()

def c1(t):
    k = t[0]
    if k == "var": return t
    if k == "lapp": return ("app", c1(t[1]), c1(t[2]))
    if k == "lam": return _abstract(t[1], c1(t[2]))
    return t  # SKI passthrough

def _abstract(x, m):
    if m == ("var", x): return IG                                   # A-1
    if x not in _fv(m): return ("app", KG, m)                       # A-2
    if m[0] == "app":                                                # A-3
        return ("app", ("app", SG, _abstract(x, m[1])), _abstract(x, m[2]))
    raise ValueError("free variable escapes abstraction")
