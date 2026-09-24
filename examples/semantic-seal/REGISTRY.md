# Pre-registration: a semantic counterexample seals re-admission (third live vertical)

Written at stargate `main` `4d236ab` before any model of it is created or checked, and
before the black-heart fix exists. Not edited after the run; what is learned goes to
`RESULTS.md`.

## The target, and the live reproducer that came first

black-heart's scoped re-admission registry (`scoped_admission.py`) keeps refusals of a
candidate under an evaluator and a requirement. SCOPED_ADMISSION-0.1 SA2: a
`RESOURCE_LIMIT` refusal may be retested with a strictly larger budget; a
`SEMANTIC_COUNTEREXAMPLE` is unconditional with respect to budget, and the module's own
refusal text says it is "permanent under unchanged requirement".

**Source identity (buggy).** black-heart `origin/main`
`3893fad4bc1cbfa6152a5cecd967c73471a38fde`, `scoped_admission.py` blob
`78b5ac6b80e9ce37a34e108dc96f2e939d00afa9` (sha256 `db38200b…11362`).

**Live reproducer, run before this registration** (`reproducer_3893fad.py`, refuses any
other file): register a `SEMANTIC_COUNTEREXAMPLE` for `(candidate, evaluator,
requirement)` — a larger budget on it is `BLOCKED_BY_EXISTING_EVIDENCE`; register a
`RESOURCE_LIMIT` refusal for the **same triple**; a retest through it runs the executor,
succeeds, and `grant_scoped_admission` admits the candidate. `assess_request` only reads
the one refusal the request names.

The same script reproduces a second, separate finding (**D**, not modelled here): an
older `export_state()` passed to `import_state()` rolls the spent retest quota and the run
counter back (5 executor calls under a quota of 3, admission on the fifth, recorded
`executed_runs_count = 3`). D needs its own contract decision (durable reservation versus
a narrower SA4) and its own PR.

**Fixed correspondence.** The black-heart PR "semantic dominance in `assess_request`"
(PR-A), narrow: a request is blocked when any registered refusal of the same
`(candidate, evaluator, requirement)` is a `SEMANTIC_COUNTEREXAMPLE`, whatever its
`inputs_digest`; both records are kept (SA1). The exact head is pinned in `RESULTS.md`
after its review; if it moves, the pin moves with a note.

**No claim that the model is the code.** The code layer is black-heart's own red
regressions in PR-A and this reproducer; they are cited, not run by this vertical.

## The model: one triple, three state bits, two event bits

| bit | meaning |
| --- | --- |
| `admitted` | a scoped admission exists for the triple |
| `resource` | monitor: a `RESOURCE_LIMIT` refusal is registered for the triple |
| `semantic` | monitor: a `SEMANTIC_COUNTEREXAMPLE` is registered for the triple |

| event | meaning |
| --- | --- |
| `resource_event` | a `RESOURCE_LIMIT` refusal for the triple is registered |
| `retest_success` | a retest through a resource refusal succeeds and is granted |

Initial states: `I0` all false; `I1` `semantic` only. The semantic fact exists before
the run or never: black-heart's spec does not say a later counterexample revokes an
admission already granted, so the model proves only that an **established** seal holds.

    invariant: !semantic || !admitted

**Monitor rules (repair-authority boundary, identical in every variant),**
`world = [resource, semantic]`:

    semantic' = semantic
    resource' = resource || resource_event

### Variant `buggy` — black-heart 3893fad

    admitted' = admitted || (retest_success && resource)

### Variant `fixed` — the PR-A contract

    admitted' = admitted || (retest_success && resource && !semantic)

goals (existential): the resource-only path still admits,
`{admitted, resource, !semantic}`; semantic history coexists with a resource record and
stays blocked, `{!admitted, resource, semantic}`. No `live_goals`.

## Registered predictions (derived by hand; checked independently by the owner's reviewer)

1. `buggy`: `verified_refutation`, unsafe, **2 steps from `I1`**: `resource_event`, then
   `retest_success` (one step cannot: `admitted'` reads the old `resource`).
2. `fixed`: `verified_certificate`, **5** reachable states (`000`, `010`, `110` from `I0`;
   `001`, `011` from `I1`, in `admitted resource semantic` order), both goals reachable.
3. `fixed` as a hand repair of `buggy`: `verified_repair`.
4. `repair-search` one-edit and trace on `buggy`: **no verified repair**. `admitted` is
   the only owned rule and does not read `semantic`; the local grammar never adds a fact,
   and any rule over `(admitted, resource, events)` that admits from a state
   `(0, r, 0)` admits from its twin `(0, r, 1)`, reachable from `I1` — unsafe — or never
   admits, losing the first goal. Status and attempt counts recorded, not predicted.
5. `repair-search --strategy synth` on `buggy`: realizable, **`W*` = 6**, changed rows
   **2** (state `011` under `retest_success`, with either `resource_event`), changed
   owned rules **`admitted`** only, Hamming **2**, **`verified_repair`**; world rule
   bytes unchanged. Emitted expressions not predicted; fit within the compiler's limits
   and `max_atp` not predicted.

## Controls

| control | change | predicted |
| --- | --- | --- |
| C1 no seal in the world | `buggy` with `world` undeclared | `synth`: `not_applicable` |
| C2 forget the seal | `semantic' = false` on `buggy` | as a model: `verified_refutation` of kind `unreachable_goal` for `{!admitted, resource, semantic}` — safety holds only because the fact is erased (`semantic` is true only in `I1`, where `resource` is false); as a repair of `buggy`: not packable, the candidate does not certify — the blocked goal, not the world boundary, is what refuses it here |
| C3 guard on the wrong bit | `fixed` with `!semantic` replaced by `!resource` | safe, never admits: `verified_refutation` of kind `unreachable_goal` for `{admitted, resource, !semantic}` |

C2 is why the second goal exists: without it, erasing the seal would certify.

## Limits

One triple; `inputs_digest` is not a scope (a counterexample under other inputs still
blocks — a black-heart regression, not a model bit). Quota, replay cache, timeouts and
import (D) are not modelled. Admission revocation by a later counterexample is out of
scope by construction (`I1`).
