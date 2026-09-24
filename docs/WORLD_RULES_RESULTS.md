# Results: ownership-safe automatic repair (world rules)

The registration is [WORLD_RULES_REGISTRY.md](WORLD_RULES_REGISTRY.md) (second text,
revised before any run); it is not edited. All outcomes as registered.

| # | outcome | measured |
| --- | --- | --- |
| 1 | a repair editing a world rule | invalid — `repair alters world rule: calls.one`; an owned-only repair (`fixed`) is `verified_repair` |
| 2 | change / repair adds, drops or alters `world` | invalid in all four cases |
| 3 | `world` empty, unsorted, duplicated, or naming a non-state bit | invalid |
| 4 | a plain `certified_change` evolving a world rule | `verified_change` |
| 5 | models without `world` | certificate ModelIDs unchanged; both verticals keep every verdict; their `results.json` differ only in MachineIDs and the recorded checker ID |
| 6 | warrant vertical with `world = [calls.one, calls.two]` | `repair-search` one-edit: `neighborhood_exhausted` after 21; trace: `neighborhood_exhausted` after 22; **no repair of `calls.*`**; hand-written `fixed` still `verified_repair` |
| 7 | admission transition | new checker code with the old record: 19 identity tests red, no behavioural test (commit 7f13de6); re-baseline (`vertical/baseline.json`, build 47), new anchor `snapshot-60fcd3fcb072`, record moved to `d425682ebb14` / `80a23b477b85`: green. Both mismatch directions → `checker_unavailable`; agreement → `verified` |

**Control.** With the world-rule equality removed from `verify_repair`, the forged
"server owes nothing" repair is `verified_repair`; the real checker refuses it.

**What outcome 6 says, and does not.** The bounded one-edit search no longer returns the
repair of the world it returned in #64. It also finds no repair at all: the fix that was
adopted changes two owned rules together, outside a one-edit neighborhood. Ownership
removed a wrong answer; it did not produce a right one. Whether automatic repair should
search further is a separate question, and this change does not answer it.
