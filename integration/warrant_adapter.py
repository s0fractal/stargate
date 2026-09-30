"""Exercise the pinned Warrant run_proxy adapter and mutants with its unchanged table.

Actual adapter, threads, local subprocess and streams; an effect spy replaces cryptographic
sealing. This checks obligation attribution, not Warrant signing or arbitrary concurrency.
The caller provides a trusted source checkout. No network or repository mutation.
"""
import argparse
import contextlib
import hashlib
import io
import json
from pathlib import Path
import sys
import types
from unittest.mock import patch

PINS = {
    'warrant_mcp.py': 'caaaf1ce56c4caac39fe7107575955d7e1d32819f6992a2367be80be254ea1a4',
    'warrant_mcp_table.py': '4ab9224fac3605bd150cb12764424e9b5c7147c72a0e5259c2d0861f94746b1a',
}
COMMIT = 'ac80aeebfba09176e7dbf0b4a4eaaec3ee343b06'


def call(mid, tool):
    return dict(jsonrpc='2.0', id=mid, method='tools/call', params=dict(name=tool, arguments={}))


def response(mid, value):
    return dict(jsonrpc='2.0', id=mid, result=dict(value=value))


SCENARIOS = {
    'ordinary': ([call(1, 'a')], [response(1, 'A')], [('seal', 'a', 'A')]),
    'duplicate': ([call(1, 'a'), call(1, 'b')], [response(1, 'A'), response(1, 'B')],
                  [('unreturned', 'a'), ('unreturned', 'b'), ('unpaired', 1), ('unpaired', 1)]),
    'two_ids': ([call(1, 'a'), call(2, 'b')], [response(2, 'B'), response(1, 'A')],
                [('seal', 'b', 'B'), ('seal', 'a', 'A')]),
    'reverse_request': ([call(1, 'a')], [dict(jsonrpc='2.0', id=1, method='ping'), response(1, 'A')],
                        [('seal', 'a', 'A')]),
    'idless': ([call(None, 'a')], [response(None, 'A')], [('unreturned', 'a'), ('unpaired', None)]),
    'eof': ([call(1, 'a')], [], [('unreturned', 'a')]),
}


class Effects:
    def __init__(self):
        self.events, self.sealed = [], 0
        self.store = types.SimpleNamespace(root='<effect-spy>')

    def seal(self, tool, args, result, error, **kw):
        self.events.append(('seal', tool, (result or {}).get('value')))
        self.sealed += 1
        return 'record'

    def record_unreturned(self, tool, args, ts, **kw):
        self.events.append(('unreturned', tool))

    def record_unpaired(self, mid, result, error):
        self.events.append(('unpaired', mid))

    def record_failure(self, tool, exc):
        self.events.append(('failure', tool, type(exc).__name__))

    def write_manifest(self):
        pass

    def incomplete(self):
        return ['unresolved'] if any(row[0] != 'seal' for row in self.events) else []


def observe(source, path):
    adapter = types.ModuleType('warrant_adapter_under_test')
    adapter.__file__ = str(path)
    # Signing isn't invoked: only run_proxy and load_table are exercised. No installed
    # warrant module or an uncontrolled sibling implementation participates.
    with patch.dict(sys.modules, {'warrant': types.ModuleType('warrant')}):
        exec(compile(source, str(path), 'exec'), adapter.__dict__)
    table = adapter.load_table()  # the actual digest-pinned runtime and table
    output = {}
    for name, (host, replies, expected) in SCENARIOS.items():
        effects = Effects()
        server = 'import sys; sys.stdin.read(); sys.stdout.write(' + repr(
            ''.join(json.dumps(row) + '\n' for row in replies)) + ')'
        stdin = io.StringIO(''.join(json.dumps(row) + '\n' for row in host))
        with patch.object(sys, 'stdin', stdin), contextlib.redirect_stdout(io.StringIO()), \
                contextlib.redirect_stderr(io.StringIO()):
            adapter.run_proxy([sys.executable, '-I', '-S', '-c', server], effects, table=table)
        output[name] = effects.events
    return output


def mismatches(rows):
    return [name for name, (_, _, expected) in SCENARIOS.items() if rows[name] != expected]


def run(root):
    impl = root / 'impl'
    for name, digest in PINS.items():
        if hashlib.sha256((impl / name).read_bytes()).hexdigest() != digest:
            raise ValueError('consumer source differs from registered pin: ' + name)
    source = (impl / 'warrant_mcp.py').read_text()
    rows = observe(source, impl / 'warrant_mcp.py')
    if mismatches(rows):
        raise AssertionError(('adapter mismatch', mismatches(rows), rows))
    mutations = {
        'event_classification': ('RESPONSE if is_response else REQUEST', 'RESPONSE', 'reverse_request'),
        'id_selection': ('mid = msg.get("id")', 'mid = 1', 'two_ids'),
        'omitted_effect': ('sealer.record_unreturned(tool, tinput, ts, ambiguous=after["ambiguous"])',
                           'pass', 'duplicate'),
    }
    controls = {}
    for name, (old, new, witness) in mutations.items():
        if source.count(old) != 1:
            raise AssertionError('mutation site changed: ' + name)
        failed = mismatches(observe(source.replace(old, new), impl / 'warrant_mcp.py'))
        if witness not in failed:
            raise AssertionError('mutant survived: ' + name)
        controls[name] = failed
    return dict(status='traces_conform', source_commit=COMMIT, pins=PINS, scenarios=rows, controls=controls,
                scope='actual adapter with effect spy; not signing or arbitrary scheduling')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--warrant-root', type=Path, required=True)
    parser.add_argument('--expect-results', type=Path)
    args = parser.parse_args()
    text = json.dumps(run(args.warrant_root.resolve()), indent=2, sort_keys=True) + '\n'
    if args.expect_results and args.expect_results.read_text() != text:
        raise SystemExit('results differ from the pinned experiment')
    print(text, end='')
