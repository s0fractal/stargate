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
