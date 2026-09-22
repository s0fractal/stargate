"""Two synchronous components, explicit old-state wiring, inherited joint contract."""
import itertools
from pathlib import Path
import re

from . import lab, machine, compiler, boolean
from .canonical import canon, decode, exact, record_hash, InvalidRecord

MAX_PACKET = machine.MAX_MACHINE
GUIDE = '''A composition has exactly two named transition components, at most six
state bits total and at most two external event bits. Component bodies contain
state (local names), inputs (local port names), and next (one WPL rule per bit).
Each rule declares exactly all local state and input names; unused names are OK.
Names are simple ASCII identifiers, not dotted; env is reserved as a component.
Global state is COMPONENT.BIT; external events are env.NAME. wires maps EVERY
COMPONENT.PORT to a global state bit or external event. Fan-out, self-feedback
and mutual feedback are allowed: every read sees the SAME OLD global state.
No component runs first. Initial states, safety invariant, existential goals and
per-expression ATP budget belong to the composition, not the component bodies.
The invariant declares every global state bit. Initials and goals give complete
Boolean global states. Every external event valuation remains possible.
Reply only {"parent":"COPY_COMPOSITION_ID","component":"NAME","next":{BIT:WPL,...}}.
Replace every next rule of that component. Wiring, interfaces, the other component,
initial states, invariant, goals and budget are inherited unchanged.
The gate checks BOTH parent and candidate over their full reachable joint graphs.
Local safety does not establish joint safety. A partial graph establishes nothing.
A goal is existential from SOME initial state, not inevitable progress or fairness.
The product translation is cross-checked on ALL state/event valuations against
original component rules using the independent Boolean parser; disagreement is
checker_error, never a verdict against the candidate. This finite Boolean pass
has no ATP accounting; the graph then runs the SKI evaluator under max_atp.
composition-check or offline --composition checks a packet. composition-change
or offline --composition-change checks a proposal, using adjacent composition.json.
Both require an independently chosen --expect-composition and the usual runtime
pin offline. Output is a composition child only on successful change admission.
No implicit local component contracts, independent clocks, composition history,
network execution, state abstraction or assume/guarantee proof is claimed.
'''


def _names(values):
    lab._inputs(values)
    if any(re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]{0,31}', n) is None for n in values):
        raise InvalidRecord('composition names must be simple ASCII identifiers of at most 32 characters')


def _mapping(doc, name):
    component = doc['components'][name]
    return dict({bit:name+'.'+bit for bit in component['state']},
                **{port:doc['wires'][name+'.'+port] for port in component['inputs']})


def _lower(source, mapping, names):
    # Original syntax has already passed both parsers. Preserve operator grouping;
    # replace whole identifier tokens only and discard the original declarations.
    tokens = [m.group() for m in compiler.TOKEN.finditer(source)
              if m.group()[0] not in ' \t\r\n\f\v#']
    expression = tokens[tokens.index('check')+1:]
    return ''.join('fact '+n+': bool\n' for n in names)+'check '+ ' '.join(mapping.get(t,t) for t in expression)


def _product(doc):
    state = sorted(name+'.'+bit for name,c in doc['components'].items() for bit in c['state'])
    events = ['env.'+n for n in doc['events']]
    names = sorted(state+events)
    rules = {name+'.'+bit:_lower(source, _mapping(doc,name), names)
             for name,c in sorted(doc['components'].items()) for bit,source in sorted(c['next'].items())}
    return machine.create(dict(state=state,events=events,initial=doc['initial'],next=rules,
        invariant=doc['invariant'],goals=doc['goals'],max_atp=doc['max_atp']))


def inspect(raw):
    if not isinstance(raw,bytes) or len(raw)>MAX_PACKET:
        raise InvalidRecord('composition exceeds size limit or is not bytes')
    doc=decode(raw)
    if not isinstance(doc,dict): raise InvalidRecord('composition must be an object')
    lab._runtime(doc.get('sources'))
    exact(doc,('stargate_composition','components','wires','events','initial','invariant','goals',
               'max_atp','sources','guide','license'))
    if type(doc['stargate_composition']) is not int or doc['stargate_composition']!=32:
        raise InvalidRecord('unsupported composition contract')
    if doc['guide']!=GUIDE or doc['license']!=lab.LICENSE:
        raise InvalidRecord('composition guide or license mismatch')
    components=doc['components']
    if not isinstance(components,dict) or len(components)!=2:
        raise InvalidRecord('composition requires exactly two components')
    _names(sorted(components))
    if 'env' in components: raise InvalidRecord('env is reserved for external events')
    _names(doc['events'])
    if len(doc['events'])>2: raise InvalidRecord('at most two external events')
    ports=set();state=set()
    for name,c in components.items():
        exact(c,('state','inputs','next'));_names(c['state']);_names(c['inputs'])
        if not 1<=len(c['state'])<=6 or set(c['state']) & set(c['inputs']) or len(c['state']+c['inputs'])>8:
            raise InvalidRecord('component needs disjoint state and inputs within eight local names')
        if not isinstance(c['next'],dict) or set(c['next'])!=set(c['state']):
            raise InvalidRecord('component next must define every local state bit')
        for source in c['next'].values(): lab._program(source,sorted(c['state']+c['inputs']))
        ports.update(name+'.'+p for p in c['inputs']);state.update(name+'.'+b for b in c['state'])
    if len(state)>6: raise InvalidRecord('composition exceeds six total state bits')
    if not isinstance(doc['wires'],dict) or set(doc['wires'])!=ports:
        raise InvalidRecord('wire every component input exactly once')
    sources=state|{'env.'+e for e in doc['events']}
    if any(not isinstance(v,str) or v not in sources for v in doc['wires'].values()):
        raise InvalidRecord('wire source must be a state bit or external event')
    _product(doc)  # Validate the global contract and lowered WPL bounds too.
    return doc


def create(spec):
    spec=decode(canon(spec))
    if isinstance(spec,dict): spec.setdefault('goals',[])
    exact(spec,('components','wires','events','initial','invariant','goals','max_atp'))
    raw=canon(dict(spec,stargate_composition=32,sources=lab.runtime_sources(),guide=GUIDE,license=lab.LICENSE))
    inspect(raw)
    return raw


def _bridge(doc, product):
    """Independent original-rule oracle vs lowered compiler AST on the full domain."""
    names=sorted(product['state']+product['events'])
    originals={(name,bit):boolean.program(source,sorted(c['state']+c['inputs']),allow_unused=True)
               for name,c in doc['components'].items() for bit,source in c['next'].items()}
    lowered={bit:compiler.parse(source,dict.fromkeys(names,False),allow_unused=True)[0]
             for bit,source in product['next'].items()}
    rows=list(itertools.product((False,True),repeat=len(names)))
    expected_rows=[tuple(bool(i & (1 << (len(names)-j-1))) for j in range(len(names)))
                   for i in range(2**len(names))]
    if rows!=expected_rows: raise compiler.CompilerBug('composition bridge domain coverage or order mismatch')
    for values in rows:
        global_facts=dict(zip(names,values))
        for name,c in doc['components'].items():
            # Deliberately do not use _mapping: this is the independent wiring path.
            local={bit:global_facts[name+'.'+bit] for bit in c['state']}
            for port in c['inputs']: local[port]=global_facts[doc['wires'][name+'.'+port]]
            for bit in c['state']:
                actual=compiler.interpret(lowered[name+'.'+bit],global_facts)
                expected=boolean.evaluate(originals[name,bit],local)
                if actual!=expected: raise compiler.CompilerBug('composition translation disagrees with local rules')


def verify(raw, expected_composition, *, max_edges=256):
    if type(max_edges) is not int or not 0<=max_edges<=256: raise InvalidRecord('edge quota must be 0..256')
    record_hash(expected_composition);doc=inspect(raw)
    if lab.identity(raw)!=expected_composition: raise InvalidRecord('composition does not match recipient anchor')
    report=dict(composition_id=expected_composition,runtime_digest=lab.runtime_digest(doc['sources']))
    product=_product(doc)
    try: _bridge(doc,decode(product))
    except compiler.CompilerBug as exc: return dict(report,status='checker_error',reason=str(exc))
    checked=machine.verify(product,lab.identity(product),max_edges=max_edges)
    return dict(report,status=checked['status'],check=checked)


def verify_change(raw, proposal, expected_parent, *, max_edges=256):
    if type(max_edges) is not int or not 0<=max_edges<=256: raise InvalidRecord('edge quota must be 0..256')
    doc=inspect(raw);record_hash(expected_parent);parent=lab.identity(raw)
    if parent!=expected_parent: raise InvalidRecord('composition does not match recipient anchor')
    proposal=decode(canon(proposal))
    if len(canon(proposal))>machine.MAX_CHANGE: raise InvalidRecord('composition proposal exceeds size limit')
    exact(proposal,('parent','component','next'));record_hash(proposal['parent'])
    if proposal['parent']!=parent: raise InvalidRecord('proposal parent mismatch')
    name=proposal['component']
    if not isinstance(name,str) or name not in doc['components']: raise InvalidRecord('unknown component')
    components=dict(doc['components']);components[name]=dict(components[name],next=proposal['next'])
    candidate=canon(dict(doc,components=components));inspect(candidate)
    report=dict(status='incomplete',parent=parent,candidate=lab.identity(candidate),component=name,admitted=False,checks={})
    for role,packet in [('parent',raw),('candidate',candidate)]:
        checked=verify(packet,lab.identity(packet),max_edges=max_edges);report['checks'][role]=checked
        if checked['status']!='established':
            status='parent_rejected' if role=='parent' and checked['status'] in machine.REFUSED else checked['status']
            return dict(report,status=status,program=role),None
    return dict(report,status='safety_preserved',admitted=True,successor=lab.identity(candidate)),candidate


def read(path):
    return machine.read(path)


def read_spec(raw):
    # Human-authored JSON accepts formatting, never duplicate keys.
    import json
    def unique(pairs):
        out={}
        for k,v in pairs:
            if k in out: raise InvalidRecord('duplicate composition field: '+k)
            out[k]=v
        return out
    return json.loads(raw,object_pairs_hook=unique)


def describe(raw):
    doc=inspect(raw)
    return dict(status='unchecked_composition',composition_id=lab.identity(raw),
                runtime_digest=lab.runtime_digest(doc['sources']))
