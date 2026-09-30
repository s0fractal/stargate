# Explicit repair authority for the MCP example

These are new roots: `current.json` and `fixed.json` add `world = [calls.one,
calls.two]` to the frozen specs in `../mcp-proxy/specs`. Every other field is identical.
Only the proxy's `pending` and `ambiguous` rules may be repaired. The server's obligations
cannot be rewritten to make the invariant hold.

The old roots, results, `guarded/*` and the table Warrant pins are retained unchanged.
This is not an adoption or migration of Warrant's contract. Adding world changes the
ModelID, and the current certified-change contract deliberately refuses that transition;
a consumer must explicitly adopt a new root. The existing Warrant table still executes
the same transition function. The README walkthrough uses these stronger roots.
