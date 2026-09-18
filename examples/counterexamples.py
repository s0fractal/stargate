"""Rebuild the two case packets from immutable, reviewed Git source snapshots.

Run from a checkout containing the named commits. This generator is development
code; reading/unpacking the resulting packets never runs it or their replay code.
"""
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
# Install this checkout (editable or wheel) before running the generator.
from stargate.case import pack_case

OLD = 'aefe998f7c98dbdc4132fb464b67e17029b59c6b'
FIXED = 'e8002bbaca394675482c246d869260eafb25e256'

RUNNER = r'''"""Explicitly executed case code; -I is import isolation, NOT a sandbox."""
import io
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
from stargate import artifact
assert Path(artifact.__file__).resolve() == ROOT / 'stargate' / 'artifact.py'

CASES = {
 'M1': ('for _, _, _, _, _, deriver in prepared:',
        'for _, _, _, _, _, deriver in prepared[:1]:',
        'test_all_derivers_consume_the_same_stream',
        'test_all_derivers_consume_the_same_stream'),
 'M2': ("facts = decode(canon(req['facts'])) if deriver is None else None",
        "facts = req['facts'] if deriver is None else None",
        'test_snapshot_requests_before_verification',
        'test_snapshot_requests_before_reading'),
}
before, after, old_test, new_test = CASES[CASE]
source = (ROOT / 'stargate' / 'artifact.py').read_text()
assert source.count(before) == 1, 'mutation target must be unique'
namespace = dict(artifact.__dict__)
exec(compile(source.replace(before, after), '<mutant>', 'exec'), namespace)
namespace['_subject_chunks'] = lambda path: artifact._subject_chunks(path)
namespace['require_bundle'] = lambda *a, **kw: artifact.require_bundle(*a, **kw)
original = artifact.admit_all
rows = []
for variant, function in [('control', original), ('mutant', namespace['admit_all'])]:
    for revision, name in [('old', old_test), ('new', new_test)]:
        tests = {'__name__': 'case_tests'}
        exec(compile((ROOT / (revision + '_tests.py')).read_text(), revision, 'exec'), tests)
        stream = io.StringIO()
        with patch.object(artifact, 'admit_all', function):
            result = unittest.TextTestRunner(stream=stream).run(
                unittest.TestSuite([tests['AdmitAll'](name)]))
        expected_failure = variant == 'mutant' and revision == 'new'
        assert result.testsRun == 1 and not result.errors, stream.getvalue()
        assert len(result.failures) == int(expected_failure), stream.getvalue()
        if expected_failure:
            assert "'unsatisfied' != 'admitted'" in result.failures[0][1], stream.getvalue()
        rows.append(dict(variant=variant, test=revision, failures=len(result.failures), errors=len(result.errors)))
print(json.dumps(dict(status='reproduced', case=CASE, runs=rows), sort_keys=True))
'''


def blob(commit, path):
    return subprocess.check_output(['git', 'show', f'{commit}:{path}'], cwd=ROOT)


def build():
    modules = ('__init__', 'artifact', 'bundle', 'facts', 'kernel', 'policy', 'records', 'store')
    files = {f'stargate/{m}.py': blob(FIXED, f'stargate/{m}.py') for m in modules}
    files.update({'old_tests.py': blob(OLD, 'tests/test_admit_all.py'),
                  'new_tests.py': blob(FIXED, 'tests/test_admit_all.py'),
                  'LICENSE': blob(FIXED, 'LICENSE')})
    for case, claim in [
        ('M1', 'An unfed UTF-8 deriver returns true for empty input, so the old multi-deriver test misses the defect.'),
        ('M2', 'A snapshot test that never mutates asserted facts cannot detect storing those facts by reference.'),
    ]:
        replay = ('CASE = ' + repr(case) + '\n' + RUNNER).encode()
        manifest = dict(title=case + ': mutation-blind admission test', claim=claim,
            scope='Stargate admit_all, the included source and exactly the two selected regression tests.',
            limits=['Integrity is not truth or authenticated authorship.',
                    'Replay executes included Python with your permissions; -I is not a sandbox.',
                    'Requires Python 3.11+ and cryptography>=43; exercised only on Python 3.14.',
                    'This demonstrates sensitivity to one mutation, not general correctness.'],
            source=dict(repository='https://github.com/s0fractal/stargate', commit=FIXED),
            entrypoint='replay.py',
            expected='Both control tests pass; the mutant passes the old test and fails the new test with unsatisfied != admitted.')
        readme = f'''# {case}: reproducible counterexample

{claim}

Source snapshot: {FIXED}
Old test snapshot: {OLD}
New test snapshot: {FIXED}

The packet carries the source, old/new tests, mutation and this runner. No Git
checkout, Stargate installation, network fetch or chat transcript is needed.
Dependency: Python 3.11+ with cryptography>=43 installed (tested on 3.14 only).
Read replay.py and the included sources before running them. They execute with
your user permissions. An intact packet is not authenticated or safe code.

From this directory, after deciding to run its code:

    python -I replay.py

Exit 0 plus status=reproduced means the four observed outcomes match the expected
matrix: control old/new pass, mutant old passes, mutant new fails specifically
with unsatisfied != admitted. A dependency/import error is not reproduction.
Nothing in the Stargate case inspect/unpack commands executes this runner.
'''
        packet = pack_case(manifest, dict(files, **{'replay.py': replay, 'README.md': readme.encode()}))
        (ROOT / 'examples' / ('case-' + case.lower() + '.json')).write_bytes(packet)
        print(case, len(packet))


if __name__ == '__main__':
    build()
