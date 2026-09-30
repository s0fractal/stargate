# Bounded retry trace results — 2026-09-30

Registration: [SOKOL_TRACE_REGISTRY.md](../../docs/SOKOL_TRACE_REGISTRY.md), commit `d024e40`.
Source: Sokol #95 merged as `b94f090c033e84338bf3fde87556a8f7b263b91c`.
The production delivery file is unchanged from the previous results-v2 experiment.
[trace-results.json](trace-results.json) records source/probe SHA-256, model identities,
all observations and semantic disagreement witnesses. The JSON was reproduced twice
byte-for-byte with the final probe; the original results-v2.json also still reproduced.

Five traces / fifteen prefixes conform to the same certified model. All four source
mutants are rejected through observable disagreement, not compiler failures. The oracle
regression additionally rejects intermediate queue loss, duplicate cumulative completion,
wrong returned identity and an incomplete trace. No checker/admission source changed.

The probe follows one subject through actual Unix sockets and production retry delays.
A terminal ACK settles delivery responsibility, not application success or durable storage.
One-step coverage still supplies the wider ACK vocabulary; these traces extend temporal
coverage for selected outcomes. They do not establish full queue refinement, concurrency,
crash recovery, deadline guarantees, independent adoption or deployment qualification.

Sokol #95's final CI was green on x86_64 and arm64. An earlier run failed the CrowdSec
smoke assertions restricted to TTL 299/300. Added diagnostics on the successful run
showed reported duration 4m58.398547965s rounded to 299s and the same enforced TTL.
The earlier failing value was not retained, so its precise cause remains unconfirmed;
no test assertion was weakened to get a green run.
