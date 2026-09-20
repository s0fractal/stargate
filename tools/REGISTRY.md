# Pre-registration: the enum front-end

Written before the front-end existed and before anything below was run. Not edited
afterwards. Branch `feat/enum-frontend`, parent `16eb087` (build 41).

## What is being built

A front-end that lets a model be written over **named values** instead of bits, and
a decoder that reads bit-level states and traces back as those names. It lives in
`tools/`, produces input for `sg machine-create`, and is part of no checked closure:
the three digests must be unchanged after this change.

An enum of *k* values occupies ⌈log₂ k⌉ bits, so unless *k* is a power of two some
codes name no value. **The front-end always excludes those codes in the invariant.**
An unused code is not a state of the model, and a model that can enter one is not a
model of anything.

## Expectations

1. **Peterson over enums.** Two program counters of four values (`idle`, `want`,
   `wait`, `crit`) and a turn flag. The generated model reaches exactly the same
   states as the hand-written `examples/peterson_repair.py`: **20** for the correct
   variant, decoded to the same set of named states. The broken variant (each
   process claims the turn) is refuted with a **6**-step trace.
2. **A three-value enum.** A traffic light of `red`, `green`, `yellow` takes two
   bits and leaves one code unused. The generated invariant contains the exclusion.
3. **Control for the obligation.** A hand-built bit-level model that drives the
   light into the unused code is **refuted** against the generated invariant, and
   **certifies** once the exclusion is removed from the front-end. Both directions
   are required: a clause that nothing can violate would prove nothing.
4. **Measurement, not a prediction.** With and without the exclusion, run
   `repair-search` on a broken light and record what each returns. I expect the
   exclusion to matter here — a repair is free to park the machine in a code that
   names nothing — but I am not predicting the numbers, and whatever comes out is
   reported.

## What this will not establish

Nothing about enums as a modelling method, and nothing the checker does not already
check. The front-end emits text; if it emits the wrong text, the checker will
certify the wrong model faithfully. The decoder is a reading aid for humans: it has
no authority over any verdict.
