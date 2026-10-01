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
| 0 | `verified_certificate` (or `verified_repair` in repair mode) | Existing evidence format and offline checker |
| 4 | `verified_refutation` | Existing refutation format and counterexample/exclusion evidence |
| 3 | Incomplete or selected checker unavailable | No directory created |
| 2 | Invalid input or rejected evidence | No directory created before validation succeeds |
| 1 | Checker/operation error | No usable success; failed exports are cleaned up when possible |

Both 0 and 4 are useful completed tasks; only 0 certifies the model. A producer's
positive verdict is rechecked against identities derived from the selected input and
checker before export. Unknown statuses, absent proof and mismatching evidence cannot
create a successful handoff. A report is written last; failed writes are not completion.
If an export raises an exception (including an ordinary keyboard interrupt), the helper
removes its new directory so the same command can be retried. It never cleans up a
pre-existing destination or one whose exclusive creation failed. Use a parent directory
controlled by the caller: concurrent replacement of files/directories is unsupported.
This is exception recovery, not atomic publication or durable storage. Readers must wait
for command completion. Forced process termination, machine failure, or failed cleanup
can still leave partial output; inspect it and choose a fresh output path before retrying.

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

## Recheck a handoff with an installed Stargate

When the recipient has an independently trusted installation, the same helper can
recheck the saved data without running the packet's launcher:

```text
python tools/agent_task.py /absolute/path/handoff --check-handoff \
  --expect-spec SELECTED_INPUT_SPEC_SHA256 \
  --expect-checker SELECTED_CHECKER_SHA256 --max-steps 8384
```

For either manual or searched repairs, also pass `--expect-parent SELECTED_PARENT_MODEL`.
Choose these anchors from the task's trusted record, not the received report. In manual
repair mode the selected specification is the candidate; in search mode it is the
original defective input. The fresh report identifies that relationship as `input_role`.

The helper reads each required file within 1 MiB, checks the input's exact hash,
recreates and byte-compares `input.machine`, requires exactly one proof file and
rechecks it with the installed checker. Repairs must retain the exact verified
`successor.json`; the selected input must identify either the parent or candidate.
Search handoffs additionally require `candidate-spec.json` to reconstruct the verified
candidate model. If a manual repair includes that file, it is checked too. Candidate
specification metadata outside the proof model is not certified; its actual byte hash
is included in the fresh report for a later task to pin explicitly.

This mode is read-only and performs no search. It ignores `task-report.json`,
`replay.py` and `checker.json`, including their commands and claimed verdicts. A success
therefore verifies the selected saved model/evidence data, not the integrity of every
file, historical completion of the producer, or the supplied offline launcher. The
required data can be rechecked even if the unsigned old report is missing or damaged.
Use the authenticated offline route above when no trusted installation is available.

Exit 0 means a verified certificate/repair, 4 a verified refutation, 3 incomplete or
checker unavailable, 2 invalid data/options, and 1 an operation/checker error (including
missing required files). No error or incomplete result authorizes continuation.
Production options such as `--output`, `--search` and `--repair-parent` are refused.
Keep the directory stable during reading: this is not an atomic filesystem snapshot.
The helper grants no permission to execute a candidate or apply source changes.

## Why this helper exists

The agent profile initially supplied a fixed exercise. Applying it to a different
model required manually coordinating machine IDs, model IDs, proof kind, export and
replay options. This helper removes that repeated assembly while preserving the
existing checker and export boundary. Tests use both a certificate and a refutation,
a changed real proof, incomplete work, a lying producer and existing-directory
preservation. These are regression checks, not evidence of independent adoption or
measured productivity gains.

## Continue from a refutation to a repair

A later agent can submit a candidate specification while retaining the prior defect:

```text
python tools/agent_task.py candidate-spec.json \
  --expect-spec SELECTED_CANDIDATE_SPEC_SHA256 \
  --expect-checker SELECTED_CHECKER_SHA256 \
  --repair-parent /absolute/path/old-handoff/refutation.json \
  --expect-parent SELECTED_PARENT_MODEL_ID \
  --output /absolute/path/new-repair-handoff
```

The two repair options are required together. The parent identity comes from the
recipient's selected task, not from whichever file happens to be supplied. The parent
refutation is rechecked before candidate production. A safe candidate alone is
insufficient: the repair checker verifies the inherited contract and immutable world
rules. No old directory or proof is edited.

On exit 0, `status` is `verified_repair`; `repair.json` embeds both the original
refutation and the candidate certificate, and `successor.json` retains the verified
candidate certificate. The successor is independently checked against the candidate
model before export. The report's `model_id` identifies the candidate;
`parent_model` anchors repair replay; `successor_model` identifies the successor.
The existing proof format and offline launcher are unchanged.

After authenticating the launcher and choosing the parent/checker identities, replay:

```text
python -I -S replay.py repair.json --repair \
  --expect-model PARENT_MODEL --expect-checker CHECKER --output replayed-successor.json
```

The replayed successor matches the saved successor bytes. Keep `repair.json` alongside
that successor: the bare successor alone does not preserve the original objection.
The output path must be new. The step budget is per proof, not a total CPU/time limit.

An unsafe candidate yields `not_repaired`, exit 4 and no new directory. To retain its
separate counterexample, run the candidate as a plain task without the repair options.
Incomplete work returns 3 without exporting a repair; a wrong parent or forbidden
contract/world edit is invalid (2). A missing or wrong successor cannot be exported
under a successful repair label. Refusal never means no other repair exists.

A repair establishes the bounded model transition. It does not select the best fix,
apply source code, update a branch, or extend the agent's permission to act.

## Let the bounded producer propose a repair

When the task supplies a defective specification but no candidate, select a strategy
and candidate quota explicitly:

```text
python tools/agent_task.py defective-spec.json \
  --expect-spec SELECTED_INPUT_SPEC_SHA256 \
  --expect-checker SELECTED_CHECKER_SHA256 \
  --search synth --max-candidates 1 \
  --max-edges 256 --max-steps 8384 \
  --output /absolute/path/new-search-handoff
```

Strategies are the existing `one-edit`, `trace` and `synth` producers. The candidate
quota must be 1–256; there is no automatic strategy fallback or budget increase.
Search mode cannot be combined with `--repair-parent` or `--expect-parent`: the pinned
input specification defines the defective parent. Quotas bound candidates, explored
edges and checker steps per operation; they are not a total wall-clock deadline.

A producer's `found` is insufficient. The helper rechecks the returned repair against
the input-derived parent and selected checker, requires the exact candidate certificate
as successor, verifies that certificate and reconstructs the candidate specification
before exporting anything. Existing contract/world preservation rules still apply.

On success, exit 0 reports `verified_repair` and exports the same offline repair format
as manual repair. It also writes `candidate-spec.json`, with its hash in the report,
so another agent can inspect or continue from the discovered next-rules. `input-spec.json`
and `input.machine` retain the defective input. In search mode `model_id` and
`parent_model` identify that input; `successor_model` identifies the found candidate.
The report retains the producer's attempts, strategy and budget under `search`/`budget`.
No source patch, Git operation or publication action is performed.

Without a checked repair there is no handoff directory:

- Exit 3: `search_incomplete`, `incomplete` or `checker_unavailable`.
- Exit 4: `not_needed`, `neighborhood_exhausted`, `not_applicable`, `unrealizable`,
  `not_certified` or `repair_refused`, preserving the producer's precise meaning.
- Exit 1/2: checker/operation error or invalid input/evidence.

Save stdout/stderr and the exit code as task observations when a search stops. An
exhausted neighborhood does not establish that no repair exists. `synth` currently
handles bounded safety synthesis with explicit world ownership; it still must pass
all inherited goals, so a synthesized safety candidate can be refused. A result is
not necessarily minimal, desirable or a correct change to a real implementation.

This is bounded autonomy over model proposals: an agent can choose the next-rules,
while the existing checker decides whether the inherited obligations hold. The agent
must still review the concrete code mapping and use the repository's authorized merge
workflow for an implementation change.
