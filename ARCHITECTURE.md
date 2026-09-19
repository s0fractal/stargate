# Flat source, checked dependency direction

Build 14: Python files live directly in src/. Setuptools maps src/ to the
stargate import package; public commands remain sg/stargate. A future Rust
projection can have its own layout without requiring a Python-named source tree.
For development, install the checkout with `python -m pip install -e .` before
running tests or integration scripts. No old stargate/ source copy is retained.
Historical case packets retain their exact original stargate/ paths and bytes.

## x0 is reserved, not the current constants layer

No module is assigned to x0, and there is no placeholder implementation. It is
reserved for possible future generators of parameters such as fixed-point Q
(Q10–Q20, for example), integer cosine LUTs, or other generated data needed to
close computational cycles. No precision or generator contract is chosen now.
Existing constants stay with their current owners in the implemented layers.
Future generators require their own dependency/effect decisions; reserving x0
neither permits upward runtime imports nor implements code generation today.

## One executable layer table

`architecture.py:LAYERS` is the sole module-to-layer assignment. Run:

    python architecture.py

It prints the actual graph and exits nonzero for upward imports, cycles (including
same-layer cycles), unlisted/unknown modules, package escapes, reserved-x0 use and
explicit dynamic import calls. AST traversal includes function-local imports.
Same-layer dependencies are allowed only when acyclic. The unittest suite runs
the real graph check and controls with planted upward imports and cycles.
This is a static check, not a proof against arbitrary Python metaprogramming;
aliased/reflection-based code loading is not exhaustively analyzed.

Current separation, from lower responsibilities to higher ones:

- Canonical data, addresses, storage and reduction.
- Unsigned checks and pure compilation.
- Signed records/provenance, measurements and inert evidence data.
- Policy authoring and portable record bundles.
- Artifact admission.
- CLI adapters.

records verifies provenance through compiler; compiler executes checks without
importing records. policy authors records above both. This breaks the former
records -> policy -> records cycle without changing signed bytes or evaluator
rules. Some imported helper names remain reachable on records/policy, but there
is only one implementation of each helper and no legacy evaluator branch.

## Why coordinates are not filenames yet

Trinity's src/x6C00_audit.ts and src/audit_test.ts enforce higher-bucket warnings
for runtime-organ imports, with explicit library/uncoordinated exceptions.
Black-Heart's x-prefixed Markdown provides contract navigation. The useful shared
idea is an inspectable, executable boundary; names alone cannot establish it.

The source split and actual import gate come first. If filename prefixes are
adopted next, derive/check them against the same layer table rather than creating
a second classification. CLI commands describe user operations; they need not
mirror filenames or get one file/layer per command. Lower layers must never call
the CLI or shell out to sg to access higher functionality.

Absolute imports through `src` (including `from src...`) are rejected in scanned
package sources. `src` is a directory name, not a supported alternate package
identity. This static rule does not prevent an external caller in the checkout
from explicitly importing src; it prevents such imports from entering this
package unnoticed. Both absolute `from stargate import module` and
`from stargate.module import name` forms have positive downward and negative
upward controls, including aliasing and a function-local import.

Build 15 adds `boolean` at x2 and `lab` at x3. `boolean` has its own WPL
lexer and shunting-yard evaluator and imports no compiler or kernel code. `lab`
compares it against compiled SKI results, carries the exact runtime closure as
inert data, and constructs finite-program successors. Neither imports records,
policy, bundle or CLI. x0 remains empty.

Build 16 adds `search` at x4, above `lab`. Its generator and remembered-input
screening have no admission authority: every successful successor comes from
`lab.verify_transition`. It is outside the replay runtime closure. x0 stays empty.

Neighbor concepts used for this step (original implementation, no copied code):

- Black-Heart `cegis_kernel.py` at `3893fad4bc1cbfa6152a5cecd967c73471a38fde`:
  counterexample-guided candidate refinement and explicit inconclusive outcomes.
  We do not copy its AGPL implementation, SMT integration or observational
  equivalence pruning; finite-sample equality is not full equivalence.
- Black-Heart `docs/LIVING-LIBRARY-INTERACTION.md`, same revision: re-evaluate
  saved evidence before using it, and preserve the parent when making a successor.
- Warrant SPEC §3.1/§7 at `5c8ed0d338d88ce465c1540f195394e2ed81fa8e`:
  distinguish refusal from verdict and evidence identity from useful novelty.
  This step deduplicates exact proposal strings only; it adds no settlement rules.
- Sigma-Glyph's receipt-based reduction is already present in `kernel.py`.
  Search reuses the existing compiler/kernel path and its normal-form/ATP checks;
  it does not substitute an optimizer's predicted answer for a receipt.

Build 17 adds `invariants` at x4, depending on `lab` and `canonical`. It reuses
the established finite evaluator via self-comparison rather than adding another
evaluation path. Hypothesis discovery has no admission authority. The property
checker is included in the portable hashed closure and loaded from verified
source snapshots after `lab`; the ordinary lab module does not import it.
x0 remains empty. This extends the counterexample/refinement approach borrowed
conceptually from Black-Heart: a guessed property is a claim to recheck, not a
saved verdict to adopt. No neighboring implementation code is copied here.

Build 18 adds `lineage` at x4 above `lab`/`canonical`. The minimal history stores
one root plus ordered proposals; the existing gate reconstructs all descendants.
It deliberately excludes cached verdicts, signatures and a new admission engine.
Its checker joins the portable runtime closure, loaded from verified snapshots.
This borrows Black-Heart Living Library LI-3's re-evaluation-before-successor
principle (saved admitted flags are insufficient), without copying its code or
PDF/governance machinery. Warrant's refusal/verdict boundary remains explicit;
Sigma's receipt checks remain owned by the existing lab evaluation path. x0 is
still empty; there is no imported archive or revived retired system.

Build 19 moves pure finite property validation/assessment into `properties` at
x2 (only canonical dependency). `lab` at x3 uses it for explicit property-world
admission; `invariants` at x4 uses the same predicates for observation. This avoids
a lab -> invariants -> lab cycle. Properties belong to the anchored root, never
to a candidate's optional assertions. The snapshot loader loads properties before
lab; no new runtime, solver or network dependency is added. x0 remains empty.
The neighbor lesson applied is specification-guided candidate admission rather
than accepting a search heuristic's verdict; Sigma's receipts and the independent
Boolean oracle still own evaluation. No neighbor implementation was copied.

Build 21 adds `labtask` at x4, depending only on `lab` and `canonical`.
It transports claimed prefixes and replays them through the owned x3 lab state;
it does not deserialize state or introduce an upward lab import. The standalone
launcher includes this module after lab in its verified source snapshot closure.
CLI exposes task creation, resumption, structural inspection and unpacking.
x0 remains empty.

Build 22 adds `machine` at x4 over lab/canonical/compiler/boolean/kernel. It
checks a finite reachable graph using the existing two expression evaluators.
No kernel or language extension; x0 remains empty. Its runtime-envelope view is
validation-only, never a machine transition or emitted successor. The standalone
verified-source closure loads machine after lab, with no upward runtime import.


Build 29: composition sits at x5 above machine (x4), with CLI at x6. It translates
explicit component wiring into a private machine and independently checks the
translation against original rules. The offline runtime includes composition.py
after machine.py; machine and lab have no runtime import back to composition.
x0 remains empty.

Offline transport and replay are x6, outside all semantic source closures.
The five-file certificate checker does not import either. x0 stays empty.
