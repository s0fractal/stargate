# Stargate's own guarded model

`model.json` is the certificate model of `examples/mcp-proxy` variant `fixed`;
`projection.json` is its projection (the same bytes warrant pins). Both are written by
`python integration/mcp_proxy_vertical.py --write` and compared on every CI run.

A pull request that changes either file must carry, at `guarded/evidence.json`, a
`certified_change` or `certified_repair` whose parent is the model on the base branch
and whose verified successor is the new `model.json`, and the new `projection.json` must
conform to it. `.github/workflows/model-gate.yml` publishes the verdict as the commit
status `stargate/model-gate` on the pull request's head. The status is required on `main`, pinned to GitHub App 5041755 with strict
up-to-date checks (live acceptance: `docs/MODEL_GATE_APP_RESULTS.md`).

This frozen model predates the explicit `world` field. Its checker supports ownership,
but this root does not declare it. `examples/mcp-owned` demonstrates new roots with that
boundary; it does not silently migrate these bytes or Warrant's consumer pins.
Changes to the checker/admission source still need independent review; the model gate
only judges changes to this model and projection, not its own implementation.
