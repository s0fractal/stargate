# The Stargate model gate for pull requests

A read-only check: one verdict about one base commit and one head commit. It never
merges, pushes, writes to the repository, produces a candidate or runs a language model,
and it never executes anything the pull request contains — it reads the pull request's
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

## A consumer workflow

Run it from the **base** branch, so a pull request cannot change the pins or the action
version, and make the check required in the branch ruleset:

```yaml
name: Stargate model gate
on:
  pull_request_target:
permissions:
  contents: read
jobs:
  gate:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4          # the base branch; nothing from the head is checked out
        with: {fetch-depth: 0}
      - uses: s0fractal/stargate@<commit>  # pin the action by commit ID
        with:
          model-path: model.json
          projection-path: projection.json
          evidence-path: .stargate/evidence.json
          expect-checker: ab72a8025a564c067f6d3a8551775733a8153ef696d1942a1f1b80e4afe107cd
          expect-projection-checker: 392c11b3683dc1e9d93d708c46012600503c3ea495aaa666221d5e27cc20e4a4
```

The action fetches the head commit's objects by ID and reads them; `pull_request_target`
runs with the base branch's workflow and secrets, which is safe here only because
nothing from the head is executed. Take the two checker IDs from [ANCHORS.md](../ANCHORS.md)
at a snapshot you trust, not from a pull request.

## What this does not establish

That the repository is protected — the owner has to make the check required and keep it
on `pull_request_target`. That the pinned identities are the right ones. That the model is
the code it describes. The verdict is about the two commit IDs it was given; a new push
gets a new run and a new verdict.
