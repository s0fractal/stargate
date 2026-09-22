# Pre-registration: the vertical baseline guard (PR-01)

Written before the gate exists. Not edited after the run.

## The claim

While the projection vertical is built (PR-02 … PR-10), the machine proof checker
of build 42 does not change. `vertical/baseline.json` records it:

```json
{"build": "42", "machine_checker": "ab72a8025a56…", "temperature": 32}
```

`python tools/vertical_baseline.py --check` recomputes the checker digest and the
temperature from the installed package and compares them with the file.

* `machine_checker` must equal `certificate.checker_id()` byte for byte.
* `temperature` must equal `stargate.KELVIN`.
* `build` is where the baseline was taken. Later PRs of the vertical may raise the
  build number (SPEC: an increasing build identity), so the gate requires the
  current build to be **at least** the baseline build, not equal to it. A lower
  build is refused: that is a checkout older than the baseline, not the vertical.

Exit codes follow the repository: 0 established, 2 invalid input (missing or
malformed baseline), 4 checked and refused.

## Expected outcomes

1. The committed baseline on this source: exit 0, `established`.
2. Baseline with one changed digit of `machine_checker`: exit 4,
   `machine_checker_changed`.
3. For each of the five files of the checker closure (`__init__.py`, `store.py`,
   `canonical.py`, `boolean.py`, `certificate.py`), one appended comment byte in
   the source snapshot the gate hashes: exit 4, `machine_checker_changed`. Five of
   five.
4. A change to a file outside the closure (`machine.py`, `cli.py`, this tool):
   exit 0. The gate watches the closure, not the repository.
5. Temperature 31 in the baseline: exit 4, `temperature_changed`.
6. Baseline build `"43"` against source build 42: exit 4, `build_older_than_baseline`.
   Baseline build `"41"`: exit 0.
7. Missing file, unknown field, missing field, a digest that is not 64 hex: exit 2.
8. `tools/anchors.py --check` still `established`; the checker, runtime, controller
   and launcher digests are byte-identical before and after this PR.

## Control

The red commit ships the gate as it effectively is today — a check that compares
nothing and always says `established`. Outcomes 2, 3, 5, 6 and 7 must fail against
it on their assertions. Outcomes 1 and 4 pass against it too, so they are not
evidence for the gate and are not counted.

## What this will not establish

That the checker is correct, or that build 42's checker is the right one to freeze.
The gate compares this repository with a file in this repository: it catches a
closure edit that nobody meant to make during the vertical. A deliberate re-baseline
edits the file in its own PR, which is exactly the separate decision G4 asks for.
It is not a substitute for `ANCHORS.md`, which says which digest belongs to which
snapshot.
