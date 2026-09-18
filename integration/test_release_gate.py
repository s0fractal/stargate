#!/usr/bin/env python3
"""The release gate, exercised on a self-contained wheel.

    python3 integration/test_release_gate.py

Builds a real (tiny) wheel in a temporary directory, authors the two signed
decisions the gate expects, and drives the gate through its whole outcome
surface. Nothing here reaches the network or the repository tree, and the
installation step is exercised separately in `--with-install` mode because it
needs a venv and is slow.
"""
import base64
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
GATE = ROOT / "integration" / "release_gate.py"

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey  # noqa: E402
from stargate import bundle as B, policy as P, records as R                       # noqa: E402
from stargate.artifact import measure_subject                                     # noqa: E402
from stargate.store import Store                                                  # noqa: E402


def author_derived(rule, profile, subject, store, key):
    """Author a derived-facts record the way the CLI does.

    `author_policy` takes facts, not a profile: the `--derive` authoring mode
    lives in the CLI, so a library caller has to measure first and pass the
    measured facts and digest. See FINDINGS.md F8.
    """
    measured = measure_subject(subject, profile)
    return P.author_policy(rule, measured["facts"], store, key,
                           subject=measured["subject"])

BYTES_RULE = """# What the operator can confirm locally about the artifact's bytes.
fact is_text: bool
fact at_least_1k: bool
check !is_text && at_least_1k
"""
BYTES_PROFILE = {"is_text": {"utf8": True}, "at_least_1k": {"size_at_least": 1024}}
JUDGMENT_RULE = """# The reviewer's release rule.
fact tests_passed: bool
fact known_advisories: bool
check tests_passed && !known_advisories
"""
JUDGMENT_FACTS = {"tests_passed": True, "known_advisories": False}


def build_wheel(path, name="gatedemo", version="0.1.0", value=1, pad=2048):
    """A minimal but genuine wheel, with a RECORD the gate can check against.

    `value` changes the payload WITHOUT changing name or version — that pair is
    what an installer uses to decide it has nothing to do.
    """
    dist = f"{name}-{version}.dist-info"
    entries = {
        f"{name}/__init__.py": f"VALUE = {value}\n".encode(),
        f"{dist}/METADATA":
            f"Metadata-Version: 2.1\nName: {name}\nVersion: {version}\n\nbody\n".encode(),
        f"{dist}/WHEEL": (b"Wheel-Version: 1.0\nGenerator: test\nRoot-Is-Purelib: true\n"
                          b"Tag: py3-none-any\n"),
        f"{dist}/filler": ("0" * pad).encode(),          # push past size_at_least
    }
    record = []
    for member, raw in entries.items():
        digest = base64.urlsafe_b64encode(hashlib.sha256(raw).digest()).rstrip(b"=").decode()
        record.append(f"{member},sha256={digest},{len(raw)}")
    record.append(f"{dist}/RECORD,,")
    with zipfile.ZipFile(path, "w") as archive:
        for member, raw in entries.items():
            archive.writestr(member, raw)
        archive.writestr(f"{dist}/RECORD", "\n".join(record) + "\n")
    return path


class ReleaseGate(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.dir = Path(cls.tmp.name)
        cls.store = Store(cls.dir / "objects")
        cls.key = Ed25519PrivateKey.from_private_bytes(bytes(range(32)))
        cls.trust = R.public_key(cls.key)
        cls.wheel = build_wheel(cls.dir / "candidate.whl")
        digest = hashlib.sha256(cls.wheel.read_bytes()).hexdigest()
        (cls.dir / "bytes.wpl").write_text(BYTES_RULE)
        (cls.dir / "bytes.json").write_text(json.dumps(BYTES_PROFILE))
        (cls.dir / "judgment.wpl").write_text(JUDGMENT_RULE)
        (cls.dir / "judgment-facts.json").write_text(json.dumps(JUDGMENT_FACTS))
        byte_record = author_derived(BYTES_RULE, BYTES_PROFILE, cls.wheel, cls.store, cls.key)
        judgment = P.author_policy(JUDGMENT_RULE, JUDGMENT_FACTS, cls.store, cls.key,
                                   subject=digest)
        for name, record in (("bytes.sg.json", byte_record), ("judgment.sg.json", judgment)):
            raw, _ = B.export_bundle(cls.store.read(record["object"]), cls.store, {cls.trust})
            (cls.dir / name).write_bytes(raw)

    def run_gate(self, artifact=None, trust=None, out=None, extra=(), judgment_bundle=None):
        out = out or Path(tempfile.mkdtemp(dir=self.dir))
        argv = [sys.executable, str(GATE),
                "--artifact", str(artifact or self.wheel),
                "--trust", trust or self.trust,
                "--bytes-bundle", str(self.dir / "bytes.sg.json"),
                "--bytes-rule", str(self.dir / "bytes.wpl"),
                "--bytes-profile", str(self.dir / "bytes.json"),
                "--judgment-bundle", str(judgment_bundle or self.dir / "judgment.sg.json"),
                "--judgment-rule", str(self.dir / "judgment.wpl"),
                "--judgment-facts", str(self.dir / "judgment-facts.json"),
                "--output-dir", str(out), *extra]
        done = subprocess.run(argv, capture_output=True, text=True)
        report = json.loads(done.stdout) if done.stdout.strip() else {}
        return done.returncode, report, sorted(p.name for p in Path(out).iterdir())

    def test_approves_and_names_the_file_from_its_own_bytes(self):
        code, report, files = self.run_gate()
        self.assertEqual((code, report["status"]), (0, "approved"))
        self.assertEqual(files, ["gatedemo-0.1.0-py3-none-any.whl"])
        self.assertEqual(report["artifact"]["sha256"],
                         hashlib.sha256(self.wheel.read_bytes()).hexdigest())

    def test_tampered_artifact_is_unsatisfied_and_publishes_nothing(self):
        other = self.dir / "tampered.whl"
        other.write_bytes(self.wheel.read_bytes() + b"x")
        code, report, files = self.run_gate(artifact=other)
        self.assertEqual((code, report["status"], report["reason"]),
                         (4, "unsatisfied", "subject_mismatch"))
        self.assertEqual(files, [])

    def test_untrusted_key_is_invalid_and_publishes_nothing(self):
        code, report, files = self.run_gate(trust="aa" * 32)
        self.assertEqual((code, report["status"]), (2, "invalid"))
        self.assertEqual(files, [])

    def test_missing_artifact_is_unverified_not_unsatisfied(self):
        code, report, files = self.run_gate(artifact=self.dir / "absent.whl")
        self.assertEqual((code, report["status"]), (3, "unverified"))
        self.assertEqual(files, [])

    def test_verified_bytes_that_are_not_a_wheel_are_refused(self):
        blob = self.dir / "blob.bin"
        blob.write_bytes(bytes(range(256)) * 8)
        digest = hashlib.sha256(blob.read_bytes()).hexdigest()
        record = author_derived(BYTES_RULE, BYTES_PROFILE, blob, self.store, self.key)
        judgment = P.author_policy(JUDGMENT_RULE, JUDGMENT_FACTS, self.store, self.key,
                                   subject=digest)
        for name, rec in (("blob-bytes.sg.json", record), ("blob-judgment.sg.json", judgment)):
            raw, _ = B.export_bundle(self.store.read(rec["object"]), self.store, {self.trust})
            (self.dir / name).write_bytes(raw)
        out = Path(tempfile.mkdtemp(dir=self.dir))
        done = subprocess.run(
            [sys.executable, str(GATE), "--artifact", str(blob), "--trust", self.trust,
             "--bytes-bundle", str(self.dir / "blob-bytes.sg.json"),
             "--bytes-rule", str(self.dir / "bytes.wpl"),
             "--bytes-profile", str(self.dir / "bytes.json"),
             "--judgment-bundle", str(self.dir / "blob-judgment.sg.json"),
             "--judgment-rule", str(self.dir / "judgment.wpl"),
             "--judgment-facts", str(self.dir / "judgment-facts.json"),
             "--output-dir", str(out)], capture_output=True, text=True)
        report = json.loads(done.stdout)
        self.assertEqual((done.returncode, report["status"]), (2, "artifact_not_a_wheel"))
        self.assertEqual(sorted(p.name for p in out.iterdir()), [])

    def test_existing_target_name_is_never_replaced(self):
        out = Path(tempfile.mkdtemp(dir=self.dir))
        target = out / "gatedemo-0.1.0-py3-none-any.whl"
        target.write_bytes(b"occupied")
        code, report, files = self.run_gate(out=out)
        self.assertEqual((code, report["status"]), (1, "operation_error"))
        self.assertEqual(target.read_bytes(), b"occupied")
        self.assertEqual(files, ["gatedemo-0.1.0-py3-none-any.whl"])   # no staging left behind

    def test_the_name_is_not_taken_from_the_candidate_path(self):
        renamed = self.dir / "totally-different-name.zip"
        renamed.write_bytes(self.wheel.read_bytes())
        code, report, files = self.run_gate(artifact=renamed)
        self.assertEqual((code, report["status"]), (0, "approved"))
        self.assertEqual(files, ["gatedemo-0.1.0-py3-none-any.whl"])


    def test_missing_judgment_proof_is_unverified_and_leaves_no_stage(self):
        out = Path(tempfile.mkdtemp(dir=self.dir))
        code, report, files = self.run_gate(
            out=out, extra=(), judgment_bundle=self.dir / "absent.sg.json")
        self.assertEqual((code, report["status"]), (3, "unverified"))
        self.assertEqual(files, [])

    def test_malformed_judgment_proof_is_invalid_and_leaves_no_stage(self):
        broken = self.dir / "broken.sg.json"
        broken.write_bytes(b"{not json")
        out = Path(tempfile.mkdtemp(dir=self.dir))
        code, report, files = self.run_gate(out=out, judgment_bundle=broken)
        self.assertEqual((code, report["status"]), (2, "invalid"))
        self.assertEqual(files, [])
        # and a retry into the same directory still works: no stale stage name
        code, report, files = self.run_gate(out=out)
        self.assertEqual((code, report["status"]), (0, "approved"))
        self.assertEqual(files, ["gatedemo-0.1.0-py3-none-any.whl"])


def build_hostile_wheel(path, variant, name="gatedemo", version="0.1.0", pad=2048):
    """A wheel whose RECORD lies about its own bytes, plus a startup hook.

    The hook rewrites the installed module when the target interpreter starts —
    a deterministic stand-in for any environment that mutates itself after an
    installer finishes (Codex, PR #11 review R3). `variant`:

      "omit"         — the module and the hook are left out of RECORD
      "lie"          — everything listed, but the module's digest is the hook's target
      "honest-hook"  — RECORD agrees with every byte; only the environment lies
    """
    dist = f"{name}-{version}.dist-info"
    module = f"VALUE = 1\n".encode()
    # A .pth line runs at interpreter startup if it begins with "import". It has
    # no __file__, so the target is derived from sysconfig, as a real one would be.
    hook = (b"import os,sysconfig;p=os.path.join(sysconfig.get_paths()['purelib'],"
            b"'gatedemo','__init__.py');os.path.exists(p) and open(p,'w').write('VALUE = 999\\n')\n")
    entries = {
        f"{name}/__init__.py": module,
        "gate_probe.pth": hook,
        f"{dist}/METADATA":
            f"Metadata-Version: 2.1\nName: {name}\nVersion: {version}\n\nbody\n".encode(),
        f"{dist}/WHEEL": (b"Wheel-Version: 1.0\nGenerator: test\nRoot-Is-Purelib: true\n"
                          b"Tag: py3-none-any\n"),
        f"{dist}/filler": ("0" * pad).encode(),
    }
    def row(member, raw):
        digest = base64.urlsafe_b64encode(hashlib.sha256(raw).digest()).rstrip(b"=").decode()
        return f"{member},sha256={digest},{len(raw)}"
    record = []
    for member, raw in entries.items():
        if variant == "omit" and member in (f"{name}/__init__.py", "gate_probe.pth"):
            continue
        if variant == "lie" and member == f"{name}/__init__.py":
            record.append(row(member, b"VALUE = 999\n"))      # digest of what the hook writes
            continue
        record.append(row(member, raw))
    record.append(f"{dist}/RECORD,,")
    with zipfile.ZipFile(path, "w") as archive:
        for member, raw in entries.items():
            archive.writestr(member, raw)
        archive.writestr(f"{dist}/RECORD", "\n".join(record) + "\n")
    return path


class HostileManifest(unittest.TestCase):
    """A wheel may be admitted and still lie about itself internally."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.dir = Path(self.tmp.name)
        self.store = Store(self.dir / "objects")
        self.key = Ed25519PrivateKey.from_private_bytes(bytes(range(32)))
        self.trust = R.public_key(self.key)
        (self.dir / "bytes.wpl").write_text(BYTES_RULE)
        (self.dir / "bytes.json").write_text(json.dumps(BYTES_PROFILE))
        (self.dir / "judgment.wpl").write_text(JUDGMENT_RULE)
        (self.dir / "judgment-facts.json").write_text(json.dumps(JUDGMENT_FACTS))

    def gate_for(self, variant, install=False):
        wheel = build_hostile_wheel(self.dir / f"{variant}.whl", variant)
        digest = hashlib.sha256(wheel.read_bytes()).hexdigest()
        byte_record = author_derived(BYTES_RULE, BYTES_PROFILE, wheel, self.store, self.key)
        judgment = P.author_policy(JUDGMENT_RULE, JUDGMENT_FACTS, self.store, self.key,
                                   subject=digest)
        for name, record in ((f"{variant}-bytes.sg.json", byte_record),
                             (f"{variant}-judgment.sg.json", judgment)):
            raw, _ = B.export_bundle(self.store.read(record["object"]), self.store, {self.trust})
            (self.dir / name).write_bytes(raw)
        out = Path(tempfile.mkdtemp(dir=self.dir))
        extra = []
        if install:
            venv = self.dir / f"venv-{variant}"
            subprocess.run([sys.executable, "-m", "venv", str(venv)], check=True,
                           capture_output=True)
            extra = ["--install-into", str(venv)]
        done = subprocess.run(
            [sys.executable, str(GATE), "--artifact", str(wheel), "--trust", self.trust,
             "--bytes-bundle", str(self.dir / f"{variant}-bytes.sg.json"),
             "--bytes-rule", str(self.dir / "bytes.wpl"),
             "--bytes-profile", str(self.dir / "bytes.json"),
             "--judgment-bundle", str(self.dir / f"{variant}-judgment.sg.json"),
             "--judgment-rule", str(self.dir / "judgment.wpl"),
             "--judgment-facts", str(self.dir / "judgment-facts.json"),
             "--output-dir", str(out), *extra], capture_output=True, text=True,
            env={**os.environ, "PIP_NO_INDEX": "1"})
        return done.returncode, json.loads(done.stdout), sorted(p.name for p in out.iterdir())

    def test_record_omitting_payload_members_is_refused(self):
        code, report, files = self.gate_for("omit")
        self.assertEqual((code, report["status"]), (2, "artifact_not_a_wheel"))
        self.assertIn("omits payload members", report["error"])
        self.assertEqual(files, [])

    @unittest.skipUnless("--with-install" in sys.argv, "needs a venv; pass --with-install")
    def test_consistent_wheel_whose_environment_rewrites_it_is_not_installed(self):
        """Nothing about this wheel is inconsistent; the ENVIRONMENT mutates it.

        The hook runs when the target interpreter starts, which is what the
        readback does. `installed` must not survive that."""
        code, report, files = self.gate_for("honest-hook", install=True)
        self.assertEqual((code, report["status"]), (1, "install_unverified"))
        self.assertTrue(any("gatedemo/__init__.py" in p for p in report["problems"]),
                        report["problems"])

    def test_record_contradicting_its_own_bytes_is_refused(self):
        code, report, files = self.gate_for("lie")
        self.assertEqual((code, report["status"]), (2, "artifact_not_a_wheel"))
        self.assertIn("contradict", report["error"])
        self.assertEqual(files, [])


class EnvironmentReadback(unittest.TestCase):
    """`environment_holds` on its own: the install step's postcondition check.

    The impostor test below proves the gate installs the right bytes; this proves
    the gate would NOTICE if it had not, which is a different claim."""

    @unittest.skipUnless("--with-install" in sys.argv, "needs a venv; pass --with-install")
    def test_notices_when_the_environment_does_not_hold_the_payload(self):
        sys.path.insert(0, str(ROOT / "integration"))
        from release_gate import environment_holds, wheel_payload
        ReleaseGate.setUpClass()
        try:
            venv = Path(ReleaseGate.dir) / "readback-venv"
            subprocess.run([sys.executable, "-m", "venv", str(venv)], check=True,
                           capture_output=True)
            # pip refuses `candidate.whl`: the name must be the canonical wheel
            # name (FINDINGS.md F1, which this test tripped over too).
            named = Path(ReleaseGate.dir) / "readback" / "gatedemo-0.1.0-py3-none-any.whl"
            named.parent.mkdir(exist_ok=True)
            named.write_bytes(ReleaseGate.wheel.read_bytes())
            subprocess.run([str(venv / "bin" / "pip"), "install", "--no-deps", "--quiet",
                            str(named)], check=True, capture_output=True,
                           env={**os.environ, "PIP_NO_INDEX": "1"})
            payload = wheel_payload(ReleaseGate.wheel)
            self.assertEqual(environment_holds(venv, payload), [],
                             "a correct install must produce no complaints")

            probe = subprocess.run([str(venv / "bin" / "python"), "-c",
                                    "import json,sysconfig;print(json.dumps(sysconfig.get_paths()))"],
                                   capture_output=True, text=True)
            purelib = Path(json.loads(probe.stdout)["purelib"])
            (purelib / "gatedemo" / "__init__.py").write_text("VALUE = 999\n")
            complaints = environment_holds(venv, payload)
            self.assertTrue(any("gatedemo/__init__.py" in c for c in complaints), complaints)

            (purelib / "gatedemo" / "__init__.py").unlink()
            self.assertTrue(any("not installed" in c for c in environment_holds(venv, payload)))
        finally:
            ReleaseGate.tmp.cleanup()


class Installation(unittest.TestCase):
    """The action itself. Skipped unless --with-install is given: it builds a venv."""

    @unittest.skipUnless("--with-install" in sys.argv, "needs a venv; pass --with-install")
    def test_installed_means_the_environment_runs_the_admitted_payload(self):
        """The case the first version of this gate got wrong (Codex R1).

        A DIFFERENT wheel with the SAME name and version is already installed.
        `pip` would treat that as satisfied and skip; `installed` must therefore
        mean the environment was read back and holds the admitted payload."""
        case = ReleaseGate()
        ReleaseGate.setUpClass()
        try:
            venv = Path(ReleaseGate.dir) / "venv"
            subprocess.run([sys.executable, "-m", "venv", str(venv)], check=True,
                           capture_output=True)
            impostor = ReleaseGate.dir / "impostor" / "gatedemo-0.1.0-py3-none-any.whl"
            impostor.parent.mkdir()
            build_wheel(impostor, value=999)
            subprocess.run([str(venv / "bin" / "pip"), "install", "--no-deps", "--quiet",
                            str(impostor)], check=True, capture_output=True,
                           env={**os.environ, "PIP_NO_INDEX": "1"})
            before = subprocess.run([str(venv / "bin" / "python"), "-c",
                                     "import gatedemo; print(gatedemo.VALUE)"],
                                    capture_output=True, text=True)
            self.assertEqual(before.stdout.strip(), "999", "fixture: impostor not installed")

            code, report, _ = case.run_gate(extra=("--install-into", str(venv)))
            self.assertEqual((code, report["status"]), (0, "installed"))
            self.assertGreater(report["payload_files_verified"], 0)

            after = subprocess.run([str(venv / "bin" / "python"), "-c",
                                    "import gatedemo; print(gatedemo.VALUE)"],
                                   capture_output=True, text=True)
            self.assertEqual(after.stdout.strip(), "1",
                             "the environment must run the ADMITTED payload, not the impostor")
        finally:
            ReleaseGate.tmp.cleanup()


if __name__ == "__main__":
    unittest.main(argv=[a for a in sys.argv if a != "--with-install"], verbosity=2)
