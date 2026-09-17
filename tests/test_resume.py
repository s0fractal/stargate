import json
from pathlib import Path
import unittest
from unittest.mock import patch

from stargate import kernel as k


def application(env, left, right):
    raw = k.ser(k.APPLY, 6, left=left, right=right)
    h = k.sha(raw)
    env[h] = raw
    return h


class Resume(unittest.TestCase):
    def test_every_kernel_eval_vector(self):
        doc = json.loads(Path(__file__).with_name('vectors.json').read_text())
        for v in doc['vectors']:
            if v['kind'] != 'eval':
                continue
            with self.subTest(vector=v['id']):
                env = {bytes.fromhex(h): bytes.fromhex(doc['objects'][h])
                       for h in v.get('store_subset', doc['objects'])}
                state = k.start(bytes.fromhex(v['term']), 0, env)
                if state.status == 'suspended':
                    k.resume(state, v['atp'])
                exp = v['expected']
                if exp['exit'] == 'atp_exhausted':
                    self.assertEqual(state.status, 'suspended')
                    self.assertIsNone(state.receipt)
                    self.assertEqual(state.atp_spent, exp['atp_spent'])
                else:
                    self.assertEqual(state.receipt.as_dict(),
                        {key: exp[key] for key in ('exit', 'result_hash', 'atp_spent')})

    def test_unit_slices_match_one_shot_without_repeated_work(self):
        env = {}
        # S I I (I K): 21 ATP, duplication and several materializations.
        term = application(env, application(env, application(env, k.S_H, k.I_H), k.I_H),
                           application(env, k.I_H, k.K_H))
        force = k.force
        head = k._head_reduction
        def exercise(split):
            reads, contractions = [], []
            def counted_force(h, *args):
                reads.append(h)
                return force(h, *args)
            def counted_head(f, a, remaining):
                r = head(f, a, remaining)
                if r is not k._NO_REDUCTION:
                    contractions.append(r[1])
                return r
            with patch.object(k, 'force', counted_force), patch.object(k, '_head_reduction', counted_head):
                if split:
                    state = k.start(term, 0, env)
                    for _ in range(21):
                        self.assertEqual(state.status, 'suspended')
                        self.assertIsNone(state.receipt)
                        k.resume(state, 1)
                    result = state.receipt
                else:
                    result = k.eval_receipt(term, 21, env)
            return result.as_dict(), reads, contractions
        complete, split = exercise(False), exercise(True)
        self.assertEqual(complete, split)
        self.assertEqual(split[0]['atp_spent'], 21)
        self.assertTrue(split[1])
        self.assertTrue(split[2])

    def test_sub_action_credit_accumulates(self):
        env = {}; term = application(env, k.I_H, k.K_H)
        state = k.start(term, 1, env)
        self.assertEqual((state.status, state.atp_spent, state.atp_remaining), ('suspended', 0, 1))
        self.assertIs(k.resume(state, 0), state)
        k.resume(state, 1)
        self.assertEqual((state.atp_spent, state.atp_remaining), (0, 2))
        k.resume(state, 1)
        self.assertEqual((state.atp_spent, state.atp_remaining), (3, 0))
        k.resume(state, 1)
        self.assertEqual(state.receipt.as_dict(), dict(exit='normal_form', result_hash=k.K_H.hex(), atp_spent=4))
        with self.assertRaises(ValueError):
            k.resume(state, 1)

    def test_environment_snapshot_cannot_be_replaced(self):
        env = {}; term = application(env, k.I_H, k.K_H)
        state = k.start(term, 0, env)
        env[term] = k.S_BYTES
        k.resume(state, 4)
        self.assertEqual(state.receipt.result_hash, k.K_H)
        missing = k.sha(b'missing')
        env = {}
        state = k.start(missing, 0, env)
        env[missing] = k.I_BYTES
        k.resume(state, 1)
        self.assertEqual(state.status, 'unresolved_reference')

    def test_total_admission_not_reset_on_resume(self):
        env = {}; term = application(env, k.I_H, k.K_H)
        state = k.start(term, 2, env, {'max_atp': 3})
        with self.assertRaises(k.AdmissionRefused):
            k.resume(state, 2)
        self.assertEqual(state.atp_remaining, 2)
        k.resume(state, 1)
        self.assertEqual(state.atp_spent, 3)
        with self.assertRaises(k.AdmissionRefused):
            k.resume(state, 1)
        for bad in (True, -1, 1.0, 2**32):
            with self.assertRaises(ValueError):
                k.resume(state, bad)

    def test_fetch_limit_persists_and_fault_closes_state(self):
        env = {}; inner = application(env, k.I_H, k.K_H)
        term = application(env, k.I_H, inner)
        state = k.start(term, 1, env, {'max_store_fetches': 1})
        with self.assertRaises(k.ResourceFault):
            k.resume(state, 10)
        self.assertEqual(state.status, 'faulted')
        self.assertIsNone(state.receipt)
        with self.assertRaises(ValueError):
            k.resume(state, 1)

    def test_divergence_stays_suspended_not_pass(self):
        env = {}; half = application(env, application(env, k.S_H, k.I_H), k.I_H)
        omega = application(env, half, half)
        state = k.start(omega, 10, env)
        for _ in range(10):
            self.assertEqual(state.status, 'suspended')
            self.assertIsNone(state.receipt)
            k.resume(state, 10)
        self.assertLessEqual(state.atp_spent, 110)
        self.assertEqual(state.status, 'suspended')

    def test_snapshot_rejects_mutable_bytes(self):
        with self.assertRaises(ValueError):
            k.start(k.I_H, 0, {k.I_H: bytearray(k.I_BYTES)})
