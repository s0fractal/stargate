# Zoo: eight systems through the same pipeline

Every system here is a pair of models over the same `state`, `events`, `initial`,
`invariant` and `goals`; only `next` differs. The harness builds both, asks
`evidence.produce` for a proof of each, and then runs both repair strategies on
the broken one with the quota written in the system file.

```sh
python examples/zoo/harness.py            # rewrites results.json and prints the table
python -m unittest discover -s tests -p 'test_zoo.py'   # regenerates and compares
```

Expectations were written first, in [REGISTRY.md](REGISTRY.md), and are not edited
after a run. The one disagreement is named below and in `results.json`.

## The table

Measured at build 41 (`16eb087`), checker
`c06c1384f3b0c890ed9105da68a3212183939e8165b56950ff5629d84fabdd05`.

| system | bits (state/event) | refutation | trace | certificate | one-edit | trace search |
| --- | --- | --- | --- | --- | --- | --- |
| `alternating-bit` | 4/1 | unsafe | 1 steps | 5 states, 1913 B | found at 25 | found at 42 |
| `bounded-buffer` | 2/2 | unsafe | 3 steps | 3 states, 1114 B | found at 102 | found at 11 |
| `interlock` | 2/1 | unsafe | 2 steps | — | neighborhood_exhausted at 11 | neighborhood_exhausted at 11 |
| `peterson` | 5/1 | unsafe | 6 steps | 20 states, 3216 B | neighborhood_exhausted at 178 | found at 1 |
| `philosophers` | 4/1 | unsafe | 4 steps | 10 states, 2112 B | found at 24 | found at 28 |
| `readers-writer` | 3/2 | unsafe | 2 steps | 6 states, 1415 B | found at 42 | found at 46 |
| `token-ring-natural` | 3/1 | unsafe | 1 steps | 3 states, 1258 B | neighborhood_exhausted at 37 | neighborhood_exhausted at 39 |
| `token-ring-onestep` | 3/1 | unsafe | 1 steps | 3 states, 1258 B | found at 12 | found at 15 |

"trace" is the length of the refuting counterexample for the broken model;
"certificate" is the inductive set proved for the correct one. The `interlock`
certificate column is empty because both of its models are refuted — see below.

## What the numbers say about the trace strategy

On eight systems, with the same quota per system:

* `trace` needed **more** attempts on five: alternating-bit (42 vs 25),
  readers-writer (46 vs 42), philosophers (28 vs 24), token-ring-onestep (15 vs 12),
  token-ring-natural (39 vs 37, both exhausted).
* It needed the **same** on one: interlock, where both strategies exhaust at 11.
* It needed **fewer** on two: bounded-buffer (11 vs 102) and peterson (1 attempt and
  a repair, where one-edit exhausts after 178 without one).

So the ordering is not an improvement of the search in general; it is an
improvement on models whose fault sits upstream of the violated invariant, which
is what the ranking looks for. Where it wins it can change the outcome, not just
the cost — Peterson has no repair inside the plain one-edit neighborhood at all.
Where it loses, it loses two to four attempts, except alternating-bit, where the
compound exchanges cost 68% more work before the same repair.

This is eight systems chosen by one author, with one quota each and one fault per
system. It does not establish an average, a distribution, or that either strategy
behaves this way on systems outside this file.

## The one disagreement with the pre-registration

**interlock.** The registration expected the `correct` side to certify. It does
not: both models are refuted. `examples/interlock.json` is the model the repository
README *repairs* — it is the defect, not the fix, and the repaired rule
(`open = request && armed`) exists only inside a search result. The zoo entry
therefore pairs two defects, and the row records that instead of hiding it. The
pre-registered cell is kept as written; `results.json` lists `interlock` in
`mismatches`.

## What this table does not establish

* Nothing about the systems as engineering artifacts. These are synchronous
  Boolean models of a few bits; a model that certifies here is not a correct lift,
  protocol or buffer.
* Nothing about the faults being representative. `token-ring-onestep` is
  constructed to sit one edit from the correct rule, and its own file says so.
* Nothing about repair quality. `found` means one repair inside a finite
  neighborhood was proved, not that it is the repair an engineer would choose.
* Nothing about absent goals or liveness. Today the checker proves safety and the
  existence of goal paths; see the philosophers limit below.

## The limit the zoo makes visible

`philosophers` in its honest form **certifies today** although the deadlock state
`h0 && h1 && !e0 && !e1` is reachable and has no way out. Deadlock is not a safety
violation, and both goals are reachable from the initial state, so every command in
the repository accepts the model:

```sh
python examples/zoo/harness.py --print   # philosophers: correct = verified_certificate
```

That is the red example for a goal-reachability obligation: a certificate would
have to prove the goals reachable from *every* state of the certified set, not only
from the initial one. Nothing in this pull request adds that obligation.

## What did not fit

* **Hyman's algorithm** (CACM 9(1), 1966) was dropped before any run. Its fault is
  a race between reading the other process's flag and writing `turn`; steps here
  are atomic per process, so every six-bit encoding of it is safe for the wrong
  reason. No command refused it — it was never submitted, and that is the honest
  statement: this is an analysis, not a measurement.
* **Four systems from an earlier Gemini session** (lift doors, traffic lights,
  bounded buffer, railroad crossing) were requested with their rules frozen as they
  are. They are not in this repository or in any handoff, so nothing was frozen and
  nothing was invented in their place. The `bounded-buffer` here is a new encoding
  written for this zoo.
* One command did refuse during the work: `machine-create` rejected state names in
  an order of my choosing —
  `InvalidRecord: inputs must be at most eight sorted unique WPL names`. The
  harness sorts names before building a machine; the system files keep the order
  that reads best.
