# Stargate

A portable experiment can carry its rules, evidence and an independently checkable
continuation. A participant needs no founder key to propose or check a model change.

**Build 38 · 32K draft.** Contracts may change incompatibly. A tag records a source
snapshot; it does not freeze the temperature or certify the checker as correct.

## Start with a real model: Peterson mutual exclusion

Two processes share a turn bit. The example has five state bits and one scheduler
event. A broken transition gives the turn to the current process; the corrected
transition yields it to the other process. The same initial states, safety invariant
and goals apply to both. The broken model reaches simultaneous critical sections
in six steps; the corrected model has an inductive set of 20 states.

```sh
python -m venv .venv
. .venv/bin/activate
python -m pip install -e .
python examples/peterson_repair.py peterson-demo
MODEL=$(cat peterson-demo/broken-id)
CHECKER=$(sg certificate-checker | python -c 'import json,sys; print(json.load(sys.stdin)["checker"])')
sg certificate-repair-pack peterson-demo/broken.json peterson-demo/peterson.json \
  --output peterson-demo/repair.json
sg certificate-repair-check peterson-demo/repair.json --expect-model "$MODEL" \
  --expect-checker "$CHECKER" --output peterson-demo/successor.json
sg evidence-unpack peterson-demo/repair.json --output peterson-demo/offline
python -I -S peterson-demo/offline/replay.py peterson-demo/offline/repair.json \
  --repair --expect-model "$MODEL" --expect-checker "$CHECKER" \
  --output peterson-demo/replayed.json
cmp peterson-demo/successor.json peterson-demo/replayed.json
```

This proves mutual exclusion and the declared existential goals **of the model**.
It does not prove fairness, starvation freedom, real hardware memory ordering or
correct translation from another implementation. The event scheduler may choose
one process forever. The example checks a given repair; it does not synthesize it.

The commands above use the locally installed checker for a self-contained demo.
For received artifacts obtain the checker and launcher IDs independently, using
[ANCHORS.md](ANCHORS.md) and a selected source snapshot. A packet cannot authenticate
its own judge merely by containing that judge's digest.

## The canonical machine path

For durable machine results, use **proof data**, not a producer's verdict:

1. `machine-create` materializes a bounded exploration input.
2. `machine-evidence` searches and independently checks a certificate or refutation.
3. `evidence-check` checks that proof against your ModelID and checker ID.
4. `evidence-unpack` exports any existing certificate-family packet for offline checking.

An inductive certificate establishes initial inclusion, transition closure, safety,
and a path to every goal. A refutation establishes an unsafe path or a closed set
excluding a required goal. Incomplete exploration creates no proof. A certificate
may contain safe unreachable states; a goal still needs a concrete path.

A model's identity covers state, events, initial states, transition rules, invariant
and goals, independent of producer runtime and ATP. Current limits: six state bits,
two event bits, at most 64 states. The producer's MachineID additionally identifies
its runtime and budget; it is not a ModelID. ATP and edge quotas are not CPU limits.

| Operation | Existing packet | Required anchor | Successful result |
| --- | --- | --- | --- |
| `evidence-check` | certificate or refutation | model + checker | certificate/0 or refutation/4 |
| `certificate-change-check` | two certificates | parent model + checker | candidate certificate/0 |
| `certificate-repair-check` | refutation + certificate | defective parent model + checker | candidate certificate/0 |
| `certificate-history-check` | root + certificate sequence | root model + checker | final certificate/0 |

Changes and repairs preserve all contract fields except `next`. A repair proves both
the original defect and the entire candidate contract. A history rechecks every
proof and returns no tip if a tail fails. Branches may coexist; no chronology,
minimality, consensus, or privileged main branch is established. Keep the repair
packet to preserve the objection: the bare successor does not carry its provenance.

Packing commands package unchecked data. Inspecting and unpacking do not establish
claims. Output paths are exclusive. Invalid evidence is not evidence of an unsafe
model. See [SPEC.md](SPEC.md) for exact formats and quotas.

| Exit | Meaning (the report names the precise status) |
| --- | --- |
| 0 | The requested operation succeeded; packing remains unchecked |
| 1 | Operational or checker failure |
| 2 | Invalid input/evidence |
| 3 | Unfinished or unavailable verification |
| 4 | Verified refutation, failed requirement, or refused candidate, according to operation |

## One offline launcher, separate trust domains

All current exports contain identical `replay.py` bytes. It requires `python -I -S`,
checks exactly one independently selected source closure, then executes the captured
text. It never adds the received directory to the module search path or uses its
bytecode caches. Adjacent Python files do not become dependencies.

| Selected closure | Anchor | Modes |
| --- | --- | --- |
| Small machine proof checker | `--expect-checker` + `--expect-model` | certificate, `--refutation`, `--change`, `--history`, `--repair` |
| Boolean laboratory | `--expect-runtime` | transitions, properties, resumable tasks, histories, machine/composition exploration |
| Compiler experiment controller | `--expect-controller` + `--execute-runtimes` | two explicitly executed compiler subjects |

One launcher does **not** load all three closures. The proof checker excludes the
compiler, SKI, producer, exporter and launcher. Transport text changes do not change
its source identity. Python, standard library and host remain trusted. Explicit
compiler-subject execution is not sandboxed and carries the operator's privileges.

Build38 removes `machine-certify` (use `machine-evidence`) and the five specialized
proof unpack commands (use `evidence-unpack`). There are no compatibility aliases.
Existing packet formats remain; old bytes require their original pinned sources
and launcher. No implicit repinning or migration is performed.

## Other capabilities and their boundaries

These remain useful tools, but their reports do not replace machine proof data:

- `machine-check/change/search/discover/claim` and `composition-*`: bounded graph
  exploration, candidate generation, observations and synchronous product models.
  Their input envelopes still pin the producer; export certificates/refutations for
  independently checked machine outcomes. Search experience only screens proposals.
- `lab-*`, `lineage-*`: exhaustive Boolean programs (up to eight inputs), cheaper
  equivalent rewrites, property contracts, observations and resumable row tasks.
  Every imported task prefix is recomputed; progress is not trusted computation.
- `runtime-pack`, `experiment-*`: compare two compiler snapshots on an explicit
  corpus with an independent Boolean oracle. `agreement`/0 is corpus-scoped; costs
  and terms are self-reported. Two subjects can fake answers and ATP0. A negative-only
  corpus can be passed by rejecting everything. `expect: reject` is a corpus
  obligation, not a proved fact about the grammar.
- `record/policy/export/verify-bundle`: signed closed computations and source
  provenance. Recipient trust in a signer is distinct from checking a finite model.
- `require/admit/admit-all`: recipient rules for signed artifact admission, including
  locally derived size/UTF-8 facts. Admission publishes the checked staged bytes;
  it does not prove arbitrary package behavior. See `integration/` for the wheel gate.
- `case-*`: inert evidence packets. Integrity and unpacking do not replay a claim.
- `eval` and the Python continuation API: SKI computation with explicit local
  resource limits. Splitting work can cause additional resource checks and failures.

Use `sg --help` and `sg COMMAND --help` for arguments. `sg` and `stargate` are the
same CLI. [SPEC.md](SPEC.md) owns semantics; [ARCHITECTURE.md](ARCHITECTURE.md) owns
layer rules; [VISION.md](VISION.md) describes direction, not extra guarantees.

## Development

Python 3.11–3.14, one flat `src/` projection installed as `stargate`. x0 remains an
empty reserve. No mandatory legacy adapters or frozen protocol temperature.

```sh
python architecture.py
python -I -m unittest discover -s "$PWD/tests"
python integration/test_release_gate.py --with-install
```

CI builds and tests the installed wheel outside the checkout on all supported Python
versions. Tests, mutation controls and independent review are evidence about the
implementation, not proof that its specification expresses everything a user needs.
Changes to the judge require independent exact-head review before merge.

Stargate descends from Sigma-Glyph's evaluator and Warrant's signed-record work.
Historical artifacts retain their own identities; this repository does not confer
new authority on archived projects. Licence: [MIT](LICENSE).
