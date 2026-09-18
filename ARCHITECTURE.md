# Dependency direction before file coordinates

Status: design recommendation, not an implemented import gate or a rename plan.

The user proposed Trinity's x-prefixed flat files for Stargate. Read against
Trinity src/x6C00_audit.ts (classifyImport) and src/audit_test.ts: higher-bucket
runtime-organ imports warn; lower/equal imports are allowed. Library targets are
explicitly exempt, as are uncoordinated importers. That is a useful executable
boundary, but not a proof that every dependency follows filename order.
Black-Heart's x-prefixed Markdown provides navigation and contract addresses;
it does not by itself enforce Python imports.

## Recommendation

Keep the flat package. Adopt explicit dependency direction, then consider visible
coordinates. CLI exposure does not change this: cli.py is an outer adapter that
may call lower layers, while lower layers must never call the CLI or shell out to
sg to reach another function. External command names need not mirror filenames.

A possible ordering after separating today's cycle:

| Proposed layer | Responsibility |
|---|---|
| x0 | canonical data, addresses, constants |
| x1 | bounded evaluator and low-level storage |
| x2 | pure policy compilation, primitive signatures/records |
| x3 | record verification including policy binding, bundles |
| x4 | artifact admission, measurements, evidence packages |
| x5 | CLI adapters and application integration |

These are responsibilities, not assignments to all existing files. Actual current
imports include records -> policy (inside verify_policy) and policy -> records
(authoring); treating those modules as distinct ordered layers would be false.
A useful next architecture change is to separate pure compilation from signed
policy authoring and extract shared canonical-data helpers. It should have its
own focused review, rather than hide in the evidence-packet implementation.

For the eventual gate, inspect Python AST imports including function-local imports,
resolve relative imports, reject unknown in-package modules, and test a planted
upward edge and cycle. Declare any dynamic-import exception explicitly. An AST
check is a static boundary check, not a proof about arbitrary Python execution.
A small module-to-layer table can enforce this before renaming anything. If the
coordinates materially improve navigation, names such as x1000_kernel.py can
then expose the same checked table. Do not maintain two independent maps.

No new compatibility layer, plugin registry, directory hierarchy, hex ontology,
or layer per CLI command is needed. No filename prefix or import enforcement was
added in build 13. This document records the proposed direction and the concrete
cycle that must be resolved first.
