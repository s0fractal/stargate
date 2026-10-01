# Agent review observations

Results under the unchanged [shadow registration](AGENT_REVIEW.md). These are
observations and maintainer assessments, not certificates or an estimate of the
reviewer's general accuracy. Keep the raw verdict; later assessments do not rewrite it.

## Run 1: Stargate #108 — 2026-10-01

- PR: [#108](https://github.com/s0fractal/stargate/pull/108), head
  `0720319379d9295912aa92a5cb2f14cb1c7dc024`.
- Base: `9fee980612ca9fdd581049ed2f767dd3ea7a5570`.
- Reviewer: pinned Claude CLI/model from the trusted base workflow, separate from
  the implementation session. [Run 36871458847](https://github.com/s0fractal/stargate/actions/runs/36871458847).
- [Raw published verdict](agent-review-results/108.json): `pass`, two `minor`
  findings, no `major` or `blocker`. The head was not changed after review.
- Merge: `d512620994fd1f063b2a2c68f8ce137bf9fe714f`; its tree equals the reviewed head.
- Timing from GitHub's second-resolution timestamps: review/publish step
  `13:48:54–13:49:30 UTC` (36 s); job `13:48:43–13:49:32 UTC` (49 s).
  These include orchestration and publication, not pure model inference time.
  Subscription usage, token counts and monetary cost were not retained by this workflow.

### Finding assessments

1. **Frozen observation not compared in public CI — acknowledged validation gap.**
   The private-source execution boundary was already explicit. Direct hashing at the
   reviewed head confirmed the adapter, intent, actuator and receiver digests match
   the stored report, and the actual experiment reproduced the report byte-for-byte.
   No incorrect digest was found. [Sokol #100](https://github.com/ValkyrieSentinel/sokol-core/pull/100)
   proposes recurring live and frozen reproduction where private source is available;
   it is a separate change, not evidence that #108 already had that CI.
2. **Explicit receiver status check — optional hardening, no reproduced defect.**
   The existing revision fence prevents a cancelled action from committing. Receipt
   lookup intentionally permits historical duplicate responses. A blanket refusal
   of every non-pending status would change that behavior. The implementation was
   retained; the finding does not demonstrate an effect after cancellation.

Both findings give line ranges beyond the 218-line adapter at this head. The named
file and `dispatch` symbol allow inspection, but those numerical locations are wrong.
They remain in the raw record rather than being silently repaired.

### What this run establishes

The workflow ran, published a verdict on the exact candidate, and the implementer
read and assessed the findings before merge. The 709 local tests, actual private-source
experiment and green CI are separate evidence, not work performed by the reviewer.

This run found no confirmed code defect requiring a patch. It does not estimate missed
bugs, independence of model errors, false-block rates or economic value. Five to ten
runs remain the registered pilot scale; one `pass` is insufficient to make this check
required. Publication still uses the shadow status mechanism.
