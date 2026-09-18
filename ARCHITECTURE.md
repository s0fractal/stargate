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
