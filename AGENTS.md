# Using Stargate as an agent

Read `docs/CURRENT.md` for current status and `docs/AGENT_PROFILE.md` for the agent
workflow. Independent users are not a prerequisite for development. Internal agent
use under the operator's existing authorization is an intended use, not independent
adoption. Do not revive archived workspace projects from provenance references.

For a relevant small state-machine decision, consider modelling the failure and
checking a repair before changing production behavior. Do not force every coding task
into a model. Start with `examples/agent-evidence/README.md` for a runnable agent task;
for a custom model use `tools/agent_task.py` as documented in `docs/AGENT_TASK.md`;
use the existing CLI, JSON evidence and replay instead of inventing a second protocol.

Keep producer proposals separate from checker verdicts. Preserve expected identities,
world rules, inherited contracts and frozen evidence. Unknown/incomplete/error results
must not authorize the next operation. Recheck after candidate or requirement changes.
Model proofs, code correspondence, observed behavior and operator authorization are
separate claims. Agent-created evidence never grants additional permissions.

For code changes, run relevant regressions and required repository CI. Include a
semantic refusal control when changing a gate or evidence consumer. Do not change the
checker merely to make an integration pass. Follow the existing exact-candidate merge
workflow; no additional human approval requirement is introduced by this file.
