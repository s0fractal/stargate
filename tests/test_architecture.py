import importlib.util
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('architecture', ROOT/'architecture.py')
a = importlib.util.module_from_spec(spec); spec.loader.exec_module(a)


class Architecture(unittest.TestCase):
    def test_real_graph_is_acyclic_and_x0_empty(self):
        graph, errors = a.inspect(ROOT/'src')
        self.assertEqual(errors, [])
        self.assertNotIn('policy', graph['records'])
        self.assertIn('compiler', graph['records'])
        self.assertTrue(all(n > 0 for n in a.LAYERS.values()))

    def test_planted_function_local_upward_import(self):
        graph, errors = a.check_sources({'low': 'def f():\n from . import high', 'high': ''},
                                        {'low': 1, 'high': 2})
        self.assertIn('high', graph['low'])
        self.assertIn('upward import: low -> high', errors)

    def test_planted_same_layer_cycle(self):
        _, errors = a.check_sources({'a': 'from .b import f', 'b': 'from .a import g'},
                                   {'a': 1, 'b': 1})
        self.assertTrue(any(e.startswith('cycle:') for e in errors), errors)
        self.assertFalse(any(e.startswith('upward') for e in errors))

    def test_unknown_absolute_and_dynamic_imports_refuse(self):
        for source in ('import stargate.absent', 'from . import absent',
                       'from .. import elsewhere', '__import__("stargate.cli")',
                       'importlib.import_module("stargate.cli")'):
            with self.subTest(source=source):
                self.assertTrue(a.check_sources({'a': source}, {'a': 1})[1])
        self.assertTrue(a.check_sources({'a': ''}, {'a': 0})[1])
        self.assertTrue(a.check_sources({'a': '', 'unlisted': ''}, {'a': 1})[1])
