# One real integration: a release gate

Integrator code, not part of the Stargate contract. It answers one question —
*what does it actually take to use Stargate for something?* — by gating a real
artifact before a real action.

**The scenario.** `sigma-glyph 0.7.0` was published to PyPI on 2026-09-17. The
only evidence that the wheel was fit to install was "the publish workflow said
success". Here, an operator refuses to install it unless two signed decisions
hold about **those exact bytes**:

- a **judgment** record — the reviewer asserts `tests_passed`,
  `reviewed_by_second_party`, `!known_advisories`;
- a **bytes** record — facts the operator can re-derive locally (`!is_text`,
  `size_at_least 10240`, `size_at_most 1048576`).

Both are bound to the wheel's SHA-256 as their signed subject.

## Run it

Reviewer side (once):

```sh
sg keygen reviewer.key                      # prints the public key
sg policy rule.wpl --facts facts.json --subject sigma_glyph-0.7.0-py3-none-any.whl --key reviewer.key
sg policy bytes-rule.wpl --derive bytes-profile.json --subject sigma_glyph-0.7.0-py3-none-any.whl --key reviewer.key
sg export <object> judgment.sg.json --trust <public key>
sg export <object> bytes.sg.json    --trust <public key>
```

Operator side:

```sh
python3 integration/release_gate.py \
  --artifact candidate.whl --trust <public key> \
  --bytes-bundle bytes.sg.json --bytes-rule bytes-rule.wpl --bytes-profile bytes-profile.json \
  --judgment-bundle judgment.sg.json --judgment-rule rule.wpl --judgment-facts facts.json \
  --output-dir approved/ --install-into /path/to/venv
```

What actually happened on the real wheel:

```json
{"status": "installed",
 "artifact": {"path": "approved/sigma_glyph-0.7.0-py3-none-any.whl",
              "sha256": "c9ee47687cfed43c7abb2764e4c8f4d885dd8be4975d0cc8b5e8dc8ee7d6276a"}}
```

and the venv imports `sigma_glyph` at version `0.7.0`.

## What the gate does, and why in that order

1. **`admit` the bytes decision.** One read of the candidate feeds the digest,
   the staged copy and the derived measurements; the requirement is checked
   before anything is published. Nothing afterwards reads the candidate again.
2. **`require` the judgment decision against the admitted digest** — not against
   the candidate path, which could have changed in between.
3. **Name the admitted file from its own bytes** (`.dist-info/METADATA` and
   `WHEEL`), because `pip` refuses a wheel whose filename is not
   `{name}-{version}-{python}-{abi}-{platform}.whl` and no signed decision says
   anything about names.
4. **Install the admitted path** — forced, because `pip` skips a distribution
   whose name and version are already present — and then **read the environment
   back**: every payload member of the wheel's **ZIP** is hashed where the
   installer put it (`RECORD` is checked for agreement with those bytes before
   the install, and then not believed). The install root is resolved from
   `pyvenv.cfg` and from `python -I -S`, so no code the environment installed
   decides where the check looks. `installed` means that check passed; a mismatch is
   `install_unverified`, exit 1.

## Outcomes

| exit | status | meaning |
|---|---|---|
| 0 | `approved` / `installed` | both decisions hold for these bytes |
| 1 | `operation_error` / `install_unverified` / `environment_untrusted` | local I/O: target name taken, missing directory, install failed; the environment does not hold the admitted payload; or it runs `.pth` startup code the wheel did not bring (`--allow-startup-hooks` overrides) |
| 2 | `invalid` / `artifact_not_a_wheel` | malformed or untrusted input, or verified bytes that are not installable |
| 3 | `unverified` | material missing or unreadable — **nothing was decided** |
| 4 | `unsatisfied` | a decision was reached and it does not admit this artifact |

3 and 4 are the pair that matters: "I could not check" must never read as
"I checked and refused".

## Tests

```sh
python3 integration/test_release_gate.py                  # 11 tests, builds its own wheels
python3 integration/test_release_gate.py --with-install   # 16, incl. hostile environments
```

They cover approval and naming, a tampered artifact, an untrusted key, a missing
artifact, verified bytes that are not a wheel, a taken target name, a candidate
whose *path* name is misleading, missing and malformed second proofs (with no
staging left behind and a retry that still works), the environment readback on
its own, a `RECORD` that omits payload members, a `RECORD` that contradicts the
wheel's own bytes, and — with `--with-install` — a venv where a **different**
wheel of the same name and version was already installed, and an environment
that rewrites the installed module at interpreter startup.

## What this cost

[FINDINGS.md](FINDINGS.md) lists the twelve things I had to invent at the
boundary between verification and action — and the four that Stargate already
got right, which is why the gate is 150 lines and not a subsystem.
