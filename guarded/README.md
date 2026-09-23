# Stargate's own guarded model

`model.json` is the certificate model of `examples/mcp-proxy` variant `fixed`;
`projection.json` is its projection (the same bytes warrant pins). Both are written by
`python integration/mcp_proxy_vertical.py --write` and compared on every CI run.

A pull request that changes either file must carry, at `guarded/evidence.json`, a
`certified_change` or `certified_repair` whose parent is the model on the base branch
and whose verified successor is the new `model.json`, and the new `projection.json` must
conform to it. `.github/workflows/model-gate.yml` publishes the verdict as the commit
status `stargate/model-gate` on the pull request's head. Until the live test (PR-09b)
and the owner's ruleset change, that status is published but not required.
