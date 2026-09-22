# Zoo: thirteen systems through the same pipeline

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

Measured at build 42, machine proof checker
`ab72a8025a564c067f6d3a8551775733a8153ef696d1942a1f1b80e4afe107cd`. The last column
declares every goal of the `correct` model live (reachable from every certified
state) and reports what the checker then says; `interlock` and `railroad-crossing-v1`
have no certificate to extend, because their `correct` models are refuted for safety
first.

| system | bits (state/event) | refutation | trace | certificate | one-edit | trace search | goals live |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `alternating-bit` | 4/1 | unsafe | 1 steps | 5 states, 1913 B | found at 25 | found at 42 | yes |
| `bounded-buffer-gemini` | 2/1 | unsafe | 3 steps | 3 states, 896 B | found at 7 | found at 9 | yes |
| `bounded-buffer` | 2/2 | unsafe | 3 steps | 3 states, 1114 B | found at 102 | found at 11 | yes |
| `interlock` | 2/1 | unsafe | 2 steps | — | neighborhood_exhausted at 11 | neighborhood_exhausted at 11 | verified_refutation |
| `lift-doors` | 3/1 | unsafe | 4 steps | 5 states, 1220 B | found at 19 | found at 21 | yes |
| `peterson` | 5/1 | unsafe | 6 steps | 20 states, 3216 B | neighborhood_exhausted at 178 | found at 1 | yes |
| `philosophers` | 4/1 | unsafe | 4 steps | 10 states, 2112 B | found at 24 | found at 28 | no, trap of 1 |
| `railroad-crossing-v1` | 3/1 | unsafe | 4 steps | — | found at 4 | found at 6 | verified_refutation |
| `railroad-crossing` | 3/1 | — | — | 6 states, 1280 B | not_needed at 0 | not_needed at 0 | yes |
| `readers-writer` | 3/2 | unsafe | 2 steps | 6 states, 1415 B | found at 42 | found at 46 | yes |
| `token-ring-natural` | 3/1 | unsafe | 1 steps | 3 states, 1258 B | neighborhood_exhausted at 37 | neighborhood_exhausted at 39 | yes |
| `token-ring-onestep` | 3/1 | unsafe | 1 steps | 3 states, 1258 B | found at 12 | found at 15 | yes |
| `traffic-lights` | 3/1 | unsafe | 1 steps | 5 states, 1321 B | found at 11 | found at 13 | yes |

"trace" is the length of the refuting counterexample for the broken model;
"certificate" is the inductive set proved for the correct one. The `interlock`
certificate column is empty because both of its models are refuted — see below.

## What the numbers say about the trace strategy

On twelve systems that need a repair at all, with the same quota per system:

* `trace` needed **more** attempts on nine: alternating-bit (42 vs 25),
  readers-writer (46 vs 42), philosophers (28 vs 24), lift-doors (21 vs 19),
  traffic-lights (13 vs 11), bounded-buffer-gemini (9 vs 7), railroad-crossing-v1
  (6 vs 4), token-ring-onestep (15 vs 12), token-ring-natural (39 vs 37, both
  exhausted). Eight of those nine cost exactly two extra attempts.
* It needed the **same** on one: interlock, where both strategies exhaust at 11.
* It needed **fewer** on two: bounded-buffer (11 vs 102) and peterson (1 attempt and
  a repair, where one-edit exhausts after 178 without one).
* `railroad-crossing` needs no repair at all, so neither strategy runs.

So the ordering is not an improvement of the search in general; it is an
improvement on models whose fault sits upstream of the violated invariant, which
is what the ranking looks for. Where it wins it can change the outcome, not just
the cost — Peterson has no repair inside the plain one-edit neighborhood at all.
Where it loses, it loses two to four attempts, except alternating-bit, where the
compound exchanges cost 68% more work before the same repair.

This is thirteen systems, eight chosen by one author and five carried over from an
earlier session, with one quota each and one fault per system. It does not establish an average, a distribution, or that either strategy
behaves this way on systems outside this file.

## The one disagreement with the pre-registration

**interlock.** The registration expected the `correct` side to certify. It does
not: both models are refuted. `examples/interlock.json` is the model the repository
README *repairs* — it is the defect, not the fix, and the repaired rule
(`open = request && armed`) exists only inside a search result. The zoo entry
therefore pairs two defects, and the row records that instead of hiding it. The
pre-registered cell is kept as written; `results.json` lists `interlock` in
`mismatches`.

## The live-goal column

Of the eight systems registered first, seven `correct` models keep every goal
reachable from every state they can reach. `philosophers` does not: one state,
`h0 && h1 && !e0 && !e1`, can reach neither eating goal, and the checker names
exactly that set. This was predicted in the second registration of
[examples/live_goals_REGISTRY.md](../live_goals_REGISTRY.md) before it was run,
and every row came out as predicted.

The five systems carried over from the earlier session (`bounded-buffer-gemini`,
`lift-doors`, `railroad-crossing`, `railroad-crossing-v1`, `traffic-lights`)
reached this branch only when it was synchronised with `main`, after that
registration. Their live-goal cells are **measured, not predicted**: four say
`yes`, and `railroad-crossing-v1` has no certificate to extend because its
`correct` model is refuted for safety. The registry was not edited to include them.

The column says nothing about fairness: a live goal is reachable under *some*
event sequence from every certified state, never under every sequence.

It is not an extra, either. Every system here is measured with its goals live, and a
new system is added with that column filled, because safety plus reachability from
the initial state is a contract a machine can satisfy while parked: a repair that
freezes a model in one state forever satisfies both and is refused only by this
column. The repair search found exactly such a repair for a three-colour traffic
light in `tools/` work, and nothing but a live goal saw it.

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

## The limit this zoo made visible, and what closed it

`philosophers` in its honest form **certifies** as long as its goals are ordinary
goals, although the deadlock state `h0 && h1 && !e0 && !e1` is reachable and has no
way out: deadlock is not a safety violation, and both goals are reachable from the
initial state. That is the row that motivated `live_goals`.

The same model, with the same rules and one added field, is now refuted, and the
trap the checker names is exactly that one state — see the last column above and
`tests/test_live_goals.py`. The model without the field still certifies: the
obligation is opt-in, and the old verdict is not retracted, it is a different
question.

## The five systems from the earlier session

`lift-doors`, `traffic-lights`, `bounded-buffer-gemini` and the two
`railroad-crossing` variants come from a Gemini session log; the owner carried the
rules over unchanged and reported that session's numbers before this harness ever
saw them. They are registered in
[REGISTRY-GEMINI.md](REGISTRY-GEMINI.md) and every registered cell reproduced here:
19/21, 11/13 and 7/9 attempts, and both railroad verdicts.

The two railroad rows are the interesting ones, and neither is a success:

* `railroad-crossing-v1` is the first variant. Its **correct** model is refuted as
  well, so the pair says nothing about the defect — the certificate column is empty
  for it. Repair search still finds a repair for the broken side, because it repairs
  against the invariant, not against whatever the author meant by "correct".
* `railroad-crossing` is what the rules became after that. Now the **broken** model
  certifies: the defect stopped being a defect, `repair-search` answers `not_needed`,
  and there is nothing left to demonstrate. That row never reached the earlier
  table.

Both variants are kept as they are, marked as a discarded variant and its
replacement. This is what "the table wins" looks like when the table has nothing to
show.

## What did not fit

* **Hyman's algorithm** (CACM 9(1), 1966) was dropped before any run. Its fault is
  a race between reading the other process's flag and writing `turn`; steps here
  are atomic per process, so every six-bit encoding of it is safe for the wrong
  reason. No command refused it — it was never submitted, and that is the honest
  statement: this is an analysis, not a measurement.
* **The four systems from the earlier Gemini session** were not in this repository
  or in any handoff when the first eight rows were written, so nothing was frozen
  and nothing was invented in their place. The owner has since supplied them from
  the session log and they are the five rows above. The plain `bounded-buffer` row
  remains a separate encoding written for this zoo; `bounded-buffer-gemini` is the
  one from the log.
* One command did refuse during the work: `machine-create` rejected state names in
  an order of my choosing —
  `InvalidRecord: inputs must be at most eight sorted unique WPL names`. The
  harness sorts names before building a machine; the system files keep the order
  that reads best.
