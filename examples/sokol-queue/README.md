# Bounded Sokol queue correspondence

Registered in [SOKOL_QUEUE_REGISTRY.md](../../docs/SOKOL_QUEUE_REGISTRY.md), commit
`86b239d`, before implementation or measurement. The production delivery source is from
Sokol main `5ffaf0854158f4674a470378279a4dd4d237f9fb` (merged #95/#96).
No production code, checker, old model or historical results are changed.

## What is certified and what is tested

[model.json](model.json) is a new capacity-two reference model using five state bits and
two event bits within the existing checker limits. `front`/`rear` record occupancy,
`front_b`/`rear_b` distinguish payload classes A and B, and `dropped` latches whether any
overflow occurred. The invariant prevents a rear without a front or a payload in an
empty slot. There are no reachability/liveness goals and no eventual-delivery claim.

| x | y | Reference event |
|---|---|---|
| false | false | enqueue A |
| false | true | enqueue B |
| true | false | terminal ACK removes the front, or stutters when empty |
| true | true | stutter, including an unrecognized reply |

The certificate proves representation safety. Separately, an ordinary list specification
checks every event from every valid encoding: 14 states × 4 events = 56 transitions.
This checks FIFO and drop-oldest semantics of the model, beyond its structural invariant.
A regression injects a structurally valid wrong-FIFO transition and requires rejection.

The real Rust Outbox is compiled from an authorized private checkout and called through
its public API over Unix sockets. Four scenarios cover 24 operation prefixes:

- FIFO with `flush(0)`, `flush(1)`, a new arrival and final drains.
- A batch whose first item succeeds and second receives an unknown ACK; arrival during
  backoff, reconnect, duplicate ACK for the retained item, then completion of the newcomer.
- One overflow, which must discard the oldest item and count one loss.
- Repeated overflow, partial flush and final drain, with exact cumulative loss accounting.

Every prefix compares pending/loss counts, returned occurrence IDs in order, error status
and cumulative wire requests. A final drain makes retained order observable. Exact loss
counts and distinct IDs A1/B1/A2/B2 are oracle obligations outside the five-bit abstraction.
The reference enforces `pushed = pending + cumulative completions + lost`.

## Reproduction and negative controls

Install Stargate, ensure Rust is available, and use an authorized Sokol checkout:

```sh
python integration/sokol_queue.py --sokol-root /path/to/sokol-core \
  --expect-results examples/sokol-queue/results.json
```

[results.json](results.json) records the source/probe hashes, model/checker identities,
all prefixes and six semantic-mutation witnesses. Two final runs reproduced its bytes;
the earlier results-v2.json and trace-results.json also still reproduced unchanged.
No private production source is included in this repository.

All six wrong Rust variants produce observable mismatches: evict newest on overflow,
omit loss accounting, reverse insertion, remove newest after ACK, allow an extra flush
item, and discard on a transport error. Compile/process errors fail the harness and are
not counted as mutation kills. Additional oracle regressions reject wrong occurrence
identity, unexpected sends during `flush(0)`, wrong error status and incomplete traces.

This is finite evidence for capacity two and these schedules, not a proof of arbitrary
capacities, concurrent callers, timer bounds, process restart, storage durability or
whole-program refinement. A terminal ACK retires delivery responsibility, not necessarily
application work. No new defect in the current production source was found. The operator
influences both repositories; this is not evidence of independent demand or deployment.
