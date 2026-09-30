# Reproduce the consumer pilot

This is the handoff for the completed P0–P3 technical strategy. Start from a checkout
of this repository with Python 3.11–3.14. Install into a new environment:

```sh
python3 -m venv .venv
. .venv/bin/activate
python -m pip install .
python integration/reproduce.py --profile public --output public-replay.json
```

Exit 0 and `status: passed` mean every stage required by the selected profile passed.
A report path must be new; existing reports are never overwritten. Omit `--output`
to emit JSON only to stdout. The installed Python sources must match this checkout;
reinstall after changing `src/`. The runner does not download sources or submit reports.

## What each profile checks

| Profile | Inputs | Executed checks |
| --- | --- | --- |
| `public` | This repository and installed Stargate | Model identities, 18 saved delivery observations, 15 saved retry prefixes, 24 saved queue prefixes, 56 reference queue transitions, public probe hashes |
| `full` | Public inputs, Rust `rustc` on PATH, exact Warrant and authorized Sokol source roots | Public checks plus actual Warrant adapter, Sokol delivery, retry and queue harnesses; all four outputs must equal frozen bytes |

Public checks bind saved observations to models. They do not execute Sokol's private
production module or the Warrant adapter. The Warrant artifact is inventoried by hash
in the public report; its adapter is executed only in the full profile (and separately
in public CI). Public checks are not a replacement for source execution.

The full profile runs six Warrant cases with three semantic mutants; eighteen Sokol
delivery cases with four mutants; five retry sequences with fifteen prefixes and four
mutants; and four capacity-two queue sequences with twenty-four prefixes and six
mutants. Queue reference enumeration checks fourteen valid states times four events.
Counts across these overlapping suites are not counts of unique bugs or users.

## Full source replay

Obtain authorized checkouts in new directories. Warrant is public; Sokol access is
required and is not granted by Stargate. Use these exact commits:

- Warrant: `ac80aeebfba09176e7dbf0b4a4eaaec3ee343b06`.
- Sokol: `5ffaf0854158f4674a470378279a4dd4d237f9fb`.

For example, outside this checkout, with credentials already configured for Sokol:

```sh
git clone --no-checkout https://github.com/s0fractal/warrant.git warrant-replay
git -C warrant-replay checkout --detach ac80aeebfba09176e7dbf0b4a4eaaec3ee343b06
git clone --no-checkout https://github.com/ValkyrieSentinel/sokol-core.git sokol-replay
git -C sokol-replay checkout --detach 5ffaf0854158f4674a470378279a4dd4d237f9fb
```

Return to this Stargate checkout with its environment active, substitute absolute
paths, then run:

```sh
python integration/reproduce.py --profile full \
  --warrant-root /absolute/path/warrant-replay \
  --sokol-root /absolute/path/sokol-replay \
  --output full-replay.json
```

The runner checks the two Warrant input files and two Sokol input files by SHA-256
before executing them. An export containing those files also works: the replay binds
file bytes, not the surrounding Git history. Rust probes run the actual delivery
module against local test sockets; the Warrant harness substitutes an effect spy for
cryptographic signing. These are bounded integration checks, not production actions.
Missing inputs, changed pins, a child failure, missing stage evidence or changed output
bytes fail the full profile. There is no automatic downgrade to public-only success.

Sokol CI additionally tests its *current* checkout without frozen-output equality; its
separate pinned-source steps require equality. See [consumer contracts](CONSUMER_CONTRACTS.md)
for the live-versus-frozen boundary and [current status](CURRENT.md) for adoption claims.

## Reading and retaining the report

`stargate.consumer-replay.v1` records the profile, expected/completed stages, checker
identity, source manifest, installed-source fingerprint, artifact hashes, Python and
Rust versions where applicable, timestamps, elapsed time and any failure. Save the
report alongside the exact Stargate commit used (`git rev-parse HEAD`). No private
source text is copied into the report. Inspect it before sharing environment details.

Reports are unsigned observations with `authority: observation_only`. They are not
certificates, authorization tokens or inputs to the merge gate. Timestamps and elapsed
times vary; the four frozen result hashes do not. Runtime is not modelling effort,
integration effort, a speedup claim or evidence of independent demand.

The Boolean proof covers the declared bounded model. It does not prove arbitrary
Rust/Python correctness, unbounded queues, concurrent producers, crash recovery,
fairness or inevitable delivery. Additional count/order/loss oracles are checks outside
the Boolean theorem. A successful author-run replay is not an independent participant.

## Next use by an agent or participant: blank observation record

An agent or human participant can record the following alongside their report. Leave unknown
fields unknown; this template is not a completed experiment or an invitation.

- Participant's relationship to the operator and any author assistance received.
- Concrete contract/problem, model boundaries, and whether the result was useful.
- Exact Stargate commit, profile, source pins and report location/hash.
- Setup, modelling and integration time separately, including failed attempts.
- Rejected mutations, unexpected refusals/false blocks and their reproducible inputs.
- Whether the participant returned to use the tool for a second real decision.

Independent usefulness is optional evidence. Internal agent utility is now the primary
development criterion; see the [agent profile](AGENT_PROFILE.md). Wider semantics require a named
contract that cannot be represented now; a new synthesizer requires repeated failures
and a registered comparison. The completed technical pilot alone establishes neither.
