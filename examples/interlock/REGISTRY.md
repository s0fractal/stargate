# Pre-registration: the interlock shadow experiment (PR-10-shadow)

Written before the experiment's files and script exist. Not edited after the run. The
two prototype runs made while preparing bagowix/interlock#224 (a 2-bit model that
certified a planted defect, and the 4-bit model below) are the reason for this
registration, not results of it; they are re-run here from committed files.

## The one question

Can Stargate's current, frozen language express a useful contract of a real external
state machine strongly enough that meaningful wrong transitions do **not** certify —
without any semantic extension?

## The subject, by identity only

`bagowix/interlock` at commit `50de2b3d3acf2a53239d5910d6e605efe011f0f7`:
`interlock/_state_machine.py` blob `39135c1487a1a8499b6f5876f06807b6a7ccea55`,
`tests/test_state_machine.py` blob `9c26a8b7e66fccb780efa419add7f37fc5f5c00d`,
`tests/test_state_machine_model.py` blob `d9708b0db250ba019a030d4a9a8dc17b60639d98`.
Nothing is vendored. `upstream.json` records these identities as the bytes that
motivated the abstraction; it claims no correspondence.

## The models

Events for both: `bad` — in CLOSED the already-computed trip condition, in HALF_OPEN an
unhealthy completed probe round; `elapsed` — in OPEN the open wait has passed, in
HALF_OPEN the probe round has completed. `open`, `half` encode CLOSED (neither), OPEN,
HALF_OPEN; both at once is excluded by the invariant. Goal and live goal: CLOSED.

* `lifecycle-too-weak.json` — 2 state bits, invariant `!(open && half)` only.
* `lifecycle.json` — the same two bits plus observers `demand_open` (the last event
  required OPEN: a trip in CLOSED or a bad round in HALF_OPEN) and `from_open` (the machine
  was OPEN one step ago); invariant adds `demand_open → open` and
  `from_open → open ∨ half`.
* `mutations/*.json` — one planted defect each, as rule overrides for both models:
  `bad-round-closes`, `trip-ignored`, `open-skips-half-open`, `half-open-stuck`.

## Expected outcomes

1. The too-weak model certifies (3 reachable states).
2. The too-weak model does **not** see `bad-round-closes`: that mutant certifies. Also
   predicted for the too-weak model: `trip-ignored` certifies, `open-skips-half-open`
   certifies, `half-open-stuck` is refuted as a liveness trap.
3. The 4-bit model certifies, 5 reachable states, CLOSED live.
4. Under the 4-bit model all four mutants are refuted: `bad-round-closes` unsafe in 3
   steps, `trip-ignored` unsafe in 1, `open-skips-half-open` unsafe in 2,
   `half-open-stuck` a liveness trap.
5. The 4-bit model's projection has 64 rows and `projection-check` says `conforms`.
6. One flipped projection cell: `mismatch`; the Python table runtime executes the flipped
   cell as given.
7. No claim of correspondence with `_state_machine.py`.
8. The outreach (bagowix/interlock#224) is recorded separately as
   `external_response: pending`, and is not a result of this experiment.

`python integration/interlock_shadow.py` runs 1–6 through `sg` from a clean directory and
compares with `results.json`; CI runs it.

## What interlock's own tests already cover — written before the run

Each planted defect is already asserted directly by a deterministic test at the pinned
blob (`test__closed__failure_rate_at_threshold__opens`,
`test__open__before_wait_elapsed__rejects`,
`test__open__after_wait_elapsed__transitions_to_half_open`,
`test__half_open__probe_failures_at_threshold__reopens`,
`test__half_open__all_probes_succeed__closes`), and the Hypothesis model predicts the
state after every step. This experiment therefore cannot show that Stargate finds a bug
interlock's suite misses; it can only show whether the frozen language states the
lifecycle contract strongly enough, exhaustively, as portable proof data.

## What this will not establish

Sliding-window or rate arithmetic, probe counts and concurrent admission, generation
fencing, backoff timing, the override states `FORCED_OPEN`/`DISABLED`/`METRICS_ONLY`,
inconclusive probes, Redis coordination, or that the Python code is the model.
