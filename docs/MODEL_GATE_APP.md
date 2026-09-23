# The model gate as a GitHub App (PR-09b-App): setup and pre-registered acceptance

Written before the App exists and before any App-signed status is posted. Not edited
after the run. Why: [MODEL_GATE_LIVE.md](MODEL_GATE_LIVE.md), probe 4 — a status posted
with `GITHUB_TOKEN` is indistinguishable from one posted by any workflow of the pull
request under review.

## The owner's setup (not something an agent may do)

1. **Create a GitHub App** `stargate-model-gate` under `s0fractal` (Settings → Developer
   settings → GitHub Apps → New): webhook off; repository permissions **Commit statuses:
   Read and write**, **Pull requests: Read-only**, **Contents: Read-only** (Metadata is
   implied); installable on this account only. Generate a private key.
2. **Install it on `s0fractal/stargate` only.**
3. **Create the environment** `model-gate-publisher` in this repository: deployment
   branches → selected branches → `main` only. Add the environment **secret**
   `MODEL_GATE_APP_PRIVATE_KEY` (the `.pem`) and the environment **variable**
   `MODEL_GATE_APP_CLIENT_ID`.
4. Tell the builder the App's **integration ID** (the App ID) — needed for the ruleset,
   and to recognise the App's statuses.

Then this branch can merge: `model-gate.yml` mints a short-lived installation token with
`actions/create-github-app-token` (pinned by full SHA) inside that environment and posts
only with it. The workflow's own `GITHUB_TOKEN` keeps `contents: read` and nothing else.

## Acceptance, in order (live, on this repository)

1. **Attribution.** A valid probe pull request gets `stargate/model-gate=success` whose
   creator is the App, not `github-actions[bot]`.
2. **The key does not leak to a pull request.** A probe pull request whose own workflow
   declares `environment: model-gate-publisher` does not receive the secret: its run is
   refused or the secret is empty, and no App-signed status appears.
3. **Spoof, before the ruleset.** Probe 4 again: the App posts `failure`; the pull
   request's own workflow later posts `success` with `GITHUB_TOKEN`. Expected: both
   statuses exist on the head, the combined `/status` may say `success` — that is not the
   test.
4. **The owner adds to `protect-main`** a required status check `stargate/model-gate` with
   `integration_id` = the App ID (strict policy already on).
5. **Spoof, with the ruleset.** Probe 4 again under the rule. **Expected: the pull request
   stays blocked** — the merge box and `mergeStateStatus` are the evidence, not the
   combined status.
6. **The full actuator loop against `main`.** A valid probe pull request is green; `main`
   advances; the pull request becomes behind/blocked; after "update branch" the new head
   is judged and, if valid, green again.

A failure at any step stops the sequence; it is recorded, not worked around.

## What this will not establish

That the App's key is safe from anyone with admin rights on the repository or the App;
that GitHub enforces rulesets as documented beyond what these probes observe; that fork
pull requests are handled (still needs a second account).
