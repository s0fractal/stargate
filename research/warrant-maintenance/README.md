# Warrant table maintenance comparison

Scope recorded before execution, 2026-10-01. This is a retrospective simplification
check, outside the three-item utility screening and its denominator. It is not a new
bug discovery, a blind comparison, or a productivity experiment.

Compare the existing pinned Warrant table with a handwritten Python transition
function on every Boolean input (16 states × 4 events) and the existing six adapter
scenarios. The author has read the model, table and adapter. Use the unchanged adapter
and effect spy; signing, arbitrary schedules and malformed inputs are outside scope.
Require two deliberately wrong replacements to fail, including one that the six
adapter scenarios miss. No production consumer or checker changes are permitted.

Decision rule: equal transitions plus equal observed effects establish a candidate
simplification for this fixed transition policy only. Count source bytes and physical
lines separately from generated table bytes. These counts are not maintenance effort.
Do not claim a replacement preserves digest refusal, projection parsing, or independently
checked model-to-table provenance. Record those lost properties before recommending
adoption. A mismatch blocks the simplification claim; neither outcome justifies a new
framework. Active labour, token cost and future maintenance cost are not measured.

Source: Warrant master `e4591b2338fc41a398ae9ec6a6d4e4c403df161b`, read from GitHub on
2026-10-01. Its two relevant source files are byte-identical to the existing adapter
pin `ac80aee`. The current source already has no installed Stargate dependency; it
vendors a fixed runtime and embeds a projection.

## Result and decision

[Recorded run](results.json): **64/64 transitions equal**, all six existing actual
adapter scenarios equal, with two mutant controls. The handwritten branch function
was informed by the model; this is equivalence evidence, not independent rediscovery.
The files exported from current master match the older harness hashes exactly.

| Measured source component | Bytes | Physical lines |
| --- | ---: | ---: |
| Vendored generic runtime | 6,017 | 143 |
| Embedded projection assignment | 13,741 | 145 |
| Digest-checking loader | 832 | 12 |
| Candidate function and class | 829 | 17 |

The projection's actual JSON payload is 12,574 bytes; it is included in the assignment
count, not additional to it. The comparison excludes surrounding adapter code, pin
constants, generation/checking tools and tests. Generated data lines and handwritten
logic lines have different maintenance costs. The 0.29-second observation is one local
execution of this comparison, including subprocesses, not a performance benchmark of
either policy implementation. Writing, review, CI and token costs are not measured.

The duplicate-handling mutant changes four rows and fails the duplicate adapter case.
The END-no-reset mutant changes fifteen rows but passes all six adapter cases: the
adapter clears its ID map at EOF regardless of returned state. That is a model-contract
difference, not a demonstrated externally visible production defect. Exhaustive ordinary
Python tests catch it here; a certificate is not necessary to run this enumeration.

**Keep the production consumer unchanged for now; prefer ordinary code for a new
fixed-policy consumer unless portable checked projection provenance is a named need.**
A compact replacement is feasible on this valid-input transition domain. This does not
establish that migrating a working consumer pays for itself. The current consumer also
refuses altered runtime/projection bytes before spawning a server, validates canonical
projection syntax and binds execution to a checked projection. The candidate implements
none of those loader contracts, is not a drop-in `load_table` replacement and has no
certificate. A migration would need an explicit choice about these properties and tests
of that choice, not just the smaller function. Retaining the offline model for policy
review does not require a table interpreter in the production path.

This supports a narrower development direction: model/check small policies when useful;
do not make production table execution the default integration architecture. No new
production bug, labour saving, signing guarantee or independent adoption was measured.
This result does not change the earlier three-case screening's INCONCLUSIVE verdict.

## Reproduce

Obtain only `impl/warrant_mcp.py` and `impl/warrant_mcp_table.py` from the Warrant commit
above (public GitHub source), preserving those paths under a trusted export directory.
The runner refuses source bytes that do not match the existing adapter pins. It executes
that trusted code and creates local child processes. From the Stargate repository root:

```sh
python3 research/warrant-maintenance/compare.py --warrant-root /path/to/export
```

Every run checks equivalence and the expected mutant outcomes. `elapsed_seconds` varies;
other output fields should match the recorded result. Source equality is checked, not
Git ancestry or whether the supplied directory is still current master. The comparison
uses the existing adapter harness, which spies on effects instead of signing them and
sends host requests before server replies; it is not an arbitrary concurrency test.
