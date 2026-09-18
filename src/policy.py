"""Policy authoring: compile, sign and publish above record verification."""
from . import kernel as k
from .canonical import canon, decode
from .compiler import compile_source, PolicyError, CompilerBug, DEFAULT_MAX_ATP
from .records import create_record, record_id


def author_policy(source, facts, store, key, *, max_atp=DEFAULT_MAX_ATP, subject=None):
    facts_raw = canon(facts)
    facts = decode(facts_raw)
    if not isinstance(facts, dict):
        raise PolicyError('facts must be an object')
    compiled = compile_source(source, max_atp=max_atp, facts=facts)
    rule_raw = source.encode('utf-8')
    rule_hash, facts_hash = k.sha(rule_raw).hex(), k.sha(facts_raw).hex()
    provenance = dict(rule=rule_hash, facts=facts_hash)
    staged = dict(compiled.objects)
    staged[k.sha(rule_raw)] = rule_raw
    staged[k.sha(facts_raw)] = facts_raw
    envelope = create_record(compiled.check, staged, key, policy=provenance, subject=subject)
    for raw in staged.values():
        store.put(raw)
    envelope_object = store.put(canon(envelope))
    return dict(record=record_id(envelope['body']), object=envelope_object,
                decision=envelope['body']['decision'], policy=provenance, subject=subject,
                policy_value=compiled.value, atp_spent=compiled.atp_spent,
                check=compiled.check)
