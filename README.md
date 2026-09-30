# Stargate

Stargate checks proofs about small state machines, and nothing else. A model is a few
Boolean state bits, at most two event bits and a rule per bit; a proof is a finite
certificate or a refutation that a small checker re-verifies without trusting whoever
produced it. A certified model can then be written out as a canonical transition table
that a fixed runtime executes by lookup.

**Build 47 · 32K draft.** Contracts may change incompatibly. The checker digests are in
[ANCHORS.md](ANCHORS.md); a tag records a source snapshot, not a certified checker.

## One real case: warrant's MCP sealing proxy

`warrant-mcp` sits between an MCP host and a server and seals every `tools/call` result
into an evidence pack. [examples/mcp-proxy](examples/mcp-proxy/REGISTRY.md) models how it
tracks one request id: what the server still owes, whether the proxy holds a record,
whether the id is marked ambiguous. The invariant says the proxy never loses track of a
call it forwarded. Local setup, not run by the README check (CI installs the wheel
itself): `python -m pip install -e .`. Then, from this directory:

```sh
W=$(mktemp -d); S=examples/mcp-owned
field() { python -c "import json,sys; print(json.load(sys.stdin)$1)"; }
expect() { test "$1" = "$2" || { echo "expected $2, got $1" >&2; exit 1; }; }
CURRENT=$(sg machine-create $S/current.json --output $W/current.machine | field '["machine_id"]')
FIXED=$(sg machine-create $S/fixed.json --output $W/fixed.machine | field '["machine_id"]')
```

**What it proves.** The model of today's proxy is refuted: exit 4, and the refutation
is a concrete trace the checker replays — the host sends `tools/call` twice with one id.

```sh
sg machine-evidence $W/current.machine --expect-machine $CURRENT --output $W/current.proof \
  > $W/refuted.json || expect $? 4
expect "$(field '["check"]["status"]' < $W/refuted.json)" verified_refutation
python -c 'import json,sys; print([s["event"] for s in json.load(open(sys.argv[1]))["claim"]["trace"]["steps"]])' $W/current.proof
```

That was a live bug in warrant: the first call vanished from the pack and the second was
sealed with the first call's result. A proof says what holds **in the model**: every
reachable state, not a sample of runs.

**How an agent proposes a repair.** A proposal is data: new rules for the bits the
proxy owns (`specs/fixed.json` marks a reused id ambiguous). It is not trusted; the
checker verifies the old defect and the new certificate together, with a model ID and
checker ID the recipient chose:

```sh
sg machine-evidence $W/fixed.machine --expect-machine $FIXED --output $W/fixed.proof > /dev/null
CHECKER=$(sg certificate-checker | field '["checker"]')
PARENT=$(field '["model_id"]' < $W/refuted.json)
sg certificate-repair-pack $W/current.proof $W/fixed.proof --output $W/repair.json > /dev/null
expect "$(sg certificate-repair-check $W/repair.json --expect-model $PARENT \
  --expect-checker $CHECKER --output $W/successor.json | field '["status"]')" verified_repair
```

**How the verified model becomes a table.** `model-project` writes the transition
function as data; a separate verifier compares every row with the certified model; a
fixed runtime (standard library only, lookup only) executes the table:

```sh
PROJ=$(sg model-project $W/fixed.machine --expect-machine $FIXED --output $W/projection.json | field '["model"]')
PCHECKER=$(sg projection-checker | field '["projection_checker"]')
expect "$(sg projection-check $W/projection.json $W/fixed.proof --expect-model $PROJ \
  --expect-checker $CHECKER --expect-projection-checker $PCHECKER | field '["status"]')" conforms
sg projection-materialize $W/projection.json --lang python --output $W/app > /dev/null
(cd $W/app && python -I -S -c 'import sys; sys.path.insert(0, "."); from runtime import ProjectionMachine
m = ProjectionMachine.load("projection.json"); idle = dict.fromkeys(m.state_names, False)
first = m.step(idle, {"host": True, "reply": False}); print(first)
print(m.step(first, {"host": True, "reply": False}))')
```

Warrant's proxy **already runs a pinned Stargate table** on `master` `ac80aee`
([merged integration](https://github.com/s0fractal/warrant/pull/84)). The stronger roots
used above explicitly protect the world rules `calls.one` and `calls.two`; only the
proxy's `pending` and `ambiguous` may be repaired. They are **new roots**, not a migration
of Warrant's pinned model. The original experiment, `guarded/*` and consumer pins keep
their exact bytes ([ownership example](examples/mcp-owned/README.md)).

**Where the proof ends.** This is one request id, not the whole proxy. Id-less calls,
event decoding, choosing the right id and recording the table's effects are code-level
obligations. The [consumer checks](docs/CONSUMER_CONTRACTS.md) exercise actual adapters
and deliberately broken ones; those traces are evidence, not model/code equivalence.

A live goal means **a path to the goal remains possible from every reachable state**.
It does not promise eventual completion for every sequence of events, fairness, a
schedule or a deadline. This matters for synthesis: the smallest safety repair sets
`ambiguous` forever, and the checker refuses it because `idle` becomes unreachable:

```sh
sg repair-search $W/current.machine --expect-machine $CURRENT --strategy synth \
  --output $W/search.json > $W/search-report.json || expect $? 4
expect "$(field '["status"]' < $W/search-report.json)" not_certified
expect "$(field '["synthesis"]["candidate_claim"]' < $W/search-report.json)" trap
rm -rf "$W"
```

The hand repair above does preserve that path. Ownership prevents the producer from
"repairing" the server's obligations; it does not make every repair useful or findable.
The frozen [original results](examples/mcp-proxy/RESULTS.md) retain the earlier weak-root
counterexample. [Current status](docs/CURRENT.md) distinguishes proof, integration,
adoption and outstanding review.

## More

* [docs/WALKTHROUGHS.md](docs/WALKTHROUGHS.md) — Peterson, live goals, repair search,
  model commits, offline replay and the other paths that used to open this file.
* [SPEC.md](SPEC.md) the contract · [ANCHORS.md](ANCHORS.md) checker identities ·
  [SURFACE.md](SURFACE.md) every command · [examples/zoo](examples/zoo/README.md)
  thirteen systems through one pipeline.

## Development

Python 3.11–3.14, one flat `src/` projection installed as `stargate`. x0 remains an
empty reserve. No mandatory legacy adapters or frozen protocol temperature.

```text
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
