# Pre-registration: the Python table runtime (PR-05)

Written before the runtime exists. Not edited after the run.

## The claim

A `projection-1` table can be executed by a **fixed, generic** Python runtime that
only looks rows up. No transition logic is generated; no model, WPL, Boolean
evaluator or compiler is reachable from it; it offers no callbacks or hooks. The
table is the only generated semantic data.

## The runtime

`src/projection_runtime.py`, one file, standard library only (`json`, `hashlib`,
`itertools`, `pathlib`), **no import from `stargate`**. It is copied byte for byte
next to a projection; the copy runs without Stargate installed.

```python
fsm = ProjectionMachine.load('projection.json')        # or ProjectionMachine.from_bytes(raw)
fsm.step({'a': False, 'b': True}, {'e': True})          # -> {'a': ..., 'b': ...}
```

* Loading reads at most 4 193 586 bytes (`projection.MAX_PROJECTION`; the runtime
  cannot derive it, because the derivation is about WPL, which it must not know, so a
  test holds the literal equal to the producer's derived value), refuses non-canonical
  or duplicate-key JSON, and checks the full projection-1 structure: exact fields,
  1..6 / 0..2 sorted disjoint names, full Boolean assignments, no duplicate, missing or
  misplaced row. A malformed projection is refused **before** any `step`.
* `step(state, event)`: `state` and `event` must be dicts with exactly the table's
  names and Boolean values, else `ValueError` (`unknown state` / `unknown event`). The
  answer is a new dict from the one matching row. No other behaviour.
* It exposes `state_names`, `event_names`, `model`, `projection_id` (SHA-256 of the
  bytes) and `RUNTIME_ID = "python-table-1"`. It never claims the table is correct.

## Materialization

```sh
sg projection-materialize projection.json --lang python --output app/
```

writes `app/projection.json` (the same bytes), `app/runtime.py` (the runtime's bytes)
and `app/RUNTIME.json` = `{"runtime": "python-table-1", "runtime_digest": SHA-256 of
runtime.py, "projection": projection SHA-256, "model": ModelID}`; `python` is the only
`--lang`. It checks projection structure, never overwrites, and reports those four
fields. It does not verify the projection against anything and says so.

## Expected outcomes

1. For every zoo system (13, `correct` model), `step` over every row of its projection
   returns that row's `next`; Peterson: 64 of 64.
2. For every certified zoo system, the projection `conforms` (PR-03) **and** the
   runtime answers equal the rows — the runtime executes the checked table.
3. `step` with a missing name, an extra name, a non-Boolean value, or a list instead of
   a dict: `ValueError` naming state or event. Both for state and for event.
4. Malformed projections are refused at load: duplicate row, missing row, swapped rows,
   an extra field, non-canonical bytes, duplicate JSON key, more than the ceiling.
5. `projection_runtime.py` imports only `json`, `hashlib`, `itertools`, `pathlib`;
   contains no `eval`, `exec`, `compile`, `__import__`, `importlib`, `getattr`,
   `setattr`, `globals`, `pickle`, `marshal`; no function or method takes a callable.
6. Two loads of the same bytes: same answers for every row, same `projection_id`.
7. Materialize: three files, `runtime.py` byte-identical to `src/projection_runtime.py`,
   `RUNTIME.json` digests correct; the copied runtime run under `python -I -S` from the
   output directory alone gives the same answers as the installed module.
8. Machine checker, lab runtime, controller, projection checker and launcher unchanged;
   `anchors --check` and `vertical_baseline --check` established.

## Controls

* **Separation of authority** (from the plan): flip one cell. The runtime executes the
  flipped cell faithfully; `projection-check` returns `mismatch` for the same bytes.
* **G8**: with exactly the domain check removed from the loader (duplicate, missing and
  misplaced rows — one block), a projection whose row 3 is replaced by a copy of row 2
  with a flipped `next` loads; row 2's question then gets an answer from one of two
  conflicting rows, and row 3's question fails only at `step` time. The real runtime
  refuses that projection at load. (A check of order alone would prove nothing here:
  every row carries its own key, so swapped rows still answer correctly.)

## What this will not establish

That the runtime is correct: the projection verifier checks the table, not this code.
That the host calling `step` feeds it the real system's state, or acts on the answer.
That anything outside the table — timing, concurrency, I/O — follows the model.
