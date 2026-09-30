# Sokol delivery: measured results

Registration: Sokol `a5ee3df` (`docs/pilots/STARGATE-REGISTRY.md`) and Stargate
`4329f02`. Model/socket harness committed in Stargate `5d93219` before its first run.
Native repair/probe: Sokol `946b451`. No checker source or admission identity changed.

The original public API retires a queued signal on `OK something else\n`, returns
`Rejected`, and leaves `lost=0`. That is not one of the node's recognized terminal replies.
Code inspection found the issue; the model subsequently refuted the abstraction.

- Current model: `verified_refutation` (an unrecognized reply suffices).
- Declared fixed model: `verified_certificate`; manual packet: `verified_repair`.
- One-edit search: `neighborhood_exhausted`, 11 candidates.
- Safety synthesis: `found`, one candidate, `verified_repair`. Four winning states;
  one changed row; both owned bits (`queued`, `settled`) change; Hamming delta 2.
  The world-owned acknowledgement latch's bytes are preserved.
- Thirteen real Rust/socket observations agree with the certified projection.
- All four registered semantic source mutants are distinguished by the expected witnesses.
- Native tests additionally check unknown reply → retry → `OK duplicate`, no-newline EOF,
  full-queue loss accounting and down-node recovery. The proof remains one signal.

`results.json` records the exact source/probe hashes, comparisons and all mutant witnesses.
`python integration/sokol_delivery.py --sokol-root PATH --expect-results
examples/sokol-delivery/results.json` reproduces it. The recorded reply classes, not every
possible byte string, are tested. Existing native tests are the ordinary baseline: they
accepted unknown replies as Rejected before this contract revision; the new regression
would also find the defect without Stargate. Stargate contributes bounded closure, an
independently checked repair and a reusable correspondence check, not exclusive discovery.

The declared repair is agent-authored. This run has no separate independent agent arm
and measures no labor savings. Minimal-Hamming is one producer choice, not a generally
best repair. The full-domain and reachable-row comparison is in `model.comparison`.

This is a cross-language engineering pilot under operator influence. Independent demand,
maintainer acceptance, production adoption, NIC behavior and a release remain unestablished.

## Extended consumer review: final measurement

The first repair omitted five valid ADR-0019 retraction replies sent through the same
outbox. A strict parser would retry them indefinitely. Sokol's separately registered
amendment and correction `a0614ba` recognize those exact strings (not arbitrary `OK *`)
and add an eighth native regression. This issue was found by reviewing the server's
vocabulary, not by the three-bit model.

`results-v2.json` is the final run: **18 socket cases, all four semantic mutants
rejected**. The model and synthesis results are unchanged. The initial `results.json`
is preserved. Reproduce with the final source and `--expect-results
examples/sokol-delivery/results-v2.json`. This is evidence of why the adapter boundary
must be reviewed on both sides before adoption.
