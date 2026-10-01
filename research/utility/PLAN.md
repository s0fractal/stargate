# Utility comparison: prospective pilot

Protocol committed before implementation investigation and model execution. This file is not amended after a
run starts; amendments receive a separate file and apply only to future cases.

## Question

Does adding Stargate to ordinary source inspection, tests and separate model review
change a real maintenance decision enough to justify modelling and integration work?
Correct certificates and passing fixtures alone do not answer this question.

## Selection and denominator

Screen at most three unfinished obligations in this fixed source order: Sokol
ROADMAP.md numbered "next" list, Sokol open issues by ascending issue number,
Warrant open issues by ascending number, then Warrant README-linked current work.
Within a numbered roadmap item, dependent subitems belong to the same obligation.
Take the first three unfinished obligations, including externally blocked ones;
classify their eligibility, with a named target and observable failure/success
condition, without replacing excluded cases. Record owner commit/path and the task statement before
looking at its implementation. Do not select for fitting six Boolean bits.
Do not execute archived projects, previous Stargate fixtures, already-known defects
or requests whose owner says they are only notices or await an external prerequisite.
These exclusions remain in the three screened records and are not replaced.
Keep every screened item and exclusion reason; do not replace an inconvenient result
with a fourth task. If fewer than three eligible tasks exist, report that shortage.
This is an operator-controlled convenience sample, not independent demand.
Disclosure: open-issue listings were read before the first protocol commit; owner
roadmap/README documents were previewed during plan review, before acceptance of
this revision. The source order is therefore not blind or pre-registered against
all source exposure. No implementation baseline or model run has started. Preserve
this limitation rather than calling the eventual sample unbiased.

## Execution

For each selected task, freeze the contract and repository revision first.
1. Baseline: source inspection, existing tests and the smallest useful additional
   test. Record defects, proposed changes and unresolved questions. Separate Claude
   review can challenge the baseline; validate a finding before counting it.
2. Freeze the baseline record before applying Stargate. State whether its bounded
   domain can express the relevant obligation without deleting the failure mode.
   If not, record OUT_OF_DOMAIN; do not force a model or grow the framework.
3. For eligible tasks, use existing Stargate tools only. Map model states/events
   to actual code and name assumptions. Credit a new defect only after reproducing
   it against the frozen implementation. A rejected bad repair or a reusable
   checked obligation counts separately from defect discovery.
4. For the first eligible model, also attempt the same bounded obligation with
   TLC, using the official existing CLI if available. TLC sees the baseline,
   mapping, Stargate model and findings. This is a portability/replication attempt,
   not independent discovery or a fair speed race. Charge the shared modelling
   effort to both routes; report additional translation time separately. The same
   useful result from TLC means the benefit is not established as Stargate-specific. Retain specification,
   invocation and verdict. If unavailable, record NOT_RUN, never an automatic win
   for Stargate. No claim that agents cannot use standard tools.

The Stargate phase sees baseline findings. This is an incremental-value pilot,
not a randomized comparison or a blind measurement of independent discovery.
The same implementer cannot unlearn a defect. Reviewer access/context is recorded.
Historical reruns and mutation checks are regressions, not additional real tasks.

## Bounds and records

Per case: at most 20 minutes wall time for baseline investigation, 20 minutes for
Stargate and 20 minutes for the comparator, measured with UTC start/end markers.
Waits, setup and model-review time are included and labelled; elapsed time is not
human labour or token cost. Stop at each limit and retain INCONCLUSIVE if unfinished.
Do not install a new service, create a new adapter framework, or change a checker
for this pilot. Correctness/safety problems found in ordinary work may still be
fixed, but repair/CI/merge time is a separate cost and does not reset a phase budget.

Record UTC start/end for screening too, and retain protocol commit and file digest
before screening. OUT_OF_DOMAIN requires an explanation tied to the frozen failure
mode before any model run; a second model may challenge but cannot validate it alone.

Each case record retains task provenance, exact revisions, eligibility, commands,
outputs or their retained paths/digests, baseline findings, incremental findings,
limitations and time. Credential material and private source are not published.
Public summaries may name private-file paths and hashes; reproducible private
artifacts remain in the corresponding private repository or local experiment folder.

## Decisions fixed before results

- Count baseline findings, Stargate-only validated findings, useful repair refusals,
  and added formal coverage separately. Do not convert a certificate into a bug found.
- OUT_OF_DOMAIN, NOT_RUN and INCONCLUSIVE stay in the screened denominator, but are
  not failed proof attempts or evidence of correctness. Count completed eligible
  cases separately. Infrastructure failures receive no correctness verdict.
- Before the Stargate phase, baseline must name its proposed action: merge a named
  repair, refuse it, keep the code, or investigate a specific unresolved question.
  A decision change is a different action justified by a newly reproduced failing
  regression on baseline code, or a counterexample to the proposed repair that is
  reproduced in actual code. A new certificate/test alone does not qualify. The
  named failing command and before/after action must let another reader check it;
  a model verdict or the implementer's satisfaction is insufficient.
- Record modelling, mapping validation, dependency setup, integration, review and
  subsequent repair/CI time separately when observable. Unknown token/monetary
  cost remains unknown. Existing framework development is sunk cost, not zero cost.
  Record added maintained files/lines and every required future recurring check.
- Continue only a named use case with a validated decision change within the
  20-minute added Stargate phase, no new maintained adapter/dependency/service,
  and a replay command runnable by the existing consumer. This is an operator
  engineering threshold, not a measured financial return or general superiority.
- Zero positives among two or more completed eligible cases: stop expanding this
  integration. One or more qualifying positives: permit only those named uses;
  no general expansion. Fewer than two completions: overall INCONCLUSIVE, even if
  one case is positive. Out-of-domain/excluded cases never create a positive.
  Equal results from TLC establish no Stargate-specific advantage; prefer the
  route needing less added maintained integration, or report an unresolved tie.
- A shortage of fitting tasks is a reason not to add general agent infrastructure
  now, not evidence that Stargate is universally useless.
- Any important real failure omitted by the abstraction voids its application to
  that obligation. Keep the failed mapping; no post-hoc replacement of the task.
- A pass from another model is review evidence, not ground truth about utility.

After this pilot, change or remove only the unnecessary path identified by evidence.
Do not delete historical evidence or functioning consumers to satisfy a rhetoric test.
