# Current status and next evidence

2026-09-30. Source baseline: `d9fc9ae`; contract pilot registration: `4329f02`.
This page owns the current development status. Registrations/results retain their dated
bytes and describe what was measured then; they are not silently rewritten as new runs.

- **Proof core:** build 47, checker `d425682ebb142a03021c13de63c8443dfd06c07f68ab1624a63df858e50b43fa`.
  Six state bits, two event bits; inductive safety, reachable goals and goals that remain
  reachable from every reachable state. No universal eventual progress or fairness.
- **Repair authority:** explicit `world` next-rules are immutable in a repair. Ordinary
  certified changes can evolve next-rules, but neither change nor repair may add/drop
  the world declaration. `examples/mcp-owned` is a new-root demonstration, not adoption
  by existing consumers. Frozen `guarded/*` and Warrant's pinned model have no world field.
- **Actual consumer:** Warrant `ac80aee` runs the pinned table (PRs #82–84 merged).
  Sigma-Glyph #59 and Black-Heart #99 repairs merged; that does not mean their runtimes
  execute Stargate tables. The original README's pending-adoption description was stale.
- **Admission policy:** on 2026-09-30 the operator removed mandatory GitHub approval
  from `protect-main` (ruleset 23849266), including extra approval for unattributed
  changes. Required Python checks, strict base freshness, the pinned model-gate App,
  force-push/deletion protection and an empty bypass list remain. The live ruleset was
  read back; this is a mutable configuration, not an immutable mathematical guarantee.
- **Strategy integration:** [PR #88](https://github.com/s0fractal/stargate/pull/88) merged
  as `5ed8aba3d2b32e8f352e9209517cfa664f444fb2`; its tree matches reviewed head `d7679d3`.
- **Merge gate:** the GitHub App 5041755 publishes the required `stargate/model-gate` check;
  strict base freshness is enabled. The gate checks guarded model/projection changes.
  `untouched` does not certify arbitrary code or a change to the checker itself.
- **Consumer boundary:** [actual adapter checks](CONSUMER_CONTRACTS.md) cover six Warrant
  scenarios/three mutants and eighteen Sokol socket observations/four mutants. Proof and
  code correspondence remain distinct claims.
- **Sokol pilot:** Rust delivery protocol repair, native regressions and shadow model
  comparison. See [results](../examples/sokol-delivery/RESULTS.md). The operator has direct
  influence; external demand and production qualification are not established.
- **Synthesis:** the new delivery case yields a verified owned-only repair; one-edit
  exhausts. Existing sigma/semantic-seal successes and Warrant live-goal refusal remain
  the acceptance set. No new solver, domain size, runtime or trust authority was added.

## Review and acceptance

Admission is controlled by the repository's required executable checks; a human GitHub
approval is not a prerequisite. Changes to checker or admission code need exact-head
regressions and adversarial controls that demonstrate rejected invalid inputs and prevent
publication after incomplete or failed verification. Independent review remains useful
evidence, but an implementation author's own tests must not be labelled independent.
The model gate's scope is limited: it does not prove arbitrary implementation correctness.
Policy changes, check results and actual merges must be reported separately.

## Next decision criteria

The next user must reproduce a useful result without author assistance. Measure modelling
and integration time, rejected mutations, false blocks and repeat use. A cross-language
success does not establish independent demand. Wider semantics need a named contract that
cannot be expressed today; a new synthesizer needs repeated failures with a registered
comparison. Keep portable evidence and historical checker identities unchanged.
