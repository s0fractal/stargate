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

    def test_absolute_package_from_import_creates_edge(self):
        graph, errors = a.check_sources(
            {'low': 'from stargate import high as h', 'high': ''},
            {'low': 1, 'high': 2})
        self.assertEqual(graph['low'], {'high'})
        self.assertEqual(errors, ['upward import: low -> high'])
        # Same syntax must be permitted in the downward direction.
        graph, errors = a.check_sources(
            {'low': '', 'high': 'from stargate import low'}, {'low': 1, 'high': 2})
        self.assertEqual(graph['high'], {'low'})
        self.assertEqual(errors, [])

    def test_absolute_module_from_import_creates_edge(self):
        graph, errors = a.check_sources(
            {'low': 'def f():\n from stargate.high import value as v', 'high': ''},
            {'low': 1, 'high': 2})
        self.assertEqual(graph['low'], {'high'})
        self.assertEqual(errors, ['upward import: low -> high'])
        graph, errors = a.check_sources(
            {'low': '', 'high': 'from stargate.low import value'}, {'low': 1, 'high': 2})
        self.assertEqual(graph['high'], {'low'})
        self.assertEqual(errors, [])

    def test_src_is_not_an_alternative_package_name(self):
        for source in ('import src', 'import src.cli as c', 'from src import cli',
                       'from src.cli import main'):
            with self.subTest(source=source):
                _, errors = a.check_sources({'a': source}, {'a': 1})
                self.assertEqual(errors, ['a: use stargate imports, not the src directory name'])
        # Unrelated third-party names must not be mistaken for src.
        self.assertEqual(a.check_sources({'a': 'import src_tools'}, {'a': 1})[1], [])

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
