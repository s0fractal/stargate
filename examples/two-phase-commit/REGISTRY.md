# Pre-registration: does two-phase commit need a third event bit?

Written before anything below was run, and not edited afterwards. Branch
`feat/2pc-evidence`, parent `16eb087` (build 41).

`VISION.md` says a domain extension needs a concrete model that cannot be expressed.
This file registers that model and what must be shown about it **before** any change
to the checker is considered.

## The model

A two-phase commit truncated to what six state bits hold: a coordinator
(`init`, `wait`, `commit`, `abort`) and two participants (`idle`, `yes`, `no`,
`done`), two bits each.

Its environment has **three independent inputs**: participant A may vote yes this
step, participant B may vote yes this step, and the coordinator may time out this
step. Any combination can occur, including a vote that arrives exactly as the
coordinator gives up. Three independent inputs are eight combinations and cannot be
carried by two event bits, which offer four.

The serialized alternative carries the same three actions on two bits by allowing at
most one per step: `00` nothing, `01` A votes, `10` B votes, `11` timeout.

## What must be shown

| claim | expected |
| --- | --- |
| the simultaneous model is refused today | `sg machine-create` refuses it: `machine requires 1..6 state bits and 0..2 disjoint event bits`, exit **2** |
| the serialized model is accepted | `verified_certificate` for the correct rules |
| the serialized model catches the planted defect | `verified_refutation` for a coordinator that commits on A's vote alone |
| **the decisive measurement** | the reachable state set of the simultaneous model, computed by an oracle that shares no code with the checker, **equals** the set the serialized model reaches |

If those sets are equal, a third event bit buys no state that cannot already be
reached, and the extension is not justified by this model — only genuine simultaneity
is lost, and no safety or existential-goal question can see it. I expect them to be
equal. If they differ, the difference is the evidence, and it is reported exactly as
measured.

## What this will not establish

Nothing about two-phase commit as a protocol: this is a truncation that drops
messages, logs, recovery and every failure except a timeout. It cannot show that
three event bits are useless in general — only what this model does or does not need.
