# Pre-registration: goals that must stay reachable (T2)

Written and committed before the obligation was implemented and before any of the
four models below was run against it. Not edited afterwards.

Committed on branch `feat/live-goals`, parent `228a6b2` (T0's zoo, build 41).

## The contract being added

A model may carry an optional field `live_goals`: a subset of `goals` that must
stay reachable **from every state of the certified inductive set**, not only from
an initial state. A model without the field keeps its identity and its behaviour
exactly as before.

* Positive proof: a rank per live goal for every state of the certified set — zero
  at the goal, and every other state has at least one event whose successor has a
  strictly smaller rank. Existential progress, as everywhere else in this
  repository: some schedule reaches the goal, not every schedule.
* Refutation: a trap — a set of states closed under all events, not containing the
  goal, together with a trace from an initial state into it.

## Expected outcomes

| model | `live_goals` | expected |
| --- | --- | --- |
| philosophers, honest rules (zoo `philosophers.correct`) | both eating goals | **refuted**, trap = the single state `h0 && h1 && !e0 && !e1` |
| philosophers, asymmetric fix: only P0 releases its fork when the other holds one | both eating goals | **refuted** (a trap remains) |
| philosophers, symmetric fix: both release when the other holds one | both eating goals | **verified_certificate** |
| peterson (zoo `peterson.correct`) | both critical-section goals | **verified_certificate** |

The honest philosophers model certifies today, before this change. That is the
exhibit: the same model, unchanged except for the new field, must be refused after
it.

## Compatibility

* Every existing test must pass unchanged: models without `live_goals` keep their
  model ID, their certificates and their refutations.
* A repair candidate inherits `live_goals` from its parent like every other
  protected field; a repair that loses the field must be refused.

## Controls (each new obligation gets one)

* Rank obligation: with the rank-decrease check removed from the checker, a
  certificate whose ranks never decrease must pass. It must not pass unmutated.
* Trap obligation: with the closure check removed, a set that is not closed must
  be accepted as a trap. It must not be accepted unmutated.
* Inheritance: with the inheritance check removed, a candidate that drops
  `live_goals` must be admitted.

## What this will not establish

Not liveness under fairness: `live_goals` says a schedule to the goal exists from
every certified state, not that every schedule reaches it. A model that satisfies
it can still loop forever if the scheduler never cooperates.

---

# Second registration: the zoo column

Written before the column was implemented and before it was run. The column takes
each zoo system's `correct` model, declares **all** of its goals live, and records
the verdict.

| system | expected |
| --- | --- |
| alternating-bit | live (certifies) |
| bounded-buffer | live (certifies) |
| interlock | no certificate either way — its `correct` model is already refuted for safety |
| peterson | live — already measured above, not a prediction |
| philosophers | not live, trap `h0 && h1 && !e0 && !e1` — already measured above, not a prediction |
| readers-writer | live (certifies) |
| token-ring-natural | live (certifies) |
| token-ring-onestep | live (certifies) |

The two rows marked "already measured" are recorded for completeness and are not
counted as predictions. Disagreements are reported, not corrected.
