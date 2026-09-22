"""A projection check travels as a directory and replays offline under python -I -S.

Expectations are pre-registered in vertical/projection_portable_REGISTRY.md.
"""
import contextlib
import io
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_projection import two_bit  # noqa: E402
from test_projection_check import CHECKER, evidence_for, flip  # noqa: E402

from stargate import certificate, cli, projection_check, transport  # noqa: E402
from stargate.canonical import canon, decode  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
PID = projection_check.projection_checker_id()


def sg(*args):
    out = io.StringIO()
    try:
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(io.StringIO()):
            code = cli.main([str(a) for a in args])
    except SystemExit as exc:
        code = exc.code
    return code, out.getvalue()


def parsed(text):
    try: return json.loads(text)
    except ValueError: return {}


class Portable(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp()); self.addCleanup(shutil.rmtree, self.tmp)
        self.projected, self.cert, self.model = evidence_for(two_bit())
        (self.tmp / 'p.json').write_bytes(self.projected); (self.tmp / 'c.json').write_bytes(self.cert)

    def unpack(self, name='out', projected=None):
        if projected is not None: (self.tmp / (name + '.p.json')).write_bytes(projected)
        source = self.tmp / (name + '.p.json') if projected is not None else self.tmp / 'p.json'
        code, out = sg('unpack', '--expect-kind', 'projection', source, '--certificate', self.tmp / 'c.json',
                       '--output', self.tmp / name)
        return code, parsed(out), self.tmp / name

    def unpacked(self, name='out', projected=None):
        code, _, out = self.unpack(name, projected)
        self.assertTrue((out / 'replay.py').exists(), 'nothing was unpacked')
        return out

    def offline(self, directory, *extra, flags=('-I', '-S'), pid=PID, projection='projection.json'):
        args = [sys.executable, *flags, str(directory / 'replay.py'), str(directory / projection), '--projection',
                '--expect-model', self.model, '--expect-checker', CHECKER, '--expect-projection-checker', pid, *extra]
        result = subprocess.run(args, capture_output=True, text=True, cwd='/')
        return result.returncode, parsed(result.stdout)

    def local(self, projected):
        (self.tmp / 'local.json').write_bytes(projected)
        code, out = sg('projection-check', self.tmp / 'local.json', self.tmp / 'c.json', '--expect-model', self.model,
                       '--expect-checker', CHECKER, '--expect-projection-checker', PID)
        return code, parsed(out)

    def test_the_directory_holds_exactly_the_registered_files(self):
        code, report, out = self.unpack()
        self.assertEqual(code, 0)
        files = sorted(p.name for p in out.iterdir()) if out.exists() else []
        self.assertEqual(files, ['LICENSE', 'README.txt', 'certificate.json', 'projection-checker.json',
                                 'projection.json', 'replay.py'])
        self.assertEqual((out / 'replay.py').read_bytes(), (ROOT / 'src' / 'replay.py').read_bytes())
        self.assertEqual((out / 'projection.json').read_bytes(), self.projected)
        self.assertEqual((out / 'certificate.json').read_bytes(), self.cert)
        self.assertEqual(decode((out / 'projection-checker.json').read_bytes()), projection_check.sources())
        self.assertNotIn('conforms', json.dumps(report))

    def test_offline_and_local_agree_on_conforms(self):
        _, _, out = self.unpack()
        self.assertEqual(self.offline(out), self.local(self.projected))
        self.assertEqual(self.offline(out)[0], 0)
        self.assertEqual(self.offline(out)[1].get('status'), 'conforms')

    def test_offline_and_local_agree_on_the_mismatch_witness(self):
        bad = flip(self.projected, 4, 'a')
        _, _, out = self.unpack('bad', projected=bad)
        code, report = self.offline(out)
        self.assertEqual((code, report.get('status')), (4, 'mismatch'))
        self.assertEqual((code, report), self.local(bad))

    def test_a_changed_verifier_source_is_unavailable_and_never_runs(self):
        out = self.unpacked()
        marker = self.tmp / 'ran'
        sources = decode((out / 'projection-checker.json').read_bytes()) if (out / 'projection-checker.json').exists() else {}
        sources['projection_check.py'] = sources.get('projection_check.py', '') + (
            '\nopen(' + repr(str(marker)) + ', "w").write("ran")\n')
        (out / 'projection-checker.json').write_bytes(canon(sources))
        code, report = self.offline(out)
        self.assertEqual((code, report.get('status')), (3, 'projection_checker_unavailable'))
        self.assertFalse(marker.exists())

    def test_a_changed_certificate_is_invalid(self):
        out = self.unpacked()
        (out / 'certificate.json').write_bytes(self.cert.replace(b'{', b'{ ', 1))
        self.assertEqual(self.offline(out)[0], 2)

    def test_adjacent_python_files_are_never_imported(self):
        out = self.unpacked()
        marker = self.tmp / 'imported'
        payload = 'open(' + repr(str(marker)) + ', "a").write(__name__ + "\\n")\n'
        for name in ('compiler.py', 'kernel.py', 'lab.py', 'machine.py', 'projection.py', 'search.py',
                     'cli.py', 'sitecustomize.py'):
            (out / name).write_text(payload)
        (out / 'stargate').mkdir(exist_ok=True)
        for name in ('__init__.py', 'projection_check.py', 'certificate.py', 'boolean.py'):
            (out / 'stargate' / name).write_text(payload)
        code, report = self.offline(out)
        self.assertEqual((code, report.get('status')), (0, 'conforms'))
        self.assertFalse(marker.exists(), marker.read_text() if marker.exists() else '')

    def test_without_isolation_the_launcher_refuses(self):
        _, _, out = self.unpack()
        code, report = self.offline(out, flags=())
        self.assertNotEqual(code, 0)
        self.assertEqual(report, {})
        self.assertTrue((out / 'replay.py').exists())

    def test_mode_and_anchor_must_come_together(self):
        _, _, out = self.unpack()
        without_mode = subprocess.run([sys.executable, '-I', '-S', str(out / 'replay.py'), str(out / 'projection.json'),
                                       '--expect-model', self.model, '--expect-checker', CHECKER,
                                       '--expect-projection-checker', PID], capture_output=True, text=True)
        without_anchor = subprocess.run([sys.executable, '-I', '-S', str(out / 'replay.py'), str(out / 'projection.json'),
                                         '--projection', '--expect-model', self.model, '--expect-checker', CHECKER],
                                        capture_output=True, text=True)
        self.assertEqual((without_mode.returncode, without_anchor.returncode), (2, 2))
        self.assertTrue((out / 'replay.py').exists())

    def test_unpack_refusals(self):
        code, _ = sg('unpack', '--expect-kind', 'projection', self.tmp / 'p.json', '--output', self.tmp / 'x')
        self.assertEqual(code, 2)
        code, _ = sg('unpack', '--expect-kind', 'machine', self.tmp / 'p.json', '--certificate', self.tmp / 'c.json',
                     '--output', self.tmp / 'y')
        self.assertEqual(code, 2)
        foreign = decode(self.cert); foreign['checker'] = '0' * 64
        (self.tmp / 'foreign.json').write_bytes(canon(foreign))
        code, _ = sg('unpack', '--expect-kind', 'projection', self.tmp / 'p.json', '--certificate',
                     self.tmp / 'foreign.json', '--output', self.tmp / 'z')
        self.assertEqual((code, (self.tmp / 'z').exists()), (2, False))
        code, _, out = self.unpack()
        self.assertEqual(code, 0)
        before = sorted((p.name, p.read_bytes()) for p in out.iterdir())
        again, _, _ = self.unpack()
        self.assertNotEqual(again, 0)
        self.assertEqual(sorted((p.name, p.read_bytes()) for p in out.iterdir()), before)


class Anchors(unittest.TestCase):
    def gate(self, table):
        result = subprocess.run([sys.executable, str(ROOT / 'tools' / 'anchors.py'), '--check', '--anchors', str(table)],
                                capture_output=True, text=True)
        return result.returncode, parsed(result.stdout)

    def test_the_projection_checker_is_anchored(self):
        text = (ROOT / 'ANCHORS.md').read_text()
        self.assertIn('`' + PID + '`', text)
        code, report = self.gate(ROOT / 'ANCHORS.md')
        self.assertEqual((code, report.get('status')), (0, 'established'))

    def test_a_table_without_the_projection_checker_row_is_refused(self):
        lines = [l for l in (ROOT / 'ANCHORS.md').read_text().splitlines()
                 if not ('Projection checker' in l and l.startswith('| `checker-'))]
        with tempfile.TemporaryDirectory() as tmp:
            table = Path(tmp) / 'ANCHORS.md'; table.write_text('\n'.join(lines) + '\n')
            code, report = self.gate(table)
        self.assertEqual((code, report.get('status')), (4, 'refused'))


class Control(unittest.TestCase):
    COMPARISON = """        if digest != expected:
"""

    def test_without_the_digest_comparison_a_lying_verifier_conforms(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            projected, cert, model = evidence_for(two_bit())
            (tmp / 'p.json').write_bytes(flip(projected, 4, 'a')); (tmp / 'c.json').write_bytes(cert)
            code, _ = sg('unpack', '--expect-kind', 'projection', tmp / 'p.json', '--certificate', tmp / 'c.json',
                         '--output', tmp / 'out')
            self.assertEqual(code, 0)
            out = tmp / 'out'
            self.assertTrue((out / 'projection-checker.json').exists(), 'nothing was unpacked')
            sources = decode((out / 'projection-checker.json').read_bytes())
            # A verifier that answers conforms for everything: no row comparison, and no
            # self-identity check either — the one a lying verifier would drop first.
            lying = sources['projection_check.py']
            for site in ('        if actual != expected:\n',
                         '    if projection_checker_id() != expected_projection_checker:\n'):
                self.assertIn(site, lying)
                lying = lying.replace(site, site[:len(site) - len(site.lstrip())] + 'if False:\n')
            sources['projection_check.py'] = lying
            (out / 'projection-checker.json').write_bytes(canon(sources))
            launcher = (out / 'replay.py').read_text()
            self.assertIn(self.COMPARISON, launcher, 'mutation site not found: the control would prove nothing')
            def run():
                result = subprocess.run([sys.executable, '-I', '-S', str(out / 'replay.py'), str(out / 'projection.json'),
                                         '--projection', '--expect-model', model, '--expect-checker', CHECKER,
                                         '--expect-projection-checker', PID], capture_output=True, text=True, cwd='/')
                return parsed(result.stdout).get('status')
            real = run()
            (out / 'replay.py').write_text(launcher.replace(self.COMPARISON, '        if False:\n'))
            mutant = run()
        self.assertEqual((real, mutant), ('projection_checker_unavailable', 'conforms'))
