# Stargate contract

Status: **32K — DRAFT, incomplete**. This file currently specifies the version
policy, not an executable evaluation or record protocol. There are no valid
Stargate records defined by this bootstrap.

## One temperature

A single Kelvin integer identifies the semantic edition: canonical data bytes
and addressing, evaluation and budget rules, canonical exits, record identity,
signature inputs, verification, fingerprints and settlement.
Internal modules have no independent protocol versions.

Start at 32K. After the first contract is defined and released, a change to any
of those semantics consumes a step: 32K → 31K → … → 0K. Changes to an unreleased
draft do not consume steps. Temperature is neither progress percentage nor a
reward for tests, and there is no deadline to reach zero.

The same temperature may receive implementation corrections to an unambiguous
contract, performance improvements and CLI changes. If a correction changes
observed results, describe the defect and affected builds/results. If the
contract itself was ambiguous or changes, lower the temperature. A test suite
alone does not establish semantic equivalence.

At 0K the semantic contract is frozen. Implementations may still be repaired to
conform to it. A semantic change requires a distinct contract identity; do not
reset the temperature under the same identity or disguise it as a bug fix.

## Identity and unsupported editions

The eventual canonical signed/hashed record envelope must identify Stargate
and its temperature. Exact encoding is deferred until the first executable
flow. Hashes of predecessor records must not be silently reused for new meanings.

A current verifier supports one temperature. It must explicitly reject an
unsupported edition before interpreting or executing its contents. It must not
skip unknown reasons, reinterpret historical data, dynamically fetch old code,
or silently route to a legacy evaluator. Older releases are separate historical
verification tools, with declared environments and no promise of perpetual
platform support. New records derived from old records receive new identities;
original signed bytes are preserved.

## Build identity

The package version is an increasing build number, initially 1. Its source of
truth is `stargate.__version__`; packaging reads it directly. The CLI reports
both build and temperature. Never replace a published artifact in place.
A result's provenance must identify the implementation build as well as the
semantic edition. Detailed receipt encoding remains to be designed.

Kelvin is not used as the Python package version, so newer packages do not sort
behind older ones. Public package-name availability has not been checked; local
installation under the working name is not a claim on an index namespace.

## Implementation boundary

Python is the only initial implementation. Filesystem layout, local operational
limits, help text and Python internals are not automatically frozen protocol
surfaces. Local resource failure must remain distinguishable from a canonical
computation result. Operational improvements must preserve signed bytes and
semantic results for successfully executed supported inputs.

Before calling 32K implemented, specify canonical encodings, evaluation costs,
exit/result distinctions, signature domains and decision rules, and exercise
one end-to-end path plus its critical failure cases. The files reserved for
these operations currently contain no implementation.

## Origin of the version approach

The policy is Stargate's adaptation, not a claim to reproduce Urbit's complete
versioning or update machinery. Urbit distinguishes Kelvin-versioned Arvo from
its separately versioned runtime:
https://github.com/urbit/docs.urbit.org/blob/master/content/user-manual/os/updates.md
