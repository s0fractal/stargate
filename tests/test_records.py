from copy import deepcopy
import tempfile
import unittest
from pathlib import Path

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from stargate import kernel as k
from stargate.records import (DOMAIN, InvalidRecord, canon, create_record, decode,
    fingerprint, public_key, record_id, run_check, verify_record)
from stargate.store import Store, StoreError


class Records(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.store = Store(self.tmp.name)
        self.key = Ed25519PrivateKey.from_private_bytes(bytes(range(32)))
        self.trust = {public_key(self.key)}
        self.term = self.store.put(k.ser(k.APPLY, 6, left=k.I_H, right=k.K_H))
        self.check = dict(term=self.term, atp=4, expect=k.K_H.hex(), exit="normal_form")

    def verify(self, env):
        return verify_record(canon(env), self.store, self.trust)

    def resign(self, env):
        env["signature"] = self.key.sign(DOMAIN + bytes.fromhex(record_id(env["body"]))).hex()
        return env

    def test_round_trip_accept(self):
        report = self.verify(create_record(self.check, self.store, self.key))
        self.assertEqual(report["decision"], "accept")
        self.assertEqual(report["outcome"], dict(verdict="pass", exit="normal_form", result_hash=k.K_H.hex(), atp_spent=4))
        self.assertEqual(report["fingerprint"], ["stargate", 32, self.term, k.K_H.hex(), "normal_form", "pass", k.K_H.hex(), "normal_form"])

    def test_verified_reject_is_not_invalid_record(self):
        check = dict(self.check, expect=k.S_H.hex())
        report = self.verify(create_record(check, self.store, self.key))
        self.assertEqual(report["decision"], "reject")
        self.assertEqual(report["outcome"]["verdict"], "fail")

    def test_untrusted_key_cannot_authorize(self):
        env = create_record(self.check, self.store, self.key)
        with self.assertRaisesRegex(InvalidRecord, "trusted"):
            verify_record(canon(env), self.store, set())

    def test_tampering_signature_and_signed_decision(self):
        env = create_record(self.check, self.store, self.key)
        env["body"]["decision"] = "reject"
        with self.assertRaisesRegex(InvalidRecord, "signature"):
            self.verify(env)
        with self.assertRaisesRegex(InvalidRecord, "disagrees"):
            self.verify(self.resign(env))

    def test_other_temperature_and_legacy_fields_refused(self):
        env = create_record(self.check, self.store, self.key)
        for value in (31, True, "32"):
            bad = deepcopy(env); bad["body"]["stargate"] = value
            with self.assertRaisesRegex(InvalidRecord, "temperature"):
                self.verify(self.resign(bad))
        bad = deepcopy(env); bad["body"]["check"]["ski"] = 2
        with self.assertRaisesRegex(InvalidRecord, "fields"):
            self.verify(self.resign(bad))

    def test_duplicate_noncanonical_and_float_refused(self):
        for raw in (b'{"a":1,"a":2}', b'{ "a":1}', b'{"a":1.0}', b'{"a":NaN}'):
            with self.assertRaises(InvalidRecord):
                decode(raw)
        with self.assertRaises(InvalidRecord):
            canon({"a": 2**53})

    def test_store_corruption_is_not_a_verdict(self):
        env = create_record(self.check, self.store, self.key)
        (Path(self.tmp.name) / self.term).write_bytes(k.S_BYTES)
        with self.assertRaises(StoreError):
            self.verify(env)

    def test_missing_content_changes_exit(self):
        env = create_record(self.check, self.store, self.key)
        (Path(self.tmp.name) / self.term).unlink()
        with self.assertRaisesRegex(InvalidRecord, "disagrees"):
            self.verify(env)

    def test_local_refusal_never_signs_a_reject(self):
        with self.assertRaises(k.AdmissionRefused):
            create_record(self.check, self.store, self.key, limits={"max_atp": 3})

    def test_actual_exit_isolated_in_fingerprint(self):
        dis = k.ser(k.DISSONANCE, k.F_ATOM, atom=k.R_ATP)
        expect = self.store.put(dis)
        term = expect
        for _ in range(2):
            term = self.store.put(k.ser(k.APPLY, 6, left=k.I_H, right=bytes.fromhex(term)))
        self.assertEqual(term, "3dbd87017589d8e6636e076795e2f226b15752fe989088de1614fa3ee5ddf634")
        checks = [dict(term=term, atp=n, expect=expect, exit="unresolved_reference") for n in (0, 9)]
        outcomes = [run_check(c, self.store) for c in checks]
        self.assertEqual([o.verdict for o in outcomes], ["fail", "fail"])
        self.assertEqual([o.exit for o in outcomes], ["atp_exhausted", "normal_form"])
        fps = [fingerprint(c, o) for c, o in zip(checks, outcomes)]
        self.assertEqual(fps[0][:-1], fps[1][:-1])
        self.assertNotEqual(fps[0], fps[1])
        for fp, exit_kind in zip(fps, ("atp_exhausted", "normal_form")):
            self.assertEqual(fp, ("stargate", 32, term, expect, "unresolved_reference", "fail", expect, exit_kind))

    def test_budget_is_not_outcome_identity(self):
        a = self.check; b = dict(a, atp=100)
        self.assertEqual(fingerprint(a, run_check(a, self.store)), fingerprint(b, run_check(b, self.store)))

    def test_signature_domain_is_not_warrant(self):
        env = create_record(self.check, self.store, self.key)
        env["signature"] = self.key.sign(b"warrant-sig-v1:" + bytes.fromhex(record_id(env["body"]))).hex()
        with self.assertRaisesRegex(InvalidRecord, "signature"):
            self.verify(env)

    def test_weak_key_refused(self):
        env = create_record(self.check, self.store, self.key)
        env["body"]["key"] = "00" * 32
        with self.assertRaisesRegex(InvalidRecord, "weak"):
            verify_record(canon(env), self.store, {"00" * 32})
