# Stargate

One Python system for content-addressed computation and signed, reproducible
checks. Working successor to Sigma-Glyph and Warrant; commands `stargate` / `sg`.

**Build 4 · 32K draft (resume candidate).** The evaluator, object store and one signed-check flow
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
- `tests/`: semantic vectors, signature/refusal controls and end-to-end CLI.

## Scope of this transfer

Ported: current Book I evaluator, exit-aware check semantics from S2, canonical
JSON and signature safeguards, one create → execute → sign → verify flow.
Not ported: Warrant collective settlement/governance, policy authoring language,
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

Local resume validation: all 32 tests passed both in the checkout and against a
wheel-installed package outside the checkout, including the 49 imported kernel
cases. Both console aliases report build 4 / 32K. An external in-memory mutation
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
claim: Python traversal overhead and elapsed time were not benchmarked.

No CLI session service, checkpoint files, signed continuations or serialized
state are added. Objects are trusted in-process state; mutating private fields
or passing them between threads is unsupported. Discarding a suspended object
abandons the computation. Existing fixed-budget `eval_receipt` and signed-record
verification retain their canonical atp_exhausted behavior.
