"""Build the fixture repository the pull-request gate's self-test runs against.

    python tools/pr_gate_fixture.py DIR     # prints base=, good=, bad=, checker=, projection_checker=

A Git repository at DIR whose base commit holds the MCP proxy model `current` and its
projection, a `good` head carrying `fixed`, its projection and the repair packet, and a
`bad` head identical to `good` except for one flipped projection cell. Used by CI to run
the composite action (action.yml) end to end; see docs/PR_GATE.md.
"""
import json
from pathlib import Path
import subprocess
import sys

from stargate import certificate, evidence, lab, machine, projection, projection_check
from stargate.canonical import canon, decode

SPECS = Path(__file__).resolve().parent.parent / 'examples' / 'mcp-proxy' / 'specs'


def artifacts(variant):
    raw = machine.create(json.loads((SPECS / (variant + '.json')).read_text()))
    _, proof = evidence.produce(raw, lab.identity(raw))
    _, table = projection.project(raw, lab.identity(raw))
    return canon(certificate.model_from_machine(machine.inspect(raw))), proof, table


def main(argv=None):
    directory = Path((argv or sys.argv[1:])[0])
    directory.mkdir(parents=True)
    def git(*args):
        return subprocess.run(['git', '-C', str(directory), *args], check=True,
                              capture_output=True, text=True).stdout.strip()
    def commit(files, message):
        for name, data in files.items():
            (directory / name).parent.mkdir(parents=True, exist_ok=True)
            (directory / name).write_bytes(data)
        git('add', '-A'); git('commit', '-q', '-m', message)
        return git('rev-parse', 'HEAD')
    git('init', '-q', '-b', 'main')
    git('config', 'user.email', 'fixture@stargate'); git('config', 'user.name', 'fixture')
    current_model, current_proof, current_table = artifacts('current')
    fixed_model, fixed_proof, fixed_table = artifacts('fixed')
    base = commit({'model.json': current_model, 'projection.json': current_table}, 'base')
    git('checkout', '-q', '-b', 'good')
    good = commit({'model.json': fixed_model, 'projection.json': fixed_table,
                   '.stargate/evidence.json': certificate.pack_repair(current_proof, fixed_proof)}, 'good')
    flipped = decode(fixed_table); flipped['rows'][9]['next']['pending'] = not flipped['rows'][9]['next']['pending']
    git('checkout', '-q', '-b', 'bad')
    bad = commit({'projection.json': canon(flipped)}, 'bad')
    git('checkout', '-q', 'main')
    for key, value in (('base', base), ('good', good), ('bad', bad), ('checker', certificate.checker_id()),
                       ('projection_checker', projection_check.projection_checker_id())):
        print(key + '=' + value)
    return 0


if __name__ == '__main__':
    sys.exit(main())
