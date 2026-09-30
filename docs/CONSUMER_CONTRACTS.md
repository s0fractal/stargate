# Check the boundary between a model and its consumer

A certificate establishes a statement inside a model. The integration must separately
bind real events, subject identity, state and effects to that model. Neither a digest nor
a model certificate establishes that binding. This pilot exercises actual consumer code
and requires deliberate defects in that binding to fail.

## Warrant: the table stays right while the adapter goes wrong

Pinned source: warrant `ac80aeebfba09176e7dbf0b4a4eaaec3ee343b06`. Obtain that ordinary
source checkout, install Stargate, then:

```sh
python integration/warrant_adapter.py --warrant-root /path/to/warrant \
  --expect-results examples/warrant-adapter/results.json
```

The harness checks SHA-256 of the exact adapter and table runtime, calls the real
`run_proxy`, uses its threads and a real local subprocess, and replaces sealing with an
effect spy. Six scenarios: ordinary result, reused id, two distinct ids with reordered
responses, reverse request, id-less call and server EOF. Independently specified expected
effects check which call was sealed or recorded unreturned/unpaired. Cryptographic
sealing, arbitrary thread schedules and all JSON-RPC input forms are not covered.

With the pinned table unchanged, three source mutants must fail: a reverse request
classified as a response, selecting the wrong id, and omitting an unreturned-call effect.
A mutation site that disappears is an error, not a silently skipped control. These are
trace regressions, not a proof of model/code equivalence or new defects in current Warrant.

## Sokol-Core: a different language and a live protocol defect

Source base: `2e82e1111795114cf99cddac0bfa73205d8b5574`; fixed delivery source and probe:
`a0614ba26a94b1ec29a2648faf644caacdc71d63`. With a checkout containing those files and Rust:

```sh
python integration/sokol_delivery.py --sokol-root /path/to/sokol-core \
  --expect-results examples/sokol-delivery/results-v2.json
```

The harness compiles `orchestrator/src/delivery.rs` directly, runs Unix-socket exchanges
through the actual public Outbox API, and compares eighteen observations with Stargate's
certified table. A recognized terminal ACK may retire a signal; an unknown, prefix-lookalike,
truncated or absent ACK must preserve it. `OK pending` retires delivery responsibility,
not the node's application obligation; none of these ACKs certify durable storage.

Four Rust source mutants must be distinguished: consume unknown replies, accept an ERR
prefix-lookalike, accept an unterminated line and pop on a transport error. Compiler or
process failures fail the harness; they are never counted as killed mutants. Production
code gains no Stargate dependency. This is offline/shadow testing, not XDP qualification,
a deployment, a release or a proof of a whole queue, restart persistence or concurrency.

The operator has direct influence on both projects. This demonstrates cross-language
transfer, not independent demand or external maintainer adoption. The GitHub workflow
runs exact pinned consumer sources; updating pins/results is an explicit experiment.

## Contract worksheet for another integration

1. Name the subject and its lifetime (one id, one queue item, one decision round).
2. State the obligation and the externally observable violation.
3. Identify who may establish each fact and which next-rules the repair owns (`world`).
4. Specify event decoding, state selection, effect mapping and reset/restart boundaries.
5. Preserve required outcomes as goals; say whether a path must remain possible or a
   stronger eventual-progress assumption is actually required.
6. Write a code-level reproducer first and record the baseline test behavior.
7. Register positive and negative controls before implementation; include malformed,
   replayed, missing-identity and weaker-record paths where applicable.
8. Report proof, tested correspondence, adopted source and production deployment separately.

Use the existing checker and an adapter harness first. A contract that does not fit is
recorded as a limitation before proposing a larger language or new checker authority.
