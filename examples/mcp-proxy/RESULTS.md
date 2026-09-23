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

warrant PR [#81](https://github.com/s0fractal/warrant/pull/81), branch
`fix/mcp-proxy-duplicate-id` on `origin/master` `b273b9e`, pushed with the owner's
authorization. **Review state: AMEND** (Codex, adversarial), and warrant's own agent gate
**REJECT** on size (+500 lines against `agent_ceiling` 300 at the first head; the
vendored runtime and table are most of it). Green CI there is not acceptance.

* `604709e` red: G — two `tools/call` with id 5 held open. On `master`: no unreturned
  call, the second call sealed with the first call's result, complete, exit 0.
* `f5ae01c` the table fix: per-id decisions from the pinned table (runtime
  `4ab9224fac36…`, projection `6235a212057f…`, pinned in `warrant_mcp.py`, not read
  from `RUNTIME.json`; a difference refuses to start, exit 2). G passes; A–F unchanged;
  H: a changed runtime or projection is refused.
* `a062427` red and `a67c2c9` fix for the review finding below, plus the reviewer's
  hardening: `run_proxy` loads the table before it spawns a server.

## Found by the integration, not by the model

The model is one request id. Codex's review of #81 found a call that has **no id**: a
`tools/call` notification (no `id`, or `id: null`). The downstream server may execute
it; the proxy ignored it on the host side (`"id" in msg` false) and the server's
`id: null` answer on the other (`mid is None`). Result on #81's first head: a
consequential effect with `sealed_calls: 0`, `unreturned_calls: []`,
`observation_complete: true`, exit 0 — a false green.

No bit of the model could see it: the model's first step is "a call with this id", and
there was no id. The table was not wrong; the model's world was too small. The fix
(`a67c2c9`) records such a call unreturned with `"reason": "no request id"` and keeps a
null-id response unpaired; it does not go through the table, because the table is about
calls that can be paired at all.

Two lessons from one vertical, kept apart on purpose:

| from | found | why the other could not |
| --- | --- | --- |
| the formal model | a reused id loses a call and misattributes a result (live on warrant `master`) | a test has to guess the interleaving; the refutation names it (call, call) |
| the real integration and its review | an id-less call leaves a clean pack | the model only describes calls that have an id |

What the warrant tests do not show: that every path through `run_proxy` is the model.
They exercise the paths the model has — a reused id, a server request on a held id (F),
an unanswered call at EOF (E) — plus the id-less call the model lacks (I), and nothing
about threads or more than two outstanding calls per id.
