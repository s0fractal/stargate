# Pre-registration: world rules a repair may not change (the one candidate from the verdict)

Written before any code. Not edited after the run. Source: docs/VERDICT.md — the only
semantic change a real vertical produced. In the warrant vertical, `repair-search`
"repaired" the proxy model by making the server's rule `calls.one'` identically false,
and `certificate-repair-check` accepted it: the contract protects state, events,
initial states, invariant and goals, but every `next` rule is editable.

## The change

An optional model field `world`: a nonempty, sorted, duplicate-free subset of `state`
naming the bits whose `next` rules describe the environment. A certified change or
repair must leave `world` itself and the `next` rule of every world bit byte-identical;
only the other ("owned") bits' rules may change. A model without `world` behaves exactly
as today (every rule editable) and keeps its model ID.

This is a machine-checker change (`certificate.py`, `_preserves_contract` and model
validation). It therefore needs, in this order and as separate commits:

1. registration (this file);
2. red tests on the current checker;
3. the checker change → a new checker ID;
4. the new snapshot row in `ANCHORS.md`, `vertical/baseline.json` re-baselined **as its
   own named decision**, and the transition of `guarded/admission.json` to the new
   checker — the first real use of 09c's rule that a transition is a state change;
5. `repair-search` skips world rules (producer side; it proposes nothing the checker would
   refuse anyway);
6. the warrant vertical re-run with `world = ["calls.one", "calls.two"]`.

## Expected outcomes

1. A change or repair that edits a world bit's rule: `invalid` — "certified change alters
   world rule: calls.one".
2. A change or repair that adds, drops or edits the `world` field: `invalid`.
3. `world` naming an unknown bit, unsorted, duplicated or empty: `invalid`.
4. A model without `world`: every existing test, zoo row and vertical unchanged, byte for
   byte, except where the checker ID is recorded.
5. The warrant vertical with `world = ["calls.one", "calls.two"]`: `repair-search` on
   `current`, both strategies — **measured, not predicted**; whatever it returns, it does
   not edit `calls.*`, and the hand-written `fixed` still verifies as a repair.
6. Admission: until the transition commit, the gate on `main` refuses guarded changes
   under the new code (`checker_unavailable`, fail closed); after it, it admits them.

## Control

With the world-rule comparison removed from `_preserves_contract`, the warrant
"repair" that edits `calls.one` is accepted again.

## What this will not establish

That the world rules are the right model of the environment, that a search finds a
repair within the owned rules, or anything about models that do not declare `world`.
