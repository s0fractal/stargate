# Pre-registration: the README vertical (PR-07)

Written before the README is rewritten. Not edited after the run.

## The claim

A stranger can understand Stargate from one real workflow without reading builds 1–46,
and every command the README shows is run by CI.

## What changes

* The first ~100 lines of README.md answer six questions, in order: what Stargate does;
  what it actually proves; how an agent proposes a repair; how the verifier checks it
  independently; how a verified model becomes a canonical projection; where the proof
  ends. The one walkthrough is the warrant-mcp vertical (examples/mcp-proxy).
* The earlier README sections move, unchanged in substance, to `docs/WALKTHROUGHS.md`.
  SPEC, ANCHORS and the registries are not touched. Those walkthroughs are **not** run by
  CI; the move says so instead of implying otherwise.
* `tools/readme_walkthrough.py` runs every ```sh block of README.md in order as one bash
  script (`set -euo pipefail`, from the repository root) and fails if the script fails or
  if it leaves the checkout changed. CI runs it after installing the wheel.
* The walkthrough needs machine specifications a reader can pass to `sg machine-create`;
  `examples/mcp-proxy/specs/{current,historic,fixed}.json` are written by
  `integration/mcp_proxy_vertical.py --write` and compared byte for byte on every run.

## Expected outcomes

1. Against today's README the runner fails: its blocks create a virtualenv, install the
   package and write `peterson-demo/` and `interlock-*.json` into the checkout.
2. Against the new README it exits 0 and the checkout is unchanged.
3. The runner itself: a README with no ```sh block is invalid input (2); a block that
   writes into the checkout fails (1) even if every command succeeds; a block with a
   failing command fails with that command's status; ```text blocks are not run.
4. Every ID the walkthrough prints is computed from command output, never pasted, and
   the refutation trace, the repair verdict, `conforms` and the runtime's answer it shows
   are the ones `examples/mcp-proxy/results.json` records.

## What this will not establish

That the README is complete or true beyond what its commands check. Prose between the
commands is read, not run.
