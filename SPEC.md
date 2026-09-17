# Stargate contract

Status: **32K — DRAFT, implemented for the single signed-check flow below**.
Build 4 is a local development implementation, not an adopted or published
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
There is no collective settlement, historical-runtime routing, persisted resume, wave
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
{"stargate":32,"build":"3","key":"<public key hex>","check":{"term":"<hash>","atp":4,"expect":"<hash>","exit":"normal_form","environment":["<term hash>"]},"decision":"accept"}
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
("stargate", 32, tuple(environment), term, expect, expected_exit, verdict, result_hash, actual_exit)
```

ATP budget and atp_spent do not affect this identity. Each record still signs its
own budget. A fingerprint is not an admission vote or settlement. Stargate does
not yet implement Warrant's disagreement graph, thresholds or re-litigation.

The check has exactly term, atp, expect, exit and environment. Environment is a
sorted, duplicate-free list of lowercase SHA-256 addresses. It is signed as
part of the body and included in the outcome fingerprint. It defines the entire
non-intrinsic domain visible to evaluation; objects outside it are absent EVEN
IF the local store holds them. Genesis I/K/S remain intrinsic regardless of this
list. A demanded listed object unavailable locally is a StoreError naming its
hash: UNVERIFIED, with no verdict or decision. Corrupt bytes are likewise local
faults. Unused listed objects need not be fetched or locally present.

Thus an explicit absence (outside the signed domain) can canonically produce
unresolved_reference; a local missing copy (inside the domain) cannot. Two
verifiers able to supply the demanded listed bytes evaluate the same domain,
regardless of extra local objects. This does not assert availability elsewhere
or prove that the author chose a domain appropriate to an external question.
An explicit empty domain is legal, but is not a claim that a term is globally
unresolvable. Different domains may have the same outcome; this fingerprint is
not a settlement novelty/admissibility rule.

API callers must supply the domain explicitly. CLI `record` by default first
captures addresses actually demanded by this evaluation; any missing fetch
aborts before signing. Then it re-executes against that bound domain and signs.
This performs two evaluations; it is not an optimization. To intentionally
claim absence, use `--environment FILE` with a JSON address list (possibly []).
Each execution caches fetched bytes, checking their addresses. No signed
local rejection is manufactured from an unobserved missing object.

Raw CLI `eval` remains a diagnostic over the supplied local store, with no
signature or decision; its unresolved_reference is not a verified record.
Corrupt addressed bytes, I/O and resource failures during verification
are local unverified outcomes, never fail/reject. Input decoding and reading
object files are not charged ATP; this CLI is not a hostile-input network service.

## CLI results

`init`, `keygen`, `put`, `genesis`, `apply`, `eval`, `record`, `verify` output JSON.
`record` returns both RecordID and envelope object hash; `verify` takes the latter
and an explicit `--trust` key. Key generation creates a new mode-0600 seed file
and refuses to overwrite any existing path. Exit 0 means the operation completed
(including a successfully verified reject); inspect decision/verdict. Exit 1 / operation_error is an operational command failure, such as refusing
to overwrite a key or being unable to read a key/input file during authoring.
Exit 2 / invalid is malformed input/signature/unsupported edition. Exit 3 /
unverified is inability to evaluate/verify the declared computation locally,
including missing demanded domain members; no decision is returned. `eval` and
`verify` I/O failures also use 3. Argparse syntax errors use exit 2 with its
standard text diagnostic; JSON statuses apply after argument parsing.

The record API raises InvalidRecord for malformed record fields, including
term, expect, environment addresses and signer keys. StoreError,
AdmissionRefused and ResourceFault remain separate local-failure exceptions.

## In-process continuation (build 4 candidate)

`start(term_hash, atp, env, limits=None)` returns an Evaluation.
`resume(state, additional_atp)` advances that same object. The state is internal
Python memory, not a wire format, record or new canonical exit. Default local
limits are VERIFIER_LIMITS. Environment must be a mapping of 32-byte keys to
immutable bytes, copied at start; resume accepts no replacement environment or
limits. Content/address mismatch remains checked when a node is demanded.

Grant is cumulative uint32 credit. Both each increment and the cumulative grant
must satisfy admission limits, before advancing state. Unspent credit carries
over so several small increments can fund one expensive action. Spent counts
only committed priced actions and never resets. Fetch counters and resource
limits likewise do not reset. An invalid/refused increment leaves state alone;
a resource fault while running marks the state faulted and it cannot resume.

Status suspended carries receipt=None. Normal completion or canonical unresolved
reference carries the corresponding Receipt with cumulative spent. Completed
or faulted objects cannot be resumed. A zero increment on an already suspended
object is a no-op. Initial genesis at zero credit can finish immediately.

With positive credit the machine may prepare one next action before knowing
its full cost, like the original materialization path. If unaffordable, it
retains the pending action without committing or charging it; live and pending
terms are guarded by local resource limits. Resuming does not repeat its fetch
or contraction preparation. At zero credit it performs no new demanded fetch,
but probing for an already-normal term re-traverses the search spine at each
zero-credit boundary reached during execution. This traversal can repeat and
cost CPU without spending ATP. Explicit resume(state, 0) remains a no-op;
these probes occur within start or a positive-credit resume. No-repeat claims
cover fetch and prepared contraction work, not all step5 calls or elapsed time.
Snapshot copying, Python traversal overhead and transient pending work are
not an exact CPU/memory accounting model for ATP. Snapshot allocation is outside
ATP; the interface is not a hostile-input service.

For a fixed snapshot and unchanged limits, split and one-shot executions that
finish without local faults agree on exit, result hash and cumulative spent
when total grant is equal. At insufficient total grant the resumable API is
suspended, while fixed-budget eval_receipt returns canonical atp_exhausted.
Suspension must not be coerced into that receipt or a pass/fail verdict.
Suspension is an additional resource-sampling point: small credit increments
can cause ResourceFault where the SAME term, environment, total grant and
limits complete in one shot. Such a state is terminal (status=faulted,
receipt=None); resume refuses it, and its accumulated work cannot be recovered
through this API. Splitting is therefore NOT a refinement of one-shot local
failure behavior. A caller requiring grant-schedule-independent local outcomes
must not assume this interface provides them. No changes to the signed check format follow from this
process-local API.
