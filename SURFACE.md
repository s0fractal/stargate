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
| `case-pack` | pack counterexample evidence as inert data | 1 | 0 | 0 | 0 |
| `certificate-change-check` | check a next-only change: both certificates and the inherited contract | 1 | 1 | 0 | 0 |
| `certificate-change-pack` | package parent and candidate certificates as an unchecked next-only change | 1 | 0 | 0 | 0 |
| `certificate-check` | check an inductive certificate against an expected model and checker | 1 | 0 | 0 | 0 |
| `certificate-checker` | identify the independent finite-certificate checker | 0 | 3 | 0 | 0 |
| `certificate-history-append` | extend a certificate history with the next checked certificate | 1 | 0 | 0 | 0 |
| `certificate-history-check` | check every step of a certificate history against its root | 1 | 1 | 0 | 0 |
| `certificate-history-start` | begin a certificate history at a root certificate | 1 | 0 | 0 | 0 |
| `certificate-repair-check` | check a repair: the parent defect, the candidate proof, the inherited contract | 3 | 4 | 0 | 0 |
| `certificate-repair-pack` | package a refutation and a candidate certificate as an unchecked repair | 1 | 1 | 0 | 0 |
| `composition-change` | check a next-only change to one component of a composition | 1 | 0 | 0 | 0 |
| `composition-check` | explore a composition and check the joint contract | 2 | 0 | 0 | 0 |
| `composition-create` | build a composition of two components under a joint contract | 1 | 0 | 0 | 0 |
| `eval` | evaluate a term, reporting result, exit and cost | 6 | 4 | 0 | 0 |
| `evidence-check` | check a certificate or refutation against an expected model and checker | 1 | 2 | 0 | 0 |
| `experiment-check` | compare two capsules over a corpus, executing them only with --execute-runtimes | 2 | 0 | 0 | 0 |
| `experiment-controller` | show the local experiment controller and replay identities | 0 | 2 | 0 | 0 |
| `experiment-create` | bind two source capsules and a runtime-independent corpus | 0 | 0 | 0 | 0 |
| `export` | verify and export one portable signed check | 2 | 0 | 0 | 0 |
| `genesis` | show intrinsic I/K/S hashes | 1 | 1 | 0 | 0 |
| `init` | create the object directory | 4 | 1 | 1 | 0 |
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
| `machine-create` | build a machine from a specification and write its bytes | 2 | 2 | 0 | 0 |
| `machine-discover` | report the bit properties that hold at every reached state | 1 | 0 | 0 | 0 |
| `machine-evidence` | produce a certificate or a refutation for a machine and write it | 3 | 3 | 0 | 0 |
| `machine-search` | search one-rule edits for a candidate that passes the change check | 3 | 1 | 0 | 0 |
| `model-apply` | apply a certified change or repair to a bare Git branch | 2 | 3 | 0 | 0 |
| `model-project` | write a machine's full transition table as a canonical projection, unchecked | 4 | 1 | 0 | 0 |
| `policy` | compile a boolean WPL file and sign its decision | 25 | 0 | 1 | 0 |
| `projection-check` | check a projection row by row against a verified certificate of its model | 1 | 1 | 0 | 0 |
| `projection-checker` | identify the independent projection checker | 1 | 2 | 0 | 0 |
| `put` | store object bytes | 0 | 1 | 0 | 0 |
| `record` | execute a check and store its signed decision | 10 | 3 | 0 | 0 |
| `refutation-check` | check a refutation claim against an expected model and checker | 1 | 0 | 0 | 0 |
| `refutation-create` | check a supplied model and refutation claim before writing proof data | 1 | 0 | 0 | 0 |
| `repair-search` | search a bounded neighborhood for a certified model repair | 2 | 2 | 0 | 0 |
| `require` | require a verified accept for the recipient's rule and facts | 4 | 1 | 0 | 0 |
| `runtime-pack` | snapshot the compiler source closure; never execute it | 0 | 1 | 0 | 0 |
| `unpack` | write a packet of a stated kind and an offline launcher into a directory | 12 | 3 | 0 | 0 |
| `verify` | verify a stored signed record by independent re-execution | 35 | 4 | 0 | 0 |
| `verify-bundle` | verify a file without any local object store | 1 | 0 | 0 | 0 |

58 commands. `tests`, `examples` and `integration` count the quoted command name in those files; `docs` counts `sg NAME` or `NAME` in backticks across README, VISION, SPEC and ANCHORS. These are mentions, not coverage.

<!-- inventory: end -->

A worked example of that caveat, from this very table: `init` shows one mention under
`examples` because `examples/two-phase-commit/two_phase_commit.py` names a coordinator
state `'init'`. The counter sees a quoted string, not a command. Read the columns as
"something here spells this name", never as coverage.

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
