# Command surface

The table is generated from the installed command parser and repository references.
Use it to discover commands; use each command's `--help` for arguments. The reading
below describes the current interface, not a pending proposal to remove commands.

```sh
python tools/surface.py            # rewrite the table
python tools/surface.py --check    # 0 when it matches the parser, 4 when stale
```

`tests/test_surface.py` regenerates and compares, and a control requires the check to
fail on a stale table.

<!-- inventory: generated -->

| command | what it does | tests | docs | examples | integration |
| --- | --- | ---: | ---: | ---: | ---: |
| `admit` | publish verified artifact bytes without replacing an existing file | 3 | 0 | 0 | 0 |
| `admit-all` | publish one artifact only after every named requirement holds | 1 | 1 | 0 | 0 |
| `apply` | store an application of two hashes | 1 | 1 | 0 | 0 |
| `case-pack` | pack counterexample evidence as inert data | 1 | 0 | 0 | 0 |
| `certificate-change-check` | check a next-only change: both certificates and the inherited contract | 1 | 1 | 0 | 0 |
| `certificate-change-pack` | package parent and candidate certificates as an unchecked next-only change | 1 | 0 | 0 | 0 |
| `certificate-check` | check an inductive certificate against an expected model and checker | 1 | 0 | 0 | 0 |
| `certificate-checker` | identify the independent finite-certificate checker | 0 | 4 | 0 | 1 |
| `certificate-history-append` | extend a certificate history with the next checked certificate | 1 | 0 | 0 | 0 |
| `certificate-history-check` | check every step of a certificate history against its root | 1 | 1 | 0 | 0 |
| `certificate-history-start` | begin a certificate history at a root certificate | 1 | 0 | 0 | 0 |
| `certificate-repair-check` | check a repair: the parent defect, the candidate proof, the inherited contract | 3 | 5 | 0 | 5 |
| `certificate-repair-pack` | package a refutation and a candidate certificate as an unchecked repair | 1 | 2 | 0 | 4 |
| `composition-change` | check a next-only change to one component of a composition | 1 | 0 | 0 | 0 |
| `composition-check` | explore a composition and check the joint contract | 2 | 0 | 0 | 0 |
| `composition-create` | build a composition of two components under a joint contract | 1 | 0 | 0 | 0 |
| `eval` | evaluate a term, reporting result, exit and cost | 7 | 5 | 0 | 0 |
| `evidence-check` | check a certificate or refutation against an expected model and checker | 1 | 2 | 0 | 0 |
| `experiment-check` | compare two capsules over a corpus, executing them only with --execute-runtimes | 2 | 0 | 0 | 0 |
| `experiment-controller` | show the local experiment controller and replay identities | 0 | 2 | 0 | 0 |
| `experiment-create` | bind two source capsules and a runtime-independent corpus | 0 | 0 | 0 | 0 |
| `export` | verify and export one portable signed check | 2 | 0 | 0 | 0 |
| `genesis` | show intrinsic I/K/S hashes | 1 | 1 | 0 | 0 |
| `init` | create the object directory | 5 | 1 | 1 | 0 |
| `inspect` | describe a packet of a stated kind and check its shape; never run it | 18 | 2 | 0 | 0 |
| `keygen` | write a new private seed (never overwrite) | 4 | 1 | 0 | 0 |
| `lab-check` | exhaustively check a text proposal without trusted keys | 9 | 3 | 0 | 0 |
| `lab-check-invariant` | recompute a finite property claim without trusting its author | 1 | 0 | 0 | 0 |
| `lab-create` | create a portable finite boolean experiment (no keys) | 3 | 0 | 0 | 0 |
| `lab-discover` | enumerate and check finite input/output properties | 2 | 0 | 0 | 0 |
| `lab-search` | search a bounded WPL neighborhood using replayed counterexamples | 4 | 1 | 0 | 0 |
| `lab-task-resume` | continue a lab task, recomputing every imported row | 3 | 0 | 0 | 0 |
| `lab-task-start` | begin a portable lab task from a world and a row budget | 1 | 0 | 0 | 0 |
| `lineage-append` | extend a world history with the next checked transition | 2 | 0 | 0 | 0 |
| `lineage-check` | replay a world history against its declared root | 6 | 0 | 0 | 0 |
| `lineage-start` | begin a world history at a root world | 1 | 0 | 0 | 0 |
| `machine-change` | check a next-only change, exploring parent and candidate again | 3 | 1 | 0 | 0 |
| `machine-check` | explore every reachable state and check the invariant and the goals | 2 | 0 | 0 | 0 |
| `machine-claim` | check one claimed property at every reached state | 1 | 0 | 0 | 0 |
| `machine-create` | build a machine from a specification and write its bytes | 2 | 4 | 0 | 7 |
| `machine-discover` | report the bit properties that hold at every reached state | 1 | 0 | 0 | 0 |
| `machine-evidence` | produce a certificate or a refutation for a machine and write it | 3 | 5 | 0 | 6 |
| `machine-search` | search one-rule edits for a candidate that passes the change check | 3 | 1 | 0 | 0 |
| `model-apply` | apply a certified change or repair to a bare Git branch | 2 | 3 | 0 | 0 |
| `model-project` | write a machine's full transition table as a canonical projection, unchecked | 4 | 3 | 0 | 2 |
| `policy` | compile a boolean WPL file and sign its decision | 25 | 0 | 1 | 0 |
| `projection-check` | check a projection row by row against a verified certificate of its model | 2 | 2 | 0 | 4 |
| `projection-checker` | identify the independent projection checker | 1 | 4 | 0 | 2 |
| `projection-materialize` | write a projection next to the fixed table runtime; verify nothing | 3 | 2 | 0 | 1 |
| `put` | store object bytes | 0 | 1 | 0 | 0 |
| `record` | execute a check and store its signed decision | 10 | 3 | 0 | 1 |
| `refutation-check` | check a refutation claim against an expected model and checker | 1 | 0 | 0 | 0 |
| `refutation-create` | check a supplied model and refutation claim before writing proof data | 1 | 0 | 0 | 0 |
| `repair-search` | search a bounded neighborhood for a certified model repair | 2 | 3 | 0 | 6 |
| `require` | require a verified accept for the recipient's rule and facts | 4 | 1 | 0 | 0 |
| `runtime-pack` | snapshot the compiler source closure; never execute it | 0 | 1 | 0 | 0 |
| `unpack` | write a packet of a stated kind and an offline launcher into a directory | 17 | 4 | 0 | 0 |
| `verify` | verify a stored signed record by independent re-execution | 36 | 4 | 0 | 0 |
| `verify-bundle` | verify a file without any local object store | 1 | 0 | 0 | 0 |

59 commands. `tests`, `examples` and `integration` count the quoted command name in those files; `docs` counts `sg NAME` or `NAME` in backticks across README, VISION, SPEC, ANCHORS and docs/WALKTHROUGHS. These are mentions, not coverage.

<!-- inventory: end -->

A worked example of that caveat, from this very table: `init` shows one mention under
`examples` because `examples/two-phase-commit/two_phase_commit.py` names a coordinator
state `'init'`. The counter sees a quoted string, not a command. Read the columns as
"something here spells this name", never as coverage.

## Current inspection and export interface

The public parser provides one `inspect` and one `unpack`. The caller must select an
explicit `--expect-kind`; the packet does not choose its own reader. The old per-kind
command spellings are not public aliases. For example:

```text
sg inspect machine.json --expect-kind machine
sg inspect proof.json --expect-kind certificate
sg unpack proof.json --expect-kind evidence --output new-offline-directory
sg unpack projection.json --expect-kind projection --certificate certificate.json --output new-projection-directory
```

`inspect --help` lists the supported inspection kinds; `unpack --help` lists the
export kinds. They are different lists: `evidence` export covers certificates,
refutations and compound proof packets, while `projection` export requires a separate
certificate. `--certificate` is refused for other export kinds.

Inspection checks a packet's structure and describes it; it does not establish its
claims. Export writes the packet and replay material into a new directory; it does
not verify the proof. Use the matching evidence/repair/projection check with selected
identities to establish a result. Follow the exported launcher's authentication
instructions before executing captured source.

## Choosing an operation

Command help distinguishes operations within a family. In particular:

| Need | Operation | Meaning of completion |
| --- | --- | --- |
| Build model bytes from a specification | `machine-create` | A model was produced, not certified |
| Check reachable states | `machine-check` | A bounded exploration result; read its status and budget |
| Produce reusable proof data | `machine-evidence` | Checked certificate or refutation, or an incomplete/error result |
| Replay existing proof data | `evidence-check` | Recheck against recipient-selected model and checker identities |
| Package a proposed repair | `certificate-repair-pack` | An unchecked packet; packing is not verification |
| Check the proposed repair | `certificate-repair-check` | Verify the original defect and inherited candidate obligations |
| Export a model table | `model-project` | Produced transition data; check it with `projection-check` |

For an agent's complete workflow, use the [agent profile](docs/AGENT_PROFILE.md) and
[task helper](docs/AGENT_TASK.md). These compose the existing operations rather than
expanding what a checker verdict proves. They do not apply changes or grant authority.

## Limits of this inventory

The number of commands comes from the generated table. Reference counts are lexical
mentions in its stated file set, not usage telemetry, executed CLI call sites or test
coverage. A command with no mentions may still be used outside this checkout. A mention
may name data instead of invoking a command, as the `init` example above illustrates.
The `docs` column deliberately scans only the files named in the generated footer;
it is not an index of every document, including the newer agent guides.

A stale generated table is rejected by `tools/surface.py --check`; the handwritten
explanation still needs to be checked against the parser and behavior when it changes.
Use concrete missing behavior or repeated task friction to justify a new command or
removal. Do not infer either decision from mention counts alone.
