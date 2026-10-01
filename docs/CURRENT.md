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
  The consumer `shadow` check is also required, bound to GitHub Actions App 15368;
  its successful check identity and the updated ruleset were read back.
- **Strategy integration:** [PR #88](https://github.com/s0fractal/stargate/pull/88) merged
  as `5ed8aba3d2b32e8f352e9209517cfa664f444fb2`; its tree matches reviewed head `d7679d3`.
- **Merge gate:** the GitHub App 5041755 publishes the required `stargate/model-gate` check;
  strict base freshness is enabled. The gate checks guarded model/projection changes.
  `untouched` does not certify arbitrary code or a change to the checker itself.
- **Consumer boundary:** [actual adapter checks](CONSUMER_CONTRACTS.md) cover six Warrant
  scenarios/three mutants and eighteen Sokol socket observations/four mutants. Proof and
  code correspondence remain distinct claims. Frozen Sokol observations/model identities
  and public-probe hashes are now checked by public tests. Sokol CI separately replays
  all three frozen results on exact source `5ffaf08`, alongside live-checkout checks.
- **Sokol pilot:** Sokol #95 merged as `b94f090`; Rust delivery protocol repair, native
  regressions and shadow model comparison. The trace extension checks fifteen prefixes
  across five sequences, including reconnect/retry and empty flushes after acknowledgement.
  The [capacity-two extension](../examples/sokol-queue/README.md) checks 56 reference
  transitions and 24 actual operation prefixes with six semantic mutants.
  See [initial results](../examples/sokol-delivery/RESULTS.md). The operator has direct
  influence; external demand and production qualification are not established.
- **Synthesis:** the new delivery case yields a verified owned-only repair; one-edit
  exhausts. Existing sigma/semantic-seal successes and Warrant live-goal refusal remain
  the acceptance set. No new solver, domain size, runtime or trust authority was added.

The [2026-10-01 publisher review](PUBLISHER_BINDING_REVIEW.md) reproduces and repairs
stale binding publication and event-subset ambiguity, with actual gate/API scenarios
and a bounded observed-binding model. Final API reads and status POST are not atomic.

## Review and acceptance

Admission is controlled by the repository's required executable checks; a human GitHub
approval is not a prerequisite. Changes to checker or admission code need exact-head
regressions and adversarial controls that demonstrate rejected invalid inputs and prevent
publication after incomplete or failed verification. Independent review remains useful
evidence, but an implementation author's own tests must not be labelled independent.
The model gate's scope is limited: it does not prove arbitrary implementation correctness.
Policy changes, check results and actual merges must be reported separately.

## Technical strategy completion

P0–P3 are implemented and merged: owned examples and accurate claims (P0), actual
Warrant adapter checks (P1), the Sokol delivery repair and bounded consumer checks
(P2), and verified owned-only repair with a registered search comparison (P3).
Stargate PRs [#90](https://github.com/s0fractal/stargate/pull/90),
[#91](https://github.com/s0fractal/stargate/pull/91) and
[#92](https://github.com/s0fractal/stargate/pull/92) add retry traces, queue semantics
and frozen public evidence checks. Sokol PRs #96–98 add their live and frozen CI
replays; #98 merged as `bfad6ad22a03ef243753575612c60f36885302fd`.

The [reproduction handoff](REPRODUCE.md) provides explicit public/full profiles,
a report with input hashes, and a blank observation template for a future user.
A full run must reproduce all four frozen harness outputs byte for byte; missing
sources, failed stages or incomplete evidence fail the run. Reports are unsigned
observations, never admission credentials. Neither profile establishes independent
adoption. The author-run fresh-environment check is a setup check, not a new pilot.

This closes the technical implementation of P0–P3. On 2026-09-30 the operator
selected an [agent-use profile](AGENT_PROFILE.md), explicitly allowing zero independent
users. The previous requirement to wait for an unassisted external user is superseded.
Historical pilot results and their non-independence remain unchanged.

The [custom agent task helper](AGENT_TASK.md) now packages arbitrary supported models
into existing-format offline evidence. It pins the input and checker, rechecks producer
output and preserves certificate/refutation exit semantics. This is an ergonomic
producer extension; checker identities and admission authority remain unchanged.
Its repair mode accepts a selected parent refutation, enforces the inherited contract
and world rules, and retains the repair plus independently checked successor for offline
replay. Incomplete checks and invalid repairs do not export a new handoff.
Explicit bounded search can now propose the candidate through the same helper, using
the existing strategies. It rechecks repairs and materialized candidate identities,
preserves stop reasons and does not escalate budgets or apply code automatically.
The read-only `--check-handoff` mode binds saved input/machine/evidence and repair
successors using the installed checker, without executing packet code or trusting the
old task report. Recipient-selected anchors remain required.

The [shared-action experiment](../examples/shared-action/README.md) checks a resource
release candidate against separate custodian and reclaimer requirements. Premature
release and permanent retention each receive a different checked objection; guarded
release satisfies both. Selected world/candidate/contract identities and complete
checks are required for model eligibility. This is a synthetic two-role experiment,
not a production actuator, federation, economic mechanism or impossibility result.
Its [SQLite extension](../examples/shared-action/ACTUATOR.md) exercises one atomic toy
state update after joint verification, live-state membership and projection checking;
stale revisions, changed selections and competing attempts withhold duplicate effects.
This does not make external side effects atomic or prove distributed exactly-once behavior.
The optional operation receipt now commits with the local effect and lets another
agent session reconcile a lost response without repeating the effect. Exact request
replays return a historical observation; conflicting reuse refuses. Tests terminate
processes before/after commit, deny receipt storage and race identical operations.
This closes a local propose/check/apply/reconcile loop, not a power-loss guarantee.
The [Sokol receipt experiment](../examples/sokol-receipts/README.md) now connects
the actual Rust outbox to this toy receiver. Six socket scenarios check retained
requests, acknowledged local effects, conflicting reuse and changed conditions;
two semantic mutants must fail by observed mismatches. The sender remains an
in-memory queue, and the fixture is not the production Sokol node endpoint.

## Current development criteria

Primary consumers are agents performing operator-authorized work, including repository
maintenance. The first agent task models stale evidence after candidate changes, checks
an owned repair, and retains replayable artifacts with refusal controls
([exercise](../examples/agent-evidence/README.md)). It is a synthetic workflow exercise,
not a production GitHub adapter or a new independent pilot.

Prioritize useful internal decisions, reuse across sessions, clear refusals and low
integration cost. Record concrete tasks where a counterexample or checked repair
changed the outcome; count repeated fixtures as regressions, not adoption. Independent
use remains optional evidence, not a development gate. Wider semantics still need a
named contract that cannot be expressed today; new synthesis needs repeated failures
and a registered comparison. Preserve portable evidence and historical checker IDs.
