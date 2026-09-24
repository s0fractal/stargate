# Results: an authenticated semantic counterexample seals re-admission

Registration: `REGISTRY.md` (`93cd93e`; revised before any run in `5d2e1a4` and pinned in
`4c7a227` by the reviewer: buggy black-heart `3893fad` / blob `78b5ac6`, fixed reviewed
head `5344c87`, merge `7396cd1`). Model data and harness committed before the first run
(`5822b4c`). Checker `d425682ebb14…` (build 47). Reproduce:
`python integration/semantic_seal_vertical.py` (compares `results.json` byte for byte).

## Against the registration

| # | registered | measured |
| --- | --- | --- |
| 1 | `buggy`: unsafe, 2 steps from `I1` | `verified_refutation`, unsafe, from `I1`: `resource_event`, then `retest_success` |
| 2 | `fixed`: certified, 5 states, both goals | `verified_certificate`, 5 states, 2 goals |
| 3 | `fixed` repairs `buggy` | `verified_repair` |
| 4 | one-edit / trace: no repair | both `neighborhood_exhausted` after 9; no monitor edit |
| 5 | `synth`: `W*` 6, 2 rows, `admitted` only, Hamming 2, `verified_repair` | exactly that; status `found`, world rule bytes unchanged, `admitted` rule 519 bytes |
| C1 | no world → `not_applicable` | `not_applicable` |
| C2 | erased seal → `unreachable_goal` on the blocked goal; not packable as a repair | exactly that (the pack refuses a refutation as the candidate) |
| C3 | guard on the wrong bit → `unreachable_goal` on the admitting goal | exactly that |

Every registered prediction held.

**One harness defect, fixed after the first run.** The first run's C1 invocation omitted
`--output`; `sg repair-search` refused it at argument parsing (exit 2), so C1 was not
measured. `06ce91d` adds the argument and changes nothing else; the second run measured
the registered `not_applicable`. Every other outcome was identical in both runs.

**The synthesized rule.** Without knowing the hand fix, `synth` produced the parent XOR two
rows:

    ((admitted || (retest_success && resource)) && !(F)) || (!(admitted || (retest_success && resource)) && F)
    F = (!admitted && resource && !resource_event && retest_success && semantic)
     || (!admitted && resource &&  resource_event && retest_success && semantic)

It is the hand fix's guard, `!semantic` on the retest path, stated only where it matters:
from a reachable state with a resource refusal and a semantic seal.

## What this establishes

- A third live defect, in a third repository, fails the same kind of invariant: an
  established authority fact — here an authenticated semantic counterexample — was
  bypassed through a second, weaker record of the same subject.
- The fix merged in black-heart (`7396cd1`) is modelled by `fixed`, which certifies with
  both the admitting and the blocked outcome reachable.
- The ownership-safe synthesizer found a verified owned-only repair on its own; the
  bounded mutation search cannot (it never adds `semantic` to the rule).
- C2: erasing the seal would have certified safety; the blocked goal is what refuses it.

## What it does not establish

That the model is the code (the code layer is black-heart's regressions and the
reproducer); anything about unauthenticated semantic-shaped records (no bit; black-heart
returns `APPLICABILITY_UNKNOWN`); quota finding D; revocation of an admission granted
before a later counterexample.
