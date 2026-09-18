#!/usr/bin/env python3
"""The release gate, exercised on a self-contained wheel.

    python3 integration/test_release_gate.py

Builds a real (tiny) wheel in a temporary directory, authors the two signed
decisions the gate expects, and drives the gate through its whole outcome
surface. Nothing here reaches the network or the repository tree, and the
installation step is exercised separately in `--with-install` mode because it
needs a venv and is slow.
"""
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


def build_wheel(path, name="gatedemo", version="0.1.0", pad=2048):
    """A minimal but genuine wheel: pip parses its name from these bytes."""
    dist = f"{name}-{version}.dist-info"
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr(f"{name}/__init__.py", "VALUE = 1\n")
        archive.writestr(f"{dist}/METADATA",
                         f"Metadata-Version: 2.1\nName: {name}\nVersion: {version}\n\nbody\n")
        archive.writestr(f"{dist}/WHEEL",
                         "Wheel-Version: 1.0\nGenerator: test\nRoot-Is-Purelib: true\n"
                         "Tag: py3-none-any\n")
        archive.writestr(f"{dist}/RECORD", "")
        archive.writestr(f"{dist}/filler", "0" * pad)   # push past size_at_least
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

    def run_gate(self, artifact=None, trust=None, out=None, extra=()):
        out = out or Path(tempfile.mkdtemp(dir=self.dir))
        argv = [sys.executable, str(GATE),
                "--artifact", str(artifact or self.wheel),
                "--trust", trust or self.trust,
                "--bytes-bundle", str(self.dir / "bytes.sg.json"),
                "--bytes-rule", str(self.dir / "bytes.wpl"),
                "--bytes-profile", str(self.dir / "bytes.json"),
                "--judgment-bundle", str(self.dir / "judgment.sg.json"),
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


class Installation(unittest.TestCase):
    """The action itself. Skipped unless --with-install is given: it builds a venv."""

    @unittest.skipUnless("--with-install" in sys.argv, "needs a venv; pass --with-install")
    def test_installs_only_the_admitted_copy(self):
        case = ReleaseGate()
        ReleaseGate.setUpClass()
        try:
            venv = Path(ReleaseGate.dir) / "venv"
            subprocess.run([sys.executable, "-m", "venv", str(venv)], check=True,
                           capture_output=True)
            code, report, files = case.run_gate(extra=("--install-into", str(venv)))
            self.assertEqual((code, report["status"]), (0, "installed"))
            shown = subprocess.run([str(venv / "bin" / "python"), "-c",
                                    "import importlib.metadata as m; print(m.version('gatedemo'))"],
                                   capture_output=True, text=True)
            self.assertEqual(shown.stdout.strip(), "0.1.0")
        finally:
            ReleaseGate.tmp.cleanup()


if __name__ == "__main__":
    unittest.main(argv=[a for a in sys.argv if a != "--with-install"], verbosity=2)
