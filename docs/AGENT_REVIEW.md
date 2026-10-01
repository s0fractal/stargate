# Agent review: shadow registration

Written 2026-10-01, before the first live run. Not edited after runs; results go in a
separate file.

## Why

Approval was removed from `protect-main` on 2026-09-30. What remains decides whether a
change is admissible only for `guarded/*` (model gate) and for what the author's own tests
cover. Every pull request since then was written, tested and merged by one side. This adds
a reviewer that is not the author: a separate model session that sees only the change.

## Mechanism

* `.github/workflows/agent-review-request.yml` — on `pull_request`; no permissions, runs
  nothing; its completion triggers the trusted half.
* `.github/workflows/agent-review.yml` — on `workflow_run`, from the default branch, so a
  pull request cannot change the reviewer, its prompt (`tools/agent_review_prompt.md`) or
  its pins (`@anthropic-ai/claude-code@2.1.286`, model `claude-opus-5-5`).
* `tools/agent_review.py` binds the run to exactly one open pull request exactly as
  `tools/pr_gate_publish.py` does, exports the head with `git archive` (nothing from it is
  executed) and computes the diff from the merge base with the current base tip.
* The reviewer is the Claude Code CLI in print mode with `--tools Read,Grep,Glob` in a
  scratch directory holding only `head/` and `review.diff`. Reads outside it are refused
  (verified locally: a file beside the directory and `/proc/self/status` were denied). Its
  environment holds `PATH`, a scratch `HOME` and `CLAUDE_CODE_OAUTH_TOKEN`; the status
  token is never passed to it.
* Its answer must match a JSON schema and be self-consistent: `pass` has no blocker or
  major finding, `deny` has a blocker. Output containing the credential is refused.
* Status `stargate/agent-review` on the head: `pass` → success, `hold`/`deny` → failure,
  anything else (CLI or API failure, schema or consistency violation, timeout) → error.
  The findings are written to the run's step summary.

## What it is not

* **Not required.** The status is written with the GitHub Actions token. A pull request's
  own workflow holds the same token and could publish the same context, so the context
  must not become required until a dedicated App publishes it (as model-gate does, App
  5041755, key in a `main`-only environment).
* **Not a certificate.** A pass is one model's reading of one diff. It does not replace
  the model gate, the tests or the consumer contracts, and it is not independent of
  Anthropic models in general. Most changes are written by another model family.
* Billing: the credential is a Claude subscription OAuth token, so reviews consume the
  operator's subscription limits. The default CLI model needs usage credits on that plan,
  hence the explicit model pin.

## Shadow period and decision

Run on the next 5–10 pull requests. For each: verdict, findings, and afterwards whether a
finding was real (fixed or acknowledged), false, or a defect was found later that the
review missed. Measured cost: wall time per run. Make the context required only if false
`deny`/`hold` are rare enough not to stall work, and only after moving publication to a
dedicated App. Until then it informs; it does not admit or refuse.

Pre-run local observation (not a shadow result): on merged #105 (`260db63...0c295e7`) the
reviewer returned `pass` with three minor findings in 43 s.
