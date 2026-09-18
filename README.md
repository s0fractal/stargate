# Stargate

One Python system for content-addressed computation and signed, reproducible
checks. Working successor to Sigma-Glyph and Warrant; commands `stargate` / `sg`.

**Build 9 · 32K draft (artifact subject candidate).** The evaluator, object store and one signed-check flow
work. This is a development implementation, not an independently accepted
release. Predecessor repositories remain unchanged.

## Install and run

```sh
python3 -m venv .venv
.venv/bin/python -m pip install .
.venv/bin/sg --version
.venv/bin/sg --help
```

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

- `kernel.py`: canonical nodes, reduction, ATP and explicit exits; C1 compiler.
- `records.py`: canonical bytes, Ed25519, checks and outcome fingerprints.
- `store.py`: atomic object writes and SHA-256-checked reads.
- `cli.py`: both command aliases.
- `policy.py`: small boolean WPL frontend; emits existing SKI checks.
- `bundle.py`: portable signed checks; no archive extraction or store fallback.
- `tests/`: semantic vectors, signature/refusal controls and end-to-end CLI.

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
python3 -m unittest discover -s tests -v
```

Python 3.14 is the tested environment for this port; metadata permits Python
3.11+, which has not been independently exercised here. Tests include a real
subprocess CLI flow, corruption, signature/decision tampering, unsupported
editions, local refusal, and the isolated same-result/different-exit case.

Local artifact-subject validation: all 76 tests passed both in the checkout and against a
wheel-installed package outside the checkout, including the 49 imported kernel
cases. Both console aliases report build 7 / 32K. An external in-memory mutation
omitting actual exit from the fingerprint makes the isolating test fail by an
assertion. These are implementation checks, not an independent review.

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

The subject is a statement of what the decision concerns, not evidence that the
boolean facts describe that file correctly. Its bytes are not bundled, stored,
or fetched by the evaluator. `verify-bundle` authenticates the subject claim
without checking artifact availability; `require --subject` compares local bytes.
No filename, filesystem permission, safety, freshness or single-use guarantee is
implied. The result concerns bytes read during hashing: it does not lock a path
or guarantee what a later upload/execution will read. Use an immutable artifact
when connecting this check to another action. Stargate performs no such action.

This replaces the current unreleased draft shape: bodies missing subject are
invalid. There is no compatibility branch or temperature freeze.
