# Results: a named review verdict is immutable within a round

Registration: `REGISTRY.md` (commits `1b2b355`, revised before any run in `d740079` and
`f4d25fd`). Model data and harness committed before the first run. Checker
`d425682ebb14…` (build 47, world rules from PR #83). Reproduce:
`python integration/sigma_verdict_vertical.py` (compares `results.json` byte for byte).

## Outcomes against the registration

| # | registered | measured | |
| --- | --- | --- | --- |
| 1 | `buggy`: refuted, 2 steps | `verified_refutation`, unsafe, 2 steps: named non-`REJECT`, then `NO VERDICT` → `sealed_adopt` with `named = false` | held (see deviation 2) |
| 2 | `fixed`: certified, 3 states, both goals in 1 step | `verified_certificate`, 3 states, 2 goals, 2 path steps | held |
| 3 | `fixed` repairs `buggy` | `verified_repair` | held |
| 4 | `repair-search` finds no repair, touches no monitor rule | one-edit: `neighborhood_exhausted` after 6; trace: `neighborhood_exhausted` after 6; no candidate on `sealed_*` | held |
| C1 | seal `named` only → refuted | `verified_refutation`, unsafe | held |
| C2 | seal `reject` only → refuted | `verified_refutation`, unsafe | held |
| C3 | blinded observer → `goal_unreachable` | `verified_refutation` of kind `unreachable_goal` (sealed `REJECT`); safety holds | predicate held, name wrong (deviation 1) |
| C3b | un-latched observer: model certifies; refused as a repair with the boundary; `verified_repair` without it | `verified_certificate`; `invalid`: `repair alters world rule: sealed_adopt`; `verified_repair` | held |

**Deviation 1 (name, not predicate).** The registration used `goal_unreachable`, which is
a status of the reachability report. `machine-evidence` reports an unreached goal as a
checked refutation whose claim kind is `unreachable_goal`. The harness checks the
registered predicate (no unsafe claim; a sealing goal unreached) under the real name, and
says so in a comment. The refutation names the first goal only (sealed `REJECT`); that
sealed `ADOPT` is unreached too is true by hand (both `sealed_*` rules are `false`) and
not separately evidenced.

**Deviation 2 (the example, not the length).** The registration illustrated the 2-step
counterexample as "a `REJECT` seals, then …" and said which trace the checker picks was
not predicted. The checker picked the mirror: a named `ADOPT` seals, then `NO VERDICT`
makes it disappear. It is the defect in its second form — a named verdict that vanishes,
not one that flips.

## What this establishes, and what it does not

- The governance invariant ("a named verdict is immutable within a round; only
  `NO VERDICT` permits another attempt") fails on the model of sigma-glyph master
  `40a9bff` and holds on the model of the #59 contract, with both sealed outcomes still
  reachable — the fix does not buy safety by refusing everything.
- **C3b is why the monitor is behind the repair-authority boundary.** An observer that
  records only the latest answer makes the invariant vacuous and certifies the *buggy*
  tool with both goals reachable; goals do not catch it. Declared without `world`, it is
  accepted as a `verified_repair` of `buggy`. With `sealed_*` declared, the checker
  refuses it by name. The boundary, not anything else, is what separates the two runs.
- The bounded search cannot find this fix (the fix changes two rules; the neighborhood
  changes one) and says `neighborhood_exhausted` rather than returning a monitor edit.
- **Not established:** that `tools/candidate_gate.py` implements either model. The code
  layer is sigma-glyph's offline regression `tests/candidate_gate_retry_test.py`; one
  family only; plain run and `--retry` are one event.

## Fixed correspondence

sigma-glyph PR #59 head at the time of this run:
`46dd64c412c77a2680f03f810e237daf703ea42b` (after Codex's append-only AMEND). Not yet
merged; if the head moves before merge, this pin is replaced with a note, never silently.
