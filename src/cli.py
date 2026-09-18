"""One CLI, exposed as both stargate and sg."""
import argparse
import json
import os
from pathlib import Path
import sys

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives import serialization

from . import CONTRACT_STATUS, KELVIN, __version__, kernel
from .records import canon, decode, capture_environment, create_record, public_key, record_id, verify_record
from .store import Store, StoreError, hex_hash
from .bundle import export_bundle, verify_bundle, read_bundle, write_bundle, require_bundle
from .policy import author_policy, CompilerBug, DEFAULT_MAX_ATP
from .case import pack_case, inspect_case, read_case, unpack_case
from . import lab, search, invariants, lineage
from .artifact import subject_hash, admit_bundle, admit_all, measure_subject


def parser():
    p = argparse.ArgumentParser(prog="sg", allow_abbrev=False,
        description="Stargate: computation and signed checks. 32K is a draft contract.")
    p.add_argument("--version", action="version",
                   version=f"Stargate build {__version__} · {KELVIN}K ({CONTRACT_STATUS})")
    p.add_argument("--store", default=".stargate", help="content-addressed object directory")
    sub = p.add_subparsers(dest="command")
    def cmd(name, help):
        return sub.add_parser(name, help=help, allow_abbrev=False)
    cmd("init", "create the object directory")
    q = cmd("keygen", "write a new private seed (never overwrite)")
    q.add_argument("path", type=Path)
    q = cmd("put", "store object bytes")
    q.add_argument("path", type=Path)
    cmd("genesis", "show intrinsic I/K/S hashes")
    q = cmd("apply", "store an application of two hashes")
    q.add_argument("left", type=hex_hash); q.add_argument("right", type=hex_hash)
    q = cmd("eval", "evaluate a term, reporting result, exit and cost")
    q.add_argument("term", type=hex_hash); q.add_argument("--atp", required=True, type=int)
    q = cmd("record", "execute a check and store its signed decision")
    q.add_argument("term", type=hex_hash); q.add_argument("--atp", required=True, type=int)
    q.add_argument("--expect", required=True, type=hex_hash)
    q.add_argument("--exit", required=True, choices=kernel.EXITS)
    q.add_argument("--subject", type=Path, help="bind to SHA-256 of this regular file")
    q.add_argument("--key", required=True, type=Path)
    q.add_argument("--environment", type=Path,
                   help="JSON list defining the exact object domain; otherwise capture demanded objects")
    q = cmd("policy", "compile a boolean WPL file and sign its decision")
    q.add_argument("source", type=Path)
    inputs = q.add_mutually_exclusive_group(required=True)
    inputs.add_argument("--facts", type=Path)
    inputs.add_argument("--derive", type=Path, help="derive boolean facts from subject bytes using this JSON profile")
    q.add_argument("--subject", type=Path, help="bind to SHA-256 of this regular file")
    q.add_argument("--key", required=True, type=Path)
    q.add_argument("--max-atp", type=int, default=DEFAULT_MAX_ATP)
    q = cmd("verify", "verify a stored signed record by independent re-execution")
    q.add_argument("object", type=hex_hash)
    q.add_argument("--trust", required=True, action="append", type=hex_hash,
                   help="explicitly trusted public key; repeat for multiple keys")
    q = cmd("export", "verify and export one portable signed check")
    q.add_argument("object", type=hex_hash)
    q.add_argument("output", type=Path)
    q.add_argument("--trust", required=True, action="append", type=hex_hash)
    q = cmd("verify-bundle", "verify a file without any local object store")
    q.add_argument("path", type=Path)
    q.add_argument("--trust", required=True, action="append", type=hex_hash)
    q = cmd("require", "require a verified accept for the recipient's rule and facts")
    q.add_argument("path", type=Path)
    q.add_argument("--trust", required=True, action="append", type=hex_hash)
    q.add_argument("--rule", required=True, type=Path)
    inputs = q.add_mutually_exclusive_group(required=True)
    inputs.add_argument("--facts", type=Path)
    inputs.add_argument("--derive", type=Path, help="derive boolean facts from subject bytes using this JSON profile")
    q.add_argument("--subject", type=Path, help="require SHA-256 of this regular file; omission requires an unbound record")
    q = cmd("admit", "publish verified artifact bytes without replacing an existing file")
    q.add_argument("path", type=Path)
    q.add_argument("--trust", required=True, action="append", type=hex_hash)
    q.add_argument("--rule", required=True, type=Path)
    inputs = q.add_mutually_exclusive_group(required=True)
    inputs.add_argument("--facts", type=Path)
    inputs.add_argument("--derive", type=Path, help="derive boolean facts from subject bytes using this JSON profile")
    q.add_argument("--subject", required=True, type=Path)
    q.add_argument("--output", required=True, type=Path)
    q = cmd("admit-all", "publish one artifact only after every named requirement holds")
    q.add_argument("plan", type=Path, help="recipient JSON plan; paths relative to this file")
    q.add_argument("--subject", required=True, type=Path)
    q.add_argument("--output", required=True, type=Path)
    q = cmd("case-pack", "pack counterexample evidence as inert data")
    q.add_argument("manifest", type=Path)
    q.add_argument("--root", required=True, type=Path)
    q.add_argument("--output", required=True, type=Path)
    q = cmd("case-inspect", "check packet integrity; never execute its contents")
    q.add_argument("path", type=Path)
    q = cmd("case-unpack", "materialize evidence in a new directory; never execute it")
    q.add_argument("path", type=Path)
    q.add_argument("--output", required=True, type=Path)
    q = cmd("lab-create", "create a portable finite boolean experiment (no keys)")
    q.add_argument("rule", type=Path)
    q.add_argument("--input", action="append", default=[], dest="inputs")
    q.add_argument("--max-atp", type=int, default=1000)
    q.add_argument("--objective", choices=("equivalence", "satisfy", "lower_max_atp"), default=None)
    q.add_argument("--output", required=True, type=Path)
    q.add_argument("--properties", type=Path, help="JSON property contract; explicitly permits behavior changes")
    q = cmd("lab-inspect", "describe a finite experiment; never run included code")
    q.add_argument("path", type=Path)
    q = cmd("lab-check", "exhaustively check a text proposal without trusted keys")
    q.add_argument("path", type=Path)
    q.add_argument("proposal", type=Path)
    q.add_argument("--output", type=Path, help="write an admitted successor, never overwrite")
    q = cmd("lab-unpack", "extract a standalone checker for explicit offline replay")
    q.add_argument("path", type=Path)
    q.add_argument("--output", required=True, type=Path)
    q = cmd("lab-search", "search a bounded WPL neighborhood using replayed counterexamples")
    q.add_argument("path", type=Path)
    q.add_argument("--max-candidates", type=int, default=32)
    q.add_argument("--experience", type=Path, help="previous experience object, rechecked before use")
    q.add_argument("--output", type=Path, help="write found successor; never overwrite")
    q = cmd("lab-discover", "enumerate and check finite input/output properties")
    q.add_argument("path", type=Path)
    q.add_argument("--output", type=Path, help="write complete discovery report; never overwrite")
    q = cmd("lab-check-invariant", "recompute a finite property claim without trusting its author")
    q.add_argument("path", type=Path)
    q.add_argument("claim", type=Path)
    for name in ('lineage-start', 'lineage-append', 'lineage-check', 'lineage-unpack'):
        q = cmd(name, 'create, extend, replay or materialize an anchored world history')
        q.add_argument('path', type=Path)
        if name == 'lineage-append': q.add_argument('proposal', type=Path)
        if name in ('lineage-append', 'lineage-check'):
            q.add_argument('--expect-root', required=True)
        q.add_argument('--output', type=Path, required=name != 'lineage-check')
    return p



def read_facts(path):
    def unique(pairs):
        out = {}
        for name, value in pairs:
            if name in out:
                raise ValueError("duplicate fact: " + name)
            out[name] = value
        return out
    return json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=unique)


def selected_facts(args):
    if args.derive:
        measurement = measure_subject(args.subject, read_facts(args.derive))
        return measurement['facts'], measurement['subject'], measurement
    return read_facts(args.facts), subject_hash(args.subject), None


def read_admission_plan(path):
    """Read every local input before staging. Trust is selected per requirement."""
    try:
        plan = read_facts(path)
        if not isinstance(plan, list) or not 1 <= len(plan) <= 32:
            raise ValueError('admission plan must contain 1 to 32 requirements')
        loaded = []
        for req in plan:
            if not isinstance(req, dict) or set(req) not in (
                    {'name', 'bundle', 'trust', 'rule', 'facts'},
                    {'name', 'bundle', 'trust', 'rule', 'derive'}):
                raise ValueError('invalid admission plan requirement fields')
            mode = 'derive' if 'derive' in req else 'facts'
            for field in ('bundle', 'rule', mode):
                if not isinstance(req[field], str) or not req[field]:
                    raise ValueError('plan input paths must be nonempty strings')
            loaded.append(dict(name=req['name'], trust=req['trust'],
                bundle=read_bundle(path.parent / req['bundle']),
                rule=(path.parent / req['rule']).read_bytes().decode('utf-8'),
                **{mode: read_facts(path.parent / req[mode])}))
        return loaded
    except OSError as exc:
        raise StoreError('cannot read admission plan input: ' + str(exc)) from exc


def execute(args):
    if args.command.startswith('lineage-'):
        try:
            raw = lab.read_world(args.path) if args.command == 'lineage-start' else lineage.read(args.path)
            if args.command == 'lineage-append':
                with args.proposal.open('rb') as stream:
                    proposal = lab.read_proposal(stream.read(lab.MAX_PROPOSAL + 1))
        except OSError as exc:
            raise StoreError('cannot read lineage input: ' + str(exc)) from exc
        if args.command == 'lineage-start':
            created = lineage.create(raw)
            write_bundle(args.output, created)
            return dict(status='created', lineage_id=lab.identity(created), root=lab.identity(raw))
        if args.command == 'lineage-unpack':
            return lineage.unpack(raw, args.output)
        if args.command == 'lineage-append':
            report, output = lineage.append(raw, proposal, args.expect_root)
        else:
            report, output = lineage.verify(raw, args.expect_root)
        if output is not None and args.output is not None:
            write_bundle(args.output, output)
        return report
    if args.command in ('lab-discover', 'lab-check-invariant'):
        try:
            raw = lab.read_world(args.path)
            if args.command == 'lab-check-invariant':
                with args.claim.open('rb') as stream:
                    claim = lab.read_proposal(stream.read(lab.MAX_PROPOSAL + 1))
        except OSError as exc:
            raise StoreError('cannot read invariant input: ' + str(exc)) from exc
        if args.command == 'lab-check-invariant':
            return invariants.verify_claim(raw, claim)
        report = invariants.discover(raw)
        if report['status'] == 'complete' and args.output is not None:
            write_bundle(args.output, canon(report))
        return report
    if args.command == 'lab-search':
        try:
            raw = lab.read_world(args.path)
            experience = read_facts(args.experience) if args.experience else None
        except OSError as exc:
            raise StoreError('cannot read search input: ' + str(exc)) from exc
        report, successor = search.search(raw, max_candidates=args.max_candidates, experience=experience)
        if successor is not None and args.output is not None:
            write_bundle(args.output, successor)
        return report
    if args.command == "lab-create":
        props = read_facts(args.properties) if args.properties else None
        if args.properties is not None and props is None:
            raise ValueError("property contract must be a nonempty list, not null")
        raw = lab.create_world(args.rule.read_bytes().decode('utf-8'), sorted(args.inputs),
                               max_atp=args.max_atp, objective=args.objective,
                               properties=props)
        write_bundle(args.output, raw)
        return dict(status='created', world_id=lab.identity(raw), path=str(args.output))
    if args.command in ('lab-inspect', 'lab-check', 'lab-unpack'):
        try:
            raw = lab.read_world(args.path)
        except OSError as exc:
            raise StoreError('cannot read experiment: ' + str(exc)) from exc
        if args.command == 'lab-unpack':
            return lab.unpack_world(raw, args.output)
        if args.command == 'lab-check':
            try:
                with args.proposal.open('rb') as stream:
                    proposal = lab.read_proposal(stream.read(lab.MAX_PROPOSAL + 1))
            except OSError as exc:
                raise StoreError('cannot read proposal: ' + str(exc)) from exc
            report, successor = lab.verify_transition(raw, proposal)
            if successor is not None and args.output is not None:
                write_bundle(args.output, successor)
            return report
        doc = lab.inspect_world(raw)
        return dict(status='intact', world_id=lab.identity(raw),
                    runtime_digest=lab.runtime_digest(doc['sources']),
                    replay_digest=lab.identity(lab.REPLAY.encode()), guide=doc['guide'],
                    rule=doc['rule'], inputs=doc['inputs'], max_atp=doc['max_atp'],
                    contract=doc['contract'], properties=doc.get('properties'),
                    objective=doc['objective'], predecessor=doc['predecessor'])
    if args.command == "case-inspect":
        return inspect_case(read_case(args.path))[0]
    if args.command == "case-unpack":
        return unpack_case(read_case(args.path), args.output)
    if args.command == "case-pack":
        from .case import _path, MAX_FILES, MAX_CASE_BYTES
        try:
            spec = read_facts(args.manifest)
            if not isinstance(spec, dict) or set(spec) != {'manifest', 'files'}:
                raise ValueError('expected manifest and files')
            names = spec['files']
            if (not isinstance(names, list) or not 1 <= len(names) <= MAX_FILES or
                    not all(isinstance(n, str) for n in names) or len(set(names)) != len(names)):
                raise ValueError('expected 1 to 64 unique file names')
            root = args.root.resolve()
            files, total = {}, 0
            for name in names:
                _path(name)
                path = (root / name).resolve()
                if root not in path.parents:
                    raise ValueError('case input escapes root')
                # Reuse regular-file streaming checks; packing is not code execution.
                from .artifact import _subject_chunks
                from contextlib import closing
                data = bytearray()
                with closing(_subject_chunks(path)) as chunks:
                    for chunk in chunks:
                        total += len(chunk)
                        if total > MAX_CASE_BYTES // 2:
                            raise StoreError('case payload exceeds local size limit')
                        data.extend(chunk)
                files[name] = bytes(data)
        except OSError as exc:
            raise StoreError('cannot read case input: ' + str(exc)) from exc
        raw = pack_case(spec['manifest'], files)
        write_bundle(args.output, raw)
        return dict(inspect_case(raw)[0], path=str(args.output))
    if args.command == "admit-all":
        return admit_all(read_admission_plan(args.plan), subject=args.subject, output=args.output)
    if args.command == "admit":
        try:
            rule = args.rule.read_bytes().decode("utf-8")
            facts = read_facts(args.facts) if args.facts else None
            derive = read_facts(args.derive) if args.derive else None
            raw = read_bundle(args.path)
        except OSError as exc:
            raise StoreError('cannot read admission input: ' + str(exc)) from exc
        return admit_bundle(raw, set(args.trust), rule=rule, facts=facts,
                            subject=args.subject, output=args.output, derive=derive)
    if args.command == "require":
        rule = args.rule.read_bytes().decode("utf-8")
        facts, h, measurement = selected_facts(args)
        raw = read_bundle(args.path)
        report = require_bundle(raw, set(args.trust), rule=rule, facts=facts, subject=h)
        if measurement is not None:
            report['derivation'] = measurement
        return report
    store = Store(args.store)
    if args.command == "verify-bundle":
        return verify_bundle(read_bundle(args.path), set(args.trust))
    if args.command == "export":
        raw, report = export_bundle(store.read(args.object), store, set(args.trust))
        write_bundle(args.output, raw)
        return dict(bundle=str(args.output), record=report["record"], decision=report["decision"])
    if args.command == "init":
        store.path.mkdir(parents=True, exist_ok=True)
        return {"store": str(store.path)}
    if args.command == "keygen":
        key = Ed25519PrivateKey.generate()
        seed = key.private_bytes(serialization.Encoding.Raw, serialization.PrivateFormat.Raw,
                                 serialization.NoEncryption())
        fd = os.open(args.path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "w") as f:
            f.write(seed.hex() + "\n")
        return {"key": public_key(key)}
    if args.command == "put":
        return {"object": store.put(args.path.read_bytes())}
    if args.command == "genesis":
        return {"I": kernel.I_H.hex(), "K": kernel.K_H.hex(), "S": kernel.S_H.hex()}
    if args.command == "apply":
        raw = kernel.ser(kernel.APPLY, kernel.F_LEFT | kernel.F_RIGHT,
                         left=bytes.fromhex(args.left), right=bytes.fromhex(args.right))
        return {"object": store.put(raw)}
    if args.command == "eval":
        receipt = kernel.eval_receipt(bytes.fromhex(args.term), args.atp, store, kernel.VERIFIER_LIMITS)
        return dict(stargate=KELVIN, verifier_build=__version__, **receipt.as_dict())
    if args.command == "record":
        key = Ed25519PrivateKey.from_private_bytes(bytes.fromhex(args.key.read_text().strip()))
        environment = (json.loads(args.environment.read_text()) if args.environment is not None
                       else capture_environment(args.term, args.atp, store))
        check = dict(term=args.term, atp=args.atp, expect=args.expect, exit=args.exit,
                     environment=environment)
        envelope = create_record(check, store, key, subject=subject_hash(args.subject))
        return {"record": record_id(envelope["body"]), "object": store.put(canon(envelope)),
                "decision": envelope["body"]["decision"]}
    if args.command == "policy":
        key = Ed25519PrivateKey.from_private_bytes(bytes.fromhex(args.key.read_text().strip()))
        facts, h, measurement = selected_facts(args)
        report = author_policy(args.source.read_bytes().decode("utf-8"), facts, store, key,
                               max_atp=args.max_atp, subject=h)
        if measurement is not None:
            report['derivation'] = measurement
        return report
    if args.command == "verify":
        return verify_record(store.read(args.object), store, set(args.trust))
    raise ValueError("unknown operation")


def main(argv=None):
    p = parser()
    args = p.parse_args(argv)
    if args.command is None:
        p.print_help()
        return 0
    try:
        result = execute(args)
    except lab.RuntimeMismatch as exc:
        print(json.dumps({"status": "runtime_unavailable", "error": str(exc)}), file=sys.stderr)
        return 3
    except CompilerBug as exc:
        print(json.dumps({"status": "compiler_error", "error": str(exc)}), file=sys.stderr)
        return 1
    except OSError as exc:
        status = "unverified" if args.command in ("verify", "verify-bundle", "eval", "require") else "operation_error"
        print(json.dumps({"status": status, "error": str(exc)}), file=sys.stderr)
        return 3 if status == "unverified" else 1
    except (kernel.AdmissionRefused, kernel.ResourceFault, StoreError) as exc:
        print(json.dumps({"status": "unverified", "error": str(exc)}), file=sys.stderr)
        return 3
    except (ValueError, TypeError, RecursionError) as exc:
        print(json.dumps({"status": "invalid", "error": str(exc)}), file=sys.stderr)
        return 2
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    if args.command in ('lineage-check', 'lineage-append'):
        if result['status'] == 'verified_lineage': return 0
        if result['status'] == 'incomplete': return 3
        return 1 if result['status'] == 'checker_error' else 4
    if args.command in ('lab-discover', 'lab-check-invariant'):
        if result['status'] in ('complete', 'established'): return 0
        if result['status'] == 'checker_error': return 1
        return 3 if result['status'] == 'incomplete' else 4
    if args.command == 'lab-search':
        if result['status'] == 'found': return 0
        if result['status'] == 'checker_error': return 1
        return 4 if result['status'] in ('neighborhood_exhausted', 'parent_rejected') else 3
    if args.command == 'lab-check':
        if result['status'] == 'incomplete': return 3
        if result['status'] == 'checker_error': return 1
        return 0 if result['admitted'] else 4
    return 4 if result.get("status") == "unsatisfied" else 0
