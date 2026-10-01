"""Compare a trusted Warrant source export with a fixed-policy Python alternative."""
import argparse
import ast
import hashlib
import importlib.util
import itertools
import json
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from integration import warrant_adapter as harness
from direct import DirectMachine


def compare(root):
    started = time.perf_counter()
    impl = root / 'impl'
    for name, digest in harness.PINS.items():
        if hashlib.sha256((impl / name).read_bytes()).hexdigest() != digest:
            raise ValueError('source differs from pinned experiment: ' + name)
    source = (impl / 'warrant_mcp.py').read_text()
    tree = ast.parse(source)
    projection_node = next(n for n in tree.body if isinstance(n, ast.Assign)
                           and any(isinstance(t, ast.Name) and t.id == 'TABLE_PROJECTION'
                                   for t in n.targets))
    projection = ast.literal_eval(projection_node.value)
    spec = importlib.util.spec_from_file_location('pinned_runtime', impl / 'warrant_mcp_table.py')
    runtime = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(runtime)
    table = runtime.ProjectionMachine.from_bytes(projection)
    direct_source = Path(__file__).with_name('direct.py').read_text()

    def differences(machine):
        rows = []
        for state_bits in itertools.product((False, True), repeat=4):
            state = dict(zip(table.state_names, state_bits))
            for event_bits in itertools.product((False, True), repeat=2):
                event = dict(zip(table.event_names, event_bits))
                if machine.step(state.copy(), event.copy()) != table.step(state, event):
                    rows.append(dict(state=state, event=event))
        return rows

    def effects(candidate_source):
        # The adapter's test seam accepts a transition object. Only this experiment
        # overrides loading; the shipped digest and parser checks are not replicated.
        return harness.observe(source + '\n' + candidate_source +
                               '\nload_table = lambda: DirectMachine()\n',
                               impl / 'warrant_mcp.py')

    delta = differences(DirectMachine())
    original = harness.observe(source, impl / 'warrant_mcp.py')
    candidate = effects(direct_source)
    if delta or original != candidate or harness.mismatches(original):
        raise AssertionError('candidate transition/effect mismatch')
    mutations = {
        'end_does_not_reset': (
            'ambiguous, one, two, pending = False, False, False, False', 'pass'),
        'duplicate_not_ambiguous': ('ambiguous or pending, True, one',
                                    'ambiguous, True, one'),
    }
    controls = {}
    for name, (old, new) in mutations.items():
        if direct_source.count(old) != 1:
            raise AssertionError('mutation site changed: ' + name)
        changed = direct_source.replace(old, new)
        namespace = {}
        exec(compile(changed, '<deliberate-mutant>', 'exec'), namespace)
        failures = differences(namespace['DirectMachine']())
        failed_scenarios = harness.mismatches(effects(changed))
        if not failures:
            raise AssertionError('transition mutant survived: ' + name)
        if name == 'end_does_not_reset' and failed_scenarios:
            raise AssertionError('expected scenario blind spot changed')
        if name == 'duplicate_not_ambiguous' and 'duplicate' not in failed_scenarios:
            raise AssertionError('effect mutant survived')
        controls[name] = dict(different_rows=len(failures),
                              first_witness=failures[0], failed_scenarios=failed_scenarios)
    loader = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == 'load_table')
    lines = source.splitlines(keepends=True)

    def size(raw):
        return dict(bytes=len(raw), physical_lines=len(raw.splitlines()))

    return dict(
        status='equivalent_on_boolean_domain_and_six_scenarios',
        pins=harness.PINS, projection_sha256=hashlib.sha256(projection).hexdigest(),
        direct_sha256=hashlib.sha256(direct_source.encode()).hexdigest(),
        transitions=64, scenarios=sorted(candidate), controls=controls,
        footprint=dict(runtime=size((impl / 'warrant_mcp_table.py').read_bytes()),
                       embedded_projection_assignment=size(''.join(lines[
                           projection_node.lineno-1:projection_node.end_lineno]).encode()),
                       projection_payload_bytes=len(projection),
                       loader=size(''.join(lines[loader.lineno-1:loader.end_lineno]).encode()),
                       candidate=size(direct_source.encode())),
        elapsed_seconds=time.perf_counter()-started,
        scope='valid Boolean inputs; actual adapter with effect spy; not loader parity or signing')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--warrant-root', type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(compare(args.warrant_root.resolve()), indent=2, sort_keys=True))
