"""One CLI, exposed as both stargate and sg."""
import argparse
import json
import os
from pathlib import Path
import sys

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives import serialization

from . import CONTRACT_STATUS, KELVIN, __version__, kernel
from .records import canon, capture_environment, create_record, public_key, record_id, verify_record
from .store import Store, StoreError, hex_hash
from .bundle import export_bundle, verify_bundle, read_bundle, write_bundle
from .policy import author_policy, CompilerBug, DEFAULT_MAX_ATP


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
    q.add_argument("--key", required=True, type=Path)
    q.add_argument("--environment", type=Path,
                   help="JSON list defining the exact object domain; otherwise capture demanded objects")
    q = cmd("policy", "compile a boolean WPL file and sign its decision")
    q.add_argument("source", type=Path)
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
    return p


def execute(args):
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
        envelope = create_record(check, store, key)
        return {"record": record_id(envelope["body"]), "object": store.put(canon(envelope)),
                "decision": envelope["body"]["decision"]}
    if args.command == "policy":
        key = Ed25519PrivateKey.from_private_bytes(bytes.fromhex(args.key.read_text().strip()))
        return author_policy(args.source.read_text(encoding="utf-8"), store, key, max_atp=args.max_atp)
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
    except CompilerBug as exc:
        print(json.dumps({"status": "compiler_error", "error": str(exc)}), file=sys.stderr)
        return 1
    except OSError as exc:
        status = "unverified" if args.command in ("verify", "verify-bundle", "eval") else "operation_error"
        print(json.dumps({"status": status, "error": str(exc)}), file=sys.stderr)
        return 3 if status == "unverified" else 1
    except (kernel.AdmissionRefused, kernel.ResourceFault, StoreError) as exc:
        print(json.dumps({"status": "unverified", "error": str(exc)}), file=sys.stderr)
        return 3
    except (ValueError, TypeError, RecursionError) as exc:
        print(json.dumps({"status": "invalid", "error": str(exc)}), file=sys.stderr)
        return 2
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0
