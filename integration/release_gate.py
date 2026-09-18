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
  2. `require` the ASSERTED-judgment decision against the digest produced by
     `admit`; no second read of the candidate is used.
  3. Name the admitted file from its OWN bytes. `pip` refuses a wheel whose
     filename is not `{name}-{version}-{python}-{abi}-{platform}.whl`, and a
     signed decision says nothing about names — it is about bytes. So the gate
     reads `.dist-info/METADATA` out of the admitted copy and links it to the
     name those bytes declare. An operator-chosen name is never used.
  4. Before publishing/installing, pin the target root without site startup and
     classify existing root .pth files by both name and digest. Refuse foreign
     hooks unless the operator explicitly allows them.
  5. Install the admitted file, then READ THE ENVIRONMENT BACK. `pip` treats an
     already-present distribution of the same version as satisfied and skips the
     install, so "pip exited 0" does not mean the admitted code is in place: the
     gate forces the install and then hashes every payload file the wheel's
     ZIP itself contains against what is now on disk, in an install directory
     decided without running anything the environment installed, — the wheel's `RECORD` is
     checked for agreement with those bytes and then not believed. `installed`
     means that check passed, and nothing else.

Step 2 could not come first, and nothing in Stargate enforces this order — see
integration/FINDINGS.md.

EXIT CODES mirror Stargate's, because a caller that only reads the exit code must
be able to tell "refused" from "could not check":

  0  installed          every decision satisfied AND the environment now holds
                     the admitted payload, verified file by file
  1  operation_error    local I/O: the target name exists, directory missing,
                     install failed, the environment does not hold the admitted
                     payload afterwards (`install_unverified`), or it runs
                     startup code the wheel did not bring (`environment_untrusted`)
  2  invalid            a bundle, key, rule or profile is malformed or untrusted, or
                     the admitted bytes are not an installable wheel
  3  unverified         proof, rule, facts or artifact missing or unreadable;
                     NOTHING was decided
  4  unsatisfied        a decision was reached and it does not admit this artifact
"""
import argparse
import base64
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import zipfile

from stargate.artifact import admit_all                      # noqa: E402
from stargate.bundle import read_bundle          # noqa: E402
from stargate.policy import PolicyError                          # noqa: E402
from stargate.records import InvalidRecord                       # noqa: E402
from stargate.store import StoreError                            # noqa: E402
from stargate import kernel                                      # noqa: E402

EXIT_OK, EXIT_OPERATION, EXIT_INVALID, EXIT_UNVERIFIED, EXIT_UNSATISFIED = 0, 1, 2, 3, 4


def read_input(path, what):
    """Read an input file. Missing or unreadable material is UNVERIFIED, not an
    operation error: nothing has been decided yet, and a caller retrying on 3 is
    right to do so."""
    try:
        return Path(path).read_bytes()
    except OSError as exc:
        raise StoreError(f"cannot read {what}: {exc}") from exc


def read_json(path, what):
    """Read a JSON object, refusing duplicate keys the way the CLI does."""
    def unique(pairs):
        out = {}
        for key, value in pairs:
            if key in out:
                raise PolicyError(f"duplicate key in {what}: {key}")
            out[key] = value
        return out
    return json.loads(read_input(path, what).decode("utf-8"), object_pairs_hook=unique)


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


def wheel_payload(path):
    """{installed relative path: sha256} for every payload member of the WHEEL.

    The digests come from the ZIP members themselves, never from `RECORD`. A
    manifest is an artifact-controlled claim: a signed decision authenticates the
    whole archive including a contradictory `RECORD`, so believing it would let
    the artifact choose what the postcondition checks (Codex, PR #11 review R3).

    `RECORD` is still read, but only to REFUSE an internally inconsistent wheel
    before anything is installed: every payload member must be listed, with the
    digest its bytes actually have. `.dist-info/RECORD` itself is excluded (the
    installer rewrites it) and a `.data/` tree is refused, since those files land
    outside purelib and this gate does not track them.
    """
    try:
        archive = zipfile.ZipFile(path)
    except zipfile.BadZipFile as exc:
        raise NotAWheel(f"admitted bytes are not a readable wheel: {exc}") from exc
    with archive:
        records = [n for n in archive.namelist()
                   if n.endswith(".dist-info/RECORD") and n.count("/") == 1]
        if len(records) != 1:
            raise NotAWheel("admitted wheel does not carry exactly one RECORD")
        payload = {}
        for member in archive.infolist():
            name = member.filename
            if name == records[0] or name.endswith("/"):
                continue
            if ".data/" in name:
                raise NotAWheel("this gate does not handle wheels with a .data payload")
            payload[name] = hashlib.sha256(archive.read(name)).hexdigest()
        if not payload:
            raise NotAWheel("admitted wheel carries no payload members")

        # The manifest must agree with the bytes. It decides nothing here; a
        # disagreement means the artifact is internally inconsistent, and this
        # gate refuses it rather than choosing which half to believe.
        try:
            lines = archive.read(records[0]).decode("utf-8", "strict").splitlines()
        except (KeyError, UnicodeDecodeError, zipfile.BadZipFile) as exc:
            raise NotAWheel(f"admitted wheel has an unreadable RECORD: {exc}") from exc
    claimed = {}
    for line in lines:
        if not line.strip():
            continue
        name, _, rest = line.partition(",")
        if name == records[0]:
            continue
        digest = rest.split(",")[0]
        if not digest.startswith("sha256="):
            raise NotAWheel(f"RECORD entry without a sha256 digest: {name}")
        try:
            claimed[name] = base64.urlsafe_b64decode(
                digest[7:] + "=" * (-len(digest[7:]) % 4)).hex()
        except ValueError as exc:
            raise NotAWheel(f"RECORD entry with an undecodable digest: {name}") from exc
    missing = sorted(set(payload) - set(claimed))
    if missing:
        raise NotAWheel(f"RECORD omits payload members: {', '.join(missing[:4])}")
    extra = sorted(set(claimed) - set(payload))
    if extra:
        raise NotAWheel(f"RECORD lists members the wheel does not contain: {', '.join(extra[:4])}")
    lying = sorted(n for n, want in claimed.items() if payload[n] != want)
    if lying:
        raise NotAWheel(f"RECORD digests contradict the wheel's own bytes: {', '.join(lying[:4])}")
    return payload


def installation_root(venv):
    """Where this environment installs pure-Python packages, decided WITHOUT it.

    `environment_holds` used to ask the target interpreter for
    `sysconfig.get_paths()["purelib"]` on a normal startup — which runs the
    environment's own `.pth` hooks first, so the environment could rewrite the
    installed module and then send the check to a directory of clean copies
    (Codex, PR #11 review R4). The answer now comes from two sources that a
    startup hook cannot reach:

      * the layout this gate computes from `pyvenv.cfg`, executing nothing;
      * the interpreter's own answer under `-I -S`, which skips `site` (so no
        `.pth`, `sitecustomize` or `usercustomize` runs) and ignores the
        environment variables.

    They must agree, and the result must lie inside the environment. A
    disagreement is not resolved in the environment's favour — it is refused.
    """
    venv = Path(venv).resolve()
    python = venv / "bin" / "python"
    try:
        config = dict(
            (part.strip() for part in line.split("=", 1))
            for line in (venv / "pyvenv.cfg").read_text(encoding="utf-8").splitlines()
            if "=" in line)
    except OSError as exc:
        return None, [f"cannot read the environment's own pyvenv.cfg: {exc.strerror}"]
    version = re.match(r"^(\d+)\.(\d+)", config.get("version", config.get("version_info", "")))
    if not version:
        return None, ["the environment's pyvenv.cfg declares no usable version"]
    computed = venv / "lib" / f"python{version.group(1)}.{version.group(2)}" / "site-packages"

    probe = subprocess.run([str(python), "-I", "-S", "-c",
                            "import sysconfig;print(sysconfig.get_paths()['purelib'])"],
                           capture_output=True, text=True)
    if probe.returncode != 0:
        return None, [f"cannot ask the target interpreter (no site) where it installs: "
                      f"{probe.stderr.strip()[:200]}"]
    reported = Path(probe.stdout.strip()).resolve()
    if reported != computed.resolve():
        return None, [f"the environment reports {reported} as its install root while its own "
                      f"layout says {computed}"]
    if venv not in reported.parents:
        return None, [f"the environment's install root {reported} is outside {venv}"]
    return reported, []


def startup_hooks(purelib, payload):
    """Inventory root .pth files; artifact ownership requires matching bytes.

    This is a narrow .pth policy, not a general scan of Python startup behavior.
    Read/list failures propagate rather than becoming an allow-able hook name.
    """
    own, foreign = [], []
    for path in sorted(Path(purelib).iterdir()):
        if path.suffix != ".pth" or not path.is_file():
            continue
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        (own if payload.get(path.name) == digest else foreign).append(path.name)
    return dict(artifact_startup_hooks=own, foreign_startup_hooks=foreign)


def environment_holds(venv, payload, *, purelib=None):
    """Every payload member, hashed where this environment actually installs.

    Returns a list of complaints; empty means the environment holds exactly the
    admitted bytes."""
    problems = []
    if purelib is None:
        purelib, problems = installation_root(venv)
        if problems:
            return problems
    for name, want in sorted(payload.items()):
        installed = purelib / name
        try:
            got = hashlib.sha256(installed.read_bytes()).hexdigest()
        except OSError as exc:
            problems.append(f"{name}: not installed ({exc.strerror})")
            continue
        if got != want:
            problems.append(f"{name}: installed bytes differ from the admitted wheel")
    return problems


def gate(args):
    trusted = set(args.trust)

    # 1. Joint admission: one stream feeds digest, copy and byte measurements.
    #    Both requirements are checked before publishing the temporary copy.
    #    Every input is read BEFORE anything is staged, so a
    #    missing proof is `unverified` with no partial admission on disk.
    bytes_bundle = read_input(args.bytes_bundle, "bytes proof")
    bytes_rule = read_input(args.bytes_rule, "bytes rule").decode("utf-8")
    bytes_profile = read_json(args.bytes_profile, "derivation profile")
    judgment_bundle = read_input(args.judgment_bundle, "judgment proof")
    judgment_rule = read_input(args.judgment_rule, "judgment rule").decode("utf-8")
    judgment_facts = read_json(args.judgment_facts, "expected facts")

    staged = Path(args.output_dir) / f".gate-{os.getpid()}-{os.urandom(4).hex()}.admitted"
    admitted = admit_all([
        dict(name="bytes", bundle=bytes_bundle, trust=trusted, rule=bytes_rule, derive=bytes_profile),
        dict(name="judgment", bundle=judgment_bundle, trust=trusted,
             rule=judgment_rule, facts=judgment_facts),
    ], subject=args.artifact, output=staged)
    if admitted["status"] != "admitted":
        return EXIT_UNSATISFIED, dict(admitted["requirements"][-1]["report"],
                                      stage=admitted["failed"], artifact=None)

    # The stage is owned from here until the final name owns the bytes. Every
    # exit from this block — return, refusal or exception — removes it.
    try:
        bytes_report, judgment = [entry["report"] for entry in admitted["requirements"]]

        # 3. The name comes from the admitted bytes, and only then does the file
        #    get a name an installer will read.
        final = Path(args.output_dir) / wheel_filename(staged)
        payload = wheel_payload(staged)
        # Before any target pip startup, pin the readback root and classify the
        # .pth files already present. A matching NAME alone proves no ownership.
        purelib, hooks_before = None, None
        if args.install_into:
            pending_artifact = dict(path=None, sha256=admitted["artifact"]["sha256"])
            try:
                purelib, problems = installation_root(args.install_into)
            except (OSError, UnicodeError) as exc:
                purelib, problems = None, [f"cannot resolve the installation root: {exc}"]
            if problems:
                return EXIT_OPERATION, dict(status="environment_unresolved",
                    stage="environment", problems=problems, artifact=pending_artifact)
            hooks_before = startup_hooks(purelib, payload)
            if hooks_before["foreign_startup_hooks"] and not args.allow_startup_hooks:
                return EXIT_OPERATION, dict(status="environment_untrusted",
                    stage="environment", artifact=pending_artifact, **hooks_before)
        os.link(staged, final)                      # refuses to replace an existing name
    finally:
        staged.unlink(missing_ok=True)

    report = {"status": "approved", "artifact": dict(admitted["artifact"], path=str(final)),
              "bytes_requirement": bytes_report, "judgment_requirement": judgment}
    if not args.install_into:
        return EXIT_OK, report

    # 4. Act, then read the environment back. `--force-reinstall` is not an
    #    optimisation: without it pip treats an already-present distribution of
    #    the same version as satisfied and silently keeps the OTHER artifact's
    #    code (Codex, PR #11 review R1).
    done = subprocess.run([str(Path(args.install_into) / "bin" / "pip"), "install",
                           "--no-deps", "--force-reinstall", "--quiet", str(final)],
                          capture_output=True, text=True)
    if done.returncode != 0:
        return EXIT_OPERATION, dict(report, status="install_failed",
                                    error=(done.stderr or done.stdout).strip()[:400])
    problems = environment_holds(args.install_into, payload, purelib=purelib)
    if problems:
        return EXIT_OPERATION, dict(report, status="install_unverified", problems=problems)

    # Inventory again after the action, using the root pinned before pip.
    hooks = startup_hooks(purelib, payload)
    report = dict(report, installed_into=str(args.install_into),
                  payload_files_verified=len(payload), startup_hooks_before=hooks_before,
                  **hooks)
    if hooks["foreign_startup_hooks"] and not args.allow_startup_hooks:
        return EXIT_OPERATION, dict(report, status="environment_untrusted")
    return EXIT_OK, dict(report, status="installed")


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
    p.add_argument("--allow-startup-hooks", action="store_true",
                   help="allow pip to start with foreign root .pth files and report them; "
                        "this explicitly trusts that startup code")
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
