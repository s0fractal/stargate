# Agent task: stale evidence must not enable publication

A small agent workflow model, not an implementation of a GitHub gate. `fresh` means a
successful verification is bound to the current candidate and required check set.
`eligible` means the current candidate has passed the model's publication gate. It is
revocable eligibility, not a record that a previous version was published.

| a | b | Event | Adapter obligation |
| --- | --- | --- | --- |
| false | false | Idle, failure, missing or incomplete result | Do not invent success |
| false | true | Candidate or required check set changes | Invalidate evidence before any subsequent decision |
| true | false | Complete successful verification for current inputs | Compare actual content/checker/requirements identities |
| true | true | Request eligibility | Require fresh evidence |

Events are serialized. `fresh` is a world rule: repairs cannot make the environment
claim fresh evidence unconditionally. `stale.json` forgets to revoke eligibility after
an edit. `fixed.json` changes only that owned rule. Safety is `!eligible || fresh`;
both a reachable and a live goal require eligibility with fresh evidence. A permanent
refusal would not satisfy the contract. A live goal promises an available path, not
that an agent will take it.

Run from the repository root after installation:

```sh
python integration/agent_evidence.py --output /tmp/my-agent-evidence
```

The directory must not exist. The exercise refutes the stale model, certifies the fixed
model, independently rechecks the repair and saves both machines, proofs, the repair,
successor and report. Controls reject another model's proof, withhold a successor on
zero verification budget and reject a certified repair that changes the world rule.
CI repeats this task. It is operator-controlled agent use, not independent adoption.

The concrete adapter remains responsible for input hashing, complete check discovery,
error handling, serialization and checking freshness at the actual publication point.
There is no claim about a concurrent edit between check and use, process crashes,
GitHub permissions or arbitrary code correctness. This example performs no publication
and grants no authority. See the [agent profile](../../docs/AGENT_PROFILE.md) for using
existing Stargate commands on an agent's own contract.
