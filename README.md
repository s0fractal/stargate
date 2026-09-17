# Stargate

One Python system for content-addressed computation and verifiable records.
Working successor to Sigma-Glyph and Warrant; CLI aliases: `stargate` and `sg`.

**Current state: bootstrap, build 1, draft 32K.** Packaging and CLI work.
Evaluation, storage, signatures and record verification are not implemented.
The predecessor repositories have not been archived or changed by this bootstrap.

## Run

```sh
python3 -m venv .venv
.venv/bin/python -m pip install .
.venv/bin/sg --version
.venv/bin/stargate --help
```

From the checkout, `python3 -m stargate --version` also works.
Only help and version are available; unknown operations exit with an error.

## Contract and builds

[SPEC.md](SPEC.md) owns the version policy and the scope of the future contract.
Kelvin counts down toward a frozen semantic contract. Build numbers increase
for installable artifacts; they make no SemVer compatibility promise.
One current implementation targets one temperature. It does not accumulate
historical evaluators or implicitly reinterpret old records.
The current 32K label is a design starting point, not an adopted complete contract.

## Layout

- `stargate/kernel.py`: terms, canonical addresses, evaluator, budget, exits.
- `stargate/records.py`: signed records, verification and settlement.
- `stargate/store.py`: object persistence.
- `stargate/cli.py`: both command names.
- `tests/`: tests of implemented behavior; semantic vectors arrive with the evaluator.

## Next implementation

Review Warrant PR #80 on its exact head before reusing its S2 implementation.
Port the current evaluator and a minimal create → execute → verify → decide
flow as Stargate-owned Python code. Define the 32K contract with that flow,
including explicit version identity in canonical signed bytes. Do not import
both predecessor trees, their version registries or their governance machinery.
Preserve source attribution and applicable licenses when porting actual code.

Keep predecessor releases available for historical replay. Archive them only
after the successor flow and active internal dependencies have been checked.
This repository currently has no interoperability or migration claims.

## Test

```sh
python3 -m unittest discover -s tests -v
```
