# One real integration: a release gate

Integrator code, not part of the Stargate contract. It answers one question —
*what does it actually take to use Stargate for something?* — by gating a real
artifact before a real action.

**The scenario.** `sigma-glyph 0.7.0` was published to PyPI on 2026-09-17. This integration focuses on the step from release evidence to an installation
action. An operator refuses to install it unless two signed decisions
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

1. **`admit_all` the bytes and judgment decisions together.** One read of the
   candidate feeds the digest, the stage and derived measurements. Both named
   requirements must hold before the core publishes the integration's temporary
   admitted copy. Nothing afterwards reads the candidate again.
2. **Retain each requirement's report.** The same admitted digest is used for
   both; the integration no longer manually composes a second `require` after
   publishing a copy for only the first decision.
3. **Name the admitted file from its own bytes** (`.dist-info/METADATA` and
   `WHEEL`), because `pip` refuses a wheel whose filename is not
   `{name}-{version}-{python}-{abi}-{platform}.whl` and no signed decision says
   anything about names.
4. **Preflight the target before publishing or starting pip.** Resolve the install
   root using `pyvenv.cfg` and `python -I -S`, then inspect root `.pth` files.
   Foreign hooks require explicit `--allow-startup-hooks`; otherwise no pip runs
   and no final wheel is published. A hook is owned by the candidate only if its
   name AND current bytes match the admitted payload.
5. **Install the admitted path** — forced, because `pip` skips a distribution
   whose name and version are already present — and then **read the environment
   back**: every payload member of the wheel's **ZIP** is hashed where the
   installer put it (`RECORD` is checked for agreement with those bytes before
   the install, and then not believed). Readback uses the root pinned before pip,
   not a fresh location supplied after installation. `installed` means that check passed; a mismatch is
   `install_unverified`, exit 1.

## Outcomes

| exit | status | meaning |
|---|---|---|
| 0 | `approved` / `installed` | both decisions hold for these bytes |
| 1 | `operation_error` / `install_failed` / `install_unverified` | local I/O or installer failure; or payload readback failed |
| 1 | `environment_unresolved` | the installation root could not be established; inspect `problems` and repair the environment/layout |
| 1 | `environment_untrusted` | foreign root `.pth` files were detected; remove them or explicitly permit them with `--allow-startup-hooks` |
| 2 | `invalid` / `artifact_not_a_wheel` | malformed or untrusted input, or verified bytes that are not installable |
| 3 | `unverified` | material missing or unreadable — **nothing was decided** |
| 4 | `unsatisfied` | a decision was reached and it does not admit this artifact |

3 and 4 are the pair that matters: "I could not check" must never read as
"I checked and refused".

## Tests

```sh
python3 integration/test_release_gate.py                  # 19 tests, 6 install tests skipped
python3 integration/test_release_gate.py --with-install   # all 19, including real installs
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

[FINDINGS.md](FINDINGS.md) lists the thirteen things I had to invent at the
boundary between verification and action — and the four that Stargate already
got right, which kept the integration outside the core protocol implementation.


## Environment boundary and hook reporting

The report names `artifact_startup_hooks` and `foreign_startup_hooks` after a
successful payload readback, plus the pre-install inventory in `startup_hooks_before`.
These inventories cover root `.pth` files only. Matching a candidate filename is
not enough to own a preexisting hook: its digest must match too. Inventory I/O
failures are operational failures, not hook names that the override can waive.

`--allow-startup-hooks` explicitly permits execution of the reported foreign
`.pth` files when pip starts. Without it, preflight refuses before that startup.
The override never bypasses `environment_unresolved`. With `--install-into`,
either preflight refusal also withholds the final approved wheel from
`--output-dir`, even though both artifact decisions passed. These reports retain
`artifact.sha256` from the admitted bytes with `artifact.path: null`: no final
copy was published, and the temporary stage was removed. Without `--install-into`,
the gate publishes the approved copy without checking an installation environment.

Candidate-owned hooks are allowed because their bytes were admitted, and are
reported by name. They may execute on a later normal interpreter startup and
change verified files. `installed` certifies the checked payload bytes at readback,
not future imports, permanent immutability, code safety, or a sterile environment.

The operator must trust the target interpreter, its standard library and pip,
and control the environment/output directories during the operation. This gate
is not a sandbox for an arbitrary interpreter or installer. The hook inventory
is not an exhaustive startup-code audit: e.g. sitecustomize/usercustomize, import
path behavior and pip configuration are not certified. A foreign-hook refusal
must not be generalized to protection from all environment code.

The supported integration target is the Unix purelib venv layout for which the
isolated interpreter and computed layout agree; exercised here on Python 3.14.
An unsupported/mismatched layout is refused before pip. This is separate from
the library's Python support claim. No rollback is promised after pip begins;
installation/readback failures may leave the admitted wheel and a modified venv.
