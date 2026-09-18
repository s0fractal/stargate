# What one real integration needed that Stargate does not give

Integrator: Claude Opus 5, 2026-09-18, against Stargate build 11 (`7abc88c`).
Subject: `sigma_glyph-0.7.0-py3-none-any.whl` as published on PyPI
(`c9ee4768…6276a`), gated before installation into a venv.

The gate works end to end: two signed decisions, an admitted copy, an install
that cannot happen unless both hold. What follows is what I had to invent at the
boundary, in the order I hit it. None of it is a defect in the implementation —
every one is a place where the product stops and the integrator starts, and the
question for the next build is which of these belong on this side of the line.

## F1. Verification is about bytes; the acting tool needs a name

`admit` published the verified bytes to the path I named, and `pip` refused them:

```
ERROR: Invalid wheel filename (wrong number of parts): 'approved'
```

Content addressing is deliberate — build 9 accepts the same bytes under any
filename — but every real consumer reads metadata from the name. So the gate
must produce a name that no signed decision covers. Taking it from the operator
would let an unsigned label ride along with signed bytes: I installed the
admitted bytes as `sigma_glyph-9.9.9-py3-none-any.whl` and pip accepted the file
(it reports `0.7.0` afterwards, because it re-reads `.dist-info` — so the lie
does not reach the installed metadata, but it does reach every resolver that
matches on filenames).

**What I did:** read `.dist-info/METADATA` and `WHEEL` out of the *admitted copy*
and link it under the name those bytes declare. The name is then a function of
verified bytes, not of input.

**What the product could do:** nothing here is exotic, and every integrator will
hit it. Either say plainly in the docs that the admitted path must be named from
the artifact's own content, or give `admit` a way to express it.

## F2. A rule is all-asserted or all-derived

A realistic release policy mixes both: *a human says the tests passed* and *the
machine confirms the artifact is the reviewed bytes of plausible shape*. Build 11
derives **all** facts in `--derive` mode and requires an exact match with the
rule's declared facts, so the two cannot live in one rule. I had to author two
records against one artifact — one asserted, one derived.

That is a workable shape, but it means the interesting policy ("reviewed **and**
measured") exists only in the integrator's head, not in any signed object.

## F3. Two requirements about one artifact need an order the tool does not enforce

With two records there is no "require both against this file" operation, and
checking twice against a *path* is a time-of-check/time-of-use hole: the file can
change between them. The only safe order is

1. `admit` the first decision — which stages the bytes, checks, and publishes,
2. `require` the second against the **admitted** file.

It works because `admit` never re-reads the source. But nothing in the CLI or
SPEC says this is the only safe composition; I derived it from reading build 10's
implementation. An integrator who ran two `require` calls against the candidate
and then copied the file would have built something that looks identical and is
not.

## F4. The derivable vocabulary cannot describe structure

`utf8`, `size_at_least`, `size_at_most` cannot say "is a zip", "is a wheel",
"declares version 0.7.0", "contains no symlinks". So the gate parses the
artifact itself — 30 lines of ordinary Python that run on verified-but-arbitrary
bytes and decide what to name them. That code is unsigned, unreviewed by the
decision, and it is exactly where the next bug will live.

I exercised the case: a decision that is fully satisfied over bytes that are not
a wheel returns `artifact_not_a_wheel`, exit 2, and installs nothing. The gate
had to invent that classification; Stargate has no vocabulary for "verified, but
not the kind of thing you asked for".

## F5. A fact name carries no meaning the tool can check

This is accepted without complaint:

```json
{"tests_passed": {"utf8": true}}
```

and produces a signed record saying `tests_passed=false` for a wheel, because a
wheel is not UTF-8. Names are prose; the profile is the meaning. A recipient who
reads the rule source sees the truth, and `require` compares rule bytes so an
operator with the right rule is protected — but a human skimming
`policy.inputs` in a verification report is not.

## F6. A gate's conclusion cannot become the next gate's input

`require` returns an unsigned, non-transferable report (correctly documented).
So my gate's verdict — "both decisions hold for these bytes" — cannot be handed
to anyone else as an object. In a pipeline of more than one step, each step must
redo the whole check or trust an unverifiable local report. This is the ceiling
on composition today, and it is the first thing I would want after this
experiment.

## F7. Nothing expires and nothing can be withdrawn

A decision about a digest is eternal. A wheel later found vulnerable stays
admitted by a record signed before the finding, and there is no expiry field, no
revocation list, and no "supersede" relation between records. For a release gate
that is the difference between a demo and a thing you would actually run.

## F8. The CLI can author derived facts; the library cannot

`sg policy --derive PROFILE` measures the artifact and signs the measured facts.
`author_policy(source, facts, store, key, …)` takes **facts**, not a profile, so
a library caller has to reproduce the CLI's composition by hand:

```python
measured = measure_subject(subject, profile)
author_policy(rule, measured["facts"], store, key, subject=measured["subject"])
```

I hit this while writing the integration's own tests. It is two lines, but they
are two lines every library consumer will write the same way, and writing them
differently (measuring one file and signing another digest) is exactly the
mistake the API could prevent.

## What worked, and is worth keeping exactly as it is

- **Exit codes carried the whole integration.** `4` (checked, requirement not
  met) versus `3` (nothing was checked) is what let the gate refuse safely
  without inventing its own vocabulary; I mirrored 0/1/2/3/4 and it fit.
- **`admit`'s single read** made the TOCTOU story tractable: I swapped the
  source during verification and the published bytes did not change.
- **Missing material stayed `unverified`, never a verdict**, at every layer I
  touched — bundle, provenance, artifact.
- **Derived facts caught a signed lie** in the shape that matters: I signed
  `is_text=true` for a wheel and the gate refused to publish.

## F9. The action's success is not the action's postcondition

Added after review. The first version of this gate ran `pip install` and treated
exit 0 as `installed`. Codex preinstalled a **different** wheel with the same
distribution and version, ran the gate with the approved one, and got
`0 / installed` from a venv that still executed the other artifact's code — pip
considers a same-version distribution already satisfied and skips.

The label was wider than the predicate: "installed" meant "the installer exited
zero". The gate now forces the install **and reads the environment back**,
hashing every payload file the wheel's `RECORD` names against what is on disk;
`installed` is that check passing and nothing else, and a mismatch is
`install_unverified` (exit 1). Dropping `--force-reinstall` now fails the test
with `(1, 'install_unverified') != (0, 'installed')` — the readback catches the
original defect even without the flag, which is why both are there.

The general shape is worth stating, because it is not specific to pip: **a gate
that ends at "the action returned success" has verified the action, not the
world.** Every integrator wiring Stargate to a real effect needs a postcondition
they can check, and Stargate's vocabulary (bytes) rarely reaches it.

## F10. A refusal must not leave an admitted file behind

Also from review: an error in the *second* decision — missing or malformed
judgment proof — left `.gate-*.admitted` in the output directory, and a missing
proof file was classified `operation_error` (1) instead of `unverified` (3).
Both are now fixed: every input is read and classified before anything is
staged, and the staged file is owned by a `try/finally` that spans the second
decision, the naming and the publication. The lesson is the same one this project
keeps learning at a different layer: the interesting paths are the ones that
refuse, and they need the same care as the one that succeeds.

## F11. A manifest inside the verified object is a claim by the object

Added after the second review. The postcondition check built its expected hashes
from the wheel's own `RECORD`. A signed decision authenticates the **whole
archive**, including a `RECORD` that contradicts it, so the artifact was choosing
what the check would check. Codex reproduced both halves through the real gate
and real pip, using a `.pth` startup hook to rewrite the installed module:

- **omission** — leave the module out of `RECORD`: it is never examined;
- **contradiction** — list the module with the digest of the *mutated* bytes:
  the lie becomes the expected value.

In both, the gate said `0 / installed` while the environment ran `VALUE=999`
from a wheel whose own bytes say `VALUE=1`.

The fix is not to read `RECORD` more carefully. Expected hashes now come from
the **ZIP members themselves**; `RECORD` is read only to refuse an internally
inconsistent wheel *before* anything is installed — every payload member must be
listed, with the digest its bytes actually have, and a disagreement is
`artifact_not_a_wheel` (exit 2), because a gate should not choose which half of a
self-contradicting artifact to believe.

Both of Codex's variants now fail against the pre-fix gate with
`(0, 'approved') != (2, 'artifact_not_a_wheel')` and pass against the fix.

**The general shape, which is the point:** *signed* does not mean *internally
consistent*. Every layer of this project has now met the same lesson wearing
different clothes — a fact name that means nothing to the tool (build 5), a
source hash that had to be recompiled rather than believed (build 7), and now a
file manifest that had to be recomputed rather than read. Anything a verified
object says **about itself** is a claim, and a checker that reads it has verified
the claim, not the thing.

A third case is worth recording because it did **not** need the fix: a wheel
whose `RECORD` is entirely truthful, in an environment whose `.pth` hook rewrites
the module at interpreter startup, was already caught — the readback hashes what
is on disk, so it reported `install_unverified`. What no after-the-fact check can
catch is an environment that mutates *after* the gate finishes. The only honest
answer there is to install into an environment the gate creates itself, and this
gate does not.

## Method note

My first failure battery reported five bogus failures because `zsh` does not
word-split unquoted parameter expansions, so a variable holding seven arguments
arrived as one. The gate was fine; my harness was not. Recording it because I
have asked for exactly this standard from the other side of these reviews.
