# Results: the interlock shadow experiment

Measured by `python integration/interlock_shadow.py` (bytes in `results.json`, regenerated
and compared on every CI run). The registration is [REGISTRY.md](REGISTRY.md); nothing in
it was edited. Every registered outcome held on the first run.

| model | as-is | bad-round-closes | trip-ignored | open-skips-half-open | half-open-stuck |
| --- | --- | --- | --- | --- | --- |
| too weak (2 state bits, topology only) | certificate, 3 states | **certificate** | **certificate** (1 state) | **certificate** (2 states) | refuted: liveness trap |
| lifecycle (2 lifecycle + 2 observer bits) | certificate, 5 states | refuted: unsafe, 3 steps | refuted: unsafe, 1 step | refuted: unsafe, 2 steps | refuted: liveness trap |

The 4-bit model's projection has 64 rows and conforms; one flipped cell is a `mismatch`,
and the table runtime executes the flipped cell as given.

## The answer to the registered question

Yes, with a qualification. The frozen language — no new semantics — expresses the
automatic lifecycle strongly enough that all four planted wrong transitions are refused.
It does so only after the contract is stated as **transition obligations** through two
observer bits. The natural "states and topology" model, the one a reader would write
first, is too weak: it certifies three of the four mutants, including a breaker that
closes after an unhealthy probe round, and catches only the liveness defect.

## What interlock's own tests already cover

At the pinned blob, every one of the four planted defects is asserted directly by a
deterministic test (`test__closed__failure_rate_at_threshold__opens`,
`test__open__before_wait_elapsed__rejects`,
`test__open__after_wait_elapsed__transitions_to_half_open`,
`test__half_open__probe_failures_at_threshold__reopens`,
`test__half_open__all_probes_succeed__closes`), and the Hypothesis model predicts the state
after every step. So this experiment does not show Stargate finding a defect interlock
would miss. It shows exhaustive closure of a small stated contract, portable proof data
and a table checked against it — on top of an already strong suite. Contrast the warrant
vertical, where the model found a live defect CI had not.

## External response

bagowix/interlock#224 (opened 2026-09-23): `pending`. Recorded in `upstream.json`; not a
result of this experiment, and no change was proposed to interlock's repository.

## What this does not establish

Rate arithmetic, probe counts and concurrent admission, generation fencing, backoff,
the override states, inconclusive probes, Redis coordination, or that
`_state_machine.py` is this model.
