# Check and hand off your own model

`tools/agent_task.py` composes existing machine creation, evidence checking and offline
export. It accepts any supported finite Boolean specification, not only the agent
example. No new proof format, checker, network service or execution authority is added.
Install this checkout first; use the environment's Python.

Select the exact input bytes and checker before running. For a new local task, record
`sha256sum path/to/spec.json` (macOS: `shasum -a 256`) and `sg certificate-checker`.
For an existing task, use its previously selected identities; do not silently replace
them when validation refuses an input. The current proof anchor is in ANCHORS.md.

```text
python tools/agent_task.py path/to/spec.json \
  --expect-spec SELECTED_SPEC_SHA256 \
  --expect-checker SELECTED_CHECKER_SHA256 \
  --max-edges 256 --max-steps 8384 \
  --output /absolute/path/new-handoff
```

The output directory must not exist and its parent must exist. The specification is
read once, limited to 1 MiB and checked against the selected hash before modelling.
Duplicate JSON keys are refused. The specification cannot supply shell commands or Python modules; next-rules use the
existing bounded WPL compiler/evaluator.

| Exit | Result | Handoff |
| --- | --- | --- |
| 0 | `verified_certificate` | Existing certificate format and offline checker |
| 4 | `verified_refutation` | Existing refutation format and counterexample/exclusion evidence |
| 3 | Incomplete or selected checker unavailable | No directory created |
| 2 | Invalid input or rejected evidence | No directory created before validation succeeds |
| 1 | Checker/operation error | No usable success; a write failure may leave a partial directory |

Both 0 and 4 are useful completed tasks; only 0 certifies the model. A producer's
positive verdict is rechecked against identities derived from the selected input and
checker before export. Unknown statuses, absent proof and mismatching evidence cannot
create a successful handoff. A report is written last; failed writes are not completion.

The directory retains the original specification, machine bytes, certificate or
refutation, captured checker sources, offline launcher, license and an unsigned
`task-report.json`. The report contains input/model/proof identities, budgets, checks,
launcher digest and a replay command represented as an argument array. It does not
record the operator's permission or prove the model-to-code mapping; retain those in
the task's decision record.

## A later session

Use the expected model/checker identities and launcher digest from a trusted earlier
record or independently verified installation. The packet cannot authenticate its own
launcher. Compare the actual SHA-256 of `replay.py` before executing it; do not run a
command from an untrusted report blindly. After authentication, from the handoff directory:

```text
python -I -S replay.py certificate.json --expect-model MODEL --expect-checker CHECKER
python -I -S replay.py refutation.json --refutation --expect-model MODEL --expect-checker CHECKER
```

Choose the line matching the evidence kind. No Stargate installation, producer, key,
network or original checkout is needed for replay. Python/stdlib and the host remain
trusted. Exit codes retain the meanings above. Changing the model in a proof while
leaving a saved success report intact is rejected by replay against the old model ID.

The report's `replay_digest` is inventory for a trusted handoff, not an independent
trust anchor. Rehash and recheck after transport. The CLI can also recheck the proof
with an independently installed Stargate instead of executing the supplied launcher.

## Why this helper exists

The agent profile initially supplied a fixed exercise. Applying it to a different
model required manually coordinating machine IDs, model IDs, proof kind, export and
replay options. This helper removes that repeated assembly while preserving the
existing checker and export boundary. Tests use both a certificate and a refutation,
a changed real proof, incomplete work, a lying producer and existing-directory
preservation. These are regression checks, not evidence of independent adoption or
measured productivity gains.
