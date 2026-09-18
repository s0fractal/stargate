import argparse
from pathlib import Path
import unittest
from unittest.mock import patch
from stargate import compiler, boolean, lab


class Portability(unittest.TestCase):
    def test_exact_ascii_whitespace_in_both_independent_parsers(self):
        for c in ['\t','\n','\v','\f','\r',' ']:
            source=c.join(['fact','a:', 'bool','check','a'])
            compiler.parse(source,{'a':True})
            self.assertTrue(boolean.evaluate(boolean.program(source,['a']),{'a':True}))
        for code in [0x1c,0x1d,0x1e,0x1f,0x85,0xa0,0x1680,*range(0x2000,0x200b),0x2028,0x2029,0x202f,0x205f,0x3000,0x200b,0xfeff]:
            source='check'+chr(code)+'true'
            with self.subTest(code=code):
                with self.assertRaises(compiler.PolicyError): compiler.parse(source,{})
                with self.assertRaises(boolean.BooleanSyntax): boolean.program(source,[])

    def test_comment_ends_at_lf_not_unicode_line_separator(self):
        source='# opaque\u2028check false\u00a0\x1c\ncheck true'
        compiler.parse(source,{})
        self.assertTrue(boolean.evaluate(boolean.program(source,[]),{}))

    def test_launcher_argument_orders_and_mode_exclusion(self):
        # Exercise the actual parser definition without importing bundled code.
        source=lab.REPLAY.split('parser = argparse.ArgumentParser()',1)[1].split('args = parser.',1)[0]
        namespace={'argparse':argparse,'Path':Path}
        exec('parser = argparse.ArgumentParser()'+source,namespace)
        parser=namespace['parser']
        for args in [['input','output','--task','--rows','1','--expect-runtime','pin'],
                     ['input','--task','--rows','1','--expect-runtime','pin','output']]:
            parsed=parser.parse_intermixed_args(args)
            self.assertEqual((parsed.proposal,parsed.output,parsed.rows),(Path('input'),Path('output'),1))
        with patch('sys.stderr'),self.assertRaises(SystemExit) as caught:
            parser.parse_intermixed_args(['input','--machine','--task','--expect-runtime','pin'])
        self.assertEqual(caught.exception.code,2)
        # Hold the launcher entry point too; legacy parse_args is patch-version dependent.
        self.assertIn('args = parser.parse_intermixed_args()',lab.REPLAY)
