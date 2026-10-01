# Stargate for agent work

Decision, 2026-09-30: Stargate may have no independent users. Its primary development
profile is a tool used by coding/research agents, including the agent maintaining this
repository, in service of operator-authorized work. Independent adoption is optional;
it is not a prerequisite for useful work or continued development.

The useful unit is a decision improved by a reproducible check: find a counterexample
before changing code, reject an invalid repair, or let a later session replay a result
without trusting the earlier agent's prose. Agent-written code and agent-written
models remain fallible. The small checker verifies the supplied model; choosing the
right model and binding it to real code remain separate obligations.

## Choose a task, then a tool

| Agent need | Existing route | Retain | Do not infer |
| --- | --- | --- | --- |
| Find a flaw in a small workflow | `machine-create`, `machine-evidence` | Spec, machine, input ID, checked refutation/trace | A trace in an abstraction is automatically a production bug |
| Verify a proposed fix without changing obligations | `certificate-repair-pack`, `certificate-repair-check` | Parent refutation, candidate certificate, repair, checked successor | A producer's `found` is enough to apply code |
| Search when a hand fix is unclear | Bounded `repair-search` with explicit strategy and quotas | Inputs, attempted budget, repair or refusal | Exhaustion proves no repair exists |
| Compare a generated table to a model | `model-project`, `projection-check` | Certificate, table, both checker identities | Event decoding or side effects are thereby proved |
| Resume a finite lab task in another session | `lab-task-start`, `lab-task-resume` | Task bytes, task/runtime identities, row budget | Imported rows or narrative are trusted execution authority |
| Recheck known consumer contracts | `integration/reproduce.py --profile public` or `full` | Exact profile, sources, observation report | Public saved observations execute private consumer code |

Use ordinary tests and review when a state-machine abstraction adds no useful check.
The current machine domain has at most six Boolean state bits and two event bits.
Do not compress an unbounded identity, counter, deadline or concurrency problem into a
Boolean and then claim the full problem is proved. State the abstraction explicitly.

For a new model, the [task helper](AGENT_TASK.md) produces a checked certificate or
refutation and an offline handoff in one command, using the existing formats. Its
repair mode continues from a selected parent refutation, preserving the objection
and verifying the candidate before exporting a successor. With explicit `--search`
and `--max-candidates`, the same helper can propose the candidate itself; it stops at
the selected budget and exports only after independent repair verification.
A later session can use `--check-handoff` with selected input/checker anchors (and the
parent for repairs) to recheck saved data without executing any code from the packet.

## A working loop for an agent's own task

1. Name the decision and the failure to prevent. Write the concrete code/input mapping,
   environment assumptions, operator-owned requirements and permitted changes first.
2. Build a small model. Mark environment-owned next rules as `world`; write a safety
   invariant and useful reachable/live goals so doing nothing is not a spurious repair.
3. Run `machine-create` and `machine-evidence` as in the executable README walkthrough.
   Parse JSON and exit status, not human prose. A checked refutation is useful output;
   `incomplete`, checker errors and unavailable checkers establish no positive claim.
4. Use the counterexample to inspect actual code. Reproduce there before calling it a
   production defect. Propose a next-rule repair while retaining the inherited contract.
5. Recheck with the expected model and checker identities selected by the recipient.
   For a new local exercise, record the installed checker identity explicitly. For an
   existing contract, use its established anchor; never replace a mismatching anchor
   with the identity advertised by an untrusted packet just to obtain success.
6. Test the mapping back to code with actual inputs and semantic mutations. Changing
   the candidate or required checks invalidates the earlier result. Apply changes only
   through the authorized repository workflow with fresh checks of the exact candidate.
7. Leave artifacts and a short decision record for the next session. Recheck them when
   used; do not require the next agent to reconstruct the conversation.

The [agent evidence exercise](../examples/agent-evidence/README.md) executes this model
loop for stale publication eligibility, including refusal controls. It is a fixture
for agent workflow design. It does not replace this repository's real merge gate.

## Session handoff

Retain a small task directory or repository commit containing:

- The decision, owner, allowed action, code revision and model-to-code mapping.
- Original specification/machine bytes and independently selected expected identities.
- Certificate or refutation, proposed repair and verified successor when present.
- Commands, budgets, exit codes, checker versions and exact artifact hashes.
- The actual decision taken, unresolved assumptions and the next permitted operation.

`inspect` checks shape; packing and materializing do not establish a proof. A later
agent must run the appropriate evidence/repair/projection checker. A report saying
`passed` is an observation, not authority to merge, send messages, deploy or spend.
Successful proof verification never expands the operator's authorization.

## Development priorities and acceptance

**A1 — Agent entry point, now:** this guide, repository instructions, an executable
stale-evidence task and CI refusal controls. Keep one existing CLI and portable formats;
a second server/API is not justified merely by the word “agent”.

**A2 — Repeated internal use:** on relevant authorized coding tasks, record whether
Stargate changed the decision, exposed a defect or usefully refused a repair. Record
modelling/integration effort separately from runtime. Count repeated fixtures as
regressions, not new uses. Operator-controlled and agent-authored use is valid evidence
of internal utility and must be labelled as such.

**A3 — Extend from observed friction:** a new adapter needs a named repeated workflow;
a larger model domain needs a concrete contract that cannot fit; a new search strategy
needs repeated failures and a bounded comparison; an agent transport needs a client
that cannot use the current CLI/artifacts. Keep uncertainty and negative results.

Success is useful decisions and reusable verified artifacts at an acceptable cost.
Independent reviewers/users can add evidence but are not a product viability gate.
There are no adoption, productivity or defect-prevention numbers until measured. If
modelling repeatedly costs more than the decision is worth, narrow the use case.
