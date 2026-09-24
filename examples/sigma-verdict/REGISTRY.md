# Pre-registration: a named review verdict is immutable within a frozen round

Written before any model of it was built, created or checked. Not edited after the run;
anything learned later goes to `RESULTS.md`.

## The target

sigma-glyph's candidate gate (`tools/candidate_gate.py`) asks three reviewer families to
judge one frozen subject (a *round*). The gate passes only if every family has a named
verdict and none is `REJECT`. The governance invariant it has to keep:

> Once a reviewer family has returned a named verdict in a frozen round, that family's
> standing verdict cannot change or disappear within that round. `NO VERDICT` is the
> only state from which another attempt is permitted.

**Source identity (buggy).** sigma-glyph `master` at
`40a9bff758941e084289a0d9a4b0afe7513d1117`, `tools/candidate_gate.py` blob
`220c2aaede2480f2d10d34a88fc0710443df5348`. The sites:

- `standing()` counts each family's *latest* attempt (highest `attempt`, ties to the last
  file read).
- `attempt_paths(..., retry=False)` returns `review-{family}.json` whether or not it
  exists, and `review_one()` writes it with `write_text()`; `keep_prompt()` does not stop
  an unchanged prompt. A plain re-run therefore replaces the first attempt.
- `attempt_paths(..., retry=True)` files `retry-N` after any earlier attempt, whatever it
  said.

Both paths let a family that said `REJECT` be asked again until it says `ADOPT`, and the
failed gate turns into a passing one. Codex's audit of the v0.7.0 history found the
overwrite path used once (`round-3/review-deepseek.json`, `NO VERDICT` → `NO VERDICT`);
no named verdict was overwritten. The defect is in the tool, not in the record.

**Fixed correspondence.** sigma-glyph PR #59 (`fix/candidate-gate-retry-shopping`) after
its review amendments: attempt records append-only, a plain run refuses once a first
attempt exists, `--retry` only after `NO VERDICT`, the whole run refused before any call
or write. The exact head is pinned in `RESULTS.md` when the PR's final head is known; if
it moves after the pin, the pin is replaced and the change is noted, never silently.

**No claim that the model is the code.** The model states the governance invariant over
one family in one round. That the Python matches it is a separate layer of evidence:
sigma-glyph's own offline regression (`tests/candidate_gate_retry_test.py`, run in
sigma-glyph CI — REJECT, ADOPT, NO VERDICT; the same family re-asked; on old master the
gate flips; after the fix both re-ask paths refuse before any call or write). This vertical
cites that test; it does not run it and does not replace it.

## The model: one family, one round, four state bits, two event bits

One step is one delivery attempt to this family. All bits start `false`.

| bit | meaning |
| --- | --- |
| `named` | the family's standing attempt is a named verdict |
| `reject` | that named verdict is `REJECT` (`ADOPT` and `ADOPT-WITH-AMENDMENTS` are merged) |
| `sealed_reject` | observer: the family's *first* named verdict in this round was `REJECT` |
| `sealed_adopt` | observer: the family's first named verdict was a non-`REJECT` |

| answered | answer_reject | the attempt returned |
| --- | --- | --- |
| false | any | `NO VERDICT` (delivery failure, cut-off reply, no parseable line) |
| true | true | `REJECT` |
| true | false | a named non-`REJECT` verdict |

    invariant:  !(sealed_reject && sealed_adopt)
             && (!sealed_reject || (named && reject))
             && (!sealed_adopt  || (named && !reject))

goals (existential, each must be reachable): sealed `REJECT`
`{named, reject, sealed_reject, !sealed_adopt}` and sealed `ADOPT`
`{named, !reject, !sealed_reject, sealed_adopt}`. No `live_goals`: once one seal is set
the other is unreachable on purpose.

**Monitor rules: a repair-authority boundary (identical in every variant).** `sealed_*`
are not environment state. They are specification (ghost/monitor) bits: they record
what the family first said so that the invariant can talk about it. They are declared
`world = [sealed_adopt, sealed_reject]` (stargate PR #83) not because they are an outside
world but because `world` is the mechanism that takes a rule out of automatic repair's
authority: repair may change how the tool behaves, never what the monitor means. Without
that boundary a "repair" can weaken the monitor's latch instead of fixing the tool, and
the existential goals do not stop it (control C3b). This vertical runs only after #83 is
merged, on its checker.

    sealed_reject' = sealed_reject || (!sealed_adopt && answered && answer_reject)
    sealed_adopt'  = sealed_adopt  || (!sealed_reject && answered && !answer_reject)

### Variant `buggy` — sigma-glyph master 40a9bff

Every attempt's record becomes the standing one.

    named'  = answered
    reject' = answered && answer_reject

### Variant `fixed` — the contract of #59 after amendment

Once sealed, the tool refuses before asking or writing: the standing verdict is unchanged.
Before the first named verdict, a `NO VERDICT` leaves room for another attempt.

    named'  = ((sealed_reject || sealed_adopt) && named)  || (!(sealed_reject || sealed_adopt) && answered)
    reject' = ((sealed_reject || sealed_adopt) && reject) || (!(sealed_reject || sealed_adopt) && answered && answer_reject)

## Registered predictions (derived by hand)

1. `buggy`: `verified_refutation`, shortest counterexample **2 steps**: a `REJECT` seals,
   then either a non-`REJECT` answer (`reject` falls) or a `NO VERDICT` (`named` falls).
   Which of the two the checker reports is not predicted.
2. `fixed`: `verified_certificate`, both goals reachable in 1 step, exactly **3** reachable
   states: all-false, sealed `REJECT`, sealed `ADOPT` (before a seal, `named` and
   `reject` can only be false).
3. `fixed` as a hand repair of `buggy`: `verified_repair` (world rules unchanged).
4. `repair-search` on `buggy`, both strategies: **no verified repair**, and no candidate
   edits `sealed_*`. Reason, by hand: editing only `reject` leaves `named' = answered`,
   so `REJECT` then `NO VERDICT` still breaks `sealed_reject → named`; editing only `named`
   leaves `reject' = answered && answer_reject`, so `REJECT` then `ADOPT` still breaks
   `sealed_reject → reject`. The fix needs two rules; the bounded one-rule neighborhood
   must say it did not find one rather than return anything else. Status
   (`neighborhood_exhausted` or `candidate_limit`) and attempt counts are recorded, not
   predicted.

## Negative controls (G8), each predicted before the run

| control | change (to `fixed`, unless it says `on buggy`) | predicted |
| --- | --- | --- |
| C1 seal `named` only | `reject' = answered && answer_reject` | `verified_refutation` |
| C2 seal `reject` only | `named' = answered` | `verified_refutation` |
| C3 blind the observer | `sealed_reject' = false`, `sealed_adopt' = false` on `buggy` | as a model: `goal_unreachable` (safety holds vacuously, both goals unreached); as a repair of `buggy`: refused, `repair alters world rule` |
| C3b un-latch the observer | `sealed_reject' = answered && answer_reject`, `sealed_adopt' = answered && !answer_reject` on `buggy` | as a model: `verified_certificate` — the monitor now records only the latest answer, so the invariant is vacuous and both goals stay reachable in 1 step; as a repair of `buggy` with the boundary: refused, `repair alters world rule`; as a repair of `buggy` declared **without** `world`: `verified_repair` |

C3 is the reason the goals exist: without them, an observer that never seals certifies. C3b is the
reason the boundary exists: goals do not catch an observer that seals and then forgets,
and only the repair-authority boundary refuses it. The no-boundary run is the control that
shows the refusal comes from the boundary and not from anything else.

## Limits, stated now

- One family. The gate's three-family rule (three named, no `REJECT`) is not modelled; the
  model shows that no family's named verdict moves, from which "a failed gate cannot be
  made to pass by re-asking within a round" follows by hand, not by the checker.
- Plain run and `--retry` are one event ("an attempt"); the model does not distinguish
  them, and a CLI that refused one path but not the other would be a different model.
- Freezing a new round is outside the model: it is a new subject, with its own families.
- `ADOPT` and `ADOPT-WITH-AMENDMENTS` are one value; a change between them is not
  modelled as a flip.
