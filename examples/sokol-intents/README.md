# A retained intent drives the real Sokol sender

The [local journal](../../docs/RETAINED_INTENTS.md) now drives a compiled Sokol
Outbox through `integration/sokol_intents.py`. One committed reservation starts one
fresh Rust process, enqueues the retained canonical request and calls `flush(1)`
once. An explicit later invocation may spend another slot; no retry daemon runs.

```sh
python integration/sokol_intents.py --sokol-root /path/to/sokol-core \
  --expect-results examples/sokol-intents/results.json
```

The private source must be supplied explicitly. The adapter copies and compiles
`orchestrator/src/delivery.rs`, records its digest and the driver/adapter/dependency
digests, and opens only temporary Unix sockets and a toy SQLite database. It does
not modify or connect to a production Sokol node. Public unit tests use a fake
transport and do not count as execution of Sokol.

## Observed process boundaries

Each case starts a Python sender process and forcibly exits it with `os._exit(73)`
at a selected boundary. A different Python process resumes from the database:

| Case | Interruption / response | Observation after resume |
| --- | --- | --- |
| `before` | After debit, before Rust launch; two slots | Second slot sends; one receipt |
| `exhausted` | After debit, before launch; one slot | No delivery; budget exhausted |
| `lost` | After Rust finishes; effect committed, reply lost | Existing receipt completes; no resend; one slot |
| `incomplete` | First verification incomplete, then sender exits | Second slot sends the same request; one effect |
| `false_ack` | Incomplete verification but fake `OK applied` | No receipt, no completion; exhausted budget |
| `cancelled` | Receiver cancels after delivery, before effect | Revision fence refuses effect; no retry |

The sender ignores child stdout for admission. Exit status, launch errors and timeouts
are transport observations; only the exact local receipt completes an intent. A
receiver may commit after a timeout, so absence of a receipt retains uncertainty.
The public suite also tests cancellation between reservation and delivery, exact
wire binding and a semantic mutant that substitutes completion for receipt lookup.

`results.json` is a frozen local observation, not a certificate. It was produced
with Sokol source digest `4becf82d8db9194d48be14d14684e3ea9ffd8ff598bc68205553a1327d4b7f0f`.
The existing public CI cannot fetch the private source; it runs the public adapter
regressions, not these six Rust/socket cases. The older Sokol receipt results remain
unchanged.

## Trust and limits

Sender and receiver share one trusted database incarnation. The receiver selects
payload bytes from the operator-enrolled intent; the wire cannot choose a payload,
database or a different revision. This is a local experiment, not an authenticated
remote protocol. The socket and database are trusted; direct actuator calls and
arbitrary programs are outside the reservation API. The operator must select the
compiled one-flush driver and endpoint. A reservation limits driver launches, not
CPU, bytes, wall time or actions by a malicious binary.

Sokol's in-memory queue is reconstructed for each reserved attempt; it has not become
a persistent queue. Reconstructing it also resets its in-memory backoff. Callers own
retry timing; there is no automatic loop or distributed receipt lookup. Cancellation
remains the journal's coarse resource-revision fence. This does not add arbitrary
tools, production node admission, power-loss guarantees or new agent permissions.
