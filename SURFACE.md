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
