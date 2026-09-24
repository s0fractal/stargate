"""Live reproducers for black-heart scoped_admission.py at origin/main 3893fad.

    git -C BLACK_HEART show 3893fad:scoped_admission.py > /tmp/scoped_admission.py
    python examples/semantic-seal/reproducer_3893fad.py /tmp/scoped_admission.py

The file must be exactly blob 78b5ac6b80e9ce37a34e108dc96f2e939d00afa9 (sha256 below);
anything else is refused. Exit 0 when both defects reproduce, 1 otherwise. No network.

A (this vertical): a SEMANTIC_COUNTEREXAMPLE for (candidate, evaluator, requirement) is
   bypassed by registering a RESOURCE_LIMIT refusal for the same triple.
D (separate finding, not modelled here): import_state() of an older export rolls the
   spent retest quota and the run counter back.
"""
import hashlib
import importlib.util
import sys

PINNED_SHA256 = 'db38200bb193525b0649213600ae747d0ac1da6f6eab0e685413c49537f11362'


def load(path):
    data = open(path, 'rb').read()
    if hashlib.sha256(data).hexdigest() != PINNED_SHA256:
        sys.exit('refused: ' + path + ' is not the pinned scoped_admission.py of 3893fad')
    spec = importlib.util.spec_from_file_location('scoped_admission', path)
    module = importlib.util.module_from_spec(spec)
    sys.modules['scoped_admission'] = module
    spec.loader.exec_module(module)
    return module


def main(path):
    sa = load(path)
    candidate = b'candidate program'
    C, E, R = hashlib.sha256(candidate).hexdigest(), 'e' * 64, 'r' * 64
    calls = []

    def executor(outcome):
        def run(code, context):
            calls.append(context['budget_steps'])
            return outcome, 10, b'evidence'
        return run

    def refusal(kind, evidence):
        return sa.RefusalRecord.create(C, E, R, 'i' * 64, evidence, {'budget_steps': 100}, kind, 100)

    def request(ref, budget):
        return sa.ReevaluationRequest.create(ref.record_id, C, E, R, {'budget_steps': budget}, 'more budget')

    # A: semantic seal bypassed through a resource refusal for the same triple.
    reg = sa.ScopedAdmissionRegistry()
    semantic = refusal(sa.RefusalReason.SEMANTIC_COUNTEREXAMPLE, b'counterexample x=3')
    reg.register_refusal(semantic)
    blocked = reg.assess_request(request(semantic, 200))[0] == sa.ReevalEligibility.BLOCKED_BY_EXISTING_EVIDENCE
    resource = refusal(sa.RefusalReason.RESOURCE_LIMIT, b'ran out of steps')
    reg.register_refusal(resource)
    result = reg.execute_retest(request(resource, 200), candidate, executor(sa.RetestOutcome.SUCCESS))
    admitted = reg.grant_scoped_admission(result) is not None
    a = blocked and admitted and reg.admission_for(C, {'budget_steps': 200}, R, E) is not None
    print('A semantic path blocked:', blocked, '| admitted through the resource refusal:', admitted)

    # D: an older export rolls the spent quota back.
    calls.clear()
    reg = sa.ScopedAdmissionRegistry()
    reg.register_refusal(resource)
    reg.execute_retest(request(resource, 200), candidate, executor(sa.RetestOutcome.FAILURE))
    snapshot = reg.export_state()
    reg.execute_retest(request(resource, 300), candidate, executor(sa.RetestOutcome.FAILURE))
    reg.execute_retest(request(resource, 400), candidate, executor(sa.RetestOutcome.FAILURE))
    reg.import_state(snapshot)
    reg.execute_retest(request(resource, 500), candidate, executor(sa.RetestOutcome.FAILURE))
    late = reg.execute_retest(request(resource, 600), candidate, executor(sa.RetestOutcome.SUCCESS))
    d = len(calls) == 5 and reg.grant_scoped_admission(late) is not None and reg.executed_runs_count == 3
    print('D executor calls:', len(calls), '(quota', str(reg.MAX_ATTEMPTS_PER_REFUSAL_FAMILY) + ')',
          '| recorded executed_runs_count:', reg.executed_runs_count)
    return 0 if a and d else 1


if __name__ == '__main__':
    sys.exit(main(sys.argv[1]))
