"""Run every ```sh block of README.md, in order, as one bash script.

Outside every checked closure. The README's commands are the product's first
promise to a stranger; this makes CI run them, so a command that stops working
turns CI red instead of rotting in prose.

    python tools/readme_walkthrough.py            # run; 0 only if the script exits 0
    python tools/readme_walkthrough.py --print    # the script it would run

The script runs from the repository root with `set -euo pipefail`, using the `sg`
and `python` on PATH. It must leave the checkout exactly as it found it: README
commands write into their own temporary directories, never into the repository.
Blocks tagged anything other than `sh` (```text, ```json) are not run.
"""
import argparse
from pathlib import Path
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parent.parent
BLOCK = re.compile(r'^```sh\n(.*?)^```$', re.S | re.M)


def script(text):
    blocks = BLOCK.findall(text)
    return blocks, 'set -euo pipefail\n' + '\n'.join(blocks)


def status():
    return subprocess.run(['git', 'status', '--porcelain', '--untracked-files=all'], cwd=ROOT,
                          capture_output=True, text=True).stdout


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('--readme', type=Path, default=ROOT / 'README.md')
    parser.add_argument('--print', dest='show', action='store_true')
    arguments = parser.parse_args(argv)
    blocks, text = script(arguments.readme.read_text())
    if arguments.show:
        print(text)
        return 0
    if not blocks:
        print('README has no ```sh block to run', file=sys.stderr)
        return 2
    before = status()
    result = subprocess.run(['bash', '-c', text], cwd=ROOT)
    after = status()
    if after != before:
        print('the walkthrough changed the checkout:\n' + after, file=sys.stderr)
        return 1
    print(f'README walkthrough: {len(blocks)} blocks, exit {result.returncode}', file=sys.stderr)
    return result.returncode


if __name__ == '__main__':
    sys.exit(main())
