# Results: the head-SHA publisher (PR-09a)

The registration is [MODEL_GATE_PUBLISHER_REGISTRY.md](MODEL_GATE_PUBLISHER_REGISTRY.md);
it is not edited. What was measured, and what changed after review:

## Which SHA a pull_request source run carries

The review of #67 raised that a `pull_request` run's `GITHUB_SHA` is the synthetic merge
commit, so `workflow_run.head_sha` might not be the pull request's head. Measured on this
repository: the run object of `Model gate request` for PR #67 (recorded in
`tests/github_workflow_run_pull_request.json`, from `GET /actions/runs/35812474250`) has
`head_sha` `b9a9177e…`, which is PR #67's head commit and equals
`pull_requests[0].head.sha`. The `workflow_run` event's payload is that run object. The
merge commit is the run's `GITHUB_SHA`, a field the publisher does not read.

## Changed after review: nothing is written before binding

Registered outcomes 3 and 4 said an unbound run posts `error`. After review the publisher
binds first — exactly one open pull request whose API head equals the run's head — and
only then posts `pending`. A run with no such pull request, with two, or whose pull
request has moved to a newer head, writes nothing and is red; the newer head gets its own
run. The tests say so where they changed.

## Open for 09b: who may write `stargate/model-gate`

Any workflow run whose token has `statuses: write` can post a status with this context
on any commit of the repository. A pull request from a branch of this repository runs its
own workflow definitions, and such a workflow may request `statuses: write`; so the
context name alone is not an authority boundary — a collaborator's branch could post
`success` on its own head. Fork pull requests get a read-only token and cannot. A
required check that is satisfied by "the GitHub Actions app wrote this context" does not
tell the trusted publisher from any other workflow.

Candidates for 09b, to be tested live, not assumed: a dedicated GitHub App as the
publisher's identity, its key held in an environment restricted to the default branch,
and the ruleset's required status check pinned to that app's integration ID; or a
check run by that app. 09b tests spoof resistance before the owner makes the status
required.
