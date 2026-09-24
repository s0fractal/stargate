# Verdict after the plan cycle, and the map of the next one

First written at `main` `fe39706` (commit `24f93c0` on this branch) as the STOP the plan
required after its last vertical. **Revised at `main` `5a739ae`, 2026-09-24**, after the
work that continued before it merged: the world/owned repair boundary (#83) and a second
live vertical, sigma-glyph (#84). The revision changes three answers — V2, V4 and the
decision — and adds the pattern the two live verticals share. Every claim points to where
it was measured.

## What is built, and what is live

* **Proof and projection.** Machine certificates and refutations, `projection-1` tables
  and an independent projection verifier with its own closure ([SPEC](../SPEC.md)),
  portable offline replay, a fixed standard-library table runtime. The checker changed
  once since the first text: build 47, `d425682ebb14…`, which adds the repair-authority
  boundary ([WORLD_RULES_RESULTS.md](WORLD_RULES_RESULTS.md)); the transition was
  admitted through the base-branch record, not a pin.
* **A real consumer.** warrant's `warrant-mcp` proxy runs its per-request-id bookkeeping
  from a Stargate table pinned by digest in warrant's own source (warrant `master`
  `ac80aee`).
* **A gate that binds.** `protect-main` requires `stargate/model-gate` from the GitHub App
  `5041755`; a pull request's own workflow cannot satisfy it or reach the App's key
  ([MODEL_GATE_APP_RESULTS.md](MODEL_GATE_APP_RESULTS.md)). Which checker may authorize is
  a base-branch record ([ADMISSION_REGISTRY.md](ADMISSION_REGISTRY.md)).

## V1 — Is the projection constraint acceptable?

**Yes, for small contracts, on one condition** — unchanged, and now three models deep:
the warrant proxy, the interlock lifecycle and the sigma-glyph reviewer verdict each fit
in 4 state bits and 2 event bits ([mcp-proxy](../examples/mcp-proxy/RESULTS.md),
[interlock](../examples/interlock/RESULTS.md),
[sigma-verdict](../examples/sigma-verdict/RESULTS.md)).

The condition: the contract is stated as **obligations**, not topology. Interlock's
first model certified a breaker closing after an unhealthy probe until observer bits
recorded what each step demanded. sigma-glyph needed the same move: `sealed_*` monitor
bits that remember a family's first named verdict. A bounded model is cheap; a bounded
model that says the right thing is the work.

## V2 — Did the gate catch something ordinary CI did not?

**Yes, twice, in two unrelated repositories; and a control shows it is not universal.**
*(First text: "yes, once".)*

* **warrant:** the model of `run_proxy` was refuted by *call, call* — a reused request id
  lost the first call and sealed the second with the first call's result, with a green
  CI and a pack that said complete. Fixed on warrant `master`.
* **sigma-glyph:** the model of the candidate gate at `master` `40a9bff` was refuted in two
  steps — a family's named verdict can vanish or flip within a frozen round, so a failing
  three-family gate can be re-asked into passing. sigma-glyph's CI was green on that code.
  The fix is sigma-glyph #59 (reviewed, not merged at this writing; the model's
  correspondence is pinned to its exact head).
* **interlock:** a strong suite already asserts each planted defect. Stargate adds
  exhaustive closure, portable proof data and an authorization boundary there — not a
  missed defect.
* **What the models did not find, in both live cases:** warrant's id-less `tools/call`,
  and sigma-glyph's plain-rerun overwrite and two-process race, were found by adversarial
  review, not by a model. Each model is one id / one family / one attempt per step, and no
  bit of it could see them. How the two live defects were *found* matters too: by reading
  code while choosing a vertical, then refuted by the model — not by the gate running
  unattended on someone else's pull request.

## V3 — Which friction repeated?

Unchanged in kind: almost never the checker, almost always **the boundary of the
question** — the model's world smaller than the system's, obligations invisible to a
state invariant, code ↔ model correspondence by tests only, who may speak for the verdict,
ceilings guessed instead of derived. One row changed status:

| friction | where it appeared | now |
| --- | --- | --- |
| which rules are the system and which are the world / monitor | `repair-search` "repaired" the warrant model by editing the **server** | closed by #83; in sigma-glyph, control C3b shows the same boundary is what refuses a "repair" that un-latches the **monitor** |

## V4 — Is there demand for wider semantics?

**The semantics widened exactly once, for a measured reason, and nothing else has been
asked for.** *(First text: "no"; the one candidate was taken.)* The world/owned boundary
went in with its own registration, red, controls and a checker transition (#83). Since
then two verticals ran on it, and neither needed a third event bit, more than six state
bits, another checker, an adapter or federation. External demand is still **not
established**: bagowix/interlock#224 is open with no response.

## The pattern the two live verticals share

Both live defects are the same shape: **an authoritative fact, once established, can be
rewritten, re-chosen or forgotten.**

| | the established fact | how it was lost |
| --- | --- | --- |
| warrant | the proxy's record of a pending call for an id | a second call on the id overwrote it (latest wins) |
| sigma-glyph | a reviewer family's named verdict in a frozen round | a re-ask replaced it (latest attempt wins), or a `NO VERDICT` made it vanish |

And the repair has the same shape in both: the correct fix changes **two owned rules
together** (warrant: `pending` and `ambiguous`; sigma-glyph: `named` and `reject`), while
the world/monitor rules must not move. The bounded one-rule search behaves correctly and
still does not reach the fix: `neighborhood_exhausted` (warrant 21 / 22 attempts,
sigma-glyph 6 / 6), never a world or monitor edit.

This is a candidate specialization, not a finding: two cases are two cases. It is stated
so the next cycle can test it rather than assume it.

## Decision

**Keep Stargate a small bounded proof gate.** No new bits, grammar or checker semantics.
The next cycle is practical, one PR at a time, each registered before code:

1. **Two-rule repair search (producer only).** After the one-rule neighborhood is
   exhausted, search bounded unordered pairs of distinct owned rules, one local edit on
   each. Authority stays with `verify_repair`; the checker is not touched. Acceptance,
   registered before code: on warrant and on sigma-glyph the search either finds a
   verified owned-only repair, or the result records that the candidate grammar cannot
   express one.
2. **Both live verticals as its acceptance tests.**
3. **A third live bug of the same class**, hunted by criteria, not by "another state
   machine": latest-wins records, retries, replay, lineage, settled/adopted state,
   cache or current pointers, receipt/approval overwrite, fail-open on missing identity.
4. **After three verticals, look at the data again** before any roadmap.

## What this verdict does not establish

That the verticals are representative; that the pattern is more than two cases; that a
checker is correct; that a repository admin or the App's owner cannot change the rule, the
environment or the key; that fork pull requests are handled; that any model is its code.
