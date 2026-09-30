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
- **Review policy:** on 2026-09-30 `protect-main` was updated and read back: one
  approving review required, approvals dismissed on new pushes. No bypass actor was added.
  This applies to all PRs; an author cannot supply their own GitHub approval. It is a
  distinct-account review boundary, not a proof of reviewer competence.
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

Changing checker or admission code requires an independent review of the exact head.
The implementation author's own mutation checks do not satisfy it. GitHub approval policy
and actual PR states are recorded separately in the implementation report; this file must
not claim a pending PR merged or an administrator setting immutable.

## Next decision criteria

The next user must reproduce a useful result without author assistance. Measure modelling
and integration time, rejected mutations, false blocks and repeat use. A cross-language
success does not establish independent demand. Wider semantics need a named contract that
cannot be expressed today; a new synthesizer needs repeated failures with a registered
comparison. Keep portable evidence and historical checker identities unchanged.
