# From a joint proof to one local state change

`integration/shared_action_store.py` extends the read-only shared-action experiment
with a toy SQLite actuator. Its only effect is changing one database row representing
`held` and `ack`. It does not delete a file, release production storage or call a remote
service. The command creates a temporary database and removes it on completion.

The operator selects the database and installs world/candidate/contract/checker anchors
in its trusted `selection` column. The submitted payload contains specification and
proof bytes, not permission to change those selections or choose another database.
This is an integration experiment, not a new public API or production admission scheme.

## Check, then compare-and-swap

The actuator performs these steps:

1. Read the state, selected anchors and revision in one SQLite row snapshot. Require
   the caller's expected revision; copy payload mappings and require immutable bytes.
2. Recheck both contracts using the existing shared-action checker against the stored
   selections. Any refusal, error or incomplete result prevents an update.
3. Require the current state to belong to **both** certificates' inductive state sets.
   A valid global policy certificate alone does not locate the live state in its proof.
4. Generate the candidate's transition table and check it against the custodian's
   certificate with the separately pinned projection checker. Both contracts share
   the same transition rules. A projector's `projected` label is insufficient.
5. Evaluate the release request (`a=false`, `b=true`) using the existing table runtime.
   If no held resource would be released, return `no_release` without a write.
6. Begin a short SQLite write transaction and execute
   `UPDATE ... WHERE revision = expected_revision`, writing the computed successor
   and advancing the revision. Zero updated rows means `stale_revision`. With an
   operation identifier, insert its receipt in the same transaction. Only a
   successful commit reports `applied`.

The projection check is row-by-row against the verified model. The SQL binding and
revision protocol are exercised with ordinary integration tests, not proved by the
Boolean model. No revision number or database identity is compressed into a Boolean.

Every supported operator change to state or selections advances the revision. A SQL
trigger rejects ordinary updates that fail to advance it exactly once. Returning the
fields to their previous values still changes the revision (the ABA case). Revision
storage is constrained to nonnegative SQLite integers; it must not wrap or be reset.
The caller must use an idle autocommit connection, so returning `applied` does not mean
merely placing a change in an uncommitted caller transaction.

## Observed cases and refusal controls

| Case | Result |
| --- | --- |
| Both policies verify, acknowledgement absent | `no_release`; state unchanged |
| Acknowledged resource and both complete proofs | One committed release |
| Zero joint-check budget | `not_admitted`; state unchanged |
| Replay with the old revision | `stale_revision`; no second effect |
| New handoff begins after verification but before update | `stale_revision`; new handoff preserved |
| Requirements change during verification | `stale_revision`; new selections preserved |
| State changes and returns to identical values | `stale_revision` |
| Two connections verify the same revision concurrently | Exactly one update; the other is stale |
| Validly shaped generated table releases before acknowledgement | Projection mismatch; no update |
| Live state outside the certificates | `state_not_certified` |
| SQL refuses the write | Exception; no successful application report |

Tests synchronize two real SQLite connections after verification to exercise the
competing updates. Scheduled mutations inject changes during the check/update gap.
Refutation and incomplete controls consume actual checker results, and the projector
control alters an actual table row while preserving its success label.

From an installed checkout:

```sh
python integration/shared_action_store.py
```

The JSON report is an observation of the temporary experiment. The command exits
nonzero on unexpected outcomes. The required `shadow` job runs it, and the Python
matrix tests the additional concurrency and refusal cases.

## Limits

The database, host, installed runtime, schema and operator mutation path are trusted.
Selections stored there are authority because the operator controls that store, not
because a hash or proof grants authority. Acknowledgement authenticity is still an
external obligation. Direct schema changes, row deletion/recreation, backup restoration
or replacing the database can invalidate revision uniqueness; these are excluded.
Revisions are local to this database incarnation, not global operation identities.

Atomicity covers this SQLite state update and its optional receipt only. It does not cover a later file deletion,
network request, Git push or any other external effect. Without an operation identifier, an old-revision retry remains ambiguous. With
an identifier, the recovery path below distinguishes the recorded operation from
another intervening change. This is not a distributed exactly-once protocol or
a power-loss durability study.

Progress remains available rather than inevitable; the system does not provide
fair scheduling, incentives, identity federation or automatic permission expansion.
The joint proof budget is per verification, not a wall-clock limit; the separate
projection checker uses its existing bounded certificate-check defaults.


## Recover a lost response

An agent may supply `operation='agent.release.1'` to `release`. The identifier is
local to the operator-selected database incarnation. The receipt binds the action,
expected revision and SHA-256 of every submitted world/candidate/contract/proof
byte string. Verification budget is not part of a committed request's identity.

Before new verification and again under the commit lock, the actuator looks up
that identifier. Identical input returns `already_applied`, with `applied=false`
and the original committed observation in `receipt`. Different input or revision
returns `operation_conflict`. Neither path changes state. A receipt is historical:
it can be read after requirements change and does not grant permission for a new
operation. Current state must not be inferred from its historical successor.

A new operation still passes every existing proof, projection and live-state gate.
Its state update and receipt insert commit together. An insert failure rolls both
back. An incomplete check writes neither and may be retried within the original
selected revision. Two simultaneous identical operations produce one committed
effect and one matching historical receipt. Different operation identifiers still
compete through the revision check.

The runnable experiment now closes and reopens the database between application
and retry. Regression tests additionally terminate a real child process immediately
before and after commit. Before commit, recovery finds neither effect nor receipt;
after commit it finds both. A control denying receipt insertion proves that a
receipt-storage error cannot leave a committed effect without its receipt.

This is the local part of an agent/membrane loop: propose, verify, apply, reconcile.
Sokol's delivery outbox already retains unknown/incomplete acknowledgements and
retries, but its `Applied`, `Pending`, `Recorded` and `Duplicate` outcomes remain
distinct and do not establish durable storage. The [Sokol receipt experiment](../sokol-receipts/README.md) now connects the
actual outbox to this SQLite receiver and exercises those distinctions. This
fixture is not a production node endpoint. A production adapter still needs
retained sender intent, authentication and explicit cancellation/resource limits.

Receipts are kept indefinitely; ordinary SQL updates/deletes are refused. There
is no receipt garbage collection, cross-database recovery, schema migration or
production storage quota in this experiment. Database replacement, rollback to a
backup, direct schema changes and privileged tampering remain outside its contract.
The process-exit tests assume a functioning local SQLite/filesystem stack.
