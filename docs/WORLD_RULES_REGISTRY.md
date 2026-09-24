# Pre-registration: ownership-safe automatic repair (world rules)

Written before any code or run. This is its second text, revised after review of the
first and still before anything ran; it is not edited after the run.

Source: docs/VERDICT.md. In the warrant vertical, `repair-search` "repaired" the proxy
model by making the server's rule `calls.one'` identically false, and
`certificate-repair-check` accepted it. The owner set the next bounded goal as
**ownership-safe automatic repair**: a repair may change only rules the model declares
repairable; it may not change the rules of the declared world, and the independent
checker enforces that.

## The contract

* **`world`** is an optional model field. When present it is a nonempty, sorted,
  duplicate-free subset of `state`. `world: []` is invalid (it would change identity and
  mean nothing).
* `model_from_machine()` carries `world` only when the machine has it, so the
  certificate model and ModelID of models without `world` do not change. Machine packets
  and MachineIDs of existing specs **do** change: `machine.py` is in the lab runtime
  closure and `machine.create()` embeds the sources.
* **The classification is protected everywhere**: a change, a repair or a history step
  cannot add, drop or alter `world`. Changing the ownership boundary needs a new root.
* **`verify_repair` alone** also requires, for every `w` in `world`,
  `candidate.next[w] == parent.next[w]` byte for byte. A plain `certified_change` may
  still edit `next[w]`: that is a deliberate evolution of the model, not an automatic
  repair, and this change makes no claim about it.
* `repair-search` does not propose edits to world rules. That is a producer
  optimisation; the authority is `verify_repair`, which must refuse even a hand-forged
  repair of the world.

## Checker transition (09c's first real use)

`certificate.py` changes, so the machine checker changes, and through its closure the
ProjectionCheckerID; `machine.py` changes the Boolean lab runtime. Every anchored closure
is recomputed and a **new composite snapshot row** is added to `ANCHORS.md`; old rows are
not rewritten. `vertical/baseline.json` is re-baselined as its own named decision, and
`guarded/admission.json` moves to the new active pair; the old checker stays historical.

## Expected outcomes

1. `verify_repair`: a candidate that edits a world rule and otherwise certifies →
   invalid ("repair alters world rule: calls.one").
2. Change, repair and history: adding, dropping or altering `world` → invalid.
3. `world` empty, unsorted, duplicated or naming a non-state bit → invalid.
4. `verify_change`: a candidate that edits `next[w]` for a world bit, with `world`
   unchanged and both certificates valid → `verified_change`.
5. Models without `world`: their certificate ModelIDs are unchanged; every test, zoo row
   and vertical keeps its verdicts; recorded artifacts that embed a checker or runtime
   digest are regenerated and compared.
6. Warrant vertical with `world = ["calls.one", "calls.two"]`: `repair-search` on
   `current`, both strategies — **measured**. Acceptance is only: no accepted repair
   edits `calls.*`; `found` with owned-only edits and `search_incomplete` /
   `neighborhood_exhausted` are both acceptable. The hand-written `fixed` still verifies
   as a repair.
7. Admission transition, three commits observed in CI order: new checker code with the
   old record → the record test fails; the new record → it passes. And, as tests:
   base record naming the old checker while the new code runs → `checker_unavailable`;
   base record naming a checker that is not the running code → `checker_unavailable`;
   matching → `verified`.

## Control (G8)

`parent.world = ["calls.one", "calls.two"]`; a forged repair edits `calls.one` and
otherwise certifies. Real `verify_repair` → invalid. A checker mutant without the
world-rule equality → `verified_repair`.

## What this will not establish

That `world` models the environment correctly, that a repair exists within the owned
rules, or anything about models that do not declare `world`.
