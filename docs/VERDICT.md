# Verdict after the plan cycle (OP-00 … PR-10)

Written at `main` `fe39706`, 2026-09-24, as the STOP the plan required after its last
vertical. It answers the plan's four questions from what was measured, not from what was
intended. Every claim points to where it was measured. No semantics, checker, adapter,
event bit or federation work happens until this document is merged.

## What the cycle built, and what is live

* **Proof and projection.** Machine certificates and refutations (build 42 checker
  `ab72a8025a56…`, frozen by the vertical baseline), `projection-1` tables and an
  independent projection verifier with its own closure
  ([SPEC](../SPEC.md), builds 43–45), portable offline replay, and a fixed standard-library
  table runtime (build 46).
* **A real consumer.** warrant's `warrant-mcp` proxy runs its per-request-id bookkeeping
  from a Stargate table pinned by digest in warrant's own source (warrant #82, #83, #84;
  `master` `ac80aee`).
* **A gate that binds.** `protect-main` requires the status `stargate/model-gate` from the
  GitHub App `5041755`. A pull request's own workflow cannot satisfy it and cannot reach the
  App's key ([MODEL_GATE_APP_RESULTS.md](MODEL_GATE_APP_RESULTS.md), six live steps).
  Which checker may authorize is a base-branch record, not a pin and not the running code
  ([ADMISSION_REGISTRY.md](ADMISSION_REGISTRY.md), #80).

## V1 — Is the projection constraint acceptable?

**Yes, for small contracts, on one condition.** Both real models fit comfortably: the
warrant proxy in 4 state bits and 2 event bits
([examples/mcp-proxy](../examples/mcp-proxy/RESULTS.md)), the interlock lifecycle in 4 + 2
([examples/interlock](../examples/interlock/RESULTS.md)), each a 64-row table.

The condition: the contract must be stated as **obligations**, not as topology. The
interlock model a reader writes first — the three states and their arrows — certified 3
of 4 planted wrong transitions, including a breaker that closes after an unhealthy probe
round. Two observer bits that record what the last step demanded turned it into a
contract that refuses all four. The warrant model needed the same move: no observer
flags a repair could switch off, but the server's debt as state. A bounded model is
cheap; a bounded model that says the right thing is the work.

## V2 — Did the gate catch something ordinary CI did not?

**Yes, once; and a control shows it is not universal.**

* **warrant:** the model of `run_proxy` was refuted by the trace *call, call* — a host
  reusing a request id lost the first call and sealed the second with the first call's
  result, while the pack said complete and the proxy exited 0. warrant's CI was green on
  that code. The table-driven fix is now on warrant's `master`.
* **interlock:** a strong suite already asserts each planted defect directly and predicts
  the state after every step. There, Stargate adds exhaustive closure of a stated
  contract, portable proof data and an explicit authorization boundary — not a defect the
  suite misses. The experiment says so rather than claiming otherwise.
* The second warrant defect — a `tools/call` with **no** id, leaving a clean pack — was
  found by an adversarial review of the integration, **not** by the model: the model is
  one request id, and no bit of it could see a call without one.

## V3 — Which friction repeated?

The friction was almost never in the checker. It was at the **boundary of the question**,
and it recurred:

| friction | where it appeared |
| --- | --- |
| the model's world was smaller than the system's | the id-less call (warrant #81 review); fork pull requests (untested, one account) |
| which rules are the system and which are the world | `repair-search` "repaired" the warrant model by changing the **server** (`calls.one'` identically false), and the checker accepted it ([mcp-proxy RESULTS](../examples/mcp-proxy/RESULTS.md)) |
| obligations invisible to a state invariant | interlock's topology model; the fix was observer bits in both verticals |
| code ↔ model correspondence | both verticals: evidence by tests on each side, never proof |
| who may speak for the verdict | a GITHUB_TOKEN status was spoofable (09b probe 4) until the App identity |
| which checker may authorize | admission as a base record (09c) |
| ceilings guessed instead of derived | `MAX_STEPS` (#50), `MAX_PROJECTION` (#60) |
| generated artifacts coupled across files | the first App step-5 probe broke CI through `guarded/*` vs `proxy.json` |

Each was fixed or stated at its own boundary. None asked for a wider logic.

## V4 — Is there demand for wider semantics?

**No, on the evidence we have.** Nothing measured needed a third event bit, more than six
state bits, an arbitrary-code verifier, Lean/Kani/TLA adapters, a second checker, or
federation. External demand is **not established**: one outreach
(bagowix/interlock#224, opened 2026-09-23), open with no response when this was written.
A second account opening pull requests to ourselves would not establish it either.

## Decision

**Keep Stargate a small bounded proof gate. Do not widen the semantics by default.**

One semantic change stays a candidate, because a real vertical produced it rather than a
roadmap: an **ownership boundary for repair** — rules marked as the world (immutable) and
rules the repair may change. Without it, a bounded search can repair a model by editing
the environment it was meant to survive, and the checker has no way to say no.

Two honest ways forward, and a recommendation:

1. **Recommended now: no semantic change.** Mark `repair-search` as an experimental
   producer whose output a person reads before use. In both verticals every repair that
   was adopted was a proposal written against the model and then checked — the checker's
   job — while the search either produced a repair of the world (warrant) or was not
   needed (interlock). The frozen semantics stay as they are.
2. **Only if automatic repair becomes a core purpose:** exactly one change — world vs
   owned rules in the repair contract — with its own registration, red, controls and a
   re-run of the warrant vertical, where the search must no longer be allowed to edit
   `calls.*`.

## What this verdict does not establish

That the two verticals are representative; that a checker is correct; that a
repository admin or the App's owner cannot change the rule, the environment or the key;
that fork pull requests are handled; that any model is its code.
