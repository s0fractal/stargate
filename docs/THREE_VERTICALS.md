# After three live verticals: what repeated

Written at `main` `18ba4e3`, 2026-09-24, as a stop after the third live vertical and before
any new feature work. Every number below is read from a committed results file; nothing
here is a new measurement. It updates, and does not replace, [VERDICT.md](VERDICT.md).

## The three cases

| | warrant | sigma-glyph | black-heart |
| --- | --- | --- | --- |
| code | `run_proxy`, `b273b9e` | `tools/candidate_gate.py`, `40a9bff` | `scoped_admission.py`, `3893fad` |
| established fact | the proxy's record of a pending call for an id | a reviewer family's named verdict in a frozen round | an authenticated semantic counterexample for a (candidate, evaluator, requirement) |
| how it was lost | a second call on the id overwrote it (latest wins) | a re-ask replaced it (latest attempt wins), or a `NO VERDICT` made it vanish | a weaker record of the same subject (a resource refusal) opened the path the seal had closed |
| model | 4 state + 2 event bits | 4 + 2 | 3 + 2 |
| monitor / world bits | `calls.one`, `calls.two` | `sealed_adopt`, `sealed_reject` | `resource`, `semantic` |
| buggy refuted | *call, call* | 2 steps | 2 steps from the sealed initial state |
| one-rule search | exhausted, 21 / 22 attempts | exhausted, 6 / 6 | exhausted, 9 / 9 |
| safety synthesis | `W*` 9, 1 row, Hamming 1 → **refused by the checker: `trap` on live goal `idle`** | `W*` 6, 6 rows, Hamming 8 → **`verified_repair`** | `W*` 6, 2 rows, Hamming 2 → **`verified_repair`** |
| results | [mcp-proxy](../examples/mcp-proxy/RESULTS.md), [synth](SYNTH_RESULTS.md) | [sigma-verdict](../examples/sigma-verdict/RESULTS.md), [synth](SYNTH_RESULTS.md) | [semantic-seal](../examples/semantic-seal/RESULTS.md) |

Three repositories, three mechanisms (a request-id map, a file-per-attempt record store,
an in-memory refusal registry), each with a green CI on the defective code.

## What repeated

1. **One failure shape.** A decision reads *a* record — the latest write, the latest
   attempt, the refusal the request names — instead of the established fact that should
   govern it. Nothing in any of the three needed more than six bits to say so.
2. **The contract needed memory the code did not keep.** Each model needed monitor bits
   that remember the established fact (the server's debt, the first named verdict, the
   semantic seal). Those bits are the specification, so they sit behind the
   repair-authority boundary (`world`): in sigma-glyph (C3b) an un-latched monitor
   certified the buggy tool until the boundary refused it.
3. **Goals keep the monitor honest.** Erasing or blinding the seal made safety hold
   vacuously; only a goal requiring the sealed outcome to be reachable refused it
   (sigma-glyph C3, black-heart C2).
4. **Every repair adds a dependency.** The fix reads the seal (`ambiguous` reads `host`
   and `pending`; `named` reads `sealed_*`; `admitted` reads `semantic`). The one-rule
   mutation grammar never adds a fact, so it exhausted all three times — correctly, and
   uselessly.
5. **The models caught the first path, not the second.** Every case had a further way to
   lose the fact that a one-subject model has no bit for, found by adversarial review of
   code: warrant's id-less call; sigma-glyph's plain re-run overwrite and two-process race;
   black-heart's unauthenticated semantic-shaped record (in our own first fix) and the
   quota rollback on import (finding D).
6. **The fixes regressed into the same class.** The first sigma-glyph fix left the plain
   re-run and the race; the first black-heart fix gave an unauthenticated record the power
   to block forever; and the black-heart suite that proved it was, for a while, not run by
   CI at all, because a file's existence is not a test's authority in CI (fixed
   separately). Reviewing *who may establish or change a fact* found defects in the
   repairs as reliably as in the originals.

## What synthesis changed, and where it stopped

Safety synthesis turned two of three `neighborhood_exhausted` results into repairs the
checker verifies, without knowing the hand fixes: in both, the synthesized rule is the
parent XOR the few rows where the seal must hold, i.e. the hand fix's guard stated only
where it is reachable. In warrant the unique minimal *safe* change set `ambiguous` and never
cleared it; the checker refused it on liveness. That is the measured boundary between a
safety fixed point and a liveness repair. It is recorded, not patched: one liveness case
is not a reason for a second solver.

## Signs to look for in a fourth case

A decision that reads the most recent record, attempt or pointer; retry or replay after a
final decision; a sibling or weaker record of the same subject; a snapshot, import or cache
that can replace retained state; a record whose authority is its label rather than its
authentication; a counter or quota that can move backwards; a test, check or gate whose
existence is taken for its effect. Acceptance stays as it was for the third: a live
reproducer on the current default branch first, then a registered model.

## What this does not establish

That the pattern is frequent: the second and third cases were **hunted with this
criterion**, so three hits say the class exists in unrelated code, not how common it is.
All three repositories have the same owner and are Python; all three models are one
subject; no case came from an external team, and external demand is still not
established. That any model is its code (each has its own code-level regressions). That
minimal-Hamming synthesis is the right repair in general.
