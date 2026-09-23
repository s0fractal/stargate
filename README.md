# Stargate

Stargate checks proofs about small state machines, and nothing else. A model is a few
Boolean state bits, at most two event bits and a rule per bit; a proof is a finite
certificate or a refutation that a small checker re-verifies without trusting whoever
produced it. A certified model can then be written out as a canonical transition table
that a fixed runtime executes by lookup.

**Build 46 · 32K draft.** Contracts may change incompatibly. The checker digests are in
[ANCHORS.md](ANCHORS.md); a tag records a source snapshot, not a certified checker.

## One real case: warrant's MCP sealing proxy

`warrant-mcp` sits between an MCP host and a server and seals every `tools/call` result
into an evidence pack. [examples/mcp-proxy](examples/mcp-proxy/REGISTRY.md) models how it
tracks one request id: what the server still owes, whether the proxy holds a record,
whether the id is marked ambiguous. The invariant says the proxy never loses track of a
call it forwarded. Local setup, not run by the README check (CI installs the wheel
itself): `python -m pip install -e .`. Then, from this directory:

```sh
W=$(mktemp -d); S=examples/mcp-proxy/specs
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

Running this table inside warrant is a **proposed integration, not adopted**: the
change that pins it by digest in warrant's own source is under review there, split into
three pull requests ([state](examples/mcp-proxy/RESULTS.md#the-warrant-side)); warrant's
`master` still runs its old bookkeeping.

**Where the proof ends.** Two places, both found by this case:

* The model is one request id. The review of the warrant change found a `tools/call`
  with **no** id — the server may run it, nothing can be paired with it — and the model
  had no bit that could see it. A fix is proposed in warrant, not adopted; the model
  did not change.
* A repair may edit every rule, including the server's. The bounded search "repairs"
  today's model by making the server owe nothing, and the checker accepts it:

```sh
expect "$(sg repair-search $W/current.machine --expect-machine $CURRENT \
  --output $W/search.json | field '["status"]')" found
python -c 'import json,sys; n=json.load(open(sys.argv[1]))["candidate"]["model"]["next"]; print(n["calls.one"].split("check ")[1])' $W/search.json
rm -rf "$W"
```

Sound for the contract the checker has, and a change to the wrong side of the system: a
certificate does not say which rules are the world. Neither is fairness, time,
concurrency or the correspondence between a model and code proved; that last one is
evidence (tests on both sides), not proof. [RESULTS.md](examples/mcp-proxy/RESULTS.md)
has every number, and `python integration/mcp_proxy_vertical.py` reruns them.

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
