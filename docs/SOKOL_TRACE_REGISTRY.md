# Sokol trace extension registration — 2026-09-30

Registered before implementation and measurement, following merged Stargate #88 and
Sokol #95 (`b94f090`). This extends tested correspondence without changing the model,
checker, production delivery code, or the original results-v2.json experiment.

Trace scope: one queued subject, cumulative terminal outcomes, real retry/reconnect, no new enqueue or crash persistence. Replay each observed prefix through the existing certified table. Cases: unknown then duplicate; partial then applied; EOF then recorded; unknown then EOF then duplicate; terminal ACK then empty flush. Failure during the configured retry pause is a stutter step. Negative controls: consume unknown, accept partial, drop on transport error, retain after terminal ACK. Compile/process failures remain infrastructure errors. Preserve results-v2 bytes.


Acceptance: every prefix agrees with the certified projection; cumulative terminal
outcomes stay at most one, returned subject identity is preserved, and all named source
mutants produce semantic disagreement. A compile/process error is not a killed mutant.
This is bounded trace evidence, not universal progress, full queue refinement, arbitrary
scheduling, restart persistence, or independent demand. The operator influences both
repositories. Real clock waits exercise production backoff without editing its source.
