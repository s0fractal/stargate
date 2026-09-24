# Pre-registration: ownership-safe safety synthesis for repair (PR-85)

Written at `main` `7233ab9` before any code of it exists. Not edited after the run; what
is learned goes to `SYNTH_RESULTS.md`.

## Why, and why not the pair search

The verdict (docs/VERDICT.md) recorded that in both live verticals the bounded one-rule
search behaves correctly and does not reach the fix, and that both fixes change two owned
rules. A two-rule version of the same search was proposed. It is not built, for a reason
derived before any run:

**Negative design result.** The local mutation grammar (`search._mutations`: negate a
node, swap `and`/`or`, swap operands, collapse `x op x`, drop a double negation) never
adds a fact to a rule; it can only keep or lose the facts the rule already reads. On the
code at `7233ab9`, `candidates()` of warrant's `ambiguous' = ambiguous` is exactly
`[!(ambiguous)]` and of sigma-glyph's `named' = answered` exactly `[!(answered)]`. The
known repairs need `ambiguous` to read `host` and `pending`, and `named` to read
`sealed_*`. With those single edits the invariant still fails in two steps whatever the
other rule is (warrant: *call, call* leaves `calls.two` with `ambiguous` false; sigma-glyph:
a `REJECT` seals with `named` false). So no finite combination of one local mutation per
rule expresses the known repairs. No pair-search implementation is run.

## The contract

A new strategy, `repair-search --strategy synth`. **Producer only**: the checker, proof
formats, ModelID semantics and checker identity do not change. The strategy proposes;
the ordinary path decides: `evidence.produce` → `pack_repair` → `verify_repair`, which
checks invariant, goals, `live_goals`, world rules and the rest. The synthesis never
replaces that verdict.

**Applicability.**
- The parent must be refuted with claim kind `unsafe`. A parent that certifies is
  `not_needed` (as today). A refutation of kind `unreachable_goal` or `trap` gives
  `not_applicable`: a safety fixed point does not pretend to synthesize reachability or
  liveness.
- The machine must declare a nonempty `world` and leave at least one owned bit; otherwise
  `not_applicable`. An undeclared world is not read as "everything may be rewritten".

**The game.** State domain `S` = all `2^|state|` Boolean assignments (not only states the
parent reaches); events `E` = all `2^|events|` valuations, because the checker admits
every event in every reached state. For state `s` and event `e`, the world bits' next
values `worldNext(s, e)` are the parent's world rules, evaluated on the old facts; the
owned bits' next values `o` are chosen after `e`, because an owned rule is a Boolean
function of `(state, event)`.

    W0     = { s in S | invariant(s) }
    W(i+1) = { s in W(i) | for every e in E: exists o: combine(worldNext(s, e), o) in W(i) }
    W*     = the greatest fixed point (reached when W(i+1) = W(i))

**Unrealizable.** If some initial state is not in `W*`, no owned-only safety strategy
exists among *all* Boolean next-functions of the owned bits, not just in a grammar. This is
a **producer conclusion, not a proof**: the checker has no certificate of
unrealizability. Status `unrealizable`, with the size of `W*` and the first initial state
outside it; no candidate, no repair packet.

**Strategy (deterministic).** For each `(s, e)` with `s in W*`: keep the parent's owned
vector if it leads into `W*`; otherwise take an admissible owned vector at minimal Hamming
distance from the parent's, ties broken by comparing vectors as tuples in sorted owned-bit
order with `false < true`, smallest first. For `s` outside `W*`, keep the parent's rows.
World rule bytes are not touched.

**Emitter (existing WPL only).** *(Revised before the run after Codex's pre-run review of
#85: the first text ignored the compiler's 256-token ceiling, which the full-minterm form
exceeds on every owned rule of both acceptance cases — 570 / 436 / 519 / 313 tokens — and
re-emitted rules the strategy did not change.)*

- If an owned bit's chosen truth table equals the parent rule's table, the parent rule's
  bytes are kept **exactly**. `changed_owned_rules` is then exactly the set of rules whose
  bytes change.
- Otherwise, candidate representations over the rule's inputs (sorted; rows in binary
  order, first input most significant): a constant `true`/`false` if the table is
  constant; the **delta over the parent** `(P && !F) || (!P && F)`, where `P` is the parent
  rule's expression and `F` the DNF of the rows where the strategy differs from the parent
  (XOR with the changed rows; available when the parent rule is fact declarations and one
  `check`); the DNF of the true rows; `!(DNF of the false rows)`. Full minterms, no
  minimization.
- A representation is **valid** only if the current compiler parses it
  (`compiler.parse`: `compiler.MAX_SOURCE_BYTES`, `compiler.MAX_TOKENS`, grammar — no
  second copy of these limits), every row compiles within the machine's `max_atp`, and the
  independent Boolean oracle gives exactly the chosen table on every row.
- The emitter takes the valid representation with the fewest UTF-8 bytes; ties in the
  order constant, delta, true-row DNF, negated false-row DNF.
- No valid representation: `search_incomplete` with reason `rule_wpl` (carrying the
  compiler's own message) when no candidate parses, `rule_atp` when some parse but none
  compiles within `max_atp` — never "repair impossible". A table mismatch of a parsed
  candidate is a producer error. WPL is not extended, and `max_atp` is a contract field
  the synthesizer does not change.

Whether the delta forms fit `max_atp = 1000` in the two verticals is **not predicted**;
the run measures it. If they do not, the registered checker outcomes are not reached and
the result is a representability boundary, recorded as such.

**Report.** `winning_states`, `changed_rows`, `changed_owned_rules`,
`total_owned_hamming_delta`, `emitted_rule_bytes` (per owned rule), and
`final_checker_status` — plus the candidate's refutation kind when it is not certified.

## Predictions, derived by hand before the run

Exact synthesized expressions are **not** registered: they were not derived.

**sigma-glyph** (`examples/sigma-verdict`, `buggy`, world `sealed_adopt, sealed_reject`;
owned `named, reject`).
- `W0` = 6 states: unsealed with any `named, reject` (4), sealed `REJECT` with
  `named ∧ reject` (1), sealed `ADOPT` with `named ∧ ¬reject` (1). Each has, for every
  event, an owned choice back into `W0` (seal on `REJECT` → `(1,1)`; on non-`REJECT` →
  `(1,0)`; otherwise anything). **`W*` = 6, realizable.**
- Changed rows: none in the 4 unsealed states (the parent's choice already leads into
  `W*`); in sealed `REJECT`, the two `NO VERDICT` rows (`(0,0)` → `(1,1)`, distance 2 each)
  and the non-`REJECT` row (`(1,0)` → `(1,1)`, 1); in sealed `ADOPT`, the two `NO VERDICT`
  rows (`(0,0)` → `(1,0)`, 1 each) and the `REJECT` row (`(1,1)` → `(1,0)`, 1).
  **`changed_rows` = 6, `changed_owned_rules` = 2, `total_owned_hamming_delta` = 8.**
- No `live_goals`; both seal goals are reached in one step exactly as in the parent.
  **`final_checker_status` = `verified_repair`.**

**warrant** (`examples/mcp-proxy`, `current`, world `calls.one, calls.two`; owned
`ambiguous, pending`).
- `W0` = 9 states: `calls.two` with `calls.one ∧ ambiguous` (2), `calls.one ∧ ¬calls.two`
  with `pending ∨ ambiguous` (3), neither (4). From each, for every event, choosing
  `ambiguous' = pending' = true` satisfies the invariant (on `W0` the world never makes
  `calls.two'` true without `calls.one'`). **`W*` = 9, realizable.**
- Only one parent row leaves `W*`: state `{ambiguous: false, calls.one: true,
  calls.two: false, pending: true}` under a call (`host ∧ ¬reply`) goes to
  `calls.two ∧ ¬ambiguous`; the unique nearest admissible vector sets `ambiguous` (1).
  Responses, server requests and end of stream never leave `W*`.
  **`changed_rows` = 1, `changed_owned_rules` = 1 (`ambiguous`),
  `total_owned_hamming_delta` = 1.**
- The parent keeps `ambiguous' = ambiguous` everywhere else, so once set it is never
  cleared, and *call, call* reaches it. The candidate is safe, but `idle` (the live goal)
  is then unreachable from a reached state. **Predicted: the checker does not certify it —
  a refutation of kind `trap` for `idle`; no verified repair.** That would be the
  measured statement "safety synthesis is not enough here"; it is not a reason to add
  reachability or Büchi synthesis in this PR.

Both parents are refuted with kind `unsafe` (as measured in their verticals), so the
strategy applies to both.

## Controls (G8), each a mutation with a registered effect

Machine `K` (control only): state `o` (owned), `w` (world); event `x`; `w' = x`;
`o' = o`; invariant `!w`; initial all false. Event `x = true` forces `w` into the unsafe
region whatever `o` is, so `W*` is empty and the correct answer is `unrealizable`.

| control | mutation | registered effect |
| --- | --- | --- |
| G1 ∀ → ∃ | the fixed point asks for *some* event instead of every event | on `K` it reports realizable and emits a candidate, which the checker refutes (`unsafe`); the unmutated code says `unrealizable` |
| G2 world choice | the synthesizer may choose world bits' next values too | on `K` it "repairs" by holding `w` false; the candidate changes the world rule and `verify_repair` refuses it (`repair alters world rule: w`); the unmutated code says `unrealizable` |
| G3 emitter | one row of an emitted rule is flipped before the table check | the emitter check refuses before the checker is called; the unmutated emitter's rules match the strategy on every row |

## What a pass establishes, and what it does not

A `verified_repair` from `synth` is a checked repair, established by `verify_repair`, not
by the synthesis. An `unrealizable` report is a claim of the producer. The fixed point is
over safety only; goals and live goals are the checker's to judge. One synthesis
strategy (minimal Hamming, lexicographic ties) is fixed in advance; that it is the "best"
repair is not claimed.
