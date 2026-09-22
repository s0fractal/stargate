# Pre-registration: the independent projection verifier (PR-03)

Written before the verifier exists. Not edited after the run.

## The claim

A `projection-1` table can be checked against a **verified machine certificate**
without trusting the projector: every row's `next` is recomputed from the model the
certificate carries, and only a complete, row-by-row match is `conforms`.

## Trust domain

The verifier is its own closure with its own identity:

    PROJECTION_SOURCES = certificate.SOURCES + ('projection_check.py',)
    ProjectionCheckerID = identity({name: text for name in PROJECTION_SOURCES})

It includes the five-file machine checker closure because it calls
`certificate.verify`; it contains no compiler, SKI, kernel, lab, machine, search,
projector (`projection.py`), CLI, Git or renderer. The machine checker is not
changed: `vertical_baseline --check` stays `established`. Because the machine
checker is inside it, a future machine-checker change also changes
ProjectionCheckerID — intended.

`projection.py` and `projection_check.py` each have their own structural reader.
The verifier does not import the producer's; the tests hold the two to the same
accept/refuse answers on every registered case.

## Command

```sh
sg projection-check PROJECTION CERTIFICATE --expect-model MODEL_ID \
   --expect-checker MACHINE_CHECKER_ID --expect-projection-checker PROJECTION_CHECKER_ID
sg projection-checker        # prints this installation's ProjectionCheckerID
```

All three identities are the recipient's. A projection carries no checker field, so
it cannot choose its verifier; a certificate that names another machine checker is
`checker_unavailable`.

## Algorithm, in this order

1. Structural inspection of the projection (same rules as PR-02). Failure: invalid/2.
2. Local ProjectionCheckerID ≠ expected: `projection_checker_unavailable`/3.
3. Projection `model` ≠ `--expect-model`: invalid/2.
4. `certificate.verify(certificate, expected_model, expected_checker)` at the default
   quota. Invalid certificate or a certificate for another model: invalid/2.
   `checker_unavailable`/`incomplete`: 3. `checker_error`: 1. Only
   `verified_certificate` continues.
5. Projection `state`/`events` must equal the certified model's: otherwise invalid/2.
6. For every row, in order, recompute every `next` bit with the model's rules
   through `boolean.program`/`boolean.evaluate`; `checked_rows` counts each row once.
   The first disagreement stops with `mismatch`/4 and a witness
   `{state, event, expected, actual}`.
7. All rows equal: `conforms`/0 with `model`, `projection` (its SHA-256),
   `checked_rows` = 2^(|state|+|events|).

## Size ceilings, closed over the schema

* Projection bytes: the verifier refuses nothing the producer can emit. Its ceiling
  is derived inside its own closure from the rule limit that `boolean.program` and
  `certificate._model` both enforce (8192 bytes; every rule declares every name;
  shortest declaration `fact N:bool ` = len + 11, shortest tail `check!b` = 7), so
  it must equal `projection.MAX_PROJECTION` = 4 193 586.
* Certificate bytes: whatever the frozen build-42 checker accepts (1 MiB). The
  verifier adds no certificate limit of its own. It follows that a valid machine
  whose certificate would exceed 1 MiB cannot be projection-checked; that is a
  build-42 limit this vertical may not change (G4), recorded here, not fixed.
* Work: at most 256 rows × 6 bits of Boolean evaluation after the certificate's own
  quota; no separate step quota is introduced.

## Expected outcomes

1. Two-bit machine from PR-02, its certificate and its projection: `conforms`/0,
   `checked_rows` 8.
2. The same projection with row 4's `a` flipped: `mismatch`/4, witness state
   `a=T,b=F`, event `e=F`, expected `{a:T,b:T}`, actual `{a:F,b:T}`; an independent
   Python oracle in the test reproduces `expected`.
3. Missing row, duplicate row: invalid/2 before any certificate work.
4. Projection whose `model` is another ModelID: invalid/2.
5. Valid projection, valid certificate of **another** model: invalid/2.
6. Wrong `--expect-projection-checker`: 3. Certificate naming another machine checker: 3.
7. Every zoo system with a certificate: its projection `conforms`; each one-cell
   flip at a pseudo-random row: `mismatch`.
8. The PR-02 corner machine has no certificate — its invariant `!b` fails one step
   from the initial state — so the corner is taken with the same `next` rules (each
   still exactly 8 192 bytes) and a tautological invariant. The invariant is not in
   a projection, so the projection keeps the corner's size class. Expected: a
   certificate, and `conforms` on a projection within `MAX_PROJECTION`.
9. Run from a directory holding only the six closure files, under `python -I -S`,
   the verifier gives the same report, and none of `compiler`, `kernel`, `lab`,
   `machine`, `projection`, `search`, `cli` is imported.
10. `projection_check.MAX_PROJECTION == projection.MAX_PROJECTION`; the producer's and
    the verifier's structural readers agree on every registered case.
11. Machine checker, lab runtime, experiment controller and launcher unchanged.

## Control (G8)

With exactly the row comparison removed, the flipped-cell projection of outcome 2
is `conforms`. The real verifier returns `mismatch`.

## What this will not establish

That the certificate's model is the model anyone intended; that a runtime executing
the table behaves like it (PR-05); that the rows outside the certificate's inductive
set matter to safety — they are compared because the table is the transition
function, not because the certificate speaks about them. Conformance is to the
model's rules; the certificate is what makes that model a checked one.
