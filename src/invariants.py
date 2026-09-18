"""Finite input/output properties, not temporal or universal program invariants.

Discovery generates hypotheses; checking recomputes the complete finite table
through the existing SKI + independent-oracle gate. No saved report is trusted.
"""
from . import lab
from .canonical import canon, decode, exact, record_hash, InvalidRecord


def _claim(doc, parent, claim):
    claim = decode(canon(claim))
    exact(claim, ('parent', 'property'))
    record_hash(claim['parent'])
    if claim['parent'] != parent:
        raise InvalidRecord('invariant parent mismatch')
    prop = claim['property']
    if not isinstance(prop, dict):
        raise InvalidRecord('property must be an object')
    if prop.get('kind') == 'constant':
        exact(prop, ('kind', 'value'))
        if type(prop['value']) is not bool:
            raise InvalidRecord('constant value must be boolean')
    elif prop.get('kind') in ('independent', 'monotone'):
        exact(prop, ('kind', 'input'))
        if not isinstance(prop['input'], str) or prop['input'] not in doc['inputs']:
            raise InvalidRecord('unknown property input')
    else:
        raise InvalidRecord('unsupported finite property')
    return claim


def _table(raw, doc):
    # A self-comparison reuses both parsers, receipts and coverage controls.
    # Cost admission is irrelevant: equivalent/not_strictly_cheaper still gives
    # a complete checked table. Any constructed successor is deliberately ignored.
    verified, _ = lab.verify_transition(raw, {'parent':lab.identity(raw), 'candidate':doc['rule']})
    if verified['status'] != 'equivalent':
        status = 'incomplete' if verified['status'] == 'incomplete' else 'checker_error'
        return None, dict(status=status, reason=verified.get('reason', 'self-comparison disagreed'))
    rows = [dict(input=r['input'], **r['parent']) for r in verified['rows']]
    # Check the received internal table explicitly, rather than trusting a label.
    if len(rows) != 2**len(doc['inputs']):
        return None, dict(status='checker_error', reason='invariant table incomplete')
    for index, row in enumerate(rows):
        expected = {n:bool(index & (1 << (len(doc['inputs'])-j-1))) for j,n in enumerate(doc['inputs'])}
        if row['input'] != expected or type(row['value']) is not bool:
            return None, dict(status='checker_error', reason='invariant table order or values invalid')
    return rows, None


def _assess(doc, rows, claim):
    prop = claim['property']
    result = dict(claim=claim, status='established', checked=0)
    if prop['kind'] == 'constant':
        expected_checks = len(rows)
        for row in rows:
            result['checked'] += 1
            if row['value'] != prop['value']:
                result.update(status='counterexample', witness=[row])
                return result
    else:
        mask = 1 << (len(doc['inputs']) - doc['inputs'].index(prop['input']) - 1)
        expected_checks = len(rows)//2
        for index, low in enumerate(rows):
            if index & mask:
                continue
            high = rows[index | mask]
            result['checked'] += 1
            violates = (low['value'] != high['value'] if prop['kind'] == 'independent'
                        else low['value'] and not high['value'])
            if violates:
                result.update(status='counterexample', witness=[low, high])
                return result
    if result['checked'] != expected_checks:
        result.update(status='checker_error', reason='property obligations not fully checked')
    return result


def verify_claim(raw, claim):
    doc = lab.inspect_world(raw)
    claim = _claim(doc, lab.identity(raw), claim)  # Validate even when budget is too small.
    report = dict(parent=lab.identity(raw), runtime_digest=lab.runtime_digest(doc['sources']), claim=claim)
    rows, failure = _table(raw, doc)
    if failure:
        return dict(report, **failure)
    report.update(_assess(doc, rows, claim))
    return dict(report, table=rows, table_digest=lab.identity(canon(rows)), total_rows=len(rows))


def discover(raw):
    doc = lab.inspect_world(raw)
    parent = lab.identity(raw)
    report = dict(parent=parent, runtime_digest=lab.runtime_digest(doc['sources']), results=[])
    rows, failure = _table(raw, doc)
    if failure:
        return dict(report, **failure)
    properties = [dict(kind='constant', value=False), dict(kind='constant', value=True)]
    for name in doc['inputs']:
        properties.extend([dict(kind='independent', input=name), dict(kind='monotone', input=name)])
    for prop in properties:
        claim = _claim(doc, parent, dict(parent=parent, property=prop))
        verdict = _assess(doc, rows, claim)
        report['results'].append(verdict)
        if verdict['status'] == 'checker_error':
            return dict(report, status='checker_error', reason=verdict['reason'])
    return dict(report, status='complete', table=rows, table_digest=lab.identity(canon(rows)),
                total_rows=len(rows), hypotheses=len(properties))
