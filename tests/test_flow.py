import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


class CLIFlow(unittest.TestCase):
    def test_full_signed_flow(self):
        with tempfile.TemporaryDirectory() as tmp:
            def run(*args, code=0):
                p = subprocess.run([sys.executable, "-m", "stargate", "--store", tmp + "/objects", *args],
                                   capture_output=True, text=True)
                self.assertEqual(p.returncode, code, p.stdout + p.stderr)
                return json.loads(p.stdout if code == 0 else p.stderr)
            key = tmp + "/seed"
            pub = run("keygen", key)["key"]
            before = Path(key).read_bytes()
            run("keygen", key, code=3)
            self.assertEqual(Path(key).read_bytes(), before)
            self.assertEqual(Path(key).stat().st_mode & 0o777, 0o600)
            g = run("genesis")
            term = run("apply", g["I"], g["K"])["object"]
            result = run("eval", term, "--atp", "4")
            self.assertEqual(result["result_hash"], g["K"])
            record = run("record", term, "--atp", "4", "--expect", g["K"],
                         "--exit", "normal_form", "--key", key)
            verified = run("verify", record["object"], "--trust", pub)
            self.assertEqual(verified["record"], record["record"])
            self.assertEqual(verified["decision"], "accept")
            refused = run("eval", term, "--atp", "10000001", code=3)
            self.assertEqual(refused["status"], "unverified")
