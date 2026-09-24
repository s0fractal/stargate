# Results: ownership-safe safety synthesis for repair (PR-85)

Registration: `docs/SYNTH_REGISTRY.md` (written at `main` `7233ab9` before any code;
revised before any run twice — `rule_atp`, then the emitter after Codex's pre-run review).
Harness committed before the run; `python integration/synth_vertical.py` reproduces
`docs/synth-results.json` byte for byte. Checker unchanged (`d425682ebb14…`, build 47).

## Against the registration

| | registered | measured |
| --- | --- | --- |
| sigma `W*` | 6, realizable | 6, realizable |
| sigma rows / rules / Hamming | 6 / `named, reject` / 8 | 6 / `named, reject` / 8 |
| sigma checker | `verified_repair` | `verified_repair` (status `found`, world rule bytes identical) |
| warrant `W*` | 9, realizable | 9, realizable |
| warrant rows / rules / Hamming | 1 / `ambiguous` / 1 | 1 / `ambiguous` / 1 |
| warrant checker | refutation of kind `trap` on `idle`, no repair | `verified_refutation`, kind `trap`; status `not_certified`, no packet |
| `max_atp` fit | not predicted | both delta rules fit `max_atp = 1000` |

Every registered prediction held; no deviation.

**Representation.** sigma's rules are the parent XOR four changed rows each
(`named` 858 bytes, `reject` 886); warrant's `ambiguous` is 302 bytes, and `pending`, which
the strategy does not change, keeps its parent bytes (170 — the report lists candidate
rule sizes, changed or not). With the first, full-minterm emitter all four owned rules
exceeded the compiler's 256-token ceiling (Codex's pre-run count 570 / 436 / 519 / 313):
the run would have ended in the parser, not at the checker.

## What this establishes

- On sigma-glyph, a producer with no knowledge of the hand fix found a repair that
  `verify_repair` accepts, changing only owned rules. The successor is not the hand fix's
  text; on the reachable states it behaves the same (the checker, not this document,
  establishes that it is safe and reaches both seals).
- On warrant, the same producer found the unique minimal *safe* change and the checker
  refused it on liveness: `ambiguous` is set once and never cleared, so `idle` is no longer
  reachable. That is the measured boundary between **safety synthesis** and **liveness
  repair**; the hand fix clears `ambiguous` at end of stream, which no safety fixed point
  asks for. Reachability or Büchi synthesis is not added here.
- `repair-search --strategy synth` never proposed a world or monitor rule edit, and would
  be refused by the checker if it did (control G2).

## What it does not establish

That minimal Hamming is the right repair; that `unrealizable` is proved (it is a producer
claim); that the emitter's forms fit other machines' ceilings; that either successor is
its code.
