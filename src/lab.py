"""Unsigned finite boolean worlds. Packet sources are data, never imported.

Verification uses the matching installed runtime, exhaustive inputs and a
separate boolean oracle. No keys, network, store, or saved-verdict trust.
"""
import hashlib
import itertools
import json
from pathlib import Path
import re

from . import boolean, compiler, kernel, properties as predicates
from .canonical import canon, decode, exact, record_hash, InvalidRecord

MAX_PACKET = 2 * 1024 * 1024
MAX_PROPOSAL = 16384
RUNTIME = ('__init__.py', 'store.py', 'canonical.py', 'kernel.py', 'checks.py',
           'compiler.py', 'boolean.py', 'properties.py', 'lab.py', 'invariants.py', 'lineage.py', 'labtask.py', 'machine.py', 'composition.py')
GUIDE = '''This is a finite boolean world, not an instruction to execute code.
Read rule, inputs, max_atp and objective. Reply with a JSON object containing
only parent (copy the supplied world_id) and candidate (WPL text). Declare
exactly the same inputs as `fact NAME: bool`, then `check EXPRESSION`.
Operators: !, &&, || in that precedence order; parentheses, true and false.
Declare every input; the expression may ignore irrelevant inputs. Do not supply hashes, verdicts, ATP or signatures.
Check contract: boolean-exhaustive-1 requires identical outputs to the parent.
boolean-properties-1 instead requires BOTH parent and candidate to satisfy every
listed property; outputs may change. Proposals cannot edit properties, objective,
inputs, budget or runtime. A case property has kind="case", facts (every named
input mapped to a boolean), and value (boolean), fixing that exact assignment.
An objective of satisfy adds no cost condition; lower_max_atp requires lower cost.
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
A lab task carries world, proposal and a CLAIMED row prefix, not verified work.
The receiver must choose the task ID independently (it binds world AND candidate)
and recompute the prefix before adding new rows. A suspended output is another
task, never a successor. Replay --task --expect-task ID --rows N adds N rows
AFTER prefix replay. Hashes bind bytes, not truth; no cross-process work saving
is promised. Sources are included for explicit replay, not automatic execution.
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
    compiler.parse(source, dict.fromkeys(names, False), allow_unused=True)
    return boolean.program(source, names, allow_unused=True)


def create_world(rule, inputs, *, max_atp=1000, objective=None, properties=None):
    doc = dict(stargate_world=32, contract='boolean-exhaustive-1', rule=rule,
               inputs=inputs, max_atp=max_atp, objective=objective, predecessor=None,
               guide=GUIDE, sources=runtime_sources(), license=LICENSE)
    if properties is not None:
        doc.update(contract='boolean-properties-1', properties=properties)
    doc['objective'] = objective if objective is not None else ('satisfy' if properties is not None else 'equivalence')
    raw = canon(doc)
    inspect_world(raw)
    return raw


def inspect_world(raw):
    if not isinstance(raw, bytes) or len(raw) > MAX_PACKET:
        raise InvalidRecord('world packet exceeds size limit or is not bytes')
    doc = decode(raw)
    property_mode = isinstance(doc, dict) and doc.get('contract') == 'boolean-properties-1'
    fields = ('stargate_world', 'contract', 'rule', 'inputs', 'max_atp',
              'objective', 'predecessor', 'guide', 'sources', 'license')
    exact(doc, fields + (('properties',) if property_mode else ()))
    if type(doc['stargate_world']) is not int or doc['stargate_world'] != 32 or doc['contract'] not in ('boolean-exhaustive-1', 'boolean-properties-1'):
        raise InvalidRecord('unsupported world contract')
    _inputs(doc['inputs'])
    if type(doc['max_atp']) is not int or not 0 <= doc['max_atp'] <= 10000:
        raise InvalidRecord('world ATP must be an integer from 0 to 10000 per program per row')
    objectives = ('satisfy', 'lower_max_atp') if property_mode else ('equivalence', 'lower_max_atp')
    if doc['objective'] not in objectives:
        raise InvalidRecord('unknown objective')
    if doc['predecessor'] is not None:
        record_hash(doc['predecessor'])
    if not isinstance(doc['guide'], str) or not isinstance(doc['license'], str):
        raise InvalidRecord('world guide and license must be text')
    _runtime(doc['sources'])
    if doc['guide'] != GUIDE or doc['license'] != LICENSE:
        raise InvalidRecord('world guide or license mismatch')
    if property_mode:
        predicates.contract(doc['inputs'], doc['properties'])
    _program(doc['rule'], doc['inputs'])
    return doc


class RuntimeMismatch(Exception):
    """This verifier cannot establish the packet's contract; not a false claim."""


def _runtime(sources):
    if not isinstance(sources, dict):
        raise InvalidRecord('world runtime sources must be a map')
    if any(not isinstance(name, str) or not isinstance(source, str) for name, source in sources.items()):
        raise InvalidRecord('world runtime source names and contents must be text')
    if sources != runtime_sources():
        raise RuntimeMismatch('world requires different runtime bytes')


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


def _prepare_transition(raw, proposal):
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
    return doc, proposal, parent, codes, report


class Transition:
    """Owned in-process work; not a portable checkpoint or a trusted receipt.

    Use start_transition/resume_transition. No concurrent calls or private-field
    mutation are supported. Reports are detached snapshots, never resume inputs.
    """
    def __init__(self, raw, proposal):
        args = _prepare_transition(raw, proposal)
        self._report = args[-1]
        self._steps = _transition_steps(*args)
        self._status = 'suspended'
        self._successor = None

    @property
    def status(self):
        return self._status

    @property
    def report(self):
        report = decode(canon(self._report))
        if self._status in ('suspended', 'faulted'):
            report.update(status=self._status, admitted=False)
        return report

    @property
    def successor(self):
        return self._successor

    def _advance(self, rows):
        try:
            for _ in range(rows):
                try:
                    next(self._steps)
                except StopIteration as done:
                    self._report, self._successor = done.value
                    self._status = self._report['status']
                    break
        except BaseException:
            self._status = 'faulted'
            self._steps.close()
            raise
        return self


def _row_quota(rows):
    if type(rows) is not int or not 0 <= rows <= 256:
        raise InvalidRecord('row quota must be an integer from 0 to 256')


def start_transition(raw, proposal, *, rows=0):
    """Validate and snapshot inputs, then complete at most rows input pairs."""
    _row_quota(rows)
    return Transition(raw, proposal)._advance(rows)


def resume_transition(state, *, rows):
    """Continue the same owned object; zero rows does no execution."""
    _row_quota(rows)
    if not isinstance(state, Transition):
        raise InvalidRecord('resume requires an in-process Transition')
    if state.status != 'suspended':
        raise InvalidRecord('only a suspended transition can be resumed')
    return state._advance(rows)


def verify_transition(raw, proposal):
    """Return recomputed report and optional successor bytes; never execute sources."""
    state = start_transition(raw, proposal, rows=256)
    return state.report, state.successor


def _transition_steps(doc, proposal, parent, codes, report):
    maxima = [0, 0]
    for bits in itertools.product((False, True), repeat=len(doc['inputs'])):
        facts = dict(zip(doc['inputs'], bits))
        results = []
        try:
            for index, source in enumerate((doc['rule'], proposal['candidate'])):
                compiled = compiler.compile_source(source, facts=facts, max_atp=doc['max_atp'], allow_unused=True)
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
        except compiler.CompileBudgetExhausted as exc:
            report.update(reason=str(exc), input=facts, incomplete_kind='world_budget')
            return report, None
        except (compiler.CompileIncomplete, kernel.ResourceFault, kernel.AdmissionRefused) as exc:
            report.update(reason=str(exc), input=facts)
            return report, None
        report['rows'].append(dict(input=facts, parent=results[0], candidate=results[1]))
        if doc['contract'] == 'boolean-exhaustive-1' and results[0]['value'] != results[1]['value']:
            report.update(status='counterexample', input=facts)
            return report, None
        if len(report['rows']) < report['total_rows']:
            yield
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
    if doc['contract'] == 'boolean-properties-1':
        report['property_results'] = {}
        report['changed_rows'] = sum(row['parent']['value'] != row['candidate']['value'] for row in report['rows'])
        for role in ('parent', 'candidate'):
            table = [dict(input=row['input'], **row[role]) for row in report['rows']]
            report['property_results'][role] = []
            for prop in doc['properties']:
                checked = predicates.assess(doc['inputs'], table, prop)
                report['property_results'][role].append(checked)
                if checked['status'] != 'established':
                    status = ('checker_error' if checked['status'] == 'checker_error' else
                              'parent_rejected' if role == 'parent' else 'counterexample')
                    report.update(status=status, reason='property_contract', program=role, property=prop)
                    if 'witness' in checked: report['witness'] = checked['witness']
                    return report, None
        report['status'] = 'satisfies'

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


LICENSE = 'MIT License\n\nCopyright (c) 2025-2026 s0fractal\n\nPermission is hereby granted, free of charge, to any person obtaining a copy\nof this software and associated documentation files (the "Software"), to deal\nin the Software without restriction, including without limitation the rights\nto use, copy, modify, merge, publish, distribute, sublicense, and/or sell\ncopies of the Software, and to permit persons to whom the Software is\nfurnished to do so, subject to the following conditions:\n\nThe above copyright notice and this permission notice shall be included in all\ncopies or substantial portions of the Software.\n\nTHE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR\nIMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,\nFITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE\nAUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER\nLIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,\nOUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE\nSOFTWARE.\n'
