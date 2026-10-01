# Actual Sokol delivery, checked local effect, recoverable acknowledgement

This experiment connects Sokol's actual `orchestrator/src/delivery.rs` Outbox to
Stargate's [SQLite actuator](../shared-action/ACTUATOR.md) through a temporary Unix
socket. It does not run Sokol's production node, mutate its policies or release a
real resource. A receiver is configured with an operator-selected toy database,
proof payload and requirements. The wire request carries only an operation ID and
expected revision; it cannot choose a database, proof or permission set.

The original request must survive uncertain delivery unchanged. The receiver checks
and commits the effect plus its receipt before sending `OK applied`. An exact retry
returns `OK duplicate` only after locating the matching committed receipt. Neither
success reply means that the agent has permission to act on a later state.

## Measured boundary

| Case | First attempt | Retry / outcome |
| --- | --- | --- |
| Lost response after commit | Effect and receipt commit; socket closes | Same request, `duplicate`; one effect |
| Partial response after commit | `OK applied` without newline | Retained, reconnects, `duplicate`; one effect |
| Unknown response after commit | `OK unknown` | Retained, reconnects, `duplicate`; one effect |
| Incomplete proof check | No effect, no terminal acknowledgement | Complete check then one applied effect |
| Condition withdrawn before retry | Incomplete first check; operator withdraws `ack`, advancing revision | `refused stale_revision`; no effect or receipt |
| Conflicting ID reuse | Prior operation seeded; same ID submitted at a new revision | `refused operation_conflict`; seeded receipt unchanged |

Each case checks actual queue length, dequeued outcomes, loss count, transport error,
receiver statuses, final database revision/state and receipt count. Every failed
first delivery retains one item, and no item is lost to overflow in these cases.
The two semantic controls must fail by an observed mismatch: removing the queued
request on transport error, and sending `OK applied` for incomplete verification.
A compiler failure or socket infrastructure error does not count as detecting them.

## Reproduce

From an installed Stargate checkout, with Rust and an authorized Sokol checkout:

```sh
python integration/sokol_receipts.py --sokol-root /path/to/sokol-core
```

Missing source/toolchain or any unexpected result fails. The harness copies source
bytes into a temporary build directory before compiling and reports their SHA-256,
plus the driver, adapter and actuator digests. Private source is never committed here.

[results.json](results.json) records an operator-controlled run on 2026-10-01 using
Sokol `bfad6ad22a03ef243753575612c60f36885302fd`. It is an observation, not an admission
credential or independent adoption. Public Python tests execute the receiver and
its refusal controls; they do not execute private Sokol code. Re-running the command
with the corresponding sources produces the observation report; a changed digest
identifies a different observation rather than reproduction of the saved one.

## Limits and next step

The endpoint and local host are trusted. This bounded fixture accepts a canonical
JSON request over Outbox's existing line transport; it is not the production Sokol
SIGNAL grammar or an authenticated general-purpose tool endpoint. No public server
or new runtime authority is introduced. The boolean proof checks the supplied
resource policy, not the Rust transport, SQLite engine or acknowledgement authenticity.

The acknowledgement means a committed local SQLite effect only because this receiver
binds it that way. Sokol's other `Pending` and `Recorded` outcomes are not relabelled
as durable execution. Receipt/state atomicity does not include arbitrary external
effects; database rollback/replacement and power loss remain outside the experiment.

Outbox is still an in-memory bounded queue: sender process loss and capacity overflow
can lose pending work. The next agent-facing step needs retained intent and explicit
cancellation/resource limits; this experiment does not establish autonomous recovery
from every failure or unattended production readiness.
