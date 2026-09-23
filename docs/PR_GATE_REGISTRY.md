# Pre-registration: the read-only pull-request gate (PR-08)

Written before the gate exists. Not edited after the run.

## The claim

A pull request that changes a guarded model can be gated by Stargate evidence, with
exactly one final verdict about exactly one base commit and one head commit, and with
no write to the repository and no execution of anything the pull request contains.

## Who decides what

The **workflow owner** pins, in a workflow that runs from the base branch
(`pull_request_target`), and never from the pull request:

* `model-path`, `projection-path`, `evidence-path` — where the guarded model, its
  projection and the pull request's evidence packet live;
* `expect-checker` — the machine proof checker ID;
* `expect-projection-checker` — the ProjectionCheckerID;
* the Stargate action version (`uses: s0fractal/stargate@<ref>`).

The **event** supplies the base and head commit IDs. The **pull request** supplies only
bytes at those paths in its head commit. Nothing from the head is executed: files are
read as Git blobs by commit ID (`git cat-file`), with hooks, replacement objects,
inherited `GIT_*` variables and global/system configuration disabled, as `model-apply`
already does.

## The verdict, in order

1. Base and head must be full commit IDs present in the repository; paths must be
   relative, `..`-free, and name regular files (mode 100644) where present. Else
   invalid/2.
2. Base must be an ancestor of head. Else `stale_base`/4: the evidence would be about a
   parent that is not the one the pull request merges into.
3. The model at base must exist and be a canonical certificate model. Else invalid/2.
4. If the model and the projection are byte-identical at base and head: `untouched`/0.
   Nothing guarded changed; any evidence is ignored.
5. Otherwise the evidence packet at head is required: absent → `unverified`/3.
6. The packet is a `certified_change` or a `certified_repair` (its integer tag), verified
   with `verify_change`/`verify_repair` against the **base model's ID** and the pinned
   checker. Invalid or anchored to another model → 2; `checker_unavailable` or
   `incomplete` → 3; `checker_error` → 1; only a verified change or repair continues.
7. The verified successor's model must be byte-identical to the model at head. Else
   `model_not_successor`/4.
8. The projection at head is required (absent → `unverified`/3) and is checked with
   `projection_check.check` against the successor certificate, the head model's ID and
   both pinned checker IDs. `conforms` → `verified`/0; `mismatch` → `projection_mismatch`/4;
   other statuses map as in PR-03.

One JSON report and one exit code; the action's step fails on anything but 0 and writes
the report to the job summary. There is no partial pass.

## Expected outcomes (fixture: the MCP proxy model; base = `current`, head = `fixed`)

1. Head changes nothing guarded: `untouched`/0.
2. Head carries `fixed` as the model, its projection, and the repair packet (the
   `current` refutation + the `fixed` certificate): `verified`/0.
3. Same, evidence file missing: `unverified`/3.
4. Evidence not JSON: 2.
5. Evidence anchored to another parent (a `historic` repair): 2.
6. A packet whose certificates name another checker: 3, never 0.
7. Valid evidence, one projection cell flipped: `projection_mismatch`/4.
8. Valid evidence, but the head model is not the successor (the `historic` rules): 4.
9. Base not an ancestor of head: `stale_base`/4.
10. The branch advances while/after the head was chosen: the verdict is about the head
    commit ID it was given, byte for byte, and a later head gets its own verdict.
11. Model changed, projection file deleted: `unverified`/3.
12. After every run the repository's refs, index and working tree are unchanged.
13. The composite action, run in Stargate's own CI against a fixture repository, reaches
    the same verdicts for outcomes 2 and 7.

## Control (G8)

With exactly the successor-equals-head check (step 7) removed, outcome 8's pull request
— valid evidence for one model, a different model at head — passes as `verified`.

## What this will not establish

That a repository is protected: that needs the owner to make this check required and to
run it from the base branch. That the pinned identities are right. That the model is the
code. The gate never merges, pushes, writes a status by itself beyond its job's own
conclusion, produces candidates or runs a language model.
