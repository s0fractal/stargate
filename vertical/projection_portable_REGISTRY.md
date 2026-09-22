# Pre-registration: portable projection verification (PR-04)

Written before the transport exists. Not edited after the run.

## The claim

A projection check can be handed to another participant as a directory and re-run
offline with `python -I -S replay.py`, with no checkout, no network and no founder
service, and it gives the same report as `sg projection-check`. The directory
carries bytes; every identity that decides the outcome is the recipient's.

## What travels

`sg unpack --expect-kind projection PROJECTION --certificate CERTIFICATE --output DIR`
writes, without overwriting anything:

| file | what it is |
| --- | --- |
| `projection.json` | the projection bytes, unchanged |
| `certificate.json` | the certificate bytes, unchanged |
| `projection-checker.json` | the six-file verifier closure as a canonical source map |
| `replay.py` | the one offline launcher, byte-identical to `src/replay.py` |
| `LICENSE`, `README.txt` | text |

The kind is the caller's (`--expect-kind projection`), never read from the packet.
Unpacking checks structure only (both readers), and refuses a certificate that names
a machine checker other than this installation's, as `evidence` unpacking already
does. Unpacking is not verification and reports no verdict.

## Offline run

```sh
python -I -S replay.py projection.json --projection --expect-model MODEL_ID \
  --expect-checker MACHINE_CHECKER_ID --expect-projection-checker PROJECTION_CHECKER_ID
```

* `--projection` is the recipient's mode flag; it requires all three anchors, and
  `--expect-projection-checker` is refused without it.
* The launcher reads `projection-checker.json` (at most 1 MiB; the map is 41 609 bytes
  today), requires exactly the six names of the verifier closure, hashes the map and
  compares it with `--expect-projection-checker` **before** loading any of it. A
  difference is `projection_checker_unavailable`/3 and nothing is executed.
* Only those six sources are loaded, from the map, never from disk; `certificate.json`
  is read from the directory, the projection from the path given.
* Exit codes and report are those of `projection_check.check`. No `--output`.
* Without `-I -S` the launcher refuses to run, as it does for every mode.

## Anchoring

`ProjectionCheckerID` becomes a fourth closure in `ANCHORS.md` and in
`tools/anchors.py`: **Projection checker**, with the launcher digest in the same row.
The launcher changes (a new mode), so the launcher digest of this source changes for
every closure.

The rows labelled `checker-ab72a8025a56` were never tagged; they describe the
unpublished candidate that builds 42–44 left in `main`. They are updated in place —
new launcher digest, one more closure row — the same way `checker-b4eee031f709` was
replaced in #50. The label stays, because the label is derived from the machine
proof checker, which does not change.

That exposes a gap this PR does not close: a snapshot label derived from one of four
digests cannot tell two snapshots apart that share a machine checker. Once
`checker-ab72a8025a56` is tagged, the next launcher or projection-checker change
has no free label. It is recorded as an open decision, not solved here.

## Expected outcomes

1. Local `sg projection-check` and the offline run on the unpacked directory: both
   `conforms`/0, reports equal field for field.
2. One cell flipped in `projection.json`: offline `mismatch`/4 with the same witness
   as `sg projection-check`.
3. One byte of `projection_check.py` changed inside `projection-checker.json`:
   `projection_checker_unavailable`/3, and the changed code never runs (a marker it
   would write does not appear).
4. `certificate.json` changed (one bit of its JSON flipped to break canonical form):
   invalid/2.
5. `compiler.py`, `kernel.py`, `lab.py`, `machine.py`, `projection.py`, `search.py`,
   `cli.py`, `sitecustomize.py` and a `stargate/` package, each writing a marker if
   imported, placed next to `replay.py`: the run still conforms and no marker appears.
6. `python replay.py …` without `-I -S`: refused, non-zero, no report.
7. `--expect-projection-checker` without `--projection`, and `--projection` without
   `--expect-projection-checker`: usage error, exit 2.
8. `sg unpack --expect-kind projection` without `--certificate`: invalid; with a
   certificate for another machine checker: refused; into an existing directory:
   refused, nothing overwritten.
9. `tools/anchors.py --check`: `established` with four closures. The table with the
   Projection checker row removed from `checker-ab72a8025a56`: refused.
10. Machine checker, lab runtime and experiment controller unchanged;
    `vertical_baseline --check` established. The launcher digest changes, on purpose.

## Control (G8)

A launcher with exactly the projection-map digest comparison removed runs a
`projection-checker.json` whose `projection_check.py` answers `conforms` for
everything, and the flipped-cell projection then conforms. The real launcher
returns `projection_checker_unavailable`.

## What this will not establish

That the recipient's three identities are the right ones: they must come from
somewhere other than this directory (a trusted checkout, a tag). That Python,
its standard library or the host are honest. That the directory is complete: a
recipient given only part of it gets an error, not a verdict.

---

# Second registration: composite snapshot identity (after review of #62)

Written after the review chose the rule and before it is implemented; the first
registration above is left as written, including its "open decision" paragraph, which
this section answers.

## The rule

A snapshot's name is derived from **everything it anchors**:

    composite = SHA-256 of the canonical JSON object
                {"Machine proof checker": …, "Boolean lab runtime": …,
                 "Experiment controller": …, "Projection checker": …,
                 "Offline launcher": …}
    label     = "snapshot-" + composite[:12]

* `tools/anchors.py --tag` prints the label of this source; `--check-tag NAME`
  refuses any other name (`tag_not_derived_from_snapshot`).
* `--check` still requires exactly one snapshot to describe this source, and that
  snapshot's label must be the derived one; any other label for it — including the
  legacy `checker-ab72a8025a56` — is refused (`snapshot_label_not_derived_from_digests`).
* Every `snapshot-…` label anywhere in the table must equal the composite of its own
  rows (all five closures present, one launcher digest). A label that does not is
  refused (`snapshot_label_not_derived_from_its_rows`), whether or not it matches
  this source. Two snapshots that share a machine checker therefore coexist under
  different names.
* `build-37`, `build-38` keep their names as history; they never match this source.
  No `checker-…` row remains: `checker-ab72a8025a56` was never tagged, so its rows
  are relabelled rather than kept as a second name for the same bytes.

## Expected outcomes

1. `--tag` = `snapshot-` + the first 12 hex of a composite the test computes itself.
2. Changing only one of the five digests — each of the four closures, and the
   launcher alone — changes the label. Five of five.
3. The committed table plus a second, self-consistent snapshot with the **same machine
   checker** and a different projection checker: `established`, and the snapshot
   reported is this source's derived label. Exactly one snapshot matches.
4. The current rows relabelled `checker-ab72a8025a56`: refused, exit 4.
5. An extra row set labelled `snapshot-000000000000` whose rows do not hash to it:
   refused, exit 4, even though it does not describe this source.
6. `--check-tag checker-ab72a8025a56`: refused.
7. Every earlier anchor-gate test that named the `checker-` rule is moved to the new
   rule, and says so in its name.

## Control

The red commit exposes `snapshot_label(digests, launcher)` answering with the old rule
(`checker-` + machine checker). Outcomes 1–6 must fail against it on their assertions.
