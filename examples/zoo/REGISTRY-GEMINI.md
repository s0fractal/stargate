# Pre-registration: five systems from the earlier Gemini session

The rules in `systems/lift-doors.json`, `systems/traffic-lights.json`,
`systems/bounded-buffer-gemini.json`, `systems/railroad-crossing.json` and
`systems/railroad-crossing-v1.json` were carried over from that session's log by
the repository owner and are frozen as they are. This file registers what they are
expected to produce **here**, before this harness was run against them.

Committed on branch `feat/zoo-gemini`, parent `228a6b2`.

The numbers below are the owner's own measurements, reported before I ran anything.
They are predictions for this table in exactly the sense the other registration is:
if my run disagrees, the disagreement is reported and nothing is adjusted.

| system | planted defect | broken evidence | correct evidence | one-edit | trace |
| --- | --- | --- | --- | --- | --- |
| lift-doors | motor may start with the door open, and the door tracks the motor | verified_refutation | verified_certificate | found at 19 | found at 21 |
| traffic-lights | east-west goes green on the raw request | verified_refutation | verified_certificate | found at 11 | found at 13 |
| bounded-buffer-gemini | producer stops checking the full slot | verified_refutation | verified_certificate | found at 7 | found at 9 |
| railroad-crossing-v1 | train may enter before the gate is down | verified_refutation | verified_refutation | measure | measure |
| railroad-crossing | the same defect, after the correct rules were changed | verified_certificate | verified_certificate | not_needed at 0 | not_needed at 0 |

## Why the two railroad rows are the point

`railroad-crossing-v1` is the first variant from the log: its **correct** model is
refuted too, so the pair proves nothing about the defect. The rules were then
changed, and in the second variant the **broken** model certifies — the defect
stopped being a defect. That row never reached the earlier table. Both variants are
kept here on purpose, as a discarded variant and its replacement, not as exhibits of
a working repair.

## What these rows will not establish

Nothing about lifts, junctions, buffers or level crossings as engineering artifacts.
Two or three Boolean bits with one synchronous step are not a controller, and a
model that certifies here has been checked against its own invariant and goals only.
