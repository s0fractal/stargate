# Stargate

A portable lab for proposing program changes, finding counterexamples, and
replaying the history of accepted changes. Give someone a world packet; they can
propose a new rule as text, recompute the checks, and continue from the result.
The finite lab needs no author key, account or service.

Today the lab checks **Boolean rules with at most eight inputs**: every input is
run through an SKI evaluator and compared with a separate Boolean oracle.
In the default equivalence mode, a changed answer produces a concrete
counterexample. A cheaper equivalent rule
can become the next world; an unfinished check establishes nothing.

**Build 26 · 32K draft.** The contract can change incompatibly. This is an
experimental implementation, not a stable release or a general program prover.
Python only; commands `sg` and `stargate`. MIT licensed.

Two flows share the computation kernel but have different trust models:

- **Finite lab:** propose text, recompute behavior/properties and replay changes.
  No trusted signer is required. Start with the walkthrough below.
- **Artifact admission:** verify signed judgments against recipient-selected keys,
  measure artifact facts and publish only admitted bytes (`policy`, `require`,
  `admit`, `admit-all`). A signature identifies an assertion; it does not establish
  the truth of external facts.

## Try a complete transition

Clone this repository, then run from its root:

```sh
python3 -m venv .venv
.venv/bin/python -m pip install .
. .venv/bin/activate
mkdir demo
cd demo
sg lab-create ../examples/lineage-parent.wpl --input a --input b --input c \
  --objective lower_max_atp --output world.json
sg lineage-start world.json --output history.json
sg lab-search world.json --output candidate-world.json > search.json
python - <<'PYTHON'
import json
from pathlib import Path
proposal = json.loads(Path("search.json").read_text())["proposal"]
Path("proposal.json").write_text(json.dumps(proposal))
PYTHON
ROOT_ID=$(python -c 'import json; print(json.load(open("proposal.json"))["parent"])')
sg lineage-append history.json proposal.json --expect-root "$ROOT_ID" --output next-history.json
sg lineage-check next-history.json --expect-root "$ROOT_ID" --output checked-world.json
```

The search finds a rule equivalent to `!!(a || b) || c` from
`!!!!(a || b) || c`, reducing worst-case
ATP from **61 to 43**. The history checker reconstructs the same successor by
replaying the transition. Search is only a proposal generator; it cannot bypass
the gate. Run search again on `checked-world.json` to continue.

A chat participant can replace the generated proposal with their own JSON
containing only `parent` and `candidate`. `sg lab-check world.json proposal.json`
returns an admitted result, a counterexample, insufficient improvement, an
incomplete check or a checker error. Stargate refuses to overwrite its output
files; use a fresh demo directory on a rerun.
In this local example the root ID comes from the world you just created. When
receiving someone else's history, choose your expected root independently.

Next: [portable worlds and offline replay](#a-boolean-laboratory-you-can-hand-to-a-chat),
[finite properties](#discover-finite-inputoutput-properties),
[explicit behavior contracts](#let-behavior-change-within-explicit-properties), and
[replayable histories](#carry-a-replayable-history-to-the-next-participant).
See [VISION.md](VISION.md) for direction and [SPEC.md](SPEC.md) for the contract.
Packet integrity alone does not authenticate its checker; offline replay needs
independently trusted launcher/runtime digests and is not a sandbox.

## Signed checks and object storage

Stargate also provides content-addressed computation and signed checks, brought
forward from Sigma-Glyph and Warrant. These flows have explicit signer trust;
the finite lab above does not weaken it. Predecessor repositories remain unchanged.
Return to the repository root (`cd ..`) for the examples below.

Use `.venv/bin/sg` below, or activate the environment. Default object directory
is `.stargate`; override with `sg --store /path/to/objects COMMAND`.

```sh
sg keygen signing.key
sg genesis
sg apply 2f33694d09810641fa5b8c47a7c0dc42e1b99eb8c9784a00aaee9a66330f4162 bc0c2fe26e44e2aed8ce500a74963bc270fd4a49ec0c2e4837ce7a64bb0a486c
sg eval 51d8148feda28f17304c9ed6c34d9d548c83a84c380f4dd1ba0a037ceb9d4d3e --atp 4
sg record 51d8148feda28f17304c9ed6c34d9d548c83a84c380f4dd1ba0a037ceb9d4d3e --atp 4 --expect bc0c2fe26e44e2aed8ce500a74963bc270fd4a49ec0c2e4837ce7a64bb0a486c --exit normal_form --key signing.key
sg verify ENVELOPE_OBJECT_HASH --trust PUBLIC_KEY_FROM_KEYGEN
```

The final line's two placeholders come from `record` and `keygen`. `verify`
checks explicit signer trust and signature, then independently re-executes the
check. Expected output has `status: verified`, `decision: accept`, normal_form,
and 4 ATP spent. An explicitly expected exhaustion can also pass; acceptance
means agreement with the declared computation claim, not universal success.
Keep the private key outside a shared repository.

The signed check names its content environment. By default `record` captures
the demanded object addresses and refuses missing bytes before signing. Use
`--environment FILE` only to explicitly choose a closed domain: a JSON sorted
unique address list; [] intentionally excludes all non-intrinsic objects.
Verification ignores extra local objects and reports a missing demanded member
as `unverified`, naming its hash. Adding missing declared bytes can make a record
verifiable; adding undeclared bytes cannot change its decision.

| Exit | JSON status | Meaning |
|---|---|---|
| 0 | operation-specific; `verified` for verification | Completed; inspect accept/reject separately |
| 1 | `operation_error` | Operator/I/O failure, including existing key file |
| 2 | `invalid` | Malformed record, bad signature, unsupported temperature |
| 3 | `unverified` | Missing declared bytes, admission/resource or verification I/O failure |
| 4 | `unsatisfied` | `require`: verified record does not satisfy the recipient request |

Argument parsing errors use exit 2 with argparse's text diagnostic. Library
callers catch `InvalidRecord` for invalid fields, including malformed hashes;
`StoreError` and kernel admission/resource exceptions mean local inability.

## One contract

[SPEC.md](SPEC.md) defines the draft 32K wire format and semantics. Kelvin counts
down for contract changes; installable build numbers increase. One current
implementation supports one temperature. Legacy Warrant records are rejected,
not reinterpreted or routed to a historical evaluator. No dynamic plugin or
evaluator loading is present; installed package integrity is the normal code
trust boundary, not an embedded self-digest or runtime registry.

Python source lives directly in `src/`; packaging maps that directory to the
public `stargate` import package. Commands remain `sg` and `stargate`. There is no
second source copy or compatibility directory.

- `src/kernel.py`, `src/store.py`: reduction and content-addressed storage.
- `src/canonical.py`: canonical JSON, data errors and address validation.
- `src/checks.py`: bounded checks, declared environments and fingerprints.
- `src/compiler.py`: pure boolean WPL compilation; no record authoring.
- `src/records.py`: signatures and record verification, including provenance.
- `src/policy.py`: policy authoring above compilation and records.
- `src/bundle.py`, `src/artifact.py`, `src/facts.py`: transport and admission.
- `src/case.py`: inert counterexample packets.
- `src/cli.py`: both command aliases; `tests/`: executable controls.

`architecture.py` owns layer assignments and checks real imports, including
function-local imports and cycles. **x0 is reserved and empty**, for possible
future generators of fixed-point parameters (such as Q10–Q20) or LUT data.
No present constant was moved into x0. See [ARCHITECTURE.md](ARCHITECTURE.md).

## Scope of this transfer

Ported: current Book I evaluator, exit-aware check semantics from S2, canonical
JSON and signature safeguards, one create → execute → sign → verify flow.
Not ported: Warrant collective settlement/governance, the full WPL language,
MCP, Sigma waves/federation, historical runtimes, or persistent checkpoints. In-process resume is described below. There is no claim to
replace all predecessor behavior. A trusted signed check is not a quorum vote. The fingerprint is computed and
returned, but no settlement/admissibility consumer uses it yet.

## Provenance

- Kernel source: Sigma-Glyph `v0.7.0`, commit
  `9d10bbc2e92fdc394b488dc381e9b2a0942b7ea5`, `impl/sigma_glyph.py`, original SHA-256
  `f4d9990d40f07c8cfd3aa10512c2195a0a04e8dc78bc955c0f53dfe737d3feb4`.
  Adaptation removes embedded self-tests and the legacy two-value `eval_hash`
  API; Receipt becomes an immutable dataclass. Reduction rules are retained.
- Warrant S2 inspected at PR #80 head
  `16a3fae39af46222ff31f5fe10a717cb9ba8e39b`, `impl/warrant.py`.
  Canonicalization and weak-key guards are adapted; result+exit comparison is
  carried into a new single-format record implementation. This port is not an
  ACCEPT of PR #80 or a copy of its registration machinery.
- `tests/vectors.json` is preserved verbatim from the Sigma 0.7.0 tag's
  `tests/spec_conformance/vectors.json`: 49 cases (33 evaluation, 8 encoding,
  8 decoding). Its historical metadata names the source contract, not adoption
  authority for Stargate. Test assertions include exit, hash, spend and outcome.
- Source implementations are MIT, copyright s0fractal 2025–2026; see LICENSE.
  No predecessor specification text was copied into SPEC.md.

## Test

```sh
.venv/bin/python -m pip install -e .
.venv/bin/python architecture.py
.venv/bin/python -m unittest discover -s tests -v
```

The supported Python range is 3.11–3.14. CI checks each minor version, including
3.11.0 and 3.12.3 to exercise older argparse behavior, builds and installs a wheel,
then runs the suite outside the checkout with isolated imports. The test runner
prints the current count; `sg --version` reports the implementation build.
These checks are distinct from independent review.

## Continue a reduction (Python only)

```python
from stargate import kernel as k

raw = k.ser(k.APPLY, 6, left=k.I_H, right=k.K_H)
h = k.sha(raw)
state = k.start(h, 1, {h: raw})
assert state.status == "suspended" and state.receipt is None
k.resume(state, 2)  # total grant 3: materialization paid; I contraction waits
k.resume(state, 1)  # total grant 4
assert state.receipt.result_hash == k.K_H
assert state.receipt.atp_spent == 4
```

`resume` adds credit to the same process-owned object. The input mapping is
copied once; later edits to the caller's mapping cannot change execution.
Pending work and cumulative resource counters survive suspension. A suspension
has no canonical receipt and cannot serve as a completed check.

For S I I (I K), 21 grants of one ATP produce the same result, 21 ATP spent,
and exactly the same object-fetch and successful-contraction sequence as one
21-ATP run. This demonstrates retained work on that case, not a general speed
claim. Zero-credit normal-form probes can repeat the search-spine traversal;
no-repeat applies to fetches and prepared contractions, not all Python work.
Independent review measured inner step5 calls rising from 36 to 72 on its
control term with 1-ATP slicing. This is a case-specific observation, not a
universal overhead bound or wall-clock benchmark.

**Local-failure caveat:** with the same term, environment, total ATP and limits,
small increments can fault where one-shot completes, because every suspension
checks live and pending resource usage. A faulted state is terminal and cannot
be resumed; its work is lost through this API. Review reproduced one-shot
normal_form at 46 ATP versus sliced ResourceFault("term depth") under
max_node_depth=4. Do not assume splitting preserves local-failure behavior.

No CLI session service, checkpoint files, signed continuations or serialized
state are added. Objects are trusted in-process state; mutating private fields
or passing them between threads is unsupported. Discarding a suspended object
abandons the computation. Existing fixed-budget `eval_receipt` and signed-record
verification retain their canonical atp_exhausted behavior.

## A decision bound to its rule and facts

Save a reusable `rule.wpl` (fixture: `tests/eligibility-rule.wpl`):

```text
fact within_window: bool
fact retroactive: bool
check within_window && !retroactive
```

Save `facts.json` (fixture: `tests/eligibility-facts.json`):

```json
{"within_window":true,"retroactive":false}
```

```sh
sg keygen signing.key
sg policy rule.wpl --facts facts.json --key signing.key
sg export ENVELOPE_OBJECT_HASH check.sg.json --trust PUBLIC_KEY_FROM_KEYGEN
sg verify-bundle check.sg.json --trust PUBLIC_KEY_FROM_KEYGEN
```

The body signs hashes of the exact UTF-8 rule bytes and canonical JSON facts.
The recipient authenticates these bytes, recompiles the rule with those facts,
compares the ENTIRE generated check and then re-executes the signed term.
A verified report includes `policy.source` and `policy.inputs` as well as their
hashes. Missing source or facts means unverified, never a policy reject.

Changing retroactive to true produces a new signed reject under the SAME rule
hash and a DIFFERENT facts hash. Renaming a fact can leave the computational
term unchanged but changes the signed rule/facts identity. Signature verification
alone is insufficient: even a trusted signer cannot attach unrelated rule/facts
to an existing term and get a provenance-verified report.

Only boolean facts, true/false, !, &&, || and parentheses are supported. Facts
must match declarations exactly: no duplicate, missing, extra, unused or coerced
values. The CLI accepts readable JSON and stores its canonical form; duplicate
keys are refused. Inline fact assignments are not accepted in rules supplied
with a facts file. `compile_source` retains inline literals as a low-level test/
compiler convenience, not another record format or historical evaluator.

`--max-atp` bounds authoring measurement (default 100000). The record pins exact
measured spend and always expects TRUE, so false means reject. Source limits:
8192 UTF-8 bytes, 256 tokens, 32 nested parentheses/negations. Compiler errors
emit no envelope; local resource failures remain unverified.

This authenticates the rule/input/compiled-check relationship under the current
compiler contract. It does not establish real-world truth of facts or formally
prove the compiler: verifier and author use the same parser/lowering. A shared
bug agreeing on this closed input remains possible; independent truth-table and
mutation tests address examples, not all programs. Policy identity is in RecordID,
not in the computational fingerprint, which still has no settlement consumer.

Raw `sg record` has `policy: null` and makes only a computation claim. Its report
likewise has `policy: null`; it cannot masquerade as a verified rule. The build-6
body lacking this field is rejected. This is one changed UNRELEASED 32K draft,
not an added compatibility branch.

Boolean lowering follows Warrant `impl/ski_policy.py` at
`16a3fae39af46222ff31f5fe10a717cb9ba8e39b`: TRUE=K, FALSE=K I,
NOT p=p FALSE TRUE, p AND q=p q FALSE, p OR q=p TRUE q.

## Give someone a check they can verify offline

After `sg policy` or `sg record`, export the returned envelope object:

```sh
sg export ENVELOPE_OBJECT_HASH check.sg.json --trust PUBLIC_KEY
```

Send `check.sg.json`. The recipient independently selects the key they trust and
runs, even in an empty directory:

```sh
sg verify-bundle check.sg.json --trust PUBLIC_KEY
```

Only the file and an installed Stargate package are needed. The verifier does
not create or consult `.stargate`, fetch objects over the network, extract files,
or accept trust declarations inside the bundle. It produces the same record
verification report as `sg verify` on a complete store, including verified/reject.
Public-key delivery/authentication remains the recipient's responsibility.

Export first verifies the signature, explicit trust and computation. It bundles
the exact envelope and bytes fetched by verification, including mandatory rule
and facts material for policy records, plus demanded computational objects. Intrinsic
I/K/S and unused declared objects need no payload; absent unused entries do not
prevent export. The original signed environment and record identity stay intact.
Removing a demanded object produces unverified (3); hash/encoding/signature
corruption is invalid (2). A declared absence stays absent regardless of local
files. The container is canonical JSON, with a local 16 MiB file limit. Export
refuses to overwrite an existing file and publishes only a fully written file.

For policy records, the bundle now carries the authenticated rule and facts as
well as the computation. It is not a self-executing package: Python dependencies
must be installed beforehand.
There is no bundle signature or new trust system; integrity comes from the
existing signed record and content hashes. An export key is never embedded as
authority for the recipient.

## Require a proof for your own rule and facts

The recipient selects the trusted key, rule and facts independently of the bundle:

```sh
sg require check.sg.json --trust PUBLIC_KEY --rule expected.wpl --facts expected.json
```

Exit 0 / `satisfied` requires a verified policy-bound accept, the exact expected
UTF-8 rule bytes, and the expected canonical boolean facts. Whitespace changes
in a rule change its identity; JSON fact formatting and key order do not.
Both files are required, and facts must exactly match the rule declarations.
A trusted author cannot substitute an easier rule such as `check true`.

Exit 4 / `unsatisfied` preserves the successful verification under `verification`
and reports `policy_missing`, `rule_mismatch`, `facts_mismatch`, `subject_mismatch`, or `decision_reject`
(in that order). A valid record for another request is not an invalid record.
Malformed input or failed verification retains exit 2; missing bytes, resource
limits and I/O failures use 3. These failures never become an unsatisfied decision.
`verify-bundle` still returns exit 0 for a verified reject; `require` does not.

Python: `stargate.bundle.require_bundle(raw, trusted_keys, rule=source, facts=inputs)`
returns the same report and preserves verification exceptions. It reads no local
object store and performs no action beyond checking the requirement. The expected
hashes are included in the report, but the report is not a new signed artifact.
This does not establish real-world fact truth, freshness, or one-time use: the
same bundle can satisfy the same request repeatedly. Build 9 extends the draft
record with a required subject field; Kelvin remains 32K.


## Bind a decision to the artifact you are handing over

```sh
sg policy rule.wpl --facts facts.json --key signing.key --subject artifact.bin
sg export ENVELOPE_OBJECT_HASH proof.json --trust PUBLIC_KEY
sg require proof.json --trust PUBLIC_KEY --rule rule.wpl --facts facts.json --subject artifact.bin
```

Author and recipient hash their own file bytes. The signed body contains
`subject`: a lowercase SHA-256 hash, or null when no subject is selected.
Identical bytes under another filename satisfy the requirement; different bytes
produce `unsatisfied` / `subject_mismatch` (exit 4), even with the correct rule,
facts, trusted signer and accept result. Missing/unreadable recipient files give
`unverified` (3). Only regular files are accepted; directories and FIFOs are invalid (2).
Symlinks are followed: the opened target bytes are hashed, not the link or its name.
Hashing streams in bounded
chunks and refuses a change detected in file size or modification metadata.

Omitting `--subject` explicitly requires subject null, not a wildcard. A bound
record cannot silently satisfy an unbound request, or vice versa. Raw `sg record`
also accepts `--subject`, but still cannot satisfy a policy requirement.

Python `author_policy`, `create_record` and `require_bundle` accept keyword
`subject=None` or a lowercase SHA-256 digest. These APIs validate the digest;
they do not independently obtain or inspect the artifact. CLI hashes the file.
The verified report exposes the signed subject, and the requirement report also
contains the recipient's expected subject. A changed subject changes Record ID
and needs a new signature; the computational fingerprint is unaffected.

The subject alone is a statement of what the decision concerns, not evidence that
the boolean facts describe that file correctly. The optional derivation below
checks a limited set of byte properties independently. Its bytes are not bundled, stored,
or fetched by the evaluator. `verify-bundle` authenticates the subject claim
without checking artifact availability; `require --subject` compares local bytes.
No filename, filesystem permission, safety, freshness or single-use guarantee is
implied. The result concerns bytes read during hashing: it does not lock a path
or guarantee what a later upload/execution will read. Use an immutable artifact
when connecting this check to another action. `require` performs no such action;
`admit` below publishes a copy of the bytes it checked.

This replaces the current unreleased draft shape: bodies missing subject are
invalid. There is no compatibility branch or temperature freeze.


## Publish only the artifact bytes that passed

```sh
sg admit proof.json --trust PUBLIC_KEY --rule rule.wpl --facts facts.json \
  --subject candidate.bin --output approved.bin
```

`admit` streams the candidate into a private temporary file next to the output,
hashing the same chunks it writes. It runs the recipient requirement against
that digest, then publishes that staged file only on `satisfied`. It never reopens
the original for publication. Replacing or editing the original after copying
cannot alter the admitted copy. The output is a separate file with mode 0600;
source names, permissions and symlinks are not copied.

Exit 0 / `admitted` means publication completed. JSON includes
`artifact: {path, sha256}` and the satisfied report under `requirement`.
Exit 4 / `unsatisfied` returns the requirement report with `artifact: null` and
publishes nothing. Invalid inputs/proofs remain 2; unavailable source/proof
material and verifier resource failure remain 3. Output I/O errors (including
an occupied destination) are `operation_error` / 1. Existing destinations,
including symlinks and a destination created concurrently, are never replaced.
A different output path is required even when source and output bytes match.

Python: `stargate.artifact.admit_bundle(raw, trusted_keys, rule=source,
facts=inputs, subject=input_path, output=output_path)`. Verification exceptions
are preserved; source read I/O raises StoreError, destination I/O raises OSError.
It uses no local object store. Temporary files are removed on ordinary success
and failures before publication; abrupt process termination can leave a temporary
file. This is exclusive atomic publication, not crash-durable storage: there is
no fsync guarantee, and a cleanup failure after publication may leave an output
while reporting an error. Do not treat an error as proof that no output exists.

The output directory must be controlled by the caller. This is not a sandbox
against another process with access to that directory or the admitted file.
It does not prevent later writes to the output, enforce one-time use, execute
an artifact, or upload it. File size/disk use is not capped; hashing uses bounded
memory. The signed subject still expresses the signer's association with the
facts, not proof of their real-world truth. The record and bundle formats and
32K temperature are unchanged by this stage.


## Derive facts from the actual artifact

The recipient can compute byte properties instead of trusting supplied booleans.
Use a rule whose declarations match a locally selected derivation profile:

```text
fact nonempty: bool
fact small: bool
fact text: bool
check nonempty && small && text
```

Save `profile.json`:

```json
{"nonempty":{"size_at_least":1},"small":{"size_at_most":1048576},"text":{"utf8":true}}
```

```sh
sg policy rule.wpl --derive profile.json --subject candidate.txt --key signing.key
sg export ENVELOPE_OBJECT_HASH proof.json --trust PUBLIC_KEY
sg admit proof.json --trust PUBLIC_KEY --rule rule.wpl --derive profile.json \
  --subject candidate.txt --output approved.txt
```

`--derive` replaces `--facts` on policy, require and admit; they are mutually
exclusive. Derivation requires a subject file. A profile contains 1–32 named
facts, each with exactly one predicate: inclusive `size_at_least`, inclusive
`size_at_most` (nonnegative integer byte thresholds below 2^53), or `utf8: true`
(strict UTF-8 validity). Boolean thresholds, unknown predicates, duplicate JSON
keys and nonmatching/unused fact domains are invalid. No external commands or
plugins are loaded. All rule facts must be derived in this mode; manual and
derived facts cannot be mixed.

Size means byte count, not character count. UTF-8 is checked incrementally,
including a final decoder flush; malformed sequences and incomplete tails give
false. Empty content is valid UTF-8 (use size_at_least to require nonempty).
BOM and NUL are valid UTF-8; validity does not imply safe markup or safe execution.

Authoring signs the measured facts and subject through the existing record.
The recipient selects its own profile independently of the sender. In admit,
measurement sees exactly the chunks written to the staged file, in the same pass
as subject hashing. The computed facts become the expected facts for require.
A signed lie gives facts_mismatch/4; honest false facts that make the rule false
give decision_reject/4. Neither publishes. Changing the original after staging
cannot change the measured facts or admitted bytes.

The local report adds `derivation: {profile, facts, subject}` (under requirement
for admitted output). This measurement report is unsigned. The profile is local
configuration, not signed or transported: it defines what the recipient measures,
not a portable proof of how the author obtained facts. verify-bundle still checks
only signed compilation/computation, without inspecting artifact bytes.

Python: `measure_subject(path, profile)` returns the measurement in one read;
`admit_bundle(..., derive=profile, subject=path, output=path)` computes it during
staging. Exactly one of facts or derive is required. Invalid derivation profiles raise
`PolicyError`, including canonical snapshot failures; CLI still reports invalid/2.
Manual --facts mode remains
an assertion supplied by the caller. No claim is made about properties beyond
these three byte predicates, and no signed format or Kelvin change is added.


### Admit only when every requirement holds

`sg admit-all` checks several decisions about **one staged artifact** before
publishing anything. Use it when a reviewer asserts a judgment and the recipient
also measures the bytes. Each requirement has its own trusted keys; passing one
does not grant trust to another.

Create an operator-controlled `plan.json`:

```json
[
  {"name": "review", "bundle": "review.json", "trust": ["REVIEWER_PUBLIC_KEY"],
   "rule": "review.wpl", "facts": "review-facts.json"},
  {"name": "bytes", "bundle": "bytes.json", "trust": ["MEASURER_PUBLIC_KEY"],
   "rule": "bytes.wpl", "derive": "byte-profile.json"}
]
```

Replace the public-key placeholders with the trusted 64-character lowercase hex
keys. Paths in the plan are relative to the plan file, regardless of the working
directory. Then:

```sh
sg admit-all plan.json --subject candidate.whl --output approved.whl
```

The source is read once. Every derivation and every subject check uses those
same staged bytes. A change detected during that read causes an unverified/3
refusal; the original-byte guarantee applies after staging has completed. Publication occurs only after all named requests pass;
refusal or a missing/corrupt second proof leaves no output or temporary stage.
An existing output is never overwritten. The usual 0/1/2/3/4 exit meanings apply.

The report lists `requirements` in plan order. On `unsatisfied`, `failed` names
the first refusal and later requirements have **not been checked**. Each nested
report carries its own signer, expected rule/facts and optional derivation.
A plan requires 1–32 entries with unique names. It is recipient configuration:
choose it yourself, rather than adopting a sender's proposed policy. Neither
this plan nor its local report is a signed, portable proof of conjunction.

Python: `stargate.artifact.admit_all(requests, subject=path, output=path)`.
Each request uses the same keys, with bundle **bytes**, rule **text**, facts or
derive **dictionaries**, and a nonempty collection of trusted public keys. The
single-request `admit_bundle` shares the implementation. The release-gate example
now uses joint admission for its reviewer judgment and byte measurements.

### Carry a counterexample into the next session

Build 13 adds **inert evidence packets**, with source bytes, a claim, scope,
limitations and reproduction instructions. The first two are real review cases:
[M1](examples/case-m1.json) (an unfed UTF-8 deriver still returns true) and
[M2](examples/case-m2.json) (the old test never mutated asserted facts).

```sh
sg case-inspect examples/case-m1.json
sg case-unpack examples/case-m1.json --output /tmp/received-m1
```

`intact` means hashes and structure match; `materialized` means the files were
written. Neither means the claim was checked, the author authenticated, or the
included code is safe. These commands never execute packet contents. The whole
packet's `case_id` changes if someone rewrites its data and hashes together.

After reading the extracted README and code, an operator can explicitly run:

```sh
python -I /tmp/received-m1/replay.py
```

This executes included Python with your permissions; `-I` is **not a sandbox**.
The two supplied cases require Python with cryptography>=43 installed. They carry
the relevant Stargate source, tests and mutation; no checkout, network fetch or
chat transcript is needed. The runner requires four outcomes: both control tests
pass, the old test misses the mutant, and the new test fails for the stated reason.
It emits `reproduced` only after observing that matrix. This demonstrates one
counterexample, not general correctness. Both cases were exercised on Python 3.14.

To make your own packet, supply a JSON document with `manifest` (title, claim,
scope, limits, source:{repository,commit}, entrypoint, expected) and `files` (a list
of relative paths), then run `sg case-pack manifest.json --root directory --output
case.json`. The directory must remain under your control while reading. Existing
outputs refuse; unpacking requires a new directory and is not an atomic multi-file
transaction. `examples/counterexamples.py` rebuilds our two packets from pinned Git
commits. Rebuilding requires those commits; receiving/replaying the packets does not.

[Dependency direction and filename coordinates](ARCHITECTURE.md) records the
Trinity-inspired architecture recommendation. Build 14 relocates Python sources to `src/`, breaks the records/policy cycle
and enforces the layer table; coordinate filename prefixes remain a later choice.

## A boolean laboratory you can hand to a chat

Build 15 implements the first finite experiment from [VISION.md](VISION.md).
No signer or trusted key is needed. A model proposes **text**, then a matching
checker recomputes the whole truth table and produces a successor only when
the fixed objective holds. It does not modify your checkout or run generated
Python. WPL programs have up to eight inputs (at most 256 rows).

```sh
sg lab-create examples/lab-parent.wpl \
  --input a --input b --input c --input d \
  --input e --input f --input g --input h \
  --objective lower_max_atp --output experiment.json
sg lab-inspect experiment.json
```

Give the packet and the `world_id` from inspection to the model. The packet
contains a readable guide, the rule and exact checker sources. Ask it to return
only the following JSON shape, copying the parent ID verbatim:

```json
{"parent":"COPY_WORLD_ID_HERE","candidate":"fact a: bool\n...\ncheck ..."}
```

The ellipses above are placeholders, not valid WPL. All eight declarations must
be present and used. [lab-candidate.wpl](examples/lab-candidate.wpl) is a complete
valid candidate for the example. Save the model's JSON response as `proposal.json`.
It supplies no verdicts, digests, ATP claims or signatures.

```sh
sg lab-check experiment.json proposal.json --output successor.json
sg lab-unpack experiment.json --output received-experiment
# After inspecting the extracted code, explicitly execute it:
python -I -S received-experiment/replay.py --expect-runtime INDEPENDENT_RUNTIME_DIGEST \
  proposal.json successor-offline.json
```

Before executing replay, obtain `runtime_digest` and `replay_digest` from an
independently trusted installation's `lab-inspect` output for the matching
runtime, or derive them from a separately reviewed repository revision. This
reference need not come from the founder. Compare `shasum -a 256
received-experiment/replay.py` with that independent `replay_digest`; pass the
independent `runtime_digest` as `--expect-runtime`. Neither a digest copied from
the received packet nor a verdict's own reported digest establishes trust.

The runtime digest is SHA-256 of the canonical filename-to-source map. The
trusted launcher hashes extracted sources with standard-library code **before
importing them**, and refuses a mismatch with exit 3 and no successor. It then
compiles that same in-memory snapshot into modules. The packet directory never
enters `sys.path`; adjacent modules and `__pycache__` are not loaded. Source files
are not reread during execution. `-I -S` is required before any non-builtin
launcher import. All
semantic reports carry the runtime digest. A malicious launcher could bypass
this check or print a false digest; that is why its own bytes must be checked
independently before execution. The interpreter and independently checked launcher remain trusted. Source-file
changes after the snapshot cannot change the executed modules; this is not a
sandbox against arbitrary changes to the process or interpreter.

The extracted copy needs only Python >=3.11, with no installed Stargate, plugins,
keys, network or original repository. Extraction does not execute sources;
explicit replay executes Python with your permissions, **not in a sandbox**.
The provided example checks 256 rows and reduces worst-case ATP from 98 to 80.
A cheaper program with a different truth table is refused with a concrete input.

`lab-check` exit codes: 0 admitted; 4 counterexample or equivalent without the
required improvement; 3 incomplete or unavailable matching runtime; 2 invalid
input; 1 checker or local operation failure. A small budget must produce
`incomplete`, never a false equivalence. Existing outputs are not overwritten.
The console report is an observation, not a signed proof; the next checker must
recompute. A successor's parent pointer alone does not establish a valid change.

This finite mode has an independent parser/oracle, not an independently developed
second implementation of Stargate or a formal proof of its Python verifier.
The tests separately exercise a shared-parser fault, an internal lowering fault
and budget exhaustion. The packet pins exact source bytes; updating the runtime
requires an explicit new experiment rather than quietly reinterpreting an old one.


## Search with replayable counterexamples

`sg lab-search` proposes deterministic one-edit WPL mutations and runs the
existing full admission gate on survivors. It has no authority to weaken a
world's objective. Start with a newly created packet for this runtime:

```sh
sg lab-create examples/search-parent.wpl --input a --input b --input c \
  --objective lower_max_atp --output search-world.json
sg lab-search search-world.json --max-candidates 32 --output successor.json > search.json
```

The report contains every attempted candidate, full verification reports or
single-row screening witnesses, and `experience`. Save that object as JSON
(e.g. `jq '.experience' search.json > experience.json`) to reuse it:

```sh
sg lab-search search-world.json --experience experience.json --max-candidates 32
```

Experience is bound to the exact parent and runtime, and every alleged
counterexample is recomputed before it can prune candidates. A saved verdict
is never accepted as proof. A candidate matching all remembered rows must still
pass exhaustive `lab-check`; replayed examples cannot semantically reject a fully verifiable equivalent
candidate, even if another participant chose every input row. They may add
replay cost; this is not a universal speedup guarantee. The report's `proposal`
can be given directly to
that command or to standalone replay. The search implementation is not part of
the portable checker closure: its proposals need no trust in the generator.

This is a bounded neighborhood, not complete synthesis: preorder negations,
operator flips, operand swaps, idempotence and double-negation elimination.
Only identical source strings are deduplicated, not programs that happen to
agree on a finite sample. Up to 256 candidate attempts can be requested;
duplicates and invalid mutations count toward that limit. The first admitted
candidate wins; it is not asserted to be globally optimal. Experience restarts
the same search with better screening, rather than resuming an execution cursor.

Exit 0 = found; 4 = this finite neighborhood exhausted; 3 = candidate limit,
evaluation incomplete or missing material; 2 = invalid input/experience;
1 = checker or operation error. No unsuccessful path writes a successor.
An over-budget candidate is recorded as incomplete and skipped, without adding
it to experience. If any candidate remains incomplete when the neighborhood ends,
exit is 3 rather than 4. Checker errors stop immediately; unresolved incoming
experience is refused before search. Neither exhaustion status means that no
better program exists. Candidate count
and each world's ATP bound are distinct; neither promises a CPU time bound.

## Discover finite input/output properties

Build 17 adds a small hypothesis generator and a separate recomputing checker:

```sh
sg lab-create examples/invariants-parent.wpl --input a --input b \
  --objective lower_max_atp --output properties-world.json
sg lab-discover properties-world.json --output properties.json
```

For `a && (b || !b)` this establishes independence from `b` and monotonicity in
both inputs. Independence from `a` is refuted by two assignments that differ only
in `a`. The catalog tries exactly `2 + 2N` hypotheses: constant false/true,
independence from each input, and monotonicity in each input. This is exhaustive
checking of this catalog, not discovery of every possible invariant.

A participant can copy one `results[].claim` into a JSON file, or propose it in
chat without running anything. Its entire format is:

```json
{"parent":"COPY_WORLD_ID","property":{"kind":"independent","input":"b"}}
```

Other properties are `{"kind":"monotone","input":"a"}` and
`{"kind":"constant","value":true}`. No claimed answer, digest or proof is
accepted in this format. Check it with:

```sh
sg lab-check-invariant properties-world.json claim.json
```

The checker recomputes every input row through SKI and the independent Boolean
oracle, then checks the property over that table. Monotone means false-to-true
input changes cannot turn a true output into false. These are properties of the
finite Boolean function, **not loop invariants, causality, or facts about external
artifacts**. A small ATP budget gives `incomplete`, establishing nothing. Even a
counterexample is reported only after the whole table is checked in this version.
The world's optimization objective is irrelevant to property checking.

Claims are also supported by portable replay. Follow the existing `lab-unpack`
and independent launcher/runtime digest verification instructions above, then:

```sh
python -I -S replay.py claim.json --invariant --expect-runtime RUNTIME_DIGEST
```

Exit 0 means `established` for a claim, or `complete` for discovery (including
refuted hypotheses); 4 means `counterexample`; 3 means incomplete or unavailable
runtime; 2 invalid input; 1 checker/operation error. Reports include checked rows,
a table digest and concrete counterexample witnesses. They are unsigned
observations to recompute, not new authority or automatically adopted constraints.
Neither command emits a successor. `--output` exclusively writes a completed
catalog, never a partial one. Build 17 adds the property checker to the pinned
runtime closure; create a new packet for it, rather than altering historical ones.

## Carry a replayable history to the next participant

A world contains a predecessor ID, but that pointer alone does not prove how it
was reached. Build 18 adds a lineage: one initial world and at most 32 ordered
proposals. It stores no accepted verdicts or claimed successor bytes. Every check
replays every transition and reconstructs the tip through the existing gate.

```sh
sg lab-create examples/lineage-parent.wpl --input a --input b --input c \
  --objective lower_max_atp --output root.json
sg lab-inspect root.json
sg lineage-start root.json --output history-0.json
sg lab-search root.json --output next-world.json > search.json
```

Copy `proposal` from the search report (or a chat participant's proposal) into
`proposal.json`. Copy the inspected root ID as `ROOT_ID` below:

```sh
sg lineage-append history-0.json proposal.json --expect-root ROOT_ID --output history-1.json
sg lineage-check history-1.json --expect-root ROOT_ID --output checked-tip.json
```

Search or propose against `checked-tip.json`, then append to `history-1.json`.
The example has a two-step reduction `!!!!(a || b) || c` → `!!(a || b) || c` →
`(a || b) || c`, with worst-case ATP 61 → 43 → 25. Each proposal names the ID
of its immediately preceding world. Input domain, objective, budget and runtime
are inherited from the root, never supplied by the proposal.

`--expect-root` is the recipient's independently chosen starting point. Taking it
blindly from a received history would permit replacing the whole experiment.
A verified history means these particular transitions passed from that anchor;
it does not claim latest state, uniqueness of a branch, optimality, authorship or
actual chronology. A shorter valid prefix is another valid history. Zero steps
return the anchor itself without evaluating its rule. An anchored checkpoint may
already have a predecessor: history before that checkpoint is not verified here.

```sh
sg lineage-unpack history-1.json --output offline-history
```

Unpacking only validates the format/runtime and materializes files; it does not
verify transitions or run packet code. Use independently authenticated launcher
and runtime digests as for `lab-unpack`, then run inside that directory:

```sh
python -I -S replay.py lineage.json tip.json --lineage \
  --expect-root ROOT_ID --expect-runtime RUNTIME_DIGEST
```

Both installed and offline checking produce the same report and tip bytes.
On any refused, unfinished or broken transition, there is no tip output: a good
prefix cannot mask a failed tail. Reports name the zero-based failed step and
include the gate results. Append writes a new history only if every step passes;
check writes a tip only on success. Existing outputs are never overwritten.

Exit codes for append/check: 0 verified_lineage, 4 not_admitted (counterexample or
insufficient improvement), 3 incomplete or unavailable material/runtime,
2 invalid format/anchor/parent, 1 checker or local operation failure. Histories
are limited to 4 MiB and 32 proposals; each proposal has the existing 16 KiB
limit. These limits do not promise a wall-time bound. Every append replays the
prefix again: no cached report becomes authority. New build-18 runtime packets
are required; previous packet bytes are left intact.

## Let behavior change within explicit properties

The default lab preserves the parent's entire truth table. A **property world**
uses a different explicit contract: parent and candidate must both satisfy every
listed property, but their other answers may differ. The properties belong to the
root world and are inherited unchanged; a proposal still contains only parent
and candidate. Choosing that root chooses what changes are allowed.

```sh
sg lab-create examples/property-parent.wpl --input a --input b \
  --properties examples/property-contract.json --output property-world.json
sg lab-inspect property-world.json
sg lab-search property-world.json --output property-successor.json
```

This world starts with `a && b`. It requires non-decreasing behavior in both
inputs, false at `00`, and true at `11`. Search finds a rule equivalent to
`a || b`: both requirements at the corners and both monotonicity conditions hold,
while **two of four answers change**. The gate says `satisfies`, not `equivalent`.
With the default `satisfy` objective, equal cost (14 → 14 ATP) is allowed. Add
`--objective lower_max_atp` to also demand a strict cost decrease.

Properties are `constant`, `independent`, `monotone` as above, plus an exact case:
`{"kind":"case","facts":{"a":false,"b":true},"value":true}`.
A case names every input with a Boolean value; partial assignments are invalid.
The contract is a nonempty list of at most 32 distinct properties. In this example,
the two cases exclude the always-true and always-false functions. Weaker contracts
may admit trivial or unwanted programs: the checker establishes exactly the
chosen properties, not usefulness, safety or unstated intentions.

Both full truth tables are cross-checked before property assessment. A failing
parent yields `parent_rejected`; a candidate violating a property yields
`counterexample`, with the property and a concrete row or pair. No successor is
produced in either case (CLI 4). Exhaustion is still `incomplete`/3 and checker
failure is 1. Creating/inspecting a root is structural validation, not a claim
that its rule satisfies its properties. An invalid parent cannot be repaired by
an admitted transition; choose a new root contract or rule explicitly.

Lineage and offline replay use the same gate and retain the exact properties.
The recipient's root anchor therefore binds this permission to change behavior.
An empty history retains its existing zero-transition meaning; it does not check
root properties. Invariant discovery can still describe a rule that violates its
own contract: observation grants no transition authority. The discovery catalog
remains the existing 2+2N properties; exact cases can be submitted individually.

Search uses full gate checks in this mode and saves no equivalence counterexamples.
A differing answer is permitted, so screening against remembered parent/candidate
differences would be unsound. Nonempty equivalence experience is rejected for
property worlds; empty experience is harmless. Existing equivalence-world search
keeps its previous screening. This is an explicit opt-in mode, not a weaker default.

### Continue a lab check between rows (Build 20)

A Python caller can keep a check alive across bounded calls without recomputing
completed rows:

```python
from stargate import lab

state = lab.start_transition(world_bytes, proposal, rows=2)
while state.status == 'suspended':
    progress = state.report  # detached snapshot; never a resume input
    state = lab.resume_transition(state, rows=2)
report, successor_bytes = state.report, state.successor
```

Each call completes at most `rows` input pairs (parent and candidate). Quotas
are integers 0–256; zero does no evaluation. The default start quota is zero:
it validates and snapshots the world/proposal but evaluates no rows. The last
row also finishes the property/cost checks, without needing an extra call.
`verify_transition` uses the same engine to run to completion.

This is an **owned state in the same Python process**, not a transferable proof
or a file checkpoint. Keep the object itself; dictionaries, report snapshots,
copies, private-field edits and concurrent calls are not supported continuations.
A suspended check has no successor and cannot authorize a transition. Final
reports and successor bytes match an uninterrupted check under the same runtime
and environment. Both equivalence and property worlds are supported.

A row quota is not ATP, wall time or a memory limit. Each program in each row
still has the world's fixed `max_atp`; its exhaustion or a local resource refusal
ends the check as `incomplete`, which cannot be resumed. Oracle disagreement ends
it as `checker_error`. Unexpected exceptions propagate and leave the state
`faulted`, also non-resumable. Restarting after a terminal failure is a new check.
No `lab-resume` CLI or serialized checkpoint is claimed: a new process must
recompute work it did not itself verify. The compiler's existing within-row
exact-budget replay remains; slicing adds no repeat of completed rows.

### Pass an unfinished task to another chat (Build 21)

`lab-task-start` packages the world, candidate and **claimed** completed rows.
A recipient uses its own checker to recompute those rows before continuing.
The stable task ID binds both the exact world and exact candidate; obtain it
from your chosen inputs or a separately agreed source, not from an untrusted
packet you are trying to authenticate. Packet IDs change as progress grows. In Python, compute your chosen anchor with
`labtask.identity(world_bytes, proposal)` after validating your inputs.

```sh
# A suspended task is exit 3, and --output contains a task, not a successor.
sg lab-task-start world.json proposal.json --rows 2 --output task.json
sg lab-task-inspect task.json
# Recipient supplies the independently chosen TASK_ID.
sg lab-task-resume task.json --expect-task "$TASK_ID" --rows 3 --output next.json
```

Here `--rows 3` means **three new rows after replaying the prefix**. Even
`--rows 0` rechecks all claimed rows. With two imported rows and three new ones,
there are five parent/candidate pairs computed, not three. Reports separate
`replayed_rows` from `new_rows` and embed the recomputed `verification` report.
Inspection exits 0 with `unverified_progress`: it validates structure/runtime
without establishing any row's truth.

The output kind is explicit: `output_kind: task` and exit 3 when suspended;
`output_kind: world` and exit 0 only for an admitted successor. Refusal, terminal
`incomplete`, and checker failure have no output bytes. Existing output paths
are never overwritten. These examples are individual commands: in a shell using
`set -e`, deliberately handle exit 3 before running the next command.

For a recipient with Python but no installed Stargate:

```sh
sg lab-task-unpack task.json --output task-offline
python -I -S task-offline/replay.py task-offline/task.json next.json \
  --task --expect-task "$TASK_ID" --rows 3 --expect-runtime "$RUNTIME_DIGEST"
```

Authenticate `replay.py`'s digest and the runtime digest independently, just as
for world/lineage replay. Unpacking validates and writes files; it runs no packet
code. The checked launcher executes only verified source snapshots. This is not
a sandbox and still trusts Python and its standard library.

A task is canonical JSON with `stargate_task: 32`, `world`, `proposal`, and
`prefix`. It contains no continuation objects or trusted verdicts. Prefix results
are compared in full (inputs, values, term hashes and ATP), not by trusting a
sender's digest. A completed-prefix claim that exhausts the fixed world ATP
budget on replay is invalid (exit 2), even if its claimed ATP fits the budget.
A local resource failure remains incomplete (exit 3). Exhaustion in new rows
also remains incomplete: nobody claimed those rows were completed. A complete table is not a pending task. Dropping a suffix or
resetting the prefix to empty is allowed; it merely discards claimed progress.
A different candidate or world requires a different task anchor.

This transfers the **work request and its context**, not the authority of a
previous process. Repeated handoffs repeat prefix computation. No cross-process
work savings, persisted kernel state, background execution or automatic routing
between chats is claimed. The recipient still chooses to run the packet.

### Check behavior over time (Build 22)

A finite machine has 1–6 Boolean state bits and 0–2 disjoint event bits. Each
state bit gets a WPL rule for its next value; another rule is the invariant.
All next rules read the **same old state and event**. Every event valuation is
possible at every reached state. Safety means the invariant holds at all states
reachable from the listed initial states, including the initial states themselves.

```sh
sg machine-create examples/machine-delayed-failure.json --output machine.json
sg machine-inspect machine.json
# Choose MACHINE_ID from your independently selected machine.
sg machine-check machine.json --expect-machine "$MACHINE_ID"
```

This example exits **4**, with the exact counterexample `00 → 01 → 11`:
`next(a)=b`, `next(b)=!a`, invariant `!a`. An in-place implementation would
incorrectly compute the second step as `10`. The WPL examples include tautologies
for irrelevant inputs because the existing language requires using every declared
fact. Next rules declare all state/event names; the invariant declares only state
names. No new expression syntax is introduced.

The checker explores breadth-first, evaluates every initial/newly reached state,
and considers every event at each expanded state. Each expression is compiled to
SKI and compared with the independent Boolean parser/evaluator. A counterexample
carries its initial state and concrete event/state steps; it is a shortest path
in number of transitions (ties follow initial-list and Boolean event order).
Unreachable states that violate the invariant do not refute it.

`established` (exit 0) requires a fully explored graph closed under every event
and every reachable invariant checked. `--max-edges N` bounds completed edges,
not time: hitting the quota with work remaining is `incomplete` (exit 3), never
safety. The default/hard maximum is 256, sufficient for all 64×4 state/event
pairs. ATP/resource exhaustion also gives 3; a checker disagreement gives 1;
malformed input or a wrong machine anchor gives 2. Inspection and creation return
`unchecked_machine`, not a safety verdict. Admission is a separate command below.

```sh
sg machine-unpack machine.json --output machine-offline
python -I -S machine-offline/replay.py machine-offline/machine.json \
  --machine --expect-machine "$MACHINE_ID" --max-edges 256 \
  --expect-runtime "$RUNTIME_DIGEST"
```

As with other offline modes, authenticate the launcher/runtime independently.
The packet supplies the machine guide and pinned checker sources, not authority
to execute them automatically. Reports are recomputable, not signed certificates.
There is no fairness, liveness, external event restriction
or persisted graph continuation in this build. Real-world systems are covered
only to the extent that this finite model describes them accurately.


### Change a machine without weakening its safety contract (Build 23)

A proposal contains only `parent` (copy the exact MachineID) and `next` (a complete
map of state names to new WPL rules). For example, a machine whose invariant is
`!a` can change what `b` does, provided no reachable transition makes `a` true.
The candidate may reach states its parent never visited: those states must also
satisfy the inherited invariant.

This creates a safe parent holding `00` and proposes making `b` true while
keeping `a` false. Run in a fresh directory after installing Stargate:

```sh
MACHINE_ID=$(python - <<'PYTHON'
import json
from pathlib import Path
from stargate import lab, machine

def rule(expr):
    return 'fact a: bool\nfact b: bool\ncheck ' + expr

raw = machine.create(dict(state=['a', 'b'], events=[],
    initial=[dict(a=False, b=False)], max_atp=1000,
    next={'a': rule('a && (b || !b)'), 'b': rule('b && (a || !a)')},
    invariant=rule('!a && (b || !b)')))
Path('parent-machine.json').write_bytes(raw)
Path('proposal.json').write_text(json.dumps(dict(parent=lab.identity(raw), next={
    'a': rule('a && (b || !b)'), 'b': rule('(a || !a) && (b || !b)')})))
print(lab.identity(raw))
PYTHON
)
sg machine-change parent-machine.json proposal.json --expect-machine "$MACHINE_ID" \
  --output successor-machine.json
```

For offline use, unpack that parent with `machine-unpack`. Authenticate the
launcher/runtime independently, then run:

```sh
python -I -S machine-offline/replay.py proposal.json successor-offline.json \
  --machine-change --expect-machine "$MACHINE_ID" --expect-runtime "$RUNTIME_DIGEST"
```

Both parent and candidate are checked from their initial states. `safety_preserved`
(exit 0) writes the successor if requested. An unsafe parent gives
`parent_rejected` (4); an unsafe candidate gives `counterexample` (4), including
its shortest violating trace under `checks.candidate`. Neither writes a successor.
Incomplete checks give 3; checker disagreement gives 1; malformed proposals or
wrong parent anchors give 2. `--max-edges` applies separately to each graph.

The successor changes **only** `next`: initial states, state/event names, invariant,
ATP ceiling and runtime remain exact. An identical proposal is allowed and keeps
the same MachineID. No cheaper-cost or behavior-equivalence claim is made.
A weak invariant can admit undesirable behavior; the gate does not invent the
missing requirements. Repairing an unsafe root requires explicitly choosing a new
root, not calling it an admitted change. Keep the parent and proposal to replay
an admission: the successor alone carries no lineage or admission certificate.


### Let counterexamples guide machine mutations (Build 24)

```sh
sg machine-search parent-machine.json --expect-machine "$MACHINE_ID" \
  --max-candidates 32 --output found-machine.json > machine-search-report.json
python - <<'PYTHON'
import json
from pathlib import Path
r = json.loads(Path('machine-search-report.json').read_text())
Path('machine-experience.json').write_text(json.dumps(r['experience']))
Path('found-proposal.json').write_text(json.dumps(r['proposal']))
PYTHON
sg machine-change parent-machine.json found-proposal.json \
  --expect-machine "$MACHINE_ID" --output independently-checked-machine.json
sg machine-search parent-machine.json --expect-machine "$MACHINE_ID" \
  --experience machine-experience.json > repeated-search-report.json
```

Use the safe parent from the previous example. Search changes one transition rule
at a time using the existing finite WPL mutation neighborhood. It returns the first
safe, syntactically different rule map; that may still mean identical behavior.
There is no optimization, completeness or usefulness guarantee.

A failed full check contributes a concrete trace. For each later candidate, the
search replays that trace's **events from its initial state**, computing new states
and checking each invariant through SKI and the independent Boolean evaluator.
It never rejects a candidate just because somebody else's path had a bad state.
Imported experience includes the rules that failed and the exact trace: the
failure must reproduce before use, under the same parent and runtime.

Passing saved traces is not admission. Every found candidate still goes through
`machine-change`, including both full safety checks. `full_checks` counts those
calls; `trace_checks` includes imported-experience validation and screening. The
separate `parent_check` always runs first. For the example, reuse reduces full
checks from 2 to 1, while trace checks increase from 2 to 4; this is **not** a claim
of less CPU time in every case.

An unfinished candidate is counted and skipped without adding experience. Checker
errors stop the search. Exhausting the neighborhood with any unfinished candidates,
or hitting the candidate limit, gives exit 3; a completely checked neighborhood
with nothing found gives 4. `found` gives 0; unsafe parent gives 4; invalid inputs
2; checker/operation failures 1. Output is written only for `found`, without
overwriting. `--max-edges` is per full graph, not a trace-replay or wall-clock quota.

The search heuristic is installed tooling, outside the pinned offline checker.
Send its `proposal` to a chat participant: the existing offline `--machine-change`
mode can independently admit or refuse it. No new trusted author, plugin, search
server or history certificate is introduced.


### Discover properties of reachable states (Build 25)

The machine package can now answer a second question: which relationships between
state bits hold everywhere the machine can reach? `machine-discover` builds one
complete graph and checks a small explicit catalog: each bit always false/true,
equality of each pair, and each directed implication (`left` implies `right`).
Implication means `!left || right`, not causality or a next-step relationship.

```sh
sg machine-discover parent-machine.json --expect-machine "$MACHINE_ID" > discovered.json
python - <<'PYTHON'
import json
from pathlib import Path
r = json.loads(Path('discovered.json').read_text())
Path('machine-claim.json').write_text(json.dumps(dict(parent=r['machine_id'],
    property={'kind': 'bit', 'name': 'a', 'value': False})))
PYTHON
sg machine-claim parent-machine.json machine-claim.json --expect-machine "$MACHINE_ID"
```

Use the parent from the preceding examples. A chat participant can submit a claim
with just `parent` and `property`: no invented digest of results, proof or verdict.
A claim is checked by recomputing the graph. A false property returns a shortest
path to a state that violates it; unreachable assignments do not refute a property.

This is observation, **not a stronger contract**. The checker temporarily uses a
tautological invariant to explore past states that violate the original invariant.
The output identifies the original machine and the separate observation graph.
It returns no replacement machine and never changes the original admission rules.
Thus even an unsafe machine can have true discovered properties. To adopt a stronger
invariant, choose a new root explicitly; these commands do not do that.

`complete` discovery exits 0 even when some catalog properties are refuted. A single
claim gives `established`/0 or `counterexample`/4. Incomplete graph exploration gives
3 **with no property verdicts**, even if the partial graph already contains a bad
state. Checker disagreement gives 1, invalid claims or anchors give 2. `--max-edges`
applies to the observation graph; the original per-expression ATP ceiling is kept.
The observation tautology has its own cost, so a small budget can prevent discovery.

After unpacking and independently authenticating the launcher/runtime, the same
operations work offline:

```sh
python -I -S machine-offline/replay.py machine-offline/machine.json \
  --machine-discover --expect-machine "$MACHINE_ID" --expect-runtime "$RUNTIME_DIGEST"
python -I -S machine-offline/replay.py machine-claim.json \
  --machine-claim --expect-machine "$MACHINE_ID" --expect-runtime "$RUNTIME_DIGEST"
```

Neither mode accepts an output path; reports go to stdout. These are finite
reachable-state predicates, not liveness, fairness, inductive-invariant synthesis,
or a guarantee that the catalog captures what matters to your application.
