# Enum front-end

Models here are bits. A program counter of four states, a light of three colours or
a counter of three values has to be spelled as bits by hand, and the bit pattern
that names nothing has to be excluded by hand too — or it is not excluded at all.

`enum_frontend.py` lets the model be written over named values and compiles it to
the same `boolean-machine-1` input `sg machine-create` already takes. It is in no
checked closure: the proof checker, the lab runtime and the experiment controller
are byte-identical before and after this directory existed.

```sh
python tools/enum_frontend.py tools/peterson-enum.json --output peterson-spec.json
sg machine-create peterson-spec.json --output peterson-enum-world.json
MACHINE=$(python -c 'import hashlib; print(hashlib.sha256(open("peterson-enum-world.json","rb").read()).hexdigest())')
sg machine-check peterson-enum-world.json --expect-machine "$MACHINE"
```

That prints `"status": "established"` with `"checked_invariants": 20` and exits 0.

## What is checked about it

`tests/test_enum_frontend.py`:

* **It reproduces a model written by hand.** Peterson over two four-value program
  counters and a turn flag reaches exactly the 20 states of
  `examples/peterson_repair.py`, compared after decoding back to names, and its
  broken variant is refuted with the same six-step trace.
* **Unused codes are excluded, always.** Three colours take two bits; the fourth
  code names nothing, and `!(light_0 && light_1)` is part of every generated
  invariant.
* **The exclusion can fail, and does.** A model that drives the light into that
  code is refuted, and the decoder reports the endpoint as `unused_code` instead of
  inventing a colour. With the exclusion removed, the same model certifies. Both
  directions are asserted: a clause nothing can violate would prove nothing.
* **The exclusion is what leaves something to repair.** On that model
  `repair-search` finds a repair at 7 attempts; with the clause removed the same
  search answers `not_needed`, because without it there is no defect to see.

## A repair that satisfies the contract and nothing more

The repair found above parks the light in `green` forever: `light_1 = c && light_1`
means the machine never leaves the second colour. It certifies, because safety holds
and both declared goals are reachable from the initial state. Measured against the
`live_goals` obligation of the separate live-goals branch, the same repaired model
is refuted, with the trap `{light: green}`.

That is not a defect of the search. It is what the declared contract asked for.

## What this does not establish

Nothing about enums as a modelling method, and nothing the checker does not already
check. The front-end emits text; if it emits the wrong text, the checker will
certify the wrong model faithfully. `first match wins` is the transition semantics —
guard *j* applies only where no earlier guard does — and a spec whose guards were
meant to be exclusive is not checked for that. The decoder is a reading aid: it has
no authority over any verdict, and it reports an unused code rather than hiding it.
