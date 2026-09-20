# Stargate

A portable experiment can carry its rules, evidence and an independently checkable
continuation. A participant needs no founder key to propose or check a model change.

**Build 41 · 32K draft.** Contracts may change incompatibly. A tag records a source
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

## Find a repair instead of supplying one

The two-sample interlock in `examples/interlock.json` remembers the previous
`request` as `armed`. Its broken `open = request || armed` can leave the output
open after the request is withdrawn. Safety requires `open` to imply `armed`;
the goal requires an open state to remain reachable, ruling out a frozen-off fix.
This is a synchronous Boolean model, not a validated hardware controller.

```sh
sg machine-create examples/interlock.json --output interlock-world.json
MACHINE=$(python -c 'import hashlib; print(hashlib.sha256(open("interlock-world.json","rb").read()).hexdigest())')
sg repair-search interlock-world.json --expect-machine "$MACHINE" --output interlock-repair.json
```

The existing one-rule mutation generator finds `open = request && armed` on its
third attempt. Search proves the original defect, produces a candidate certificate,
and rechecks the complete repair with the small checker before writing the existing
repair packet. That packet works with `certificate-repair-check`, offline `--repair`
and `model-apply` below. No search code is needed to check or apply it.

`found` exits 0 and writes a packet; `not_needed` (already healthy) and
`neighborhood_exhausted` exit 4; unfinished work exits 3; checker failure exits 1;
invalid input exits 2. Refusals write no packet. Candidate quota exhaustion is
unfinished even if every attempted candidate was refuted: untried candidates remain.
An unfinished candidate is skipped, not refuted; exhaustion after any unfinished
candidate is also 3. The finite one-edit neighborhood is neither complete synthesis
nor a minimal-repair guarantee. Search does not write Git; applying remains a separate
explicitly scoped operation, suitable for chaining in a script with `set -e`.

### Let the counterexample guide a coupled repair

After the Peterson walkthrough, its generated `broken-world.json` can be searched:

```sh
MACHINE=$(python -c 'import hashlib; print(hashlib.sha256(open("peterson-demo/broken-world.json","rb").read()).hexdigest())')
sg repair-search peterson-demo/broken-world.json --expect-machine "$MACHINE" \
  --strategy trace --max-candidates 32 --output peterson-demo/discovered-repair.json
sg certificate-repair-check peterson-demo/discovered-repair.json \
  --expect-model "$MODEL" --expect-checker "$CHECKER" --output peterson-demo/discovered-certificate.json
```

`one-edit` remains the default baseline. `trace` walks the counterexample backward,
prioritizes upstream state outside the invariant, and proposes at most eight
compatible compound-subtree exchanges per rule before the original neighborhood.
Every rule and every old candidate remains in the stream; a quota may stop before
reaching them. The ranking is a heuristic, not proof of where the bug lives.

Candidates replay saved event sequences with their own recomputed states. Every
screening rejection is also checked as a negative proof. Passing an old trace still
requires full analysis and the final repair gate. Up to 16 distinct event traces
from proved failures are retained within the run, with no new experience format.

On this Peterson example, at the same 256-candidate limit:

| Search | Attempts | Full producer calls, including parent | Trace replays | Result |
| --- | ---: | ---: | ---: | --- |
| Original one-edit | 178 | 152 | 0 | Exhausted |
| Exchanges, ordinary rule order, no screening | 19 | 20 | 0 | Found |
| Exchanges + screening, ordinary rule order | 19 | 6 | 43 | Found |
| Backward priority + exchanges + screening | 1 | 2 | 1 | Found |

The expanded grammar makes this repair possible; ranking and screening reduce work.
These counts describe this example, not a general speed guarantee: on the thirteen
systems of [examples/zoo](examples/zoo/README.md), measured with one command,
`trace` needed **more** attempts than `one-edit` on nine of them, the same on one,
and fewer on two. Where it helps it can change the outcome rather than the cost,
and where it does not it costs extra work for the same repair. The found
transition system matches the correct Peterson program-counter model on all 64
state/event combinations. Its proof and Git application need no search implementation.

## Let the proof authorize a model commit

`model-apply` consumes an existing certified change or repair. The operator chooses
an exact base commit, branch, root-level model filename and independently trusted
checker. The packet cannot choose those permissions. No reviewer verdict is read.

After the Peterson walkthrough above, initialize a **separate local repository**:

```sh
mkdir peterson-demo/seed
python -c 'from pathlib import Path; from stargate.canonical import canon,decode; p=Path("peterson-demo"); (p/"seed/model.json").write_bytes(canon(decode((p/"broken.json").read_bytes())["model"]))'
git -C peterson-demo/seed init -b main
git -C peterson-demo/seed add model.json
git -C peterson-demo/seed -c user.name=Demo -c user.email=demo@localhost commit -m 'Initial model'
git clone --bare peterson-demo/seed peterson-demo/models.git
BASE=$(git --git-dir=peterson-demo/models.git rev-parse refs/heads/main)
sg model-apply peterson-demo/repair.json --repository peterson-demo/models.git \
  --ref refs/heads/main --model-path model.json --expect-commit "$BASE" \
  --expect-checker "$CHECKER"
git --git-dir=peterson-demo/models.git show refs/heads/main:model.json > peterson-demo/applied-model.json
python -c 'from pathlib import Path; from stargate.canonical import canon,decode; p=Path("peterson-demo"); assert (p/"applied-model.json").read_bytes()==canon(decode((p/"peterson.json").read_bytes())["model"])'
```

Exit 0 / `applied` means the branch was atomically advanced to a commit whose only
file change is the verified model, with the exact expected parent. A stale base
(including a race during checking) gives `base_changed` / 4; a verified no-op gives
`unchanged` / 4. Neither advances the branch. Incomplete checking or an unavailable
checker gives 3; invalid input/proof gives 2; repository operation failure gives 1.

The executor supports bare repositories only. It uses Git objects and compare-and-swap,
without checkout, merge drivers or hooks. It ignores inherited `GIT_*` settings and
replace objects. A failed final update can leave unreachable objects for Git GC.
The local repository/config, filesystem permissions, Git and Python are trusted;
this is not a sandbox for a hostile repository. A later authorized writer can move
the branch again. Keep the original proof packet: the commit records its SHA-256,
not its contents. The report is not a signed authorization token.

This applies a model change, not arbitrary Python PRs or a GitHub merge. The
certificate proves the model contract; it does not prove its translation into
production code. The executor is outside the unchanged five-file proof checker.

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
