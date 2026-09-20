# Command surface

An inventory, not a proposal to act. Step one of two: the table below is generated
from the parser itself, the reading follows it, and **nothing is deleted here**. What
to remove is a decision for a person, and this file ends by asking for it.

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
| `case-inspect` | check packet integrity; never execute its contents | 3 | 0 | 0 | 0 |
| `case-pack` | pack counterexample evidence as inert data | 1 | 0 | 0 | 0 |
| `case-unpack` | materialize evidence in a new directory; never execute it | 2 | 0 | 0 | 0 |
| `certificate-change-check` | check a next-only change: both certificates and the inherited contract | 1 | 1 | 0 | 0 |
| `certificate-change-pack` | package parent and candidate certificates as an unchecked next-only change | 1 | 0 | 0 | 0 |
| `certificate-check` | check an inductive certificate against an expected model and checker | 1 | 0 | 0 | 0 |
| `certificate-checker` | identify the independent finite-certificate checker | 0 | 3 | 0 | 0 |
| `certificate-history-append` | extend a certificate history with the next checked certificate | 1 | 0 | 0 | 0 |
| `certificate-history-check` | check every step of a certificate history against its root | 1 | 1 | 0 | 0 |
| `certificate-history-start` | begin a certificate history at a root certificate | 1 | 0 | 0 | 0 |
| `certificate-inspect` | describe a certificate and check its shape, never its proof | 0 | 0 | 0 | 0 |
| `certificate-repair-check` | check a repair: the parent defect, the candidate proof, the inherited contract | 3 | 4 | 0 | 0 |
| `certificate-repair-pack` | package a refutation and a candidate certificate as an unchecked repair | 1 | 1 | 0 | 0 |
| `composition-change` | check a next-only change to one component of a composition | 1 | 0 | 0 | 0 |
| `composition-check` | explore a composition and check the joint contract | 2 | 0 | 0 | 0 |
| `composition-create` | build a composition of two components under a joint contract | 1 | 0 | 0 | 0 |
| `composition-inspect` | describe a composition and check its shape, never its behaviour | 0 | 0 | 0 | 0 |
| `composition-unpack` | write a composition and an offline launcher into a directory | 0 | 0 | 0 | 0 |
| `eval` | evaluate a term, reporting result, exit and cost | 6 | 4 | 0 | 0 |
| `evidence-check` | check a certificate or refutation against an expected model and checker | 1 | 2 | 0 | 0 |
| `evidence-unpack` | write a certificate-family packet and an offline launcher into a directory | 6 | 3 | 0 | 0 |
| `experiment-check` | compare two capsules over a corpus, executing them only with --execute-runtimes | 2 | 0 | 0 | 0 |
| `experiment-controller` | show the local experiment controller and replay identities | 0 | 2 | 0 | 0 |
| `experiment-create` | bind two source capsules and a runtime-independent corpus | 0 | 0 | 0 | 0 |
| `experiment-inspect` | describe an experiment and its capsules; never run included code | 0 | 0 | 0 | 0 |
| `experiment-unpack` | write an experiment and an offline launcher into a directory | 0 | 0 | 0 | 0 |
| `export` | verify and export one portable signed check | 2 | 0 | 0 | 0 |
| `genesis` | show intrinsic I/K/S hashes | 1 | 1 | 0 | 0 |
| `init` | create the object directory | 4 | 1 | 1 | 0 |
| `keygen` | write a new private seed (never overwrite) | 4 | 1 | 0 | 0 |
| `lab-check` | exhaustively check a text proposal without trusted keys | 9 | 3 | 0 | 0 |
| `lab-check-invariant` | recompute a finite property claim without trusting its author | 1 | 0 | 0 | 0 |
| `lab-create` | create a portable finite boolean experiment (no keys) | 3 | 0 | 0 | 0 |
| `lab-discover` | enumerate and check finite input/output properties | 2 | 0 | 0 | 0 |
| `lab-inspect` | describe a finite experiment; never run included code | 6 | 2 | 0 | 0 |
| `lab-search` | search a bounded WPL neighborhood using replayed counterexamples | 4 | 1 | 0 | 0 |
| `lab-task-inspect` | describe a lab task and its progress; never run it | 1 | 0 | 0 | 0 |
| `lab-task-resume` | continue a lab task, recomputing every imported row | 3 | 0 | 0 | 0 |
| `lab-task-start` | begin a portable lab task from a world and a row budget | 1 | 0 | 0 | 0 |
| `lab-task-unpack` | write a lab task and an offline launcher into a directory | 0 | 0 | 0 | 0 |
| `lab-unpack` | extract a standalone checker for explicit offline replay | 0 | 1 | 0 | 0 |
| `lineage-append` | extend a world history with the next checked transition | 2 | 0 | 0 | 0 |
| `lineage-check` | replay a world history against its declared root | 6 | 0 | 0 | 0 |
| `lineage-start` | begin a world history at a root world | 1 | 0 | 0 | 0 |
| `lineage-unpack` | write a world history and an offline launcher into a directory | 1 | 0 | 0 | 0 |
| `machine-change` | check a next-only change, exploring parent and candidate again | 2 | 0 | 0 | 0 |
| `machine-check` | explore every reachable state and check the invariant and the goals | 2 | 0 | 0 | 0 |
| `machine-claim` | check one claimed property at every reached state | 1 | 0 | 0 | 0 |
| `machine-create` | build a machine from a specification and write its bytes | 2 | 2 | 0 | 0 |
| `machine-discover` | report the bit properties that hold at every reached state | 1 | 0 | 0 | 0 |
| `machine-evidence` | produce a certificate or a refutation for a machine and write it | 3 | 3 | 0 | 0 |
| `machine-inspect` | describe a machine and check its shape, never its reachable states | 1 | 0 | 0 | 0 |
| `machine-search` | search one-rule edits for a candidate that passes the change check | 2 | 0 | 0 | 0 |
| `machine-unpack` | write a machine and an offline launcher into a directory | 0 | 0 | 0 | 0 |
| `model-apply` | apply a certified change or repair to a bare Git branch | 2 | 3 | 0 | 0 |
| `policy` | compile a boolean WPL file and sign its decision | 25 | 0 | 1 | 0 |
| `put` | store object bytes | 0 | 1 | 0 | 0 |
| `record` | execute a check and store its signed decision | 10 | 3 | 0 | 0 |
| `refutation-check` | check a refutation claim against an expected model and checker | 1 | 0 | 0 | 0 |
| `refutation-create` | check a supplied model and refutation claim before writing proof data | 1 | 0 | 0 | 0 |
| `refutation-inspect` | describe a refutation and check its shape, never its claim | 0 | 0 | 0 | 0 |
| `repair-search` | search a bounded neighborhood for a certified model repair | 2 | 2 | 0 | 0 |
| `require` | require a verified accept for the recipient's rule and facts | 4 | 1 | 0 | 0 |
| `runtime-pack` | snapshot the compiler source closure; never execute it | 0 | 1 | 0 | 0 |
| `verify` | verify a stored signed record by independent re-execution | 35 | 4 | 0 | 0 |
| `verify-bundle` | verify a file without any local object store | 1 | 0 | 0 | 0 |

69 commands. `tests`, `examples` and `integration` count the quoted command name in those files; `docs` counts `sg NAME` or `NAME` in backticks across README, VISION, SPEC and ANCHORS. These are mentions, not coverage.

<!-- inventory: end -->

## What the numbers say

**69 commands in 24 families.** The test suite drives the command layer from
**19 `cli.main(...)` call sites** in total. Everything else is tested through the
Python functions underneath, which is where the logic lives — so what follows is
about the command layer, not about the proofs.

* **14 commands are never driven through the CLI by any test**: `certificate-checker`,
  `certificate-inspect`, `composition-inspect`, `composition-unpack`,
  `experiment-controller`, `experiment-create`, `experiment-inspect`,
  `experiment-unpack`, `lab-task-unpack`, `lab-unpack`, `machine-unpack`, `put`,
  `refutation-inspect`, `runtime-pack`. Thirteen of them appear nowhere in `tests/`
  or `integration/` at all; `put` appears only as an English word.
* **42 of 69 are never named in `README.md`, `VISION.md`, `SPEC.md` or
  `ANCHORS.md`** — not as `sg NAME`, not in backticks.
* **38 commands share their one-line help with at least one other command.** The
  parser builds families in loops and gives the whole loop one help string, so all
  nine `machine-*` commands advertise themselves as "check a finite synchronous
  machine on all reachable states", including `machine-create` and `machine-unpack`,
  which do not check anything. Someone reading `sg --help` cannot tell these
  commands apart, which is a defect independent of how many commands there are.
* The two most uniform families are eight `*-inspect` and eight `*-unpack`
  commands; nine of those sixteen have no CLI test and thirteen are undocumented.

## Three candidates, and what each would cost

Ranked by how much surface goes away per unit of risk. None is applied.

1. **One `unpack` instead of eight.** `case-unpack`, `composition-unpack`,
   `evidence-unpack`, `experiment-unpack`, `lab-task-unpack`, `lab-unpack`,
   `lineage-unpack`, `machine-unpack` all materialize a self-describing packet into
   a directory. *Lost:* the command name currently states what the caller believes
   the packet is, and a mismatch is caught by choosing the wrong command. A single
   command would dispatch on the packet's own type field, which means the packet
   picks its own reader — a small step in the direction this repository usually
   refuses. That trade is the decision, and it is not mine to make.
2. **One `inspect` instead of eight.** Same shape, same trade, and four of the eight
   (`certificate-inspect`, `composition-inspect`, `experiment-inspect`,
   `refutation-inspect`) have no test and no mention anywhere, so they are the
   cheapest to remove outright if nobody uses them.
3. **Distinct help lines, no deletion at all.** The cheapest change in the list:
   give each command its own sentence. It removes no surface, and it is the only
   item here that makes `sg --help` honest. If exactly one thing is done, this is
   the one I would do.

## What this inventory does not establish

That any command is unused. It counts mentions in this repository — nobody's shell
history is in the table, and a command with no test may still be the one command a
user runs every day. It also does not establish that the untested fourteen are
broken: their logic is covered through the Python API, and the gap is at the command
layer only.

## The decision I am asking for

Which of the three, if any. I have not removed a command, renamed one, or changed a
help string in this pull request, because the task says to stop here — and because
the difference between "nothing references it" and "nobody uses it" is exactly the
kind of gap a table like this hides.
