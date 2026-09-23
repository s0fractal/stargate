# Results: the model gate as a GitHub App (PR-09b-App acceptance)

Measured on 2026-09-23 on this repository, `main` `3866d75` (#72 merged), App
`s0fractal-stargate-model-gate` (App ID 5041755). The pre-registration is
[MODEL_GATE_APP.md](MODEL_GATE_APP.md); it is not edited. Probe pull requests were closed
unmerged and their branches deleted; statuses stay on the commits
(`GET /repos/s0fractal/stargate/commits/{sha}/statuses`).

| step | probe | head | measured | verdict |
| --- | --- | --- | --- | --- |
| 1 attribution | #73, valid change | `500e32e` | `pending` 04:29:14, `success (verified)` 04:29:15, creator `s0fractal-stargate-model-gate[bot]` (type Bot). The App was installed and minted its token | **pass** |
| 2 key isolation | #74, a PR workflow with `environment: model-gate-publisher` that would print only present/absent and try to mint a token | `43af1ab` | job refused before any runner, 0 steps: *Branch "refs/pull/74/merge" is not allowed to deploy to model-gate-publisher due to environment protection rules.* The head carries only the App's own `untouched` | **pass** |
| 3 spoof, no ruleset | #75, invalid projection + a PR workflow posting `success` with `GITHUB_TOKEN` 150 s later | `c801782` | App `failure (projection_mismatch)` 04:42:26; `github-actions[bot]` `success` 04:44:42; combined `/status`: `success` | **as registered** — both statuses exist; `/status` shows the later one |
| 4 ruleset | owner | — | `protect-main` required checks += `{context: stargate/model-gate, integration_id: 5041755}`; strict on; no bypass actor | done by the owner |
| 5 spoof, with ruleset | #77 (spoof) vs #76 (control) | `45eafbb` / `016dae9` | #77: all four `check (3.x)` success, rollup shows `stargate/model-gate: SUCCESS` (the spoof, 04:52:38), App `failure (unverified)` 04:50:22 → **`mergeStateStatus: BLOCKED`**. #76: same checks, App `success (verified)` → **`CLEAN`** | **pass** |
| 6 full loop against `main` | #76 | — | needs `main` to advance; this document's merge is that advance | pending |

## Step 5 needed a second design, and the first attempt does not count

The first run of step 5 used #75 and #73 marked ready. Both were `BLOCKED`, but both also
had all four `check (3.x)` **failing**: CI regenerates `guarded/*` from
`examples/mcp-proxy/proxy.json` and compares bytes, so a guarded change that only agrees
with its evidence breaks CI. The block was explained by those checks, not by the gate.
The probes were rebuilt so that everything but the gate is green: #76 changes the
`fixed` variant's `ambiguous` rule to a logically equivalent text and regenerates specs,
results and `guarded/*` consistently, with a valid `certified_change` (567 tests and the
README walkthrough pass locally); #77 is the same change **without** evidence plus the
spoofing workflow. The only difference between them is the App's verdict, and the
merge state follows it.

## What this settles, and what it does not

* A status posted with a pull request's `GITHUB_TOKEN` no longer satisfies the required
  check: the rule names the App, and the App's key cannot reach a pull request's run.
* The combined `/status` and the checks rollup still show the latest status of the
  context, whichever integration wrote it (here the spoof). Readers must look at the
  merge state, not at the rollup.
* Not settled: fork pull requests (one account); a repository admin or App owner, who can
  change the rule, the environment or the key; GitHub's enforcement beyond these probes.
