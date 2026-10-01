# Publisher binding review — 2026-10-01

This review concerns the path from an immutable model-gate verdict to its commit
status. It does not certify arbitrary PR code or replace the required Python/shadow
checks. Original registrations and dated live results retain their bytes.

## Reproduced defects and changes

On `d678df2`, using the real Git fixture, real gate and local HTTP API double:

1. Changing a PR's base branch *during* the gate yielded exit 0 and a `success` POST
   computed for the former base. Binding was only read before checking.
2. Two open PRs with the same head yielded exit 0 and `success` when `event_pulls`
   named only one. The uniqueness check examined that event subset.

The publisher now scans paginated open PRs regardless of event contents, filters by
exact head and requires one match. A nonempty event PR list must contain that match.
It then reads that PR directly. The scan stops after ten pages of 100; if pagination
has not completed, no binding is established. API errors cannot become success.

Before posting a final verdict it repeats discovery and compares PR number, open/head
binding, base branch and current base tip to the checked context. A change yields
`binding_changed`, exit 4 and a failure status on the original event head. The report
retains the old gate verdict under `gate_report`; it is not a current approval.
Changed base bytes also invalidate the base-owned admission record and checker choice.

The endpoint choice matters: GitHub documents that the commit-to-PR endpoint returns
the introducing merged PR when a commit is already on the default branch. It is not
used as a complete list of open PRs. The implementation uses the paginated
[open pull request list](https://docs.github.com/en/rest/pulls/pulls#list-pull-requests)
with its explicit state filter; see also the
[commit association semantics](https://docs.github.com/en/rest/commits/commits#list-pull-requests-associated-with-a-commit).

## Validation and model-to-code mapping

The publisher regressions cover head changes, retargeting, base-tip changes, PR closure,
a second matching PR, page-two ambiguity, pagination exhaustion and inconsistent or
incomplete gate reports. Existing checks still cover corrupted projection, stale base,
exceptions, refused status POST, isolated workflow entry and base-owned admission.
The semantic control disables only the final invalidation branch and reproduces a
stale success after a real gate run. Test servers now release their listening sockets.

The [finite binding model](../examples/publisher-binding/README.md) refutes the original
publication rule and verifies the owned guard repair. Its initial state represents a
completed successful gate. An observed mismatch maps to `fresh=false`; the final
invalidation branch prevents a success POST in that case. The model's observation is
an abstraction supplied by the API reads, not a theorem about the remote service.

## Merge boundary and remaining limits

Live `protect-main` readback on 2026-10-01 showed strict base freshness, required Python
3.11–3.14 and shadow checks, the model-gate status bound to App 5041755, zero mandatory
approvals and an empty bypass list. Those mutable settings were observed, not proved.
The publisher checks guarded model/projection changes; `untouched` certifies no
arbitrary source code. Missing CI remains the responsibility of the required-check
ruleset; this publisher does not aggregate or substitute for those checks.

An initially unbound run writes no status, as before; it does not revoke an older
status already attached to that head. Ambiguity refusal therefore prevents this run
from issuing a new approval, not reuse of every historical status.

The final API read and status POST are separate operations. A mutation after the read,
concurrent pagination, an older publisher run or changing rulesets cannot be excluded
by this local model. A base advance after completion does not itself trigger another
request workflow; strict freshness and rechecking after updating the head remain
necessary. Retarget events request another run. A later refusal can conservatively
supersede a previous success on the same head; rerun after the binding stabilizes.

No claim of atomic merge authorization or elimination of every race is made. A stronger
claim would require a platform-supported transaction or merge-queue integration with
its own concrete adoption task and validation. This change closes the two reproduced
publisher defects without weakening repository admission.
