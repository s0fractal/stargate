# Source snapshots and offline anchors

Choose this table from an independently trusted repository snapshot, not from an
incoming proof. A hash binds bytes, not correctness. Tags below are source
checkpoints, not frozen temperatures, signed approvals or package releases.

`build-37` points to reviewed merge `4ff8ba6502e02e95f1d49c1d36dd14e3e4375be3`.
`build-38` points to reviewed merge `5b1f2ef6c15f45705bb8da062b2aaf4930e130e2`.
Builds 39–41 add a local executor and repair producer outside these closures; all
four anchors remain identical to build-38. Build 41 is an untagged PR candidate,
not a published checkpoint.

| Snapshot | Closure | Source SHA-256 | Launcher SHA-256 |
| --- | --- | --- | --- |
| `build-37` | Machine proof checker | `b3abd95bd5bc0e485b48cee53d767dcd46c67044622c057a6b1f39ab455caca2` | `9fc07ff6b0c96e2750b64c5c56a46635c2dfab5d7f01d5619a248af0aa507645` |
| `build-37` | Boolean lab runtime | `682aaf5e008282135e4b2c8551ab25c4b434e3da7079f671cabfc0c0633df7df` | `639f1f3a9f3ebc93476f54e7a628a7a684a3492daa2029e62afcb6888f4366df` |
| `build-37` | Experiment controller | `6eacd02c2d6eb6b1602906cf9a473253b163173411e34cb6e6cab989c2d3033a` | `76787a0aa37644eadc1ec2c564877bda983a23b41de8ee1cb432ffb6ecc236fb` |
| `build-38` | Machine proof checker | `c06c1384f3b0c890ed9105da68a3212183939e8165b56950ff5629d84fabdd05` | `da59473debe6d255a8500527337963620012485101a192a19e94c46da7334a6b` |
| `build-38` | Boolean lab runtime | `3aa9144d5e786873d9d5578444b8f3dc95cc51f2f62381149fddc69e3c4acd12` | `da59473debe6d255a8500527337963620012485101a192a19e94c46da7334a6b` |
| `build-38` | Experiment controller | `8acd80175b60ed4e4cc2646cdb95ea2ff245e7fbc0f01208388947ae6cfe89c4` | `da59473debe6d255a8500527337963620012485101a192a19e94c46da7334a6b` |

For a machine proof choose its model ID separately; for histories choose the root,
for changes/repairs the parent. Runtime or checker identity does not identify the
question. Old artifacts keep their original pins; no automatic migration occurs.

Recompute source IDs with `sg certificate-checker`, `sg experiment-controller`, or
`sg lab-inspect WORLD`. Exported `replay.py` is hashed as raw UTF-8 file bytes.
Every current export uses the same launcher, but loads only its selected closure.
