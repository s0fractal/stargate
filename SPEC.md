# Stargate contract

Status: **32K — DRAFT, implemented for the single signed-check flow below**.
Build 2 is a local development implementation, not an adopted or published
standard. It is not a Warrant verifier.

## One temperature

A single Kelvin integer identifies the semantic edition: canonical data bytes
and addressing, evaluation and budget rules, canonical exits, record identity,
signature inputs, verification, fingerprints and settlement.
Internal modules have no independent protocol versions.

Start at 32K. After the first contract is defined and released, a change to any
of those semantics consumes a step: 32K → 31K → … → 0K. Changes to an unreleased
draft do not consume steps. Temperature is neither progress percentage nor a
reward for tests, and there is no deadline to reach zero.

The same temperature may receive implementation corrections to an unambiguous
contract, performance improvements and CLI changes. If a correction changes
observed results, describe the defect and affected builds/results. If the
contract itself was ambiguous or changes, lower the temperature. A test suite
alone does not establish semantic equivalence.

At 0K the semantic contract is frozen. Implementations may still be repaired to
conform to it. A semantic change requires a distinct contract identity; do not
reset the temperature under the same identity or disguise it as a bug fix.

## Identity and unsupported editions

The canonical signed body identifies Stargate through the `stargate` field
whose integer value is its temperature. The signature domain also names Stargate. Hashes of predecessor records must not be silently reused for new meanings.

A current verifier supports one temperature. It must explicitly reject an
unsupported edition before interpreting or executing its contents. It must not
skip unknown reasons, reinterpret historical data, dynamically fetch old code,
or silently route to a legacy evaluator. Older releases are separate historical
verification tools, with declared environments and no promise of perpetual
platform support. New records derived from old records receive new identities;
original signed bytes are preserved.

## Build identity

The package version is an increasing build number, initially 1. Its source of
truth is `stargate.__version__`; packaging reads it directly. The CLI reports
both build and temperature. Never replace a published artifact in place.
A result's provenance must identify the implementation build as well as the
semantic edition. Author build is signed in the body; verifier build is reported separately.
A build label is provenance, not proof of which software an author actually ran.

Kelvin is not used as the Python package version, so newer packages do not sort
behind older ones. Public package-name availability has not been checked; local
installation under the working name is not a claim on an index namespace.

## Implementation boundary

Python is the only initial implementation. Filesystem layout, local operational
limits, help text and Python internals are not automatically frozen protocol
surfaces. Local resource failure must remain distinguishable from a canonical
computation result. Operational improvements must preserve signed bytes and
semantic results for successfully executed supported inputs.

The implementation scope and wire format below define the initial flow.
There is no collective settlement, historical-runtime routing, resume, wave
layer or federation in this draft.

## Origin of the version approach

The policy is Stargate's adaptation, not a claim to reproduce Urbit's complete
versioning or update machinery. Urbit distinguishes Kelvin-versioned Arvo from
its separately versioned runtime:
https://github.com/urbit/docs.urbit.org/blob/master/content/user-manual/os/updates.md

## 32K computation

A node is an opcode byte, a flags byte, then the indicated 32-byte fields in
atom/left/right order. Exactly these forms are valid:

| Opcode | Flags | Payload |
|---|---|---|
| 0x00 literal | 0x01 | atom |
| 0x01 reference | 0x01 | target hash |
| 0x02 application | 0x06 | left hash, right hash |
| 0xff dissonance | 0x01 | reason hash |

Node addresses are SHA-256 of those bytes. I/K/S are intrinsic literal nodes
whose atoms are SHA-256 of ASCII `I`, `K`, `S`. Their bytes need not be stored.
Invalid node encoding materializes DISSONANCE(SHA-256(`Invalid Object`)).
Foreign bytes under an address cause a local fault, not an invalid-object term.

Evaluation takes a term hash, uint32 ATP, and a content environment. It uses
lazy left-spine resolution and leftmost-outermost reduction. A hash thunk has
size 1, a materialized reference size 2, a literal/dissonance size 1 and an
application size 1 + sizes of children. Materialization costs the resulting
size. I x → x, K x y → x, and reference dereference each cost 1. S x y z →
(x z)(y z) costs 1 + size(z). An unaffordable action is not charged or applied.
A zero-budget non-genesis thunk exhausts before fetching; missing demanded
content with an affordable fetch gives unresolved_reference. Dead branches need
not be fetched. Intrinsic genesis hashes are normal forms without work.

The receipt contains result_hash, atp_spent, exit. Exit is exactly normal_form,
atp_exhausted, or unresolved_reference. The latter two return dissonance terms
with atoms SHA-256(`ATP Exhausted`) and SHA-256(`Unresolved Reference`). The same
dissonance term can also be a normal form; result_hash never substitutes for exit.

Local admission/resource failures produce no canonical receipt or decision.
CLI and record verification limit ATP to 10,000,000; kernel Python callers may
supply local limits. These limits are operational, not another semantic edition.
The implementation is synchronous; concurrent in-process evaluator use is not
promised (the inherited evaluator adjusts Python's recursion limit).

## 32K signed check

An envelope has exactly `body` and `signature`. Its body has exactly:

```json
{"stargate":32,"build":"2","key":"<public key hex>","check":{"term":"<hash>","atp":4,"expect":"<hash>","exit":"normal_form"},"decision":"accept"}
```

This example is explanatory, not canonical field ordering. The encoding is
UTF-8 integer-domain JCS: UTF-16 code-unit object-key ordering, no whitespace,
no float/NaN/Infinity, no lone surrogates, no duplicate keys; integers are within
±(2^53−1). Hashes and keys are 64 lowercase hexadecimal characters, signatures
128. ATP must be an integer uint32 (booleans are rejected). Build is a nonempty
ASCII decimal string. Unknown fields, legacy shapes and other temperatures are
invalid; no older implementation is selected automatically.

RecordID = SHA-256(canonical body). Ed25519 signs the bytes
`b"stargate-record:" + bytes.fromhex(RecordID)`. The key is inside the signed
body. The envelope is canonical too. Its storage object hash differs from the
RecordID because the envelope additionally contains the signature.

Creation re-executes the check. Verdict pass requires BOTH expected result_hash
and expected exit to match. It signs decision accept for pass and reject for
fail. Verification requires an explicitly supplied trusted public key, a valid
signature and re-execution agreeing with the signed decision. Small-order and
noncanonical public keys are rejected. A self-supplied key in the record grants
no trust. Neither an expected exhaustion nor an accepted claim proves a normal
form, a real-world assertion or an external policy: it proves this stated
computation claim in the verifier's available content environment.

The outcome fingerprint is exactly:

```
("stargate", 32, term, expect, expected_exit, verdict, result_hash, actual_exit)
```

ATP budget and atp_spent do not affect this identity. Each record still signs its
own budget. A fingerprint is not an admission vote or settlement. Stargate does
not yet implement Warrant's disagreement graph, thresholds or re-litigation.

Absent demanded objects may change the canonical outcome; verification only
attests to the local environment used. No portable environment manifest or
snapshot proof is claimed. Corrupt addressed bytes, I/O and resource failures
are local unverified outcomes, never fail/reject. Input decoding and reading
object files are not charged ATP; this CLI is not a hostile-input network service.

## CLI results

`init`, `keygen`, `put`, `genesis`, `apply`, `eval`, `record`, `verify` output JSON.
`record` returns both RecordID and envelope object hash; `verify` takes the latter
and an explicit `--trust` key. Key generation creates a new mode-0600 seed file
and refuses to overwrite any existing path. Exit 0 means the operation completed
(including a successfully verified reject); inspect decision/verdict. Exit 2 is
invalid input/signature/unsupported edition, exit 3 is local unverified failure.
