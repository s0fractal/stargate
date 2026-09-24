# Source snapshots and offline anchors

Choose this table from an independently trusted repository snapshot, not from an
incoming proof. A hash binds bytes, not correctness. Tags below are source
checkpoints, not frozen temperatures, signed approvals or package releases.

`build-37` points to reviewed merge `4ff8ba6502e02e95f1d49c1d36dd14e3e4375be3`.
`build-38` points to reviewed merge `5b1f2ef6c15f45705bb8da062b2aaf4930e130e2`.
Builds 39–41 add a local executor and repair producer outside these closures; all
four anchors remain identical to build-38.
Build 42 adds the optional `live_goals` obligation, which changes the proof checker
and the lab runtime on purpose, and raises the step ceiling to 8384; the offline
launcher changes with it, because it now takes its default quota from the checker it
loads. Build 43 adds the `projection-1` producer and build 44 the projection verifier,
a separate closure (the machine checker closure plus `projection_check.py`) whose
identity `sg projection-checker` prints. Build 45 anchors that verifier as a fourth
closure, **Projection checker**, and gives the launcher a `--projection` mode.
Build 46 adds the fixed Python table runtime outside every anchored closure; the
snapshot and all five digests are unchanged, and the runtime carries its own digest in
`RUNTIME.json`.

`snapshot-60fcd3fcb072` describes build 47: the world-rules contract changes the proof
checker (and through its closure the projection checker) and the lab runtime; the
controller and the launcher do not. It is an untagged PR candidate until the reviewed
merge is tagged. `snapshot-a4b5fdb9b8fe` describes build 45 and stays as history. It is an untagged PR candidate, not a
published checkpoint, until that tag exists; the tag is published against the reviewed
merge commit, after review, never before. Its rows were first written under the older
rule as `checker-b4eee031f709` and then `checker-ab72a8025a56`; neither was ever
tagged, so they are relabelled here rather than kept as a second name for the same
bytes.

| Snapshot | Closure | Source SHA-256 | Launcher SHA-256 |
| --- | --- | --- | --- |
| `build-37` | Machine proof checker | `b3abd95bd5bc0e485b48cee53d767dcd46c67044622c057a6b1f39ab455caca2` | `9fc07ff6b0c96e2750b64c5c56a46635c2dfab5d7f01d5619a248af0aa507645` |
| `build-37` | Boolean lab runtime | `682aaf5e008282135e4b2c8551ab25c4b434e3da7079f671cabfc0c0633df7df` | `639f1f3a9f3ebc93476f54e7a628a7a684a3492daa2029e62afcb6888f4366df` |
| `build-37` | Experiment controller | `6eacd02c2d6eb6b1602906cf9a473253b163173411e34cb6e6cab989c2d3033a` | `76787a0aa37644eadc1ec2c564877bda983a23b41de8ee1cb432ffb6ecc236fb` |
| `build-38` | Machine proof checker | `c06c1384f3b0c890ed9105da68a3212183939e8165b56950ff5629d84fabdd05` | `da59473debe6d255a8500527337963620012485101a192a19e94c46da7334a6b` |
| `build-38` | Boolean lab runtime | `3aa9144d5e786873d9d5578444b8f3dc95cc51f2f62381149fddc69e3c4acd12` | `da59473debe6d255a8500527337963620012485101a192a19e94c46da7334a6b` |
| `build-38` | Experiment controller | `8acd80175b60ed4e4cc2646cdb95ea2ff245e7fbc0f01208388947ae6cfe89c4` | `da59473debe6d255a8500527337963620012485101a192a19e94c46da7334a6b` |
| `snapshot-a4b5fdb9b8fe` | Machine proof checker | `ab72a8025a564c067f6d3a8551775733a8153ef696d1942a1f1b80e4afe107cd` | `7e2b854bb2a84419a1d69ef0d54c76e258a5b609a3acdb943b27607e31d0be75` |
| `snapshot-a4b5fdb9b8fe` | Boolean lab runtime | `cb9d30cea2b59ca84e96af10aedf0ea81df35fa5eccc22c3f24dd2d313ab4e35` | `7e2b854bb2a84419a1d69ef0d54c76e258a5b609a3acdb943b27607e31d0be75` |
| `snapshot-a4b5fdb9b8fe` | Experiment controller | `8acd80175b60ed4e4cc2646cdb95ea2ff245e7fbc0f01208388947ae6cfe89c4` | `7e2b854bb2a84419a1d69ef0d54c76e258a5b609a3acdb943b27607e31d0be75` |
| `snapshot-a4b5fdb9b8fe` | Projection checker | `392c11b3683dc1e9d93d708c46012600503c3ea495aaa666221d5e27cc20e4a4` | `7e2b854bb2a84419a1d69ef0d54c76e258a5b609a3acdb943b27607e31d0be75` |
| `snapshot-60fcd3fcb072` | Machine proof checker | `d425682ebb142a03021c13de63c8443dfd06c07f68ab1624a63df858e50b43fa` | `7e2b854bb2a84419a1d69ef0d54c76e258a5b609a3acdb943b27607e31d0be75` |
| `snapshot-60fcd3fcb072` | Boolean lab runtime | `a4f9e6541b24a5ed8bd2c2cd9072325118f87ba9e8eeb1c6583801ef497abdab` | `7e2b854bb2a84419a1d69ef0d54c76e258a5b609a3acdb943b27607e31d0be75` |
| `snapshot-60fcd3fcb072` | Experiment controller | `8acd80175b60ed4e4cc2646cdb95ea2ff245e7fbc0f01208388947ae6cfe89c4` | `7e2b854bb2a84419a1d69ef0d54c76e258a5b609a3acdb943b27607e31d0be75` |
| `snapshot-60fcd3fcb072` | Projection checker | `80a23b477b853dea066ce1cc40eec5f37ed74388fc42ddfbc3e82e01dfa0c6d7` | `7e2b854bb2a84419a1d69ef0d54c76e258a5b609a3acdb943b27607e31d0be75` |

For a machine proof choose its model ID separately; for histories choose the root,
for changes/repairs the parent. Runtime or checker identity does not identify the
question. Old artifacts keep their original pins; no automatic migration occurs.

Every snapshot from now on is named after everything it anchors: `snapshot-` plus the
first twelve hex of the SHA-256 of the canonical JSON object that maps each of the four
closures, and `Offline launcher`, to its digest (`python tools/anchors.py --tag`). A
change to any one of them — the projection checker or the launcher alone included — is
a new name, and two snapshots that share a machine checker coexist. Every `snapshot-`
label in the table must be the composite of its own rows. `build-37` and `build-38`
predate the rule and keep their names; `checker-c06c1384f3b0`, the only tag of the
older `checker-` rule, points at build-38's checker. CI recomputes all five digests on every push and pull request and
refuses a table that no single snapshot describes — including a table where each
digest is present but under different snapshots — with
`python tools/anchors.py --check`; on a tag it also checks the tag name. The gate is
outside every closure and compares this repository against itself: it catches a table
that was not updated, not a table that is untrustworthy.

Recompute source IDs with `sg certificate-checker`, `sg experiment-controller`,
`sg projection-checker`, or `sg lab-inspect WORLD`. Exported `replay.py` is hashed as raw UTF-8 file bytes.
Every current export uses the same launcher, but loads only its selected closure.
