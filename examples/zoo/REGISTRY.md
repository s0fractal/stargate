# Pre-registration

Written and committed **before** the harness was run for the first time. Nothing in
this file is edited afterwards: when a measurement disagrees with the expectation,
the disagreement is reported in `README.md` and in the pull request, and the
expectation below stays as it was written.

Committed at: branch `feat/zoo`, parent `16eb087` (build 41).

## What is fixed for every system

* Two models per system that differ **only** in `next`; `state`, `events`,
  `initial`, `invariant` and `goals` are shared.
* `correct` is expected to produce `verified_certificate`, `broken` is expected to
  produce `verified_refutation`, both through `evidence.produce`.
* Repair search runs on the broken model with both strategies (`one-edit`,
  `trace`) and the quota recorded in the system file (`max_candidates`).
* "attempts" below means the `attempted` field of the search report: candidates
  the search actually handed to the checker.

## Per system

| system | planted defect | broken evidence | correct evidence | one-edit | trace |
| --- | --- | --- | --- | --- | --- |
| token-ring-natural | node keeps the token and takes the next one | verified_refutation | verified_certificate | neighborhood_exhausted at 37 | neighborhood_exhausted at 39 |
| token-ring-onestep | the same ring, fault placed one edit away | verified_refutation | verified_certificate | found at 12 | found at 15 |
| philosophers (honest) | none — deadlock `h0 && h1` is reachable | — | **verified_certificate** (the limit: today no command refuses this model) | — | — |
| philosophers (broken) | P1 stops checking P0 | verified_refutation | verified_certificate | measure | measure |
| peterson | each process claims the turn for itself | verified_refutation | verified_certificate | measure | measure |
| interlock | disarms while the door is open | verified_refutation | verified_certificate | measure | measure |
| readers-writer | writer stops checking the reader | verified_refutation | verified_certificate | measure | measure |
| alternating-bit | sender stamps the complement of its own bit | verified_refutation | verified_certificate | measure | measure |
| bounded-buffer | producer stops checking the bound | verified_refutation | verified_certificate | measure | measure |

"measure" means: no number was predicted. The measured value is a result, not a
target; it is written into `results.json` and the README table by the harness.

## The claim under test

`README.md` of the repository says, about the trace strategy of build 41, that it
reaches a repair in fewer candidates. That claim was measured on Peterson, the
system the strategy was written against. The expectation registered here is that
across the zoo the trace strategy is **not** uniformly better: on the two token
rings it is expected to need 2–3 more attempts than `one-edit`. If the measured
table contradicts this, the table wins and this paragraph stays as written.

## Inputs that were asked for and are not here

* **Four systems from an earlier Gemini session** (lift doors, traffic lights,
  bounded buffer, railroad crossing). The task asks for their rules to be frozen
  as they are. They are not in this repository, not in any handoff file and not in
  the pull request history, so there are no rules to freeze. `bounded-buffer.json`
  in this zoo is a **new** encoding written here, not that one; the other three are
  absent. Nothing was invented in their place.
* **Hyman's incorrect algorithm** (CACM 9(1), 1966) was considered as a literature
  system and dropped before any run: its fault is a race between reading the other
  process's flag and writing `turn`, and `boolean-machine-1` steps are atomic per
  process, so every encoding that fits in six bits is safe for the wrong reason.
  No command refused it — it was never submitted. This is an expressiveness note,
  not a measurement.
