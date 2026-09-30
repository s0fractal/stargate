# Bounded queue extension registration — 2026-09-30

Registered before implementation/measurement after Stargate #90 and Sokol #96.
Production source baseline: Sokol `5ffaf0854158f4674a470378279a4dd4d237f9fb`.

Scope: capacity two, two payload classes with distinct occurrence identities. A new
five-state-bit/two-event-bit reference model fits the existing checker limits; no checker,
production delivery or historical artifact changes. Events: enqueue A, enqueue B,
terminal acknowledgement, stutter. The model records FIFO payload order and whether
any overflow occurred. It certifies representation safety, not arbitrary Rust correctness.
An independent list specification checks all fourteen valid states and four events.
Exact loss counts and occurrence identity are additional executable oracle obligations.

Planned real-socket cases: bounded FIFO flush including max=0; partial batch success then
unknown ACK, enqueue during backoff, retry; one overflow; repeated overflow. Every
operation checks pending/loss counts, returned identities and order, error status and
wire requests. Final drains expose retained item order. Conservation is
pushed = pending + cumulative terminal outcomes + lost. Timeouts/compiler/process
failures are errors, not killed mutants. No arbitrary capacities, concurrency, crash
recovery or durable delivery is claimed. Operator influence remains explicit.

Negative source controls: newest-item eviction, missing loss accounting, reverse insertion,
wrong-side completion removal, off-by-one flush bound, discard on transport failure.
Acceptance requires a concrete semantic mismatch for each and byte-stable replay;
original one-step and retry trace results remain frozen.
