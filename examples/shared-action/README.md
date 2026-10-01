# Two agents, one resource-release candidate

A bounded experiment in independently checking two selected requirements against the
same proposed behavior. The roles are scripted fixtures authored by the same operator's
agent, not independent users, real competing principals or a deployed federation.
There is no money, voting, identity service, new proof format or new checker.

The custodian wants the resource retained until the result has been handed off. The
reclaimer wants a path to freeing it. Neither may silently replace the other's contract.

## Shared world and separate obligations

`world.json` defines two Boolean state bits and two event bits. Every transition reads
the old state; `a` and `b` may arrive together, and all four valuations remain possible.

| Name | Meaning | Ownership |
| --- | --- | --- |
| `held` | Resource is still retained | The candidate proposes this next-rule |
| `ack` | Handoff acknowledgement has been observed | Immutable world next-rule |
| `a` | Acknowledgement arrives | External event |
| `b` | Release requested | External event |

Initially `held=true`, `ack=false`. Acknowledgement persists (`ack OR a`); releasing
never reacquires the resource. A simultaneous acknowledgement and release request
cannot use the new acknowledgement: the guarded policy requires it in the old state.

- `custodian.json`: `held OR ack`. A released resource must have an acknowledgement.
- `reclaimer.json`: the goal `held=false, ack=true` is reachable and remains reachable
  from every reachable state. Its safety invariant is `true`.

The reclaimer's requirement is **available progress**, not inevitable release, fairness,
a deadline or a cost optimum. A scheduler may idle forever. Acknowledgements are assumed
authoritative and monotone within one handoff: authentication, lost/counterfeit messages,
resource reuse, crashes and real storage semantics are outside this model.

## Three proposals, two verdicts each

Each candidate file supplies only the `held` next-rule. The integration constructs two
ordinary machine specifications with identical dynamics and different selected contracts.
Their full model identities therefore differ; equality of those identities is not the
criterion for sharing a candidate.

| Candidate | Custodian | Reclaimer | Joint decision |
| --- | --- | --- | --- |
| `premature.json`: release on request | Refutation: release before acknowledgement | Certificate | Candidate refuted |
| `hoard.json`: never release | Certificate | Refutation: release goal unreachable | Candidate refuted |
| `guarded.json`: release on request after acknowledgement | Certificate | Certificate | Admissible in the model |

The first objection is a one-step unsafe trace. The second is a checked closed-state
set excluding the required goal. Both are retained as existing refutation artifacts.
Neither objection establishes incompatibility of the contracts: the third candidate
satisfies both. This experiment performs no search and proves no global impossibility.
An incomplete verification produces `undetermined`, never admission or incompatibility.

## Recipient selection and refusal

`selections.json` is the fixture recipient's checked-in choice of exact world, candidate,
contract bytes and checker identity. It is not an authority record learned from a
proposal, signature, identity claim, or production admission protocol. Changing these
selections is a separate operator-controlled decision; a proposal cannot update them.

The read-only `check` function in `integration/shared_action.py` requires those expected
identities as separate arguments. It reconstructs each expected model from the same
candidate and selected world, rechecks both proof byte strings with the existing
checker, and sets `admitted=true` only for two verified certificates. Producer verdicts
are not used to admit. Its result is an observation of model eligibility, not permission
to release a resource or execute code. There is no real actuator in this experiment.

Controls reject a changed candidate, a valid but stale proof, a weakened contract and
a missing party. Zero checker budget withholds admission. Tests also exercise one
incomplete party while the other succeeds and a genuine certificate under a weakened
custodian requirement. The Python reference transition rules agree with generated
candidate tables on all 48 state/event rows (three candidates times sixteen rows).
This is correspondence to a small reference function, not to production storage code.

## Reproduce and retain the disagreement

From an installed checkout:

```sh
python integration/shared_action.py --output /tmp/stargate-shared-action
```

The directory must be new and its parent must exist. The harness requires all three
expected outcomes and refusal controls; it exits nonzero on an unexpected result. CI
runs it as part of the required `shadow` job; the full test matrix also checks semantics.

The export retains the selected world/contracts, each candidate, and six directories
containing standard `input-spec.json`, `input.machine` and certificate/refutation files.
`report.json` contains the per-party model identities, check results and objections.
The two parties' proofs are separately replayable; the joint result must be reconstructed
with the same selected candidate and both requirements, not inferred from one proof.

An installed recipient can recheck each directory with `tools/agent_task.py --check-handoff`
and independently selected input/checker hashes, as described in
[AGENT_TASK.md](../../docs/AGENT_TASK.md). The experiment does not bundle an offline
launcher. Preserve the original selections when moving between sessions; never replace
a refused anchor with a received report's value just to make it pass.

Exports clean up ordinary write exceptions when possible, but are not atomic or crash
durable. Read only after completion; forced termination can leave partial artifacts.
The old report is an observation, not evidence of current authority.

This experiment tests a narrow hypothesis: agents can retain different explicit
requirements while sharing a mechanically checked candidate decision. It does not
establish truthful preference revelation, incentive compatibility, reputation, economic
incentives or independent adoption.
