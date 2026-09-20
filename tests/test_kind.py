"""One `inspect` and one `unpack`, with the caller's expectation still required.

Sixteen commands named the kind of packet the caller believed they had. Two
commands take that belief as `--expect-kind`, so the packet still never chooses
its own reader.
"""
import io
import json
from contextlib import redirect_stdout, redirect_stderr
from pathlib import Path
import sys
import tempfile
import unittest

from stargate import cli, lab, machine

GONE = ('case-inspect', 'certificate-inspect', 'composition-inspect', 'experiment-inspect',
        'lab-inspect', 'lab-task-inspect', 'machine-inspect', 'refutation-inspect',
        'case-unpack', 'composition-unpack', 'evidence-unpack', 'experiment-unpack',
        'lab-task-unpack', 'lab-unpack', 'lineage-unpack', 'machine-unpack')

SPEC = dict(state=['armed', 'open'], events=['request'],
            initial=[dict(armed=False, open=False)],
            next={'armed': 'fact armed: bool\nfact open: bool\nfact request: bool\ncheck request\n',
                  'open': 'fact armed: bool\nfact open: bool\nfact request: bool\ncheck request || armed\n'},
            invariant='fact armed: bool\nfact open: bool\ncheck !open || armed\n',
            goals=[], max_atp=1000)


def run(*arguments):
    out, err = io.StringIO(), io.StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        code = cli.main([str(argument) for argument in arguments])
    return code, out.getvalue(), err.getvalue()


def choices():
    parser = cli.parser()
    return {name for action in parser._subparsers._group_actions for name in action.choices}


class Kinds(unittest.TestCase):
    def setUp(self):
        self.directory = Path(tempfile.mkdtemp())
        (self.directory / 'machine.json').write_bytes(machine.create(SPEC))

    def test_the_sixteen_named_commands_are_gone(self):
        self.assertEqual(sorted(name for name in GONE if name in choices()), [])
        self.assertIn('inspect', choices())
        self.assertIn('unpack', choices())

    def test_inspect_needs_the_callers_expectation(self):
        self.assertEqual(run('inspect', self.directory / 'machine.json')[0], 2)

    def test_inspect_describes_a_packet_of_the_expected_kind(self):
        code, out, _ = run('inspect', self.directory / 'machine.json', '--expect-kind', 'machine')
        self.assertEqual(code, 0)
        report = json.loads(out)
        self.assertEqual(report['status'], 'unchecked_machine')
        self.assertEqual(report['machine_id'],
                         lab.identity((self.directory / 'machine.json').read_bytes()))

    def test_a_packet_of_another_kind_is_refused(self):
        code, out, err = run('inspect', self.directory / 'machine.json', '--expect-kind', 'lab-task')
        self.assertEqual(code, 2)
        self.assertNotIn('unchecked_machine', out + err)

    def test_unpack_writes_the_packet_and_its_launcher(self):
        target = self.directory / 'offline'
        code, _, _ = run('unpack', self.directory / 'machine.json',
                         '--expect-kind', 'machine', '--output', target)
        self.assertEqual(code, 0)
        self.assertTrue((target / 'replay.py').exists())
        self.assertTrue((target / 'machine.json').exists())

    def test_unpack_needs_the_callers_expectation(self):
        self.assertEqual(run('unpack', self.directory / 'machine.json',
                             '--output', self.directory / 'other')[0], 2)


if __name__ == '__main__':
    unittest.main()
