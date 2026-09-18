"""Pure predicates on a complete finite Boolean table; no evaluator or authority."""
from .canonical import canon, decode, exact, InvalidRecord


def validate(inputs, prop):
    prop = decode(canon(prop))
    if not isinstance(prop, dict):
        raise InvalidRecord('property must be an object')
    kind = prop.get('kind')
    if kind == 'constant':
        exact(prop, ('kind', 'value'))
        if type(prop['value']) is not bool:
            raise InvalidRecord('constant value must be boolean')
    elif kind in ('independent', 'monotone'):
        exact(prop, ('kind', 'input'))
        if not isinstance(prop['input'], str) or prop['input'] not in inputs:
            raise InvalidRecord('unknown property input')
    elif kind == 'case':
        exact(prop, ('kind', 'facts', 'value'))
        if (not isinstance(prop['facts'], dict) or set(prop['facts']) != set(inputs)
                or any(type(v) is not bool for v in prop['facts'].values())
                or type(prop['value']) is not bool):
            raise InvalidRecord('case requires the complete boolean input and a boolean value')
    else:
        raise InvalidRecord('unsupported finite property')
    return prop


def contract(inputs, props):
    if not isinstance(props, list) or not 1 <= len(props) <= 32:
        raise InvalidRecord('property contract requires 1 to 32 properties')
    result = [validate(inputs, prop) for prop in props]
    if len({canon(prop) for prop in result}) != len(result):
        raise InvalidRecord('duplicate contract property')
    return result


def assess(inputs, rows, prop):
    prop = validate(inputs, prop)
    result = dict(property=prop, status='established', checked=0)
    if len(rows) != 2**len(inputs):
        return dict(result, status='checker_error', reason='property table incomplete')
    for index, row in enumerate(rows):
        expected = {n: bool(index & (1 << (len(inputs)-j-1))) for j,n in enumerate(inputs)}
        if row['input'] != expected or type(row['value']) is not bool:
            return dict(result, status='checker_error', reason='property table order or values invalid')
    if prop['kind'] == 'case':
        index = sum(1 << (len(inputs)-j-1) for j,n in enumerate(inputs) if prop['facts'][n])
        row = rows[index]
        result['checked'] = 1
        if row['value'] != prop['value']:
            result.update(status='counterexample', witness=[row])
        return result
    if prop['kind'] == 'constant':
        expected_checks = len(rows)
        for row in rows:
            result['checked'] += 1
            if row['value'] != prop['value']:
                result.update(status='counterexample', witness=[row])
                return result
    else:
        mask = 1 << (len(inputs) - inputs.index(prop['input']) - 1)
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
