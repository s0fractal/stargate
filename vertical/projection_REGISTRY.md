# Pre-registration: the canonical projection format (PR-02)

Written before the projector exists. Not edited after the run.

## The claim

A bounded Boolean machine can be written out deterministically as its complete
transition table, `projection-1`, with no Python, Rust or WPL left in it. The
projector is a **producer**: it asserts nothing about its own output. Whether a
projection matches a model is PR-03's question and nobody else's.

## The format

```json
{"projection": 1, "model": "<ModelID>", "state": [...], "events": [...],
 "rows": [{"state": {...}, "event": {...}, "next": {...}}, ...]}
```

* `model` is the certificate ModelID of the machine, `certificate.identity(
  certificate.model_from_machine(machine))` — the identity a certificate names, so a
  projection and a certificate can later be compared without the machine.
* `state` has 1..6 names, `events` 0..2, each sorted and unique, disjoint — the
  machine's own ordering.
* `rows` holds exactly one row for every pair in the **full** Boolean domain,
  2^(|state|+|events|) rows, 2..256. Unreachable states and states that violate the
  invariant are rows like any other: the table is the transition function, not the
  reachable graph.
* Canonical order: states outer, events inner; each enumerated as
  `itertools.product((False, True), repeat=n)` over the names in order. Row *i* must
  be exactly the *i*-th pair. A duplicate, a missing pair and a misplaced pair are
  each invalid input, reported as such.
* `next` gives every state bit a Boolean. Nothing else: exact fields everywhere, no
  verdict (`conforms`) and no checker ID.
* `projection_id` = SHA-256 of the canonical bytes.

## Command

```sh
sg model-project MACHINE --expect-machine MACHINE_ID --output projection.json
```

Report: `{"status": "projected", "model": ..., "rows": N, "projection_id": ...}`,
exit 0. A machine that does not match `--expect-machine` is invalid input, exit 2.
An existing output path is not overwritten.

This PR adds one command and one format, which the plan asks for; the older
build-38 rule against new formats and commands is superseded by the plan for this
cycle, and that is stated here rather than silently ignored.

## Expected outcomes

1. The two-bit machine `a' = a || e`, `b' = a && !b` (state `a, b`, event `e`)
   projects to exactly these eight rows, in this order:

   | a | b | e | a' | b' |
   |---|---|---|---|---|
   | F | F | F | F | F |
   | F | F | T | T | F |
   | F | T | F | F | F |
   | F | T | T | T | F |
   | T | F | F | T | T |
   | T | F | T | T | T |
   | T | T | F | T | F |
   | T | T | T | T | F |

2. Projecting the same machine twice gives byte-identical output and the same ID.
3. A projection with one row duplicated (replacing another) is refused by
   `projection.inspect` as `duplicate row`.
4. A projection with one row removed is refused as `missing row`.
5. Two rows swapped is refused as out of canonical order.
6. Wrong shapes are refused: a state bit missing from a row, an extra field in a
   row, an extra top-level field (`conforms`), a non-Boolean value, unsorted names,
   seven state bits, three events, `projection: 2`.
7. Every zoo machine (13 systems × `correct`) projects, and a Peterson projection
   has 2^5 × 2^1 = 64 rows.
8. The machine proof checker, lab runtime, experiment controller and launcher are
   byte-identical before and after; `tools/vertical_baseline.py --check` stays 0.

## Control (what PR-02 does not claim)

A projector with one `next` cell flipped still produces a projection that
`projection.inspect` accepts, and its report still says `projected`. That is the
expected outcome, not a defect: structure is all this PR checks. The report
carries no field that could be read as a verdict about the model.

## What this will not establish

That any projection is the machine's transition function. That the machine is
safe, live or certified. That a runtime executing the table behaves like the
model. A projection is inert data produced by untrusted code until PR-03's
verifier compares it with a checked certificate.

---

# Second registration: the size ceiling (after review of `53f7ddf`)

Written after the review found the defect and before the fix; the first
registration above is left as written. The defect was reproduced once in a scratch
script before this text: a valid 197 594-byte machine (six state bits, two events,
one 8 081-byte state name) whose projection `project` builds and then refuses
itself with `projection must be bytes within 1 MiB`.

## The bound, derived from the machine schema

Nothing in the machine limits a name's length except the WPL source limit
(`compiler.MAX_SOURCE_BYTES = 8192`), and `compiler.parse` requires every `next` rule
to declare **all** k = |state| + |events| names. The shortest declaration is
`fact N:bool` plus one separator — `len(N) + 11` bytes — and the shortest tail is
`check!b` (7 bytes). So in every valid machine

    sum of name lengths  <=  8192 - 7 - 11k  =  8185 - 11k.

A projection's canonical bytes are linear in the name lengths: a state name appears
2R + 1 times (twice per row, once in `state`), an event name R + 1 times, R =
2^(|state|+|events|). Taking every value as `false` (the longer literal) and giving
all spare bytes to one state name gives an upper bound for each (|state|, |events|);
the largest is at 6 state bits and 2 events:

    MAX_PROJECTION = 4 193 586 bytes

computed from `compiler.MAX_SOURCE_BYTES`, not written as a literal in `projection.py`.
Machine semantics and the machine checker do not change.

## Expected outcomes

1. `projection.MAX_PROJECTION == 4193586`.
2. The corner machine — states `a…a` (8 081 bytes), `b, c, d, e, f`; events `x, y`;
   every rule exactly 8 192 bytes — is accepted by `machine.create`, and one more
   byte in its long name is refused (`source exceeds 8192 bytes`).
3. `model-project` on the corner machine: `projected`, 256 rows, the packet within
   `MAX_PROJECTION` and accepted by `inspect`. Its measured size is recorded, not
   predicted; it must be below the bound because some values are `true`.
4. `inspect` on `MAX_PROJECTION + 1` bytes: refused for size. On exactly
   `MAX_PROJECTION` bytes of non-projection content: refused, but not for size.
5. The closure digests and the vertical baseline are unchanged.

## What this will not establish

That 4 193 586 bytes is small. It is the price of names the schema already allows;
narrowing names would be a machine-contract change and is not made here.
