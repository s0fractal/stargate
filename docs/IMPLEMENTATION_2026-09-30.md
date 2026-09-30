# Contract strategy: implementation evidence

User authorized P0–P3 on 2026-09-30, selecting Sokol-Core with an explicit operator-influence
qualification. Worktrees preserve the original Stargate main and Sokol feature checkout.
The checker, compiler, proof formats, original guarded artifacts, anchors and consumer
runtime pins are unchanged. Registrations precede implementations and measured results.

## Completed locally

- P0: ownership-declared MCP roots, executable README, current adoption/status page,
  live-goal semantic regression and worksheet for another integration.
- P1: actual Warrant adapter, unchanged pinned table/runtime, six scenarios and three
  deliberately wrong adapters; all discriminated. Sealing is an effect spy, not signing.
- P2: actual Rust outbox defect, regression-first repair, eight native tests, eighteen
  real socket observations and four semantic mutants. Both new regressions fail when
  added to the original module and pass on the repair. Sokol registration/repair commits
  `a5ee3df` / `a0614ba`. Source code and fixture hashes are in the result JSON.
- P3: one-edit exhausts after 11 candidates; safety synthesis checks one candidate and
  obtains verified_repair. Two owned rules change on one row (Hamming 2); world untouched.
  It agrees with the declared repair on all reachable rows, differs on 5/32 full-domain
  rows. No independent agent comparison or labor-saving claim.
- Review enforcement: live GitHub ruleset 23849266 read back after update: one approving
  review required, dismiss stale approvals true, existing strict checks/App identity and
  empty bypass list preserved. This changes repository policy; it does not certify code.

## Validation

Local full Stargate suite: 610 tests, Python 3.14.7, passed (pre-existing socket
ResourceWarnings still appear). Architecture, anchors, vertical baseline, stronger-root
README walkthrough, native Rust checks, formatting and Sokol retired-surface/claim checks
passed. Existing vertical and installation regressions are also required by Python CI.
The consumer workflow replays exact source pins. Sokol's own shadow job checks its live
checkout with a pinned Stargate harness; a source/hash change is reported, not silently
called the old experiment. A compiler or process error fails without counting a mutant.

## Review, merge and non-claims

This document records implementation-author tests and adversarial controls, NOT an
independent review. PR acceptance/merge and exact-head CI must be checked live; these
local results do not claim either. No production deployment, release, native-NIC
qualification, external demand, independent maintainer adoption, arbitrary scheduling
proof or model/code equivalence was established. The pilot does not replace Sokol's
existing deployment decision process. No message to external maintainers was sent.

Next evidence is a reviewer exercising the cases without implementation-author help and
a consumer choosing continued use. Larger domains/solvers remain deferred pending a
registered case that requires them.

Consumer-side review found the first strict parser omitted five current retraction ACKs.
Sokol amendment `a0614ba` adds exact recognition and an eighth native test; eighteen
observations now run. The original thirteen-case results.json is retained; results-v2.json
is the final measurement. The model/checker are unchanged.
