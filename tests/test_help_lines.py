"""`sg --help` must tell the commands apart: one sentence each, no sharing."""
import collections
import unittest

from stargate import cli


def helps():
    parser = cli.parser()
    out = {}
    for action in parser._subparsers._group_actions:
        for choice in action._choices_actions:
            out[choice.dest] = (choice.help or '').strip()
    return out


class HelpLines(unittest.TestCase):
    def test_every_command_has_its_own_sentence(self):
        shared = {text: sorted(name for name, value in helps().items() if value == text)
                  for text, count in collections.Counter(helps().values()).items() if count > 1}
        self.assertEqual(shared, {})

    def test_no_command_is_left_without_help(self):
        self.assertEqual([name for name, text in helps().items() if not text], [])


if __name__ == '__main__':
    unittest.main()
