"""Finite observations of two compiler implementations, never runtime admission.

Inspection is inert. Execution runs arbitrary Python with operator privileges;
-I -S and process limits are reproducibility aids, NOT a sandbox.
"""
import hashlib
import itertools
import json
import os
from pathlib import Path
import platform
import re
import signal
import subprocess
import sys
import tempfile
import time

from . import boolean, compiler
from .canonical import InvalidRecord, canon, decode, exact, record_hash

PROFILE = 'boolean-compiler-observations-1'
# Ordered for bootstrap; identity is over the canonical filename -> source map.
SUBJECT = ('__init__.py', 'kernel.py', 'store.py', 'canonical.py',
           'checks.py', 'compiler.py', 'boolean.py')
CONTROLLER = SUBJECT + ('experiment.py',)
MAX_BYTES = 4 * 1024 * 1024
MAX_OUTPUT = 2 * 1024 * 1024


LICENSE = 'MIT License\n\nCopyright (c) 2025-2026 s0fractal\n\nPermission is hereby granted, free of charge, to any person obtaining a copy\nof this software and associated documentation files (the "Software"), to deal\nin the Software without restriction, including without limitation the rights\nto use, copy, modify, merge, publish, distribute, sublicense, and/or sell\ncopies of the Software, and to permit persons to whom the Software is\nfurnished to do so, subject to the following conditions:\n\nThe above copyright notice and this permission notice shall be included in all\ncopies or substantial portions of the Software.\n\nTHE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR\nIMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,\nFITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE\nAUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER\nLIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,\nOUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE\nSOFTWARE.\n'

GUIDE = """# Compiler experiment

experiment.json carries two inert compiler source maps and a finite Boolean corpus.
The controller compares every input row, independently checking both Boolean
answers. Cases may declare expect=reject: this is a corpus obligation, not
a controller-proved grammar fact. Rejection is distinct from budget exhaustion.
Agreement applies ONLY to these observations. No runtime is admitted.
A participant can propose replacement source text, or an additional corpus case;
return text rather than inventing digests or claiming an experiment has passed.
Adding a case creates a new corpus and experiment; old evidence is unchanged.

First authenticate replay.py's SHA-256 and the controller ID through an independent
channel. Values supplied by this directory alone are not a trust anchor.
Then: python -I -S replay.py experiment.json --expect-controller ID --execute-runtimes
This runs both implementations with YOUR PRIVILEGES, not in a sandbox. Use a
separately provided disposable isolation boundary for unknown code.

Exit 0: complete scoped agreement; 4: observed difference or oracle disagreement;
3: incomplete or different controller; 2: invalid input; 1: operation error.
Costs and terms are subject reports, not independently proved properties.
Python, standard library, host and independently selected controller are trusted.
"""

def digest(value):
    return hashlib.sha256(canon(value)).hexdigest()


def sources(names):
    root = Path(__file__).resolve().parent
    return {name: __loader__.get_data(str(root / name)).decode('utf-8') for name in names}


def controller_id():
    return digest(sources(CONTROLLER))


def _source_map(value, names):
    if type(value) is not dict or set(value) != set(names) or any(type(v) is not str for v in value.values()):
        raise InvalidRecord('expected the exact text source closure for this experiment profile')
    canon(value)
    return value


def pack_runtime(root=None):
    texts = sources(SUBJECT) if root is None else {
        name: (Path(root) / name).read_bytes().decode('utf-8') for name in SUBJECT}
    return canon({'runtime': 1, 'profile': PROFILE, 'sources': texts})


def runtime(raw):
    doc = decode(raw)
    exact(doc, ('runtime', 'profile', 'sources'))
    if type(doc['runtime']) is not int or doc['runtime'] != 1 or doc['profile'] != PROFILE:
        raise InvalidRecord('unsupported runtime capsule')
    return _source_map(doc['sources'], SUBJECT)


def corpus(doc, *, validate_program=True):
    exact(doc, ('corpus', 'cases'))
    if type(doc['corpus']) is not int or doc['corpus'] != 1:
        raise InvalidRecord('unsupported corpus')
    if type(doc['cases']) is not list or not 1 <= len(doc['cases']) <= 32:
        raise InvalidRecord('corpus needs 1..32 cases')
    seen = set()
    for case in doc['cases']:
        if type(case) is not dict:
            raise InvalidRecord('case must be an object')
        exact(case, ('name', 'inputs', 'rule', 'max_atp', 'expect') if 'expect' in case else ('name', 'inputs', 'rule', 'max_atp'))
        if case.get('expect', 'value') not in ('value', 'reject'):
            raise InvalidRecord('case expectation must be value or reject')
        name, names = case['name'], case['inputs']
        if type(name) is not str or re.fullmatch(r'[A-Za-z0-9_-]{1,64}', name) is None or name in seen:
            raise InvalidRecord('case names must be unique ASCII identifiers')
        seen.add(name)
        if (type(names) is not list or len(names) > 8 or
                any(type(n) is not str or re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)*', n) is None or n in compiler.RESERVED for n in names) or
                names != sorted(set(names))):
            raise InvalidRecord('inputs must be sorted unique Boolean names, at most eight')
        if type(case['max_atp']) is not int or not 0 <= case['max_atp'] <= 10000:
            raise InvalidRecord('case ATP budget must be 0..10000')
        if type(case['rule']) is not str or len(case['rule'].encode('utf-8')) > 8192:
            raise InvalidRecord('rule must be text within 8192 bytes')
        # Grammar interpretation belongs to the selected controller, not to
        # structural inspection of a packet naming another controller.
        if validate_program and case.get('expect', 'value') == 'value':
            compiler.parse(case['rule'], dict.fromkeys(names, False), allow_unused=True)
            boolean.program(case['rule'], names, allow_unused=True)
    return doc


def create(parent_raw, candidate_raw, corpus_doc, *, timeout=30):
    if type(timeout) is not int or not 1 <= timeout <= 300:
        raise InvalidRecord('timeout must be 1..300 seconds per subject')
    result = canon({'experiment': 1, 'profile': PROFILE, 'controller': controller_id(),
                   'parent': runtime(parent_raw), 'candidate': runtime(candidate_raw),
                   'corpus': corpus(corpus_doc), 'timeout': timeout})
    if len(result) > MAX_BYTES:
        raise InvalidRecord('experiment exceeds size limit')
    return result


def inspect(raw):
    if len(raw) > MAX_BYTES:
        raise InvalidRecord('experiment exceeds size limit')
    doc = decode(raw)
    exact(doc, ('experiment', 'profile', 'controller', 'parent', 'candidate', 'corpus', 'timeout'))
    if type(doc['experiment']) is not int or doc['experiment'] != 1 or doc['profile'] != PROFILE:
        raise InvalidRecord('unsupported experiment')
    record_hash(doc['controller'])
    for role in ('parent', 'candidate'):
        _source_map(doc[role], SUBJECT)
    corpus(doc['corpus'], validate_program=False)
    if type(doc['timeout']) is not int or not 1 <= doc['timeout'] <= 300:
        raise InvalidRecord('timeout must be 1..300 seconds per subject')
    return doc


def describe(raw):
    doc = inspect(raw)
    return {'status': 'intact', 'experiment_id': digest(doc), 'profile': PROFILE,
            'controller': doc['controller'], 'local_controller': controller_id(),
            'parent': digest(doc['parent']), 'candidate': digest(doc['candidate']),
            'corpus': digest(doc['corpus']), 'timeout': doc['timeout'],
            'total_rows': sum(2 ** len(c['inputs']) for c in doc['corpus']['cases'])}


# Shared captured-text bootstrap for the subject process and offline controller.
# No sys.path insertion, filesystem source reread, or bytecode cache is involved.
BOOTSTRAP = r'''
import importlib.util
import json
from pathlib import Path
import sys
if not sys.flags.isolated or not sys.flags.no_site:
    raise SystemExit('requires python -I -S')
class SnapshotLoader:
    def __init__(self, texts): self.texts = texts
    def get_data(self, path):
        name = Path(path).name
        if path != '/__stargate_snapshot__/' + name or name not in self.texts:
            raise OSError('outside source snapshot')
        return self.texts[name].encode('utf-8')
    def create_module(self, spec): return None
    def exec_module(self, module):
        exec(compile(self.get_data(module.__file__), module.__file__, 'exec'), module.__dict__)
def load(texts, names):
    loader = SnapshotLoader(texts)
    for name in names:
        fullname = 'stargate' if name == '__init__.py' else 'stargate.' + name[:-3]
        if fullname in sys.modules: raise RuntimeError('preloaded subject module')
        spec = importlib.util.spec_from_loader(fullname, loader, is_package=name == '__init__.py')
        module = importlib.util.module_from_spec(spec)
        module.__file__ = '/__stargate_snapshot__/' + name
        sys.modules[fullname] = module
        loader.exec_module(module)
        if name != '__init__.py': setattr(sys.modules['stargate'], name[:-3], module)
'''

RUNNER = BOOTSTRAP + '\n' + 'NAMES = ' + repr(SUBJECT) + r'''
request = json.loads(sys.stdin.buffer.read())
load(request['sources'], NAMES)
from stargate import compiler, kernel
rows = []
for item in request['rows']:
    try:
        result = compiler.compile_source(item['rule'], facts=item['facts'],
            max_atp=item['max_atp'], allow_unused=True)
        observed = dict(status='complete', value=result.value,
                        atp_spent=result.atp_spent, term=result.check['term'])
    except compiler.CompileIncomplete:
        observed = dict(status='incomplete', reason='compile_budget_or_exit')
    except (kernel.ResourceFault, kernel.AdmissionRefused):
        observed = dict(status='incomplete', reason='local_resource')
    except compiler.CompilerBug:
        observed = dict(status='incomplete', reason='subject_checker_error')
    except compiler.PolicyError:
        observed = dict(status='rejected', reason='subject_rejected_input')
    rows.append(dict(index=item['index'], observation=observed))
print(json.dumps(rows, separators=(',', ':')))
'''


def _run(texts, rows, timeout):
    """POSIX process-group deadline; no claim of containment against hostile code."""
    payload = json.dumps({'sources': texts, 'rows': rows}).encode()
    with tempfile.TemporaryDirectory(prefix='sg-experiment-') as cwd:
        with tempfile.TemporaryFile() as incoming, tempfile.TemporaryFile() as outgoing:
            incoming.write(payload); incoming.seek(0)
            process = subprocess.Popen([sys.executable, '-I', '-S', '-B', '-c', RUNNER],
                stdin=incoming, stdout=outgoing, stderr=subprocess.DEVNULL,
                cwd=cwd, start_new_session=True)
            reason = None
            try:
                deadline = time.monotonic() + timeout
                while True:
                    if os.fstat(outgoing.fileno()).st_size > MAX_OUTPUT:
                        reason = 'output_limit'; break
                    if time.monotonic() >= deadline:
                        reason = 'deadline'; break
                    try:
                        process.wait(timeout=0.02); break
                    except subprocess.TimeoutExpired:
                        pass
            finally:
                # Kill remaining same-group children even after the leader exits.
                try: os.killpg(process.pid, signal.SIGKILL)
                except ProcessLookupError: pass
                process.wait()
            if reason:
                return None, reason
            if process.returncode != 0:
                return None, 'subject_process_failed'
            outgoing.seek(0); raw = outgoing.read(MAX_OUTPUT + 1)
            if len(raw) > MAX_OUTPUT:
                return None, 'output_limit'
    try:
        # Reject duplicates, floats, and all non-canonical-value types as well.
        data = json.loads(raw, object_pairs_hook=_unique)
        canon(data)
        _observations(data, rows)
        return data, None
    except (ValueError, TypeError, KeyError, RecursionError):
        return None, 'invalid_subject_report'


def _unique(pairs):
    result = {}
    for key, value in pairs:
        if key in result: raise ValueError('duplicate key')
        result[key] = value
    return result


def _observations(data, rows):
    if type(data) is not list or len(data) != len(rows):
        raise InvalidRecord('subject must report every row')
    for index, (row, task) in enumerate(zip(data, rows)):
        exact(row, ('index', 'observation'))
        if type(row['index']) is not int or row['index'] != index:
            raise InvalidRecord('subject row order mismatch')
        obs = row['observation']
        if type(obs) is not dict: raise InvalidRecord('observation must be an object')
        if obs.get('status') == 'complete':
            exact(obs, ('status', 'value', 'atp_spent', 'term'))
            if (type(obs['value']) is not bool or type(obs['atp_spent']) is not int or
                    not 0 <= obs['atp_spent'] <= task['max_atp']):
                raise InvalidRecord('invalid subject value or cost')
            record_hash(obs['term'])
        elif obs.get('status') == 'rejected':
            exact(obs, ('status', 'reason'))
            if obs['reason'] != 'subject_rejected_input':
                raise InvalidRecord('invalid subject rejection')
        else:
            exact(obs, ('status', 'reason'))
            if obs['status'] != 'incomplete' or obs['reason'] not in (
                    'compile_budget_or_exit', 'local_resource', 'subject_checker_error'):
                raise InvalidRecord('invalid subject refusal')


def run(raw, *, expect_controller, execute=False):
    if execute is not True:
        raise InvalidRecord('execution requires explicit consent: --execute-runtimes (not a sandbox)')
    doc = inspect(raw)
    record_hash(expect_controller)
    report = describe(raw)
    if expect_controller != controller_id() or doc['controller'] != expect_controller:
        report['status'] = 'controller_unavailable'
        return report
    corpus(doc['corpus'])
    if os.name != 'posix':
        report.update(status='incomplete', reason='POSIX execution profile required')
        return report
    report['environment'] = {'python': platform.python_version(), 'implementation': platform.python_implementation(),
        'system': platform.system(), 'machine': platform.machine(),
        'executable_sha256': hashlib.sha256(Path(sys.executable).resolve().read_bytes()).hexdigest(),
        'flags': ['-I', '-S', '-B'], 'output_limit': MAX_OUTPUT}
    tasks, expected = [], []
    for case in doc['corpus']['cases']:
        oracle = (boolean.program(case['rule'], case['inputs'], allow_unused=True)
                  if case.get('expect', 'value') == 'value' else None)
        for bits in itertools.product((False, True), repeat=len(case['inputs'])):
            facts = dict(zip(case['inputs'], bits))
            tasks.append({'index': len(tasks), 'case': case['name'], 'facts': facts,
                          'rule': case['rule'], 'max_atp': case['max_atp']})
            expected.append(boolean.evaluate(oracle, facts) if oracle is not None else None)
    observed = {}
    for role in ('parent', 'candidate'):
        data, failure = _run(doc[role], tasks, doc['timeout'])
        if failure:
            report.update(status='incomplete', role=role, reason=failure)
            return report
        observed[role] = data
    report['rows'] = []
    incomplete, disagreements, differences = [], [], []
    for task, truth, left, right in zip(tasks, expected, observed['parent'], observed['candidate']):
        row = {'index': task['index'], 'case': task['case'], 'facts': task['facts'],
               'expect': 'reject' if truth is None else 'value',
               'oracle': truth, 'parent': left['observation'], 'candidate': right['observation']}
        report['rows'].append(row)
        for role in ('parent', 'candidate'):
            if row[role]['status'] == 'incomplete': incomplete.append({'index': task['index'], 'role': role})
            elif row[role]['status'] == 'rejected' and truth is not None:
                disagreements.append({'index': task['index'], 'role': role})
            elif row[role]['status'] == 'complete' and (truth is None or row[role]['value'] != truth):
                disagreements.append({'index': task['index'], 'role': role})
        if left['observation']['status'] == right['observation']['status'] == 'complete' and left != right:
            differences.append(task['index'])
    # A witnessed disagreement is meaningful even if other rows did not finish.
    report.update(status='oracle_disagreement' if disagreements else 'difference' if differences else
                  'incomplete' if incomplete else 'agreement',
                  incomplete_rows=incomplete, oracle_disagreements=disagreements, differences=differences)
    return report


def exit_code(report):
    return {'agreement': 0, 'difference': 4, 'oracle_disagreement': 4,
            'incomplete': 3, 'controller_unavailable': 3}[report['status']]


def read(path):
    with Path(path).open('rb') as stream: raw = stream.read(MAX_BYTES + 1)
    if len(raw) > MAX_BYTES: raise InvalidRecord('experiment input exceeds size limit')
    return raw
