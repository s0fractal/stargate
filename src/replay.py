"""One independently authenticated offline launcher; execute only captured source text."""
import argparse
import hashlib
import importlib.util
import json
import re
from pathlib import Path
import sys

PROOF = ('__init__.py', 'store.py', 'canonical.py', 'boolean.py', 'certificate.py')
PROJECTION = PROOF + ('projection_check.py',)
SUBJECT = ('__init__.py', 'kernel.py', 'store.py', 'canonical.py', 'checks.py', 'compiler.py', 'boolean.py')
LAB = SUBJECT + ('properties.py', 'lab.py', 'invariants.py', 'lineage.py', 'labtask.py', 'machine.py', 'composition.py')


def parser():
    p = argparse.ArgumentParser(allow_abbrev=False)
    p.add_argument('proposal', type=Path)
    p.add_argument('output', nargs='?', type=Path)
    p.add_argument('--output', dest='output_flag', type=Path)
    pins = p.add_mutually_exclusive_group(required=True)
    for name in ('runtime', 'checker', 'controller'): pins.add_argument('--expect-'+name)
    mode = p.add_mutually_exclusive_group()
    for name in ('invariant','lineage','task','machine','machine-discover','machine-claim',
                 'machine-change','composition','composition-change','change','history','refutation','repair',
                 'projection'):
        mode.add_argument('--'+name, action='store_true')
    for name in ('model','root','task','machine','composition'): p.add_argument('--expect-'+name)
    p.add_argument('--expect-projection-checker')
    p.add_argument('--max-steps', type=int)  # default: the loaded checker's own ceiling
    p.add_argument('--max-edges', type=int, default=256)
    p.add_argument('--rows', type=int)
    p.add_argument('--execute-runtimes', action='store_true')
    return p


class VerifiedLoader:
    def __init__(self, texts): self.texts = texts
    def get_data(self, path):
        name = Path(path).name
        if path != '/__stargate_snapshot__/' + name or name not in self.texts:
            raise OSError('outside verified source snapshot')
        return self.texts[name].encode('utf-8')
    def create_module(self, spec): return None
    def exec_module(self, module):
        exec(compile(self.get_data(module.__file__), module.__file__, 'exec'), module.__dict__)


def load(texts, names):
    loader = VerifiedLoader(texts)
    for name in names:
        fullname = 'stargate' if name == '__init__.py' else 'stargate.' + name[:-3]
        if fullname in sys.modules: raise RuntimeError('unexpected preloaded packet module')
        spec = importlib.util.spec_from_loader(fullname, loader, is_package=name == '__init__.py')
        module = importlib.util.module_from_spec(spec)
        module.__file__ = '/__stargate_snapshot__/' + name
        sys.modules[fullname] = module
        loader.exec_module(module)
        if name != '__init__.py': setattr(sys.modules['stargate'], name[:-3], module)


def dispatch(a, root):
    if a.projection:
        from stargate import certificate as c, projection_check as pc
        with a.proposal.open('rb') as f: raw = f.read(pc.MAX_PROJECTION + 1)
        report = pc.check(raw, c.read(root/'certificate.json'), a.expect_model, a.expect_checker,
                          a.expect_projection_checker)
        return report, None, pc.exit_code(report)
    if a.expect_checker:
        from stargate import certificate as c
        check = c.verify_repair if a.repair else c.verify_history if a.history else c.verify_change if a.change else c.verify_refutation if a.refutation else c.verify
        result = check(c.read(a.proposal), a.expect_model, a.expect_checker, max_steps=c.MAX_STEPS if a.max_steps is None else a.max_steps)
        report, output = result if isinstance(result, tuple) else (result, None)
        return report, output, c.exit_code(report)
    if a.expect_controller:
        from stargate import experiment
        report = experiment.run(experiment.read(a.proposal), expect_controller=a.expect_controller, execute=True)
        return report, None, experiment.exit_code(report)
    from stargate import lab, machine, composition, lineage, labtask, invariants
    output = None
    if a.composition_change:
        report, output = composition.verify_change(composition.read(root/'composition.json'), machine.read_change(a.proposal), a.expect_composition, max_edges=a.max_edges)
    elif a.composition:
        report = composition.verify(composition.read(a.proposal), a.expect_composition, max_edges=a.max_edges)
    elif a.machine_change:
        report, output = machine.verify_change(machine.read(root/'machine.json'), machine.read_change(a.proposal), a.expect_machine, max_edges=a.max_edges)
    elif a.machine_claim:
        report = machine.verify_property(machine.read(root/'machine.json'), machine.read_change(a.proposal), a.expect_machine, max_edges=a.max_edges)
    elif a.machine_discover:
        report = machine.discover_properties(machine.read(a.proposal), a.expect_machine, max_edges=a.max_edges)
    elif a.machine:
        report = machine.verify(machine.read(a.proposal), a.expect_machine, max_edges=a.max_edges)
    elif a.lineage:
        report, output = lineage.verify(lineage.read(a.proposal), a.expect_root)
    elif a.task:
        report, output = labtask.resume(labtask.read(a.proposal), a.expect_task, rows=a.rows)
    elif a.invariant:
        report = invariants.verify_claim(lab.read_world(root/'world.json'), lab.read_proposal(a.proposal.read_bytes()))
    else:
        report, output = lab.verify_transition(lab.read_world(root/'world.json'), lab.read_proposal(a.proposal.read_bytes()))
    status = report['status']
    code = (0 if report.get('admitted') or status in ('established','safety_preserved','complete','verified_lineage') else
            3 if status in ('suspended','incomplete') else 1 if status == 'checker_error' else 4)
    return report, output, code


def main(argv=None):
    if not sys.flags.isolated or not sys.flags.no_site:
        raise SystemExit('replay requires python -I -S')
    p = parser(); a = p.parse_intermixed_args(argv)
    if a.output and a.output_flag: p.error('choose one output path')
    a.output = a.output or a.output_flag
    proof_modes = a.change or a.history or a.refutation or a.repair or a.projection
    if bool(a.projection) != bool(a.expect_projection_checker): p.error('--projection and --expect-projection-checker come together')
    lab_modes = a.invariant or a.lineage or a.task or a.machine or a.machine_change or a.machine_discover or a.machine_claim or a.composition or a.composition_change
    if (proof_modes and not a.expect_checker) or (lab_modes and not a.expect_runtime): p.error('mode and anchor family disagree')
    if bool(a.expect_checker) != bool(a.expect_model): p.error('proof checking requires --expect-model')
    if bool(a.expect_controller) != a.execute_runtimes: p.error('controller execution requires --execute-runtimes')
    for active, value, label in ((a.lineage,a.expect_root,'root'),(a.task,a.expect_task,'task'),
        (a.machine or a.machine_change or a.machine_discover or a.machine_claim,a.expect_machine,'machine'),
        (a.composition or a.composition_change,a.expect_composition,'composition')):
        if bool(active) != bool(value): p.error('mode requires its own --expect-'+label)
    if (a.task and a.rows is None) or (not a.task and a.rows is not None): p.error('--rows requires --task')
    if a.output and (a.expect_controller or (a.expect_checker and not (a.change or a.history or a.repair)) or a.invariant or a.machine or a.machine_discover or a.machine_claim or a.composition):
        p.error('this check does not produce successor bytes')
    root = Path(__file__).resolve().parent
    names = PROJECTION if a.projection else PROOF if a.expect_checker else SUBJECT+('experiment.py',) if a.expect_controller else LAB
    expected = a.expect_projection_checker or a.expect_checker or a.expect_controller or a.expect_runtime
    if re.fullmatch(r'[0-9a-f]{64}', expected) is None: p.error('expected a lowercase SHA-256 source anchor')
    unavailable = 'projection_checker_unavailable' if a.projection else 'checker_unavailable' if a.expect_checker else 'controller_unavailable' if a.expect_controller else 'runtime_unavailable'
    try:
        if a.expect_runtime:
            texts = {n:(root/'stargate'/n).read_bytes().decode('utf-8') for n in names}
        else:
            source_map = 'projection-checker.json' if a.projection else 'checker.json' if a.expect_checker else 'controller.json'
            with (root/source_map).open('rb') as f: raw = f.read((1024*1024 if a.expect_checker else 4*1024*1024)+1)
            if len(raw)>(1024*1024 if a.expect_checker else 4*1024*1024): raise ValueError('source map exceeds limit')
            texts = json.loads(raw)
        if type(texts) is not dict or set(texts)!=set(names) or any(type(s) is not str for s in texts.values()):
            raise ValueError('invalid source map')
        digest = hashlib.sha256(json.dumps(texts,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()).hexdigest()
        if digest != expected:
            report = dict(status=unavailable, digest=digest)
            if a.expect_runtime: report.update(runtime_digest=digest, expected_runtime=expected, admitted=False)
            print(json.dumps(report)); return 3
        load(texts, names)  # Never read code from disk again after this comparison.
        report, output, code = dispatch(a, root)
    except (ValueError, TypeError, RecursionError) as exc:
        print(json.dumps(dict(status='invalid',error=str(exc))), file=sys.stderr if a.expect_runtime else sys.stdout); return 2
    except OSError as exc:
        print(json.dumps(dict(status='unverified',error=str(exc))), file=sys.stderr if a.expect_runtime else sys.stdout); return 3
    except Exception as exc:
        module = sys.modules.get('stargate.lab')
        if module and isinstance(exc, module.RuntimeMismatch):
            print(json.dumps(dict(status='runtime_unavailable',error=str(exc))), file=sys.stderr); return 3
        print(json.dumps(dict(status='checker_error',error=str(exc)))); return 1
    if output is not None and a.output:
        try:
            with a.output.open('xb') as f: f.write(output)
        except OSError as exc:
            print(json.dumps(dict(status='operation_error',error=str(exc)))); return 1
    print(json.dumps(report,sort_keys=True))
    return code


if __name__ == '__main__':
    raise SystemExit(main())
