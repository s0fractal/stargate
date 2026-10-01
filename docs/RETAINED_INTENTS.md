# Retained intent for a local agent task

`integration/agent_intents.py` adds an operator-created journal to the existing
[toy SQLite actuator](../examples/shared-action/ACTUATOR.md). It retains exact
world/candidate/contract/proof bytes, operation ID, expected revision and a finite
attempt limit. A later process needs the database and installed checker, rather
than the previous process's Python objects or prose report.

```sh
python integration/agent_intents.py
```

The command uses a temporary database and demonstrates recovery of a committed
operation whose result was not retained by the sender. Tests also kill actual
child processes after reservation, with and without a subsequent committed effect.

## Lifecycle

1. The operator enrolls a new identifier, payload, revision and limit of 1–1000
   attempts. Enrolment grants no new authority; normal model/projection checks
   and the operator-selected resource requirements still govern every effect.
   Re-enrolling an existing identifier fails and cannot reset its budget.
2. Before each attempt, inspect the committed receipt for the exact request.
   A matching receipt completes the intent even if its budget is exhausted;
   another request's receipt marks a conflict. Reconciliation performs no effect.
3. With no receipt and a pending intent, reserve one attempt in a committed
   transaction. Concurrent callers share the same finite counter. Only after
   committing the debit may this attempt invoke the actuator.
4. Check and execute using the retained inputs. An incomplete check, local error
   or process loss does not refund the reserved attempt. A later session first
   reconciles again, then may reserve another slot if any remains.
5. After the limit, report `budget_exhausted` without another attempt. Missing
   receipt means uncertainty, not proof that no effect could still commit from
   an already reserved worker. Read-only reconciliation remains available.

`wire(intent)` emits the existing canonical `{operation, revision}` request used
by the Sokol-receipt experiment. This journal's current `attempt()` invokes the
local actuator directly. It is not yet a persistent replacement for Sokol's
in-memory Outbox, and it does not schedule or repeatedly run tasks unattended.
The [Sokol sender adapter](../examples/sokol-intents/README.md) uses the same
reservation/reconciliation operations around an actual one-flush Outbox process.

## Cancellation and races

Cancellation and receipt reconciliation share one SQLite write transaction. If
an effect already committed, cancellation reports `completed`, preserving the
receipt; it does not claim an undo. Otherwise it marks the intent `cancelled`.
When the resource still has the selected revision, cancellation also advances
that revision without changing its state. A prepared or currently verifying
worker then fails the actuator's existing revision comparison at commit.

When a newer resource generation already exists, cancellation does not advance
or modify it. In this one-resource experiment, advancing the current revision
invalidates all prepared releases of that same generation, not only one worker.
This is deliberately coarse cancellation, not a distributed per-message revoke.

A cancellation write failure rolls back both the journal update and revision
advance. Ordinary updates cannot change the intent binding, increase its limit,
refund attempts or reopen a terminal status. The trusted database owner can still
change schema or bypass this API; the journal is not a sandbox against that owner.

## Evidence and limits

Regression cases cover process loss before/after the effect, budget retention,
six simultaneous reservations for two slots, incomplete checks, conflicting
receipts, cancellation before/during/after verification, newer generations and
storage refusal. Semantic controls detect omitting the cancellation revision
fence and omitting the persisted attempt debit. Existing actuator tests retain
receipt atomicity and projection/refusal checks.

The journal and actuator share one trusted local database incarnation. Existing
models and checker identities are unchanged. Integer budgets, process ordering
and database transactions are tested implementation contracts, not properties
proved by the six-bit model. Budget means reserved attempts, not CPU time, bytes,
currency or a guarantee that every reserved slot actually sent a request.

There is no remote cancellation, power-loss guarantee, migration, receipt/intent
retention policy, storage quota or automatic budget renewal. The operator must
select a new intent explicitly when new work or a different revision is warranted.
