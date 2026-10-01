# Utility pilot: screening stopped before execution

**Result: INCONCLUSIVE. Three screened obligations, zero eligible executions.**
This is not a comparison showing Stargate useful, useless, faster or slower. No
baseline, Stargate check or TLC run was performed. Do not count this as three
negative modelling results or reuse old Sokol fixtures to fill the denominator.

## Registration and review

Initial protocol commit: `242675a52f0a5f3a40485edcf769071f503929d7`.
[First separate Claude review](plan-review-1.json): `hold`. It identified a real
problem: counting a reusable certificate as utility could prevent the stopping
rule from firing without any changed engineering decision. Cost/benefit and TLC
interpretation also needed explicit rules.

Effective protocol: `d2da43a9aca36532721e40e810fff9fe047ea63e`, [PLAN.md](PLAN.md).
[Second review](plan-review-2.json): `pass`, with limitations retained below.
The [screening record](screening.json) contains the exact protocol/source hashes,
repository revision, UTC retrieval timestamps and exclusions. These timestamps
measure record generation only, not the implementer's labour. **Protocol deviation:**
the required start/end of the actual screening work were not captured. Screening
cost is unknown; do not reconstruct it from these 10 ms or infer efficiency.
Earlier backlog
preview is disclosed in the plan; selection is not blind.

## Screened in owner order

The owner source is Sokol `ROADMAP.md` at
`60e25015769b87239764301f37d360654a8ab59d`, its numbered next-steps list:

| Case | Existing obligation | Why not executed |
| --- | --- | --- |
| U1 | Qualify the target native NIC | Needs specified physical Linux/NIC hardware and a traffic source; no target is supplied |
| U2 | Choose pilot operator and acceptable deployment thresholds | Explicit owner decisions, not a checker-generated engineering verdict |
| U3 | Evaluate adaptation after the pilot baseline | Conditional on the outstanding pilot baseline and accepted limits |

The owner's opening status says P0/P4 await owners and hardware; the first three
next steps state these dependencies. The roadmap's historical references were not
followed into retired material. No production environment or owner policy was
changed. This source is private: its hash/path is public here, not its full text.

Open issue listings had been previewed: Sokol had none; Warrant #19 called itself
a visibility notice pending an upstream prerequisite. Those listings informed the
initial inventory but are not additional cases. No fourth roadmap item, known
bug or already-completed integration was substituted after the exclusions.

## What follows, and what does not

The planned comparison could not start on this sample. It supplies no estimate of
Stargate's incremental value. The positive count is zero because no eligible case
ran, not because Stargate failed on an engineering task.

For now, pause expansion of generic agent infrastructure. Keep the functioning
checker, existing integrations and their regressions. The next utility case must
come from an independently arising maintenance task with an executable baseline;
register a future batch without rewriting this one. Do not install TLC, invent a
new adapter, or revive a known defect just to produce a comparison result.

This follows the existing AGENT_PROFILE requirement that extensions come from
observed friction. It is an allocation decision under missing evidence, not a
claim that the project's overall cost is justified or unjustified.

The plan reviews themselves changed the study design. They are evidence about
review usefulness in this instance, **not** a positive Stargate case.

## Remaining methodological limits and cost

- The implementer is also a Stargate contributor; neither selection nor assessment
  is independent of the operator's ecosystem.
- More investigation time is confounded with tool use. Even a future reproduced
  defect would not establish that ordinary testing could not have found it.
- The sequential TLC attempt would inherit the mapping and findings. It can test
  replication, not independent discovery or relative speed; later cases would have
  no TLC comparison unless a future protocol explicitly adds one.
- The reviewers flagged an ambiguity between permitting a single named positive
  and requiring two completions for an overall conclusion. No positive or mixed
  outcome occurred. This report does not resolve that ambiguity after the fact;
  a future protocol must settle it before such cases are run.
- Exclusions are owner-document assessments, not formal impossibility results.
- Setup cost includes two Claude plan-review calls, protocol/report writing and
  repository review/CI. Model tokens, monetary cost and active labour were not
  captured, so no savings or ROI are reported. No new executable framework,
  model, runtime adapter or recurring check was added by this pilot.

Public readers can check the protocol file binding locally, but cannot establish
the private roadmap's contents from its hash alone:

```sh
python3 - <<'PY_CHECK'
import hashlib, json
from pathlib import Path
root = Path('research/utility')
record = json.loads((root / 'screening.json').read_text())
assert hashlib.sha256((root / 'PLAN.md').read_bytes()).hexdigest() == record['protocol_sha256']
PY_CHECK
```
