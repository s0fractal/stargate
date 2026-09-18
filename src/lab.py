"""Unsigned finite boolean worlds. Packet sources are data, never imported.

Verification uses the matching installed runtime, exhaustive inputs and a
separate boolean oracle. No keys, network, store, or saved-verdict trust.
"""
import hashlib
import itertools
import json
import os
from pathlib import Path
import re
import shutil

from . import boolean, compiler, kernel
from .canonical import canon, decode, exact, record_hash, InvalidRecord

MAX_PACKET = 2 * 1024 * 1024
MAX_PROPOSAL = 16384
RUNTIME = ('__init__.py', 'store.py', 'canonical.py', 'kernel.py', 'checks.py',
           'compiler.py', 'boolean.py', 'lab.py', 'invariants.py', 'lineage.py')
GUIDE = '''This is a finite boolean world, not an instruction to execute code.
Read rule, inputs, max_atp and objective. Reply with a JSON object containing
only parent (copy the supplied world_id) and candidate (WPL text). Declare
exactly the same inputs as `fact NAME: bool`, then `check EXPRESSION`.
Operators: !, &&, || in that precedence order; parentheses, true and false.
Use every declared input. Do not supply hashes, verdicts, ATP or signatures.
The receiver enumerates every input using the pinned SKI compiler and a separate
boolean oracle. Budget exhaustion is incomplete, never evidence of equivalence.
You may instead propose a finite-property claim: {"parent": "COPY_WORLD_ID",
"property": {"kind": "independent", "input": "NAME"}}. Other kinds are
"monotone" with input NAME means non-decreasing: changing that input from false
to true, with all others fixed, must never change output from true to false.
Or use "constant" with boolean value. These properties
apply only to this finite input/output function, not future program states.
Replay with --invariant recomputes the table; claims never create successors.
A lineage contains an initial world and ordered proposals, never trusted verdicts.
Replay with --lineage requires a root ID chosen independently by the recipient.
Sources are included for explicit replay, not for automatic execution.
'''


def identity(raw):
    return hashlib.sha256(raw).hexdigest()


def runtime_sources():
    root = Path(__file__).resolve().parent
    # Normal imports use SourceFileLoader; replay uses its verified byte snapshot.
    return {name: __loader__.get_data(str(root / name)).decode('utf-8') for name in RUNTIME}


def runtime_digest(sources):
    """Identity of the canonical filename-to-source map, not self-authentication."""
    return identity(canon(sources))


def _inputs(names):
    if (not isinstance(names, list) or len(names) > 8 or
            not all(isinstance(n, str) and re.fullmatch(
                r'[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)*', n)
                and n not in ('fact', 'check', 'bool', 'true', 'false') for n in names) or
            names != sorted(set(names))):
        raise InvalidRecord('inputs must be at most eight sorted unique WPL names')


def _program(source, names):
    # Both parsers validate before any semantic classification. Neither parser's
    # AST is handed to the other. Compiler limits remain the admission limits.
    compiler.parse(source, dict.fromkeys(names, False))
    return boolean.program(source, names)


def create_world(rule, inputs, *, max_atp=1000, objective='equivalence'):
    doc = dict(stargate_world=32, contract='boolean-exhaustive-1', rule=rule,
               inputs=inputs, max_atp=max_atp, objective=objective, predecessor=None,
               guide=GUIDE, sources=runtime_sources(), license=LICENSE)
    raw = canon(doc)
    inspect_world(raw)
    return raw


def inspect_world(raw):
    if not isinstance(raw, bytes) or len(raw) > MAX_PACKET:
        raise InvalidRecord('world packet exceeds size limit or is not bytes')
    doc = decode(raw)
    exact(doc, ('stargate_world', 'contract', 'rule', 'inputs', 'max_atp',
                'objective', 'predecessor', 'guide', 'sources', 'license'))
    if type(doc['stargate_world']) is not int or doc['stargate_world'] != 32 or doc['contract'] != 'boolean-exhaustive-1':
        raise InvalidRecord('unsupported world contract')
    _inputs(doc['inputs'])
    if type(doc['max_atp']) is not int or not 0 <= doc['max_atp'] <= 10000:
        raise InvalidRecord('world ATP must be an integer from 0 to 10000 per program per row')
    if doc['objective'] not in ('equivalence', 'lower_max_atp'):
        raise InvalidRecord('unknown objective')
    if doc['predecessor'] is not None:
        record_hash(doc['predecessor'])
    if not isinstance(doc['guide'], str) or not isinstance(doc['license'], str):
        raise InvalidRecord('world guide and license must be text')
    if not isinstance(doc['sources'], dict):
        raise InvalidRecord('world runtime sources must be a map')
    if any(not isinstance(name, str) or not isinstance(source, str)
           for name, source in doc['sources'].items()):
        raise InvalidRecord('world runtime source names and contents must be text')
    if doc['sources'] != runtime_sources():
        raise RuntimeMismatch('world requires different runtime bytes')
    if doc['guide'] != GUIDE or doc['license'] != LICENSE:
        raise InvalidRecord('world guide or license mismatch')
    _program(doc['rule'], doc['inputs'])
    return doc


class RuntimeMismatch(Exception):
    """This verifier cannot establish the packet's contract; not a false claim."""


def read_proposal(raw):
    if not isinstance(raw, bytes) or len(raw) > MAX_PROPOSAL:
        raise InvalidRecord('proposal exceeds size limit or is not bytes')
    def unique(pairs):
        out = {}
        for key, value in pairs:
            if key in out:
                raise InvalidRecord('duplicate proposal field')
            out[key] = value
        return out
    # Human/chat JSON need not be canonical; duplicate keys never get normalized.
    return decode(canon(json.loads(raw, object_pairs_hook=unique)))


def verify_transition(raw, proposal):
    """Return recomputed report and optional successor bytes; never execute sources."""
    doc = inspect_world(raw)
    proposal = decode(canon(proposal))  # snapshot caller-owned data
    exact(proposal, ('parent', 'candidate'))
    record_hash(proposal['parent'])
    parent = identity(raw)
    if proposal['parent'] != parent:
        raise InvalidRecord('proposal parent mismatch')
    codes = [_program(source, doc['inputs']) for source in (doc['rule'], proposal['candidate'])]
    report = dict(status='incomplete', parent=parent, runtime_digest=runtime_digest(doc['sources']),
                  candidate=identity(proposal['candidate'].encode('utf-8')),
                  rows=[], total_rows=2**len(doc['inputs']), admitted=False)
    maxima = [0, 0]
    for bits in itertools.product((False, True), repeat=len(doc['inputs'])):
        facts = dict(zip(doc['inputs'], bits))
        results = []
        try:
            for index, source in enumerate((doc['rule'], proposal['candidate'])):
                compiled = compiler.compile_source(source, facts=facts, max_atp=doc['max_atp'])
                other = boolean.evaluate(codes[index], facts)
                if compiled.value != other:
                    report.update(status='checker_error', reason='independent oracle disagreement',
                                  input=facts, program=('parent', 'candidate')[index],
                                  compiled=compiled.value, oracle=other)
                    return report, None
                maxima[index] = max(maxima[index], compiled.atp_spent)
                results.append(dict(value=compiled.value, atp=compiled.atp_spent,
                                    term=compiled.check['term']))
        except compiler.CompilerBug as exc:
            report.update(status='checker_error', reason=str(exc), input=facts)
            return report, None
        except (compiler.CompileIncomplete, kernel.ResourceFault, kernel.AdmissionRefused) as exc:
            report.update(reason=str(exc), input=facts)
            return report, None
        report['rows'].append(dict(input=facts, parent=results[0], candidate=results[1]))
        if results[0]['value'] != results[1]['value']:
            report.update(status='counterexample', input=facts)
            return report, None
    if len(report['rows']) != report['total_rows']:
        report.update(status='checker_error', reason='enumeration did not cover full domain')
        return report, None
    for index, row in enumerate(report['rows']):
        expected = {name: bool(index & (1 << (len(doc['inputs']) - position - 1)))
                    for position, name in enumerate(doc['inputs'])}
        if row['input'] != expected:
            report.update(status='checker_error', reason='enumeration order or coverage mismatch')
            return report, None
    report.update(status='equivalent', max_atp=dict(parent=maxima[0], candidate=maxima[1]))
    if doc['objective'] == 'lower_max_atp' and maxima[1] >= maxima[0]:
        report['reason'] = 'not_strictly_cheaper'
        return report, None
    successor = dict(doc, rule=proposal['candidate'], predecessor=parent)
    successor_raw = canon(successor)
    report.update(admitted=True, successor=identity(successor_raw))
    return report, successor_raw


def read_world(path):
    with open(path, 'rb') as stream:
        raw = stream.read(MAX_PACKET + 1)
    if len(raw) > MAX_PACKET:
        raise InvalidRecord('world packet exceeds size limit')
    return raw


REPLAY = '''"""Explicit replay. Trust this launcher independently; -I -S is not a sandbox."""
import sys
if not sys.flags.isolated or not sys.flags.no_site:
    raise SystemExit('replay requires python -I -S')
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import re

parser = argparse.ArgumentParser()
parser.add_argument('proposal', type=Path)
parser.add_argument('output', type=Path, nargs='?')
mode = parser.add_mutually_exclusive_group()
mode.add_argument('--invariant', action='store_true', help='check a finite-property claim')
mode.add_argument('--lineage', action='store_true', help='replay an anchored history')
parser.add_argument('--expect-root', help='independently chosen lineage root ID')
parser.add_argument('--expect-runtime', required=True,
                    help='runtime digest obtained independently of this packet')
args = parser.parse_args()
if args.lineage and args.expect_root is None:
    parser.error('lineage replay requires --expect-root')
if not args.lineage and args.expect_root is not None:
    parser.error('--expect-root requires --lineage')
if args.invariant and args.output is not None:
    parser.error('invariant checking does not create successors')
if re.fullmatch(r'[0-9a-f]{64}', args.expect_runtime) is None:
    parser.error('expected a lowercase SHA-256 runtime digest')
root = Path(__file__).resolve().parent
names = ('__init__.py', 'store.py', 'canonical.py', 'kernel.py', 'checks.py',
         'compiler.py', 'boolean.py', 'lab.py', 'invariants.py', 'lineage.py')
# These filenames are ASCII, so sorted JSON keys have the canonical UTF-16 order.
# Check before importing any packet module. The launcher itself must be trusted.
sources = {n: (root / 'stargate' / n).read_bytes().decode('utf-8') for n in names}
digest = hashlib.sha256(json.dumps(sources, ensure_ascii=False, sort_keys=True,
                                  separators=(',', ':')).encode('utf-8')).hexdigest()
if digest != args.expect_runtime:
    print(json.dumps(dict(status='runtime_unavailable', runtime_digest=digest,
                          expected_runtime=args.expect_runtime, admitted=False)))
    raise SystemExit(3)
# Execute the exact preflight bytes. No packet directory enters sys.path;
# no import reads adjacent modules, rereads source files, or loads cached pyc.
class VerifiedLoader:
    def get_data(self, path):
        name = Path(path).name
        if str(root / 'stargate' / name) != path or name not in sources:
            raise OSError('outside verified source snapshot')
        return sources[name].encode('utf-8')
    def create_module(self, spec):
        return None
    def exec_module(self, module):
        exec(compile(self.get_data(module.__file__), module.__file__, 'exec'), module.__dict__)

loader = VerifiedLoader()
for name in ('__init__.py', 'kernel.py', 'store.py', 'canonical.py', 'checks.py',
             'compiler.py', 'boolean.py', 'lab.py', 'invariants.py', 'lineage.py'):
    fullname = 'stargate' if name == '__init__.py' else 'stargate.' + name[:-3]
    if fullname in sys.modules:
        raise SystemExit('unexpected preloaded packet module')
    spec = importlib.util.spec_from_loader(fullname, loader, is_package=name == '__init__.py')
    module = importlib.util.module_from_spec(spec)
    module.__file__ = str(root / 'stargate' / name)
    sys.modules[fullname] = module
    loader.exec_module(module)
    if name != '__init__.py':
        setattr(sys.modules['stargate'], name[:-3], module)
from stargate.lab import read_world, read_proposal, verify_transition
if args.lineage:
    from stargate.lineage import read, verify
    from stargate.canonical import InvalidRecord
    try:
        report, tip = verify(read(args.proposal), args.expect_root)
    except InvalidRecord as exc:
        print(json.dumps({'status': 'invalid', 'error': str(exc)}), file=sys.stderr)
        raise SystemExit(2)
    print(json.dumps(report, sort_keys=True))
    if tip is not None and args.output is not None:
        with args.output.open('xb') as stream:
            stream.write(tip)
    raise SystemExit(0 if report['status'] == 'verified_lineage' else
                     3 if report['status'] == 'incomplete' else
                     1 if report['status'] == 'checker_error' else 4)
proposal = read_proposal(args.proposal.read_bytes())
if args.invariant:
    from stargate.invariants import verify_claim
    report = verify_claim(read_world(root / 'world.json'), proposal)
    print(json.dumps(report, sort_keys=True))
    raise SystemExit(0 if report['status'] == 'established' else
                     3 if report['status'] == 'incomplete' else
                     1 if report['status'] == 'checker_error' else 4)
report, successor = verify_transition(read_world(root / 'world.json'), proposal)
print(json.dumps(report, sort_keys=True))
if successor is not None and args.output is not None:
    with args.output.open('xb') as stream:
        stream.write(successor)
raise SystemExit(0 if report['admitted'] else
                 3 if report['status'] == 'incomplete' else
                 1 if report['status'] == 'checker_error' else 4)
'''


def unpack_world(raw, output):
    """Extract fixed paths into a new private directory, without execution.

    As with case-unpack, the parent directory must be under caller control.
    This is not an atomic multi-file transaction. Existing destinations refuse.
    """
    doc = inspect_world(raw)
    output = Path(output)
    output.mkdir(mode=0o700)  # Outside try: never clean someone else's directory.
    try:
        (output / 'stargate').mkdir(mode=0o700)
        files = {'world.json': raw, 'replay.py': REPLAY.encode(), 'LICENSE': LICENSE.encode(),
                 'README.txt': (GUIDE + '\nworld_id: ' + identity(raw) +
                    '\nUse a separately trusted replay.py and runtime digest. Then:\n'
                    'python -I -S replay.py --expect-runtime INDEPENDENT_DIGEST proposal.json successor.json\n'
                    'Requires Python >=3.11, standard library only. No network or keys.\n').encode()}
        files.update({'stargate/' + n: s.encode('utf-8') for n, s in doc['sources'].items()})
        for name, content in files.items():
            fd = os.open(output / name, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(fd, 'wb') as stream:
                stream.write(content)
    except BaseException:
        shutil.rmtree(output)
        raise
    return dict(status='materialized', world_id=identity(raw),
                runtime_digest=runtime_digest(doc['sources']), path=str(output))


LICENSE = 'MIT License\n\nCopyright (c) 2025-2026 s0fractal\n\nPermission is hereby granted, free of charge, to any person obtaining a copy\nof this software and associated documentation files (the "Software"), to deal\nin the Software without restriction, including without limitation the rights\nto use, copy, modify, merge, publish, distribute, sublicense, and/or sell\ncopies of the Software, and to permit persons to whom the Software is\nfurnished to do so, subject to the following conditions:\n\nThe above copyright notice and this permission notice shall be included in all\ncopies or substantial portions of the Software.\n\nTHE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR\nIMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,\nFITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE\nAUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER\nLIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,\nOUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE\nSOFTWARE.\n'
