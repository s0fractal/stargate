# Publication after an observed binding change

This model supports the real publisher review of 2026-10-01. Initial state is just
after a successful gate check of immutable `(base, head)` objects. `fresh` means the
observed unique/open PR, head, base branch and base tip still match that check.
`published` is a success action on this step, not a persistent historical status.

| a | b | Abstract event |
| --- | --- | --- |
| false | false | Idle |
| false | true | Observe changed/ambiguous binding |
| true | false | Successfully check a fresh binding again |
| true | true | Attempt publication |

The stale rule publishes even after invalidation. The fixed rule requires `fresh`.
The invariant is `!published || fresh`; reachable/live publication goals prevent an
always-refuse repair. Only the owned publication rule changes; freshness is `world`.
The old model is refuted by invalidate → publish. The fixed model certifies, and its
repair independently checks with the unchanged Stargate checker.

`tests/test_pr_gate_publish.py` checks both models and exercises the actual publisher
against local Git objects and an HTTP API double: a successful real gate is interrupted
by a head change, retarget, base-tip change, closure or second matching PR. The final
POST must be failure, never success. Removing the invalidation branch restores stale
success. Another scenario puts a conflicting PR on page two while the event names
only the first PR. Inconsistent/incomplete gate reports cannot become success.

This is a proof about **observed**, serialized binding changes. It is not proof of
GitHub API consistency, complete pagination under concurrent changes, or atomicity
between the final read and POST. Changes after the last observation remain outside
the model. Python/Rust tests and other required checks remain separate merge gates.
See [the current review](../../docs/PUBLISHER_BINDING_REVIEW.md) for evidence and limits.
