# Pre-registration: the MCP sealing proxy vertical (PR-06)

Written before any model of it was built or run. Not edited after the run.

## The target

`warrant-mcp` (warrant `impl/warrant_mcp.py`, published as the `warrant-mcp` command)
sits between an MCP host and an MCP server and seals every `tools/call` result into an
evidence pack. Its `run_proxy` keeps a `pending` map from request id to the call it has
seen, pops it when the server's response arrives, and at server EOF records everything
still pending as *unreturned*. Read at warrant `origin/master` `b273b9e`, lines 276–354.

What goes wrong if this machine is wrong: the evidence pack — the thing warrant exists
to produce — silently misses a call whose effect ran, or seals one call's result as
another call's evidence.

## The model: one request id, four state bits, two event bits

State (all start `false`):

| bit | meaning |
| --- | --- |
| `calls.one` | the server owes at least one response for this id |
| `calls.two` | the server owes at least two (the model tracks up to two; see limits) |
| `pending` | the proxy holds exactly one call record for this id, to be paired with the next response |
| `ambiguous` | the proxy has marked this id as unpairable for the rest of the stream |

Events, one per step, `(host, reply)`:

| host | reply | event |
| --- | --- | --- |
| true | false | the host sends `tools/call` with this id |
| false | true | the server sends a response (`result`/`error`) with this id |
| false | false | the server sends its own request or notification reusing this id (e.g. `ping`) |
| true | true | server end of stream: every outstanding call ends, the session state resets |

There are no observer flags: safety is stated over the proxy's own bookkeeping and the
server's debt, so no repair can make it true by editing a flag that only reports.

    invariant:  (!calls.two || calls.one)
             && (!calls.two || ambiguous)                  -- two calls owed on one id: responses cannot be paired
             && (!calls.one || pending || ambiguous)       -- a call is owed and the proxy has no record of it

goal and live goal: `idle` = all four bits false (reachable again from every state).

The world bits are the same in every variant:

    calls.one' = (host && !reply) || (!host && reply && calls.two) || (!host && !reply && calls.one)
    calls.two' = (host && !reply && calls.one) || (!host && !reply && calls.two)

A response to "at least two" is modelled as leaving exactly one: the model bounds
duplicates at two outstanding calls per id.

### Variant `current` — warrant `origin/master` today

`pending[id] = …` overwrites; a response pops; a server request does not touch
`pending` (fixed in warrant PR #63); EOF flushes.

    pending'   = (host && !reply) || (!host && !reply && pending)
    ambiguous' = ambiguous

### Variant `historic` — before warrant PR #63 rev 2

Any server message carrying the id popped the pending call (a `ping` sealed as the
tool's result).

    pending'   = (host && !reply)
    ambiguous' = ambiguous

### Variant `naive-fix` — "record the displaced call as unreturned"

Code-level it differs from `current` (the first call is written to the pack instead of
dropped). **Model-level it is identical**: the rules above do not change, because the
bookkeeping after the second call is the same — one record held, two responses owed.
Registered prediction: it is refuted exactly like `current`, and the reason is the next
response, which the proxy will pair with the wrong call.

### Variant `fixed` — written by hand before the run

A call on an id that is pending or already ambiguous marks the id ambiguous and holds
no record (both calls are recorded unreturned-ambiguous; later responses on that id are
recorded unpaired, never sealed); EOF clears it.

    pending'   = (host && !reply && !pending && !ambiguous) || (!host && !reply && pending)
    ambiguous' = (!host && ambiguous) || (host && !reply && (ambiguous || pending))

## Expected outcomes

1. `current`: `machine-evidence` → `verified_refutation`, unsafe, a 2-step trace
   (call, call), endpoint `calls.one, calls.two, pending, !ambiguous`.
2. `historic`: `verified_refutation`, unsafe, a 2-step trace (call, server request),
   endpoint `calls.one, !pending, !ambiguous`.
3. `naive-fix`: the same model ID as `current`, so the same refutation.
4. `fixed`: `verified_certificate`, 5 reachable states, `idle` live.
5. `repair-search` on `current`, both strategies, 256-candidate quota: **measured, not
   predicted**. If it finds a repair, `certificate-repair-check` verifies it, and which
   rule it edits is recorded. Whatever it finds, the hand-written `fixed` also goes
   through `certificate-repair-pack` + `certificate-repair-check` against the `current`
   refutation: expected `verified_repair`.
6. Projection of the chosen successor: 64 rows; `projection-check` against its
   certificate: `conforms`. Chosen successor: the search's, if it finds one **and**
   warrant's proxy tests pass with its table; otherwise `fixed`. Either way the choice
   and its reason are reported.
7. One flipped cell in that projection: `mismatch`; the Python runtime still executes
   the flipped cell (separation of authority, as in PR-05).
8. `python integration/mcp_proxy_vertical.py` runs 1–7 from a clean checkout and exits 0
   only if every outcome above holds.

## The real integration (a warrant change, its own branch and review)

warrant's `run_proxy` keeps one table state per id and decides with the table:

* host call: if the previous state was `pending` and the next is `ambiguous`, record
  the previous call unreturned (ambiguous); if the previous state was `pending` and the
  next is not `ambiguous`, the previous record is overwritten (what the table says);
  if the next state is `pending`, hold the new call, else record it unreturned (ambiguous).
* server response: if the previous state was `ambiguous`, record the response unpaired
  and seal nothing; else if the previous state was `pending`, seal.
* server request with the id: if the previous state was `pending` and the next is not,
  the request resolves the call (what the table says); otherwise forward untouched.
* EOF: record every held call unreturned.

warrant vendors `projection.json` and `runtime.py` and pins both SHA-256 digests **in
its own source**, not read from `RUNTIME.json`; it hashes the bytes, refuses to start on
any difference, and executes the runtime from the bytes it hashed.

Expected in warrant: its existing proxy tests A–F unchanged and green; a new test —
two `tools/call` with one id, then two responses, then EOF — shows both calls in the
pack as unreturned, both responses unpaired, the pack incomplete, exit 3; today's code
loses the first call.

## Controls

* The flipped projection cell (outcome 7).
* A warrant proxy started with a `projection.json` or `runtime.py` one byte different
  from the pins refuses to start.

## What this will not establish

That the model is the proxy: it was written by reading `run_proxy`, and the warrant tests
are the evidence that the table-driven proxy behaves as the model says — for the cases
they exercise. Threads (both paths hold one lock), more than two outstanding calls per
id, ids shared across ids' interactions, the content of results, and everything the
sealer does after a decision are outside the model.
