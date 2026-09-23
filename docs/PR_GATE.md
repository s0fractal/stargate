# The Stargate model gate for pull requests

A read-only check: one verdict about one base commit and one head commit. It never
merges, pushes, changes refs, the index or the working tree, produces a candidate or runs
a language model, and it never executes anything the pull request contains — it reads the pull request's
files as Git blobs by commit ID. Registered in [PR_GATE_REGISTRY.md](PR_GATE_REGISTRY.md).

## What the pull request must carry

When it changes the guarded model or its projection, the pull request's head commit holds:

* the new model at `model-path` — a canonical certificate model;
* its `projection-1` table at `projection-path`;
* at `evidence-path`, a `certified_change` or `certified_repair` whose parent is the
  model at the **base** commit and whose verified successor is exactly the head model
  (`sg certificate-change-pack` / `sg certificate-repair-pack`).

A pull request that changes neither the model nor the projection is `untouched` and passes.

## Verdicts

| status | exit | meaning |
| --- | --- | --- |
| `verified` | 0 | the evidence verifies against the base model and pinned checker, the head model is its successor, and the head projection conforms |
| `untouched` | 0 | the model and the projection are byte-identical at base and head |
| `unverified` | 3 | the guarded files changed without evidence, or the projection is gone |
| `checker_unavailable`, `projection_checker_unavailable`, `incomplete` | 3 | a pinned identity is not what the evidence or this installation provides |
| `invalid` | 2 | malformed input, evidence anchored to another model, an unknown commit |
| `stale_base` | 4 | the base is not an ancestor of the head |
| `model_not_successor` | 4 | the head model is not the verified successor |
| `projection_mismatch` | 4 | a row of the projection differs from the successor's rules |
| `checker_error`, `operation_error` | 1 | the checker or Git failed |

There is no partial pass: the step fails on anything but 0, and the report goes to the
job summary.

## Running it, and what it does not enforce yet

The action (`action.yml`) runs `python3 -I -S tools/pr_gate.py` from its own pinned
source: no `pip`, no network beyond fetching the head commit's objects, no other action.
It needs `python3` >= 3.11 on the runner. It computes a verdict and fails its step on
anything but 0. **That is not yet enforcement**, for reasons the review of #66 found in
GitHub's own state machine:

* A job that holds the pins safely must not come from the pull request. `pull_request_target`
  gives that, but it runs in the context of the default branch: its check is not
  attached to the pull request's latest head commit, so making the job "required" in a
  ruleset does not, by itself, bind the verdict to the head that merges. Binding a
  verdict to the head commit needs a publisher for that commit ID (or another mechanism)
  that is itself tested — PR-09's work, not claimed here.
* A pull request retargeted to another base changes the base without a new head commit;
  a trigger without `edited` would not re-run.
* An exact `(base, head)` verdict only describes what merges if the branch rule is
  strict (the head must be up to date with the base).
* GitHub has announced a default policy that blocks `pull_request_target` in public
  repositories from 2 November 2026 unless a policy allows it
  ([GitHub Docs](https://docs.github.com/en/actions/reference/security/securely-using-pull_request_target)).

A workflow that runs the gate today, as a verdict and nothing more:

```yaml
on:
  pull_request_target:
    types: [opened, synchronize, reopened, edited]
permissions:
  contents: read
jobs:
  gate:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@<full commit SHA>   # the base branch; nothing from the head is checked out
        with: {fetch-depth: 0}
      - uses: s0fractal/stargate@<full commit SHA>
        with:
          model-path: model.json
          projection-path: projection.json
          evidence-path: .stargate/evidence.json
          expect-checker: ab72a8025a564c067f6d3a8551775733a8153ef696d1942a1f1b80e4afe107cd
          expect-projection-checker: 392c11b3683dc1e9d93d708c46012600503c3ea495aaa666221d5e27cc20e4a4
```

Pin both actions by full commit SHA and take the checker IDs from
[ANCHORS.md](../ANCHORS.md) at a snapshot you trust, not from a pull request.

## What the gate guarantees, and what it does not

It reads the pull request's files as Git blobs by commit ID and never executes them. It
never changes refs, the index or the working tree; the action's `git fetch` does add
objects and `FETCH_HEAD` to the runner's clone. A report that does not parse, has no
known status, or whose status disagrees with the exit code fails the step (1), never
passes it. It does not establish that a repository is protected, that the pins are
right, or that the model is the code it describes. The verdict is about the two commit
IDs it was given.
