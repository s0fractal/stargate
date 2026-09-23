# Results: the MCP sealing proxy vertical

Measured by `python integration/mcp_proxy_vertical.py` (bytes in `results.json`, which
the script regenerates and compares). The registration is [REGISTRY.md](REGISTRY.md);
nothing in it was edited.

| outcome | registered | measured |
| --- | --- | --- |
| 1 `current` | refuted, unsafe, call → call, endpoint `calls.one, calls.two, pending, !ambiguous` | as registered, exit 4 |
| 2 `historic` | refuted, unsafe, call → server request, endpoint `calls.one, !pending` | as registered, exit 4 |
| 3 `naive-fix` | same model ID as `current` | same (`068d7c49a953…`) |
| 4 `fixed` | certificate, 5 states, `idle` live | as registered |
| 5 `repair-search` | measured | both strategies `found` — see below |
| 5 hand repair | `verified_repair` | `verified_repair` |
| 6 projection | 64 rows, `conforms` | 64 rows, `conforms`, for `fixed` and for the search's successor |
| 7 flipped cell | `mismatch`; the runtime runs it | as registered |

## What the search found

`repair-search` on `current` returns `found` for both strategies (one-edit after 3
candidates, trace after 10), and `certificate-repair-check` accepts the packet:
`verified_repair`. The edit is to `calls.one`:

    calls.one' = ((host && !reply) || (!host && reply && calls.two)) && (!host && !reply && calls.one)

The second conjunct needs a server request and the first needs a call or a response, so
the rule is always false: **the server never owes a response**, and with no debt the
invariant holds trivially. The repair is sound for the contract the checker has — safety,
initial states, goals and live goals preserved, only `next` changed — and it changes the
wrong side of the system. `calls.one` and `calls.two` describe the server; the proxy
cannot implement a rule that stops the server from receiving calls.

So the registered choice rule (outcome 6: the search's successor if warrant's proxy
tests pass with it, otherwise `fixed`) resolves to `fixed`: no proxy code can make the
search's table true. The search's successor is still projected and checked, to show that
the whole chain accepts it.

## What this says about Stargate, not about warrant

A machine model mixes the part being repaired (the proxy's `pending`, `ambiguous`) with
the part that is the environment (the server's `calls.*`). The repair contract protects
state, events, initial states, invariant and goals, but every `next` rule is editable, so
a bounded search can "repair" a model by changing the environment it was supposed to
survive. The checker is not wrong — it was never asked which rules are fixed.

This is recorded, not fixed: adding protected rules would be a new contract feature, and
the plan freezes new semantics until the post-PR-10 verdict (G10). It is a direct input
to verdict question V1/V3: a real vertical needs "these rules are the world" before an
automatic repair can be trusted without a human reading which rule it changed.

## What the hand repair establishes

`fixed` is the only change among the four variants that is a proxy change. It certifies
with `idle` live, and `certificate-repair-check` verifies it against `current`'s
refutation. It is the table warrant runs; see the warrant branch for the integration and
the test that reproduces today's lost call.

## The warrant side

Branch `fix/mcp-proxy-duplicate-id` in warrant, on `origin/master` `b273b9e`, **local and
not pushed**: warrant's rules require an explicit human authorization for pushing.

* `604709e` red: `tests/mcp_seal.py` G — two `tools/call` with id 5 held open, then a
  release. Today: `unreturned_calls` empty, 2 seals (the second call sealed with the
  first call's result), `observation_complete: true`, exit 0.
* `f5ae01c` the fix: `run_proxy` keeps one table state per id and decides with it;
  `warrant_mcp_table.py` is `src/projection_runtime.py` byte for byte; the runtime
  digest `4ab9224fac36…` and the projection digest `6235a212057f…` are pinned in
  `warrant_mcp.py` (not read from `RUNTIME.json`), hashed before anything runs, and a
  difference refuses to start (exit 2). G passes: both calls unreturned and
  `ambiguous`, both responses in `unpaired_responses`, one seal, incomplete, exit 3.
  A–F unchanged and green; new H: a runtime one line longer is refused before the
  server is spawned, and a changed projection is refused by `load_table`.
* The built wheel ships `warrant_mcp_table`, and the installed `warrant_mcp.load_table()`
  answers from the pinned table.

What the warrant tests do not show: that every path through `run_proxy` is the model.
They exercise the paths the model has — a reused id, a server request on a held id
(F), an unanswered call at EOF (E) — and nothing about threads or more than two
outstanding calls per id.
