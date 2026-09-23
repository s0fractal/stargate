# Live probes of the model gate publisher (PR-09b)

Measured on 2026-09-23 on this repository, after PR-09a (`a6a139b`) put
`.github/workflows/model-gate.yml` on `main`. The probe pull requests (#68, #69, #70) were
drafts, closed after measurement and never merged; their branches are deleted, and the
statuses stay on the commits as evidence (`GET /repos/s0fractal/stargate/commits/{sha}/statuses`).
The ruleset was not changed. Pins: checker `ab72a8025a56…`, ProjectionCheckerID
`392c11b3683d…`. The valid change used by the probes is a `certified_change` of
`guarded/model.json` to a model whose `ambiguous` rule is a logically equivalent
rewrite (found by `search_machine`); it has another ModelID and the same transition
function, and it is a real change of the guarded bytes, not a semantic one.

| # | probe | head | what happened | `stargate/model-gate` |
| --- | --- | --- | --- | --- |
| 1 | valid change, PR #68 → `main` | `953ce4d` | `pending` 03:24:57, final 03:24:58; the `Model gate` run (35814223743) ran on `main` `a6a139b` and wrote to the PR head | **success** — `verified (exit 0)` |
| 2a | synchronize: flipped projection cell pushed | `5863ce7` | new head judged on its own; the old head keeps its own status | **failure** — `projection_mismatch (exit 4)`; `953ce4d` stays `success` |
| 2b | retarget #68 (head `99b305d`, valid) to `probe/09b-base` (= `main` + 1 commit) | `99b305d` | `edited` re-ran the gate on the **same** head: 03:26:42 `success` → 03:27:31 `failure` | **failure** — `stale_base (exit 4)` |
| 2b′ | retarget back to `main` | `99b305d` | re-judged again | **success** 03:28:02 |
| 2c | base advance: PR #69 → `probe/09b-base`, then a commit pushed to the base | `d118963` | the base moved and **no run happened**: 90 s later the head still carried `success` against the old base. A manual re-run of the request re-judged it | stale `success`, then **failure** — `stale_base` after re-run |
| 3 | fork pull request | — | **not run**: one account cannot fork its own repository. The code fails closed (no bound pull request → nothing written, red run; unit-tested), but the live fork path is unmeasured | — |
| 4 | spoof: PR #70 carries an invalid change **and** `.github/workflows/spoof-probe.yml` (`on: pull_request`, `permissions: statuses: write`, sleeps 150 s, then posts `stargate/model-gate=success` on its head) | `b89e86c` | the real gate posted `failure` 03:31:23; the spoof posted `success` 03:33:41. Both statuses are by `github-actions[bot]`; the combined state of the context is the latest | **success — the spoof won** |

## What this settles

* **Binding to the head works.** Every verdict landed on the pull request's head commit,
  from a run on `main`; a new head gets a new verdict; a retarget re-judges the same head
  against the new base (1, 2a, 2b).
* **A base advance is not re-judged by itself** (2c). No event reaches the pull request, so
  an old `success` stays on an unchanged head. What keeps it from merging is a strict
  "up to date" branch rule (then the head must change, and a new head is judged), not the
  publisher. `protect-main` already has `strict_required_status_checks_policy: true`.
* **The context name is not an authority boundary** (4). Any workflow of a
  same-repository pull request can request `statuses: write` and post
  `stargate/model-gate=success` on its own head, and it is indistinguishable from the
  publisher: same app (GitHub Actions), same bot. Required as it is, the check would be
  satisfied by the pull request under review. **Do not add `stargate/model-gate` to the
  ruleset as published today.**

## What would have to change before the ruleset

An identity that a pull request's workflows cannot use: a dedicated GitHub App as the
publisher, its private key held in an environment whose deployment branches are
restricted to `main` (a `workflow_run` job runs on `main`; a pull request's run does
not), and the ruleset's required check pinned to that app's integration ID, so a status
from GitHub Actions does not satisfy it. Creating the App and the environment is the
owner's action. Then probe 4 is re-run: the spoof must no longer satisfy the required
check. Until that measurement, this is a candidate, not a fix.

Probe 3 needs a second account or organisation to open a fork pull request.
