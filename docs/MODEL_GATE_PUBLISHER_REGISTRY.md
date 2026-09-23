# Pre-registration: the head-SHA publisher and Stargate's own guarded model (PR-09a)

Written before the publisher exists. Not edited after the run.

## Why PR-09 is split

PR-09 in the plan holds three theses: a mechanism that binds the gate's verdict to a pull
request's head commit, Stargate using it on itself, and a checker transition policy.
The review of PR-08 showed the first is its own problem (GitHub's event model), and the
review condition for it is a **live** end-to-end test. `workflow_run` only triggers for
workflows that are already on the default branch, so the live test cannot run before
the mechanism merges. Hence:

* **09a (this):** the publisher, its workflows, Stargate's guarded model, unit tests
  against a fake GitHub API and a local "origin". Not yet required by the ruleset.
* **09b:** the live test on real pull requests of this repository, then — by the owner —
  the ruleset change that makes the status required. Architecture accepted only there.
* **09c:** active admission checkers vs historical snapshots.

## The mechanism

* `.github/workflows/model-gate-request.yml` — on `pull_request` (`opened`, `synchronize`,
  `reopened`, `edited`). It runs nothing from the pull request and has no write
  permission; it exists so that its completion triggers the trusted workflow.
* `.github/workflows/model-gate.yml` — on `workflow_run` of the request workflow. It runs
  from the default branch (so its pins cannot be changed by a pull request), checks out
  the default branch, and runs `tools/pr_gate_publish.py` with `statuses: write`,
  `contents: read`, `pull-requests: read` and nothing else.
* `tools/pr_gate_publish.py`:
  1. The head is `workflow_run.head_sha`, set by GitHub, never read from the pull request.
  2. It posts `pending` with context `stargate/model-gate` on exactly that commit.
  3. It finds the one open pull request whose head is that commit (the event's
     `pull_requests`, else `GET /commits/{sha}/pulls`). None or several: `error`, never
     `success`.
  4. The base is the **current tip** of that pull request's base branch
     (`GET /git/ref/heads/{base}`), not a SHA carried by any event.
  5. It fetches both commits' objects and runs `tools/pr_gate.py`'s `gate` and `finish`
     in-process with the pins from the workflow.
  6. It posts the final status on the same head commit and context: exit 0 → `success`;
     2, 3, 4 → `failure`; 1 or any exception → `error`. The description names the gate
     status. It makes no other write: only `POST /statuses/{head}`.

Stargate's own guarded model: `guarded/model.json` (the certificate model of
`examples/mcp-proxy` variant `fixed`), `guarded/projection.json` (its projection),
evidence at `guarded/evidence.json`. Pins: the checker and ProjectionCheckerID of
`snapshot-a4b5fdb9b8fe`.

## Expected outcomes (unit tests, fake API, local origin)

1. Valid repair: two POSTs to `/statuses/{head}` — `pending`, then `success` with
   description `stargate: verified` — and no other request with a body.
2. A flipped projection cell: `pending`, then `failure`, description names
   `projection_mismatch`.
3. No open pull request with that head: `error`; never `success`.
4. Two open pull requests with that head: `error`.
5. The base branch advanced past the pull request's base: `failure` (`stale_base`),
   because the base is the branch tip, not the event's.
6. The gate raises: `error`.
7. The status goes to the event's head SHA even if the pull request's head has moved
   on since; a later head gets its own run.
8. The API refuses the final POST: the process exits non-zero (the run is red), and no
   `success` was posted.

## Control

With exactly the "one pull request" check removed, a head shared by two pull requests
gets a verdict posted as if it were one's (outcome 4 turns into `success`).

## What this will not establish

That the status binds anything: that needs 09b's live test and the owner's ruleset.
That a fork's pull request is handled (fork runs have empty `pull_requests`; the
`/commits/{sha}/pulls` fallback is untested live). That GitHub delivers every event.
