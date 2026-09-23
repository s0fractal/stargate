# Pre-registration: which checker may authorize a new state (PR-09c)

Written before the admission record exists. Not edited after the run.

## The thesis

Proof identity (which checker a proof was made for), actuator identity (who publishes the
verdict — the App, 09b) and current authority (which checker may admit a new state
today) are three different things. 09c makes the third one an explicit, small,
base-branch record, separate from the other two.

## What exists today

The model gate's workflow pins the machine checker and ProjectionCheckerID as literals.
`certificate.verify` already refuses a proof unless the running code's `checker_id()` is
the expected one, so a checker that is not the code on `main` can never verify there.
What is missing is the state: nothing records which checker is authorized, so merging new
checker code either breaks the gate by accident or, with a gate that trusts "whatever
code runs", silently changes who authorizes.

## The record

`guarded/admission.json`, canonical JSON:

```json
{"admission": 1, "machine_checker": "<64 hex>", "projection_checker": "<64 hex>"}
```

Exactly one active machine checker and one active projection checker; no overlap window.
The gate reads it **from the base commit** (the branch tip it merges into), never from the
head. `ANCHORS.md` is history and is not read: a digest being anchored does not make it
active.

## Invariants and expected outcomes

1. **Admission comes from the base record.** Base record = the running checkers; a valid
   certified change → `verified`.
2. **The record is required.** Base without `guarded/admission.json` (while `ANCHORS.md`
   lists the running checker) → `invalid`/2. Malformed record (extra field, short digest,
   two machine checkers as a list) → 2.
3. **No packet or pull request chooses its judge.** A head that rewrites
   `guarded/admission.json` to name another checker does not change its own verdict: the
   base record decides.
4. **A transition is a state change, not a repin.** Base record names checker C₀ while
   the running code is C₁ (new code merged without a transition commit): a proof made by
   C₁ → `checker_unavailable`/3, fail closed.
5. **Historical checkers never die.** A certificate made by a C₀ closure (a synthetic
   C₀: the current closure with one comment line added, so its digest differs):
   - with the base record naming C₁ (after the transition) the gate gives no admission —
     `checker_unavailable`/3;
   - unpacked with its own C₀ closure and replayed offline with
     `python -I -S replay.py … --expect-checker C₀` → `verified_certificate`.
6. `model-gate.yml` no longer pins checker IDs; the publisher passes
   `--admission-path guarded/admission.json`. `action.yml` for other repositories keeps
   explicit pins (its owner pins in the workflow).

## Control (G8)

A gate that takes the expected checker from the running code (`certificate.checker_id()`)
instead of the base record admits outcome 4's pull request (`verified`), which the real
gate refuses. (A mutant that treats "any anchored checker" as active cannot admit
anything here — verification still runs the code on `main` — and is not used.)

## What this will not establish

Who may change `guarded/admission.json` or the checker's source: a pull request that
changes both is judged by the base record for its guarded content only, and its own code
change is the maintainers' review under the ruleset. Nothing here makes a checker correct.
