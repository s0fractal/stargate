# Does the truncated two-phase commit need a third event bit?

`VISION.md` says a domain extension needs a concrete model that cannot be expressed.
This directory is that model, and the evidence about it. **Nothing here changes the
checker**: the three closure digests are untouched, and whether the event alphabet
grows is a separate decision, argued below.

```sh
python examples/two-phase-commit/two_phase_commit.py
```

```
simultaneous: refused by machine-create: machine requires 1..6 state bits and 0..2 disjoint event bits
serialized: verified_certificate
serialized, broken coordinator: verified_refutation
states reachable with three independent inputs: 13
states reachable with two event bits:           11
```

## The model

Six state bits: a coordinator (`init`, `wait`, `commit`, `abort`) and two
participants (`idle`, `yes`, `no`; the fourth code names nothing and the invariant
forbids it). Its environment has three independent inputs — A votes, B votes, the
coordinator times out — and any combination may occur in one step.

`serialized()` carries the same three actions on two bits by allowing at most one per
step. The transition rules are literally the same text; only the input alphabet
differs.

## What was registered, and what was measured

[REGISTRY.md](REGISTRY.md) was written first. Three of its four claims held:
`machine-create` refuses the three-bit model with
`machine requires 1..6 state bits and 0..2 disjoint event bits` (exit 2), the
serialized model certifies, and the planted defect — a coordinator that commits on
A's vote alone — is refuted.

**The decisive claim did not hold.** I registered that the two alphabets reach the
same states. They do not:

| | |
| --- | --- |
| three independent inputs | 13 states |
| two event bits | 11 states |
| only with three | `A=no B=yes C=wait`, `A=yes B=no C=wait` |
| only with two | none |

Those two are the race: one participant's vote arrives in the very step the
coordinator gives up on the other. With one action per step it cannot happen, so the
serialized model is not a truncation of the concurrent one — it is a different model
that cannot express the race at all.

## But no verdict of this model changes

Both extra states satisfy the declared invariant, so for the safety question this
model actually asks, three inputs and two bits give the same answer. The difference
becomes a verdict only for a property that mentions the race. One such property is in
the file (`NO_RACE`): it is violated in the concurrent model twice and holds in the
serialized one. That property is chosen to show the difference — it is evidence that
the difference is observable, not evidence that anyone needs it.

## Why this stops here

The case for a third event bit is now concrete, and so is its price.

* Every state gains four more outgoing edges: 8 per state instead of 4. This model
  goes from 44 edges to 104.
* The worst case for six state bits goes from 256 edges to 512, and
  `machine.verify` accepts `max_edges` of at most 256. A full six-bit model with
  three event bits **cannot be checked** without also raising that ceiling — a
  second contract change, which nothing has registered or argued.
* Two other changes to the checker are already open and unreviewed.

So this pull request is the evidence and not the extension. The next step, if it is
taken, is one `[перевіряч]` change that raises the event width **and** the edge
ceiling together, with its own registration, its own anchors row and its own
controls. I did not take it here, because half of it would be a checker that accepts
models it cannot finish checking.

## What this does not establish

Nothing about two-phase commit as a protocol: no messages, no logs, no recovery, and
no failure except a timeout. It cannot show that three event bits are useless in
general, nor that they are necessary in general — only what this one model needs.
