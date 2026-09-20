# Pre-registration: the anchor gate

Written before the gate existed and before it was run. Not edited afterwards.
Branch `feat/anchor-gate`, parent `16eb087` (build 41).

## The hole being closed

`tests/test_transport.py::test_anchor_table_matches_this_snapshot` asserts that each
current digest appears **somewhere** in `ANCHORS.md`. A table where the checker comes
from one snapshot and the lab runtime from another satisfies that test: every digest
is present, and nothing says they describe the same source. A stale or mixed row set
therefore passes today.

## What the gate must require

1. All four current digests — proof checker, lab runtime, experiment controller and
   offline launcher — belong to **one** snapshot label, with that label carrying
   exactly one row per closure.
2. The name of a tag is **derived from the checker digest**, so a tag cannot claim a
   snapshot whose checker differs. Derived name: `checker-` plus the first twelve
   hexadecimal characters of the checker digest. Labels that already exist
   (`build-37`, `build-38`) predate the rule and are accepted as they are; a label
   that starts with `checker-` must equal the derived name.
3. It runs in CI on every push and pull request, and on a tag it also checks the tag.

## Expectations

| case | expected |
| --- | --- |
| this source against the committed `ANCHORS.md` | matches snapshot `build-38`, exit **0** |
| derived tag name for this source | `checker-c06c1384f3b0` |
| one hexadecimal digit changed in the checker row | refused, exit **4** |
| digests scattered across two snapshot labels | refused, exit **4** — and the existing membership test still **passes** on that table, which is the point |
| a tag named `checker-` + the wrong digest | refused, exit **4** |
| `ANCHORS.md` missing | exit **2** |

Exit codes follow the repository: 0 established, 1 checker error, 2 invalid input,
4 checked and refused.

## What this will not establish

Nothing about whether the digests are the right ones to trust. The gate compares a
table in the repository with source in the same repository; both move together in one
commit. It catches a table that was not updated, or updated inconsistently, and
nothing else. An independently obtained snapshot is still the only thing that makes
an anchor worth anything.
