#!/usr/bin/env python3
"""A release gate: install a wheel only if signed decisions admit its exact bytes.

    python3 integration/release_gate.py --artifact candidate.whl --trust KEY \
        --bytes-bundle bytes.sg.json --bytes-rule bytes.wpl --bytes-profile bytes.json \
        --judgment-bundle judgment.sg.json --judgment-rule rule.wpl --judgment-facts facts.json \
        --output-dir approved/ --install-into /path/to/venv

This is INTEGRATOR code, not part of the Stargate contract. It exists to walk one
real path end to end — a wheel downloaded from a public index, two signed
decisions about it, and an installation that must be impossible unless both hold.

THE ORDER IS THE POINT
----------------------
Two requirements about one artifact cannot both be checked against the candidate
file: between the first check and the second the file may change, and the second
would then be about different bytes. So the gate runs, in this order:

  1. `admit` the DERIVED-facts decision. That stages the candidate's bytes while
     hashing them, checks the requirement against the staged digest, and
     publishes the staged copy. Nothing after this reads the candidate again.
  2. `require` the ASSERTED-judgment decision against the ADMITTED file. The
     bytes it measures are the bytes step 1 published, by inode, not by path.
  3. Name the admitted file from its OWN bytes. `pip` refuses a wheel whose
     filename is not `{name}-{version}-{python}-{abi}-{platform}.whl`, and a
     signed decision says nothing about names — it is about bytes. So the gate
     reads `.dist-info/METADATA` out of the admitted copy and links it to the
     name those bytes declare. An operator-chosen name is never used.
  4. Install the admitted file. The installer never sees the candidate path.

Step 2 could not come first, and nothing in Stargate enforces this order — see
integration/FINDINGS.md.

EXIT CODES mirror Stargate's, because a caller that only reads the exit code must
be able to tell "refused" from "could not check":

  0  installed          every decision satisfied and the install succeeded
  1  operation_error    local I/O: the target name exists, directory missing, install failed
  2  invalid            a bundle, key, rule or profile is malformed or untrusted, or
                     the admitted bytes are not an installable wheel
  3  unverified         material missing or unreadable; NOTHING was decided
  4  unsatisfied        a decision was reached and it does not admit this artifact
"""
import argparse
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from stargate.artifact import admit_bundle                      # noqa: E402
from stargate.bundle import read_bundle, require_bundle          # noqa: E402
from stargate.policy import PolicyError                          # noqa: E402
from stargate.records import InvalidRecord                       # noqa: E402
from stargate.store import StoreError                            # noqa: E402
from stargate import kernel                                      # noqa: E402

EXIT_OK, EXIT_OPERATION, EXIT_INVALID, EXIT_UNVERIFIED, EXIT_UNSATISFIED = 0, 1, 2, 3, 4


def read_json(path, what):
    """Read a JSON object, refusing duplicate keys the way the CLI does."""
    def unique(pairs):
        out = {}
        for key, value in pairs:
            if key in out:
                raise PolicyError(f"duplicate key in {what}: {key}")
            out[key] = value
        return out
    return json.loads(Path(path).read_text(encoding="utf-8"), object_pairs_hook=unique)


WHEEL_NAME = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9._-]*[A-Za-z0-9])?$")


class NotAWheel(ValueError):
    """Verified bytes that this gate cannot install: the decisions were about
    bytes, and no signed fact says they are a wheel."""


def wheel_filename(path):
    """The name these BYTES declare, read from the admitted copy, never from input."""
    try:
        with zipfile.ZipFile(path) as archive:
            names = [n for n in archive.namelist()
                     if n.endswith(".dist-info/METADATA") and n.count("/") == 1]
            if len(names) != 1:
                raise NotAWheel(f"expected exactly one .dist-info/METADATA, found {len(names)}")
            fields = {}
            for line in archive.read(names[0]).decode("utf-8", "strict").splitlines():
                if not line:
                    break                                  # headers end at the blank line
                key, _, value = line.partition(":")
                if key in ("Name", "Version") and key not in fields:
                    fields[key] = value.strip()
            wheel = [n for n in archive.namelist()
                     if n.endswith(".dist-info/WHEEL") and n.count("/") == 1]
            tags = []
            if wheel:
                for line in archive.read(wheel[0]).decode("utf-8", "strict").splitlines():
                    if line.startswith("Tag:"):
                        tags.append(line.split(":", 1)[1].strip())
    except (zipfile.BadZipFile, KeyError, UnicodeDecodeError) as exc:
        raise NotAWheel(f"admitted bytes are not a readable wheel: {exc}") from exc
    if not {"Name", "Version"} <= set(fields) or len(tags) != 1:
        raise NotAWheel("admitted wheel does not declare exactly one name, version and tag")
    distribution = fields["Name"].replace("-", "_")
    if not (WHEEL_NAME.match(distribution) and WHEEL_NAME.match(fields["Version"])
            and WHEEL_NAME.match(tags[0].replace("-", "_"))):
        raise NotAWheel("admitted wheel declares a name, version or tag this gate will not write")
    return f"{distribution}-{fields['Version']}-{tags[0]}.whl"


def gate(args):
    trusted = set(args.trust)

    # 1. Admit: one read of the candidate feeds the digest, the staged copy and
    #    the byte measurements. The requirement is checked before publication.
    staged = Path(args.output_dir) / f".gate-{os.getpid()}.admitted"
    admitted = admit_bundle(
        read_bundle(args.bytes_bundle), trusted,
        rule=Path(args.bytes_rule).read_text(encoding="utf-8"),
        derive=read_json(args.bytes_profile, "derivation profile"),
        subject=args.artifact, output=staged)
    if admitted["status"] != "admitted":
        return EXIT_UNSATISFIED, dict(stage="bytes", **admitted)

    # 2. Require the second decision against the ADMITTED bytes, never the
    #    candidate path again.
    judgment = require_bundle(
        read_bundle(args.judgment_bundle), trusted,
        rule=Path(args.judgment_rule).read_text(encoding="utf-8"),
        facts=read_json(args.judgment_facts, "expected facts"),
        subject=admitted["artifact"]["sha256"])
    if judgment["status"] != "satisfied":
        staged.unlink(missing_ok=True)              # admitted bytes are not approved
        return EXIT_UNSATISFIED, dict(stage="judgment", **judgment)

    # 3. The name comes from the admitted bytes, and only then does the file get
    #    a name an installer will read. A failure here leaves nothing behind.
    try:
        final = Path(args.output_dir) / wheel_filename(staged)
        os.link(staged, final)                      # refuses to replace an existing name
    except BaseException:
        staged.unlink(missing_ok=True)
        raise
    staged.unlink(missing_ok=True)

    report = {"status": "approved", "artifact": dict(admitted["artifact"], path=str(final)),
              "bytes_requirement": admitted["requirement"], "judgment_requirement": judgment}
    if not args.install_into:
        return EXIT_OK, report

    # 4. Act. The installer is given the admitted path and nothing else.
    done = subprocess.run([str(Path(args.install_into) / "bin" / "pip"), "install",
                           "--no-deps", "--quiet", str(final)],
                          capture_output=True, text=True)
    if done.returncode != 0:
        return EXIT_OPERATION, dict(report, status="install_failed",
                                    error=(done.stderr or done.stdout).strip()[:400])
    return EXIT_OK, dict(report, status="installed",
                         installed_into=str(args.install_into))


def main(argv=None):
    p = argparse.ArgumentParser(prog="release_gate", allow_abbrev=False,
                                description="Install a wheel only if signed decisions admit its bytes.")
    p.add_argument("--artifact", required=True, type=Path)
    p.add_argument("--trust", required=True, action="append")
    p.add_argument("--bytes-bundle", required=True, type=Path)
    p.add_argument("--bytes-rule", required=True, type=Path)
    p.add_argument("--bytes-profile", required=True, type=Path)
    p.add_argument("--judgment-bundle", required=True, type=Path)
    p.add_argument("--judgment-rule", required=True, type=Path)
    p.add_argument("--judgment-facts", required=True, type=Path)
    p.add_argument("--output-dir", required=True, type=Path,
                   help="directory the admitted wheel is written into, under the name its own bytes declare")
    p.add_argument("--install-into", type=Path, help="venv to install the admitted wheel into")
    args = p.parse_args(argv)
    try:
        code, report = gate(args)
    except (StoreError, kernel.AdmissionRefused, kernel.ResourceFault) as exc:
        code, report = EXIT_UNVERIFIED, {"status": "unverified", "error": str(exc)}
    except NotAWheel as exc:
        code, report = EXIT_INVALID, {"status": "artifact_not_a_wheel", "error": str(exc)}
    except (InvalidRecord, PolicyError, ValueError, TypeError) as exc:
        code, report = EXIT_INVALID, {"status": "invalid", "error": str(exc)}
    except OSError as exc:
        code, report = EXIT_OPERATION, {"status": "operation_error", "error": str(exc)}
    print(json.dumps(report, ensure_ascii=False, sort_keys=True))
    return code


if __name__ == "__main__":
    sys.exit(main())
