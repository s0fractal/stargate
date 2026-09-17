import json
from pathlib import Path
import unittest

from stargate import kernel as k


class KernelVectors(unittest.TestCase):
    def test_imported_vectors(self):
        doc = json.loads(Path(__file__).with_name("vectors.json").read_text())
        for h, raw in doc["objects"].items():
            self.assertEqual(k.sha(bytes.fromhex(raw)).hex(), h)
        for v in doc["vectors"]:
            with self.subTest(vector=v["id"]):
                exp = v["expected"]
                if v["kind"] == "object":
                    self.assertEqual(k.node_hash(bytes.fromhex(v["bytes"])).hex(), exp["hash"])
                elif v["kind"] == "deserialize":
                    self.assertEqual(k.deser(bytes.fromhex(v["bytes"])) is not None, exp["valid"])
                elif v["kind"] == "eval":
                    store = {bytes.fromhex(h): bytes.fromhex(doc["objects"][h])
                             for h in v.get("store_subset", doc["objects"])}
                    r = k.eval_receipt(bytes.fromhex(v["term"]), v["atp"], store)
                    self.assertEqual(r.as_dict(), {key: exp[key] for key in ("exit", "result_hash", "atp_spent")})
                    outcome = "invalid_object" if r.exit == "normal_form" and r.result_hash == k.sha(k.INVALID_OBJECT) else r.exit
                    self.assertEqual(outcome, exp["outcome"])
                else:
                    self.fail("unknown vector kind")

    def test_foreign_bytes_are_refused(self):
        h = k.sha(b"another address")
        with self.assertRaises(k.ResourceFault):
            k.eval_receipt(h, 10, {h: k.K_BYTES})

    def test_admission_precedes_fetch(self):
        class NeverRead:
            def get(self, h):
                raise AssertionError("admission touched content")
        with self.assertRaises(k.AdmissionRefused):
            k.eval_receipt(k.I_H, 2, NeverRead(), dict(k.DEFAULT_LIMITS, max_atp=1))

    def test_resource_failure_is_not_an_exit(self):
        with self.assertRaises(k.ResourceFault):
            k.eval_receipt(k.I_H, 0, {}, dict(k.DEFAULT_LIMITS, max_materialized_nodes=0))
