# Utility comparison: prospective pilot

Registered before task selection and execution. This file is not amended after a
run starts; amendments receive a separate file and apply only to future cases.

## Question

Does adding Stargate to ordinary source inspection, tests and separate model review
change a real maintenance decision enough to justify modelling and integration work?
Correct certificates and passing fixtures alone do not answer this question.

## Selection and denominator

Screen at most three current tasks from active Sokol or Warrant owner documents or
open issues. Read the owner backlog in its recorded order; take the first three
unfinished concrete engineering obligations, with a named target and observable
failure/success condition. Record owner commit/path and the task statement before
looking at its implementation. Do not select for fitting six Boolean bits.
Exclude archived projects, previous Stargate fixtures, already-known defects and
requests whose owner says they are only notices or await an external prerequisite.
Keep every screened item and exclusion reason; do not replace an inconvenient result
with a fourth task. If fewer than three eligible tasks exist, report that shortage.
This is an operator-controlled convenience sample, not independent demand.

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
   TLC, using the official existing CLI if available. Retain specification,
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
- If at least two completed eligible cases show no decision change or reusable
  checked obligation beyond baseline, stop expanding this integration and prefer
  the simpler path. One positive case supports only that named use case.
- If fewer than two eligible cases complete, utility remains INCONCLUSIVE; do not
  advertise productivity or general superiority. A shortage of fitting tasks is
  itself a reason not to add general agent infrastructure now.
- Any important real failure omitted by the abstraction voids its application to
  that obligation. Keep the failed mapping; no post-hoc replacement of the task.
- A pass from another model is review evidence, not ground truth about utility.

After this pilot, change or remove only the unnecessary path identified by evidence.
Do not delete historical evidence or functioning consumers to satisfy a rhetoric test.
