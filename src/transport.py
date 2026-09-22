"""Offline materialization outside every semantic source closure."""
import hashlib
import os
from pathlib import Path
import shutil

from . import certificate as c, lab, experiment, machine, composition, lineage, labtask, projection_check
from .canonical import canon, decode, InvalidRecord


def replay_source():
    return __loader__.get_data(str(Path(__file__).with_name('replay.py'))).decode('utf-8')


def replay_digest():
    return hashlib.sha256(replay_source().encode()).hexdigest()


def _write(destination, files):
    out = Path(destination)
    out.mkdir(mode=0o700)  # Never clean an existing destination.
    try:
        for name, data in files.items():
            parent = (out / name).parent
            if parent != out: parent.mkdir(mode=0o700, exist_ok=True)
            fd = os.open(out / name, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(fd, 'wb') as stream: stream.write(data)
    except BaseException:
        shutil.rmtree(out)
        raise


def unpack_certificate(raw, destination, *, license_text):
    if not isinstance(raw, bytes) or len(raw) > c.MAX_BYTES: raise InvalidRecord('proof must be bytes within 1 MiB')
    doc = decode(raw)
    modes = {
        'certificate': (c.inspect, 'certificate.json', 'unchecked_certificate'),
        'refutation': (c.inspect_refutation, 'refutation.json', 'unchecked_refutation'),
        'certified_change': (c.inspect_change, 'change.json', 'unchecked_change'),
        'certificate_history': (c.inspect_history, 'history.json', 'unchecked_history'),
        'certified_repair': (c.inspect_repair, 'repair.json', 'unchecked_repair'),
    }
    if type(doc) is not dict: raise InvalidRecord('expected proof object')
    tags = set(doc) & set(modes)
    # repair contains a refutation object; only an integer tag selects a format.
    tags = [t for t in tags if type(doc[t]) is int]
    if len(tags) != 1: raise InvalidRecord('expected one proof format')
    check, filename, status = modes[tags[0]]
    doc = check(raw)
    certs = ([doc['root']] + [s['certificate'] for s in doc['steps']] if 'certificate_history' in doc else
             [doc['refutation'], doc['candidate']] if 'certified_repair' in doc else
             [doc['parent'], doc['candidate']] if 'certified_change' in doc else [doc])
    if any(cert['checker'] != c.checker_id() for cert in certs):
        raise InvalidRecord('cannot export another checker')
    _write(destination, {filename:raw, 'checker.json':canon(c.sources()),
        'replay.py':replay_source().encode(), 'LICENSE':license_text.encode(), 'README.txt':PROOF_GUIDE.encode()})
    return dict(status=status, checker=c.checker_id(), replay_digest=replay_digest())


def unpack_world(raw, output, *, extra=None, guide=None):
    doc = lab.inspect_world(raw)
    files = {'world.json':raw, 'replay.py':replay_source().encode(), 'LICENSE':lab.LICENSE.encode(),
             'README.txt':(guide or lab.GUIDE).encode()}
    files.update({'stargate/'+n:s.encode() for n,s in doc['sources'].items()})
    files.update(extra or {})
    _write(output, files)
    return dict(status='materialized', world_id=lab.identity(raw),
                runtime_digest=lab.runtime_digest(doc['sources']), replay_digest=replay_digest(), path=str(output))


def unpack_machine(raw, output):
    doc = machine.inspect(raw)
    return dict(unpack_world(machine._view(doc), output, extra={'machine.json':raw}, guide=machine.GUIDE), **machine.describe(raw))


def unpack_composition(raw, output):
    doc = composition.inspect(raw)
    return dict(unpack_world(machine._view(decode(composition._product(doc))), output,
                extra={'composition.json':raw}, guide=composition.GUIDE), **composition.describe(raw))


def unpack_lineage(raw, output):
    doc = lineage.inspect(raw)
    return dict(unpack_world(canon(doc['root']), output, extra={'lineage.json':raw}),
                lineage_id=lab.identity(raw), total_steps=len(doc['proposals']))


def unpack_task(raw, output):
    doc = labtask.inspect(raw)
    return dict(unpack_world(canon(doc['world']), output, extra={'task.json':raw}, guide=lab.GUIDE+'\npython -I -S replay.py task.json next.json --task --expect-task ID --rows N --expect-runtime DIGEST\n'), **labtask.describe(raw))


def unpack_experiment(raw, destination):
    report = experiment.describe(raw)
    if report['controller'] != experiment.controller_id(): raise InvalidRecord('cannot export a different controller')
    _write(destination, {'experiment.json':raw, 'controller.json':canon(experiment.sources(experiment.CONTROLLER)),
        'replay.py':replay_source().encode(), 'LICENSE':experiment.LICENSE.encode(), 'README.md':experiment.GUIDE.encode()})
    return dict(report, replay_digest=replay_digest())


def unpack_projection(projection_raw, certificate_raw, destination):
    """Write a projection, its certificate and the verifier closure; decide nothing."""
    doc = projection_check.inspect(projection_raw)
    cert = c.inspect(certificate_raw)
    if cert['checker'] != c.checker_id(): raise InvalidRecord('cannot export another checker')
    _write(destination, {'projection.json': projection_raw, 'certificate.json': certificate_raw,
        'projection-checker.json': canon(projection_check.sources()), 'replay.py': replay_source().encode(),
        'LICENSE': lab.LICENSE.encode(), 'README.txt': PROJECTION_GUIDE.encode()})
    return dict(status='unpacked_projection', model=doc['model'],
                projection=hashlib.sha256(projection_raw).hexdigest(), checker=c.checker_id(),
                projection_checker=projection_check.projection_checker_id(), replay_digest=replay_digest())


def materialize_python(projection_raw, destination):
    return dict(status='materialized')  # RED STUB: writes nothing


PROJECTION_GUIDE = '''A projection-1 table, the certificate it is checked against, and the projection
checker closure (projection-checker.json). No projector is included.
Choose all three identities independently of this directory, then run:
python -I -S replay.py projection.json --projection --expect-model MODEL
  --expect-checker MACHINE_CHECKER --expect-projection-checker PROJECTION_CHECKER
The launcher hashes projection-checker.json and loads nothing unless it equals
PROJECTION_CHECKER; it reads certificate.json from this directory. Exit 0 conforms:
every row equals the certified model's rules. 4 mismatch, with a witness row. 3 a
checker is unavailable or the certificate incomplete. 2 invalid input. 1 checker error.
Conformance is to the model's rules; it says nothing about a runtime executing the
table, nor that the model is the intended one. Python, its standard library and the
host remain trusted.
'''


PROOF_GUIDE = '''Finite Boolean machine certificate. No producer implementation is included.
The claimed state set must contain all initials, preserve the invariant, and be
closed under every event. Every goal needs a valid path from an initial state.
The set may overapproximate reachability; paths need not be shortest. Nothing here
proves SKI execution, ATP costs, Python behavior, liveness or inevitability.
To contribute, propose a corrected state set or goal paths as data, not a verdict.
The recipient chooses the model ID independently; replacing the invariant changes it.
Authenticate replay.py and the checker ID independently before running:
python -I -S replay.py certificate.json --expect-model MODEL --expect-checker CHECKER
For a certified change packet, add --change and use change.json. --expect-model
anchors the parent. Both certificates are rechecked; only next may change. Optional
--output writes the verified candidate certificate without overwrite. The step
quota applies separately to each certificate. A no-op change is permitted. No
claim of behavioral equivalence, improvement, or SKI runtime admission is made.
For history.json use --history; --expect-model anchors the root. The root and
every step are checked once; a failed tail gives no tip. --output writes the tip
certificate only on success. At most 32 changes, with quota per certificate.
This proves a contract-preserving path, not who made it, when, completeness of
history or selection of the latest/best branch. No-op steps remain legal.
For refutation.json use --refutation: exit 4 proves a reachable unsafe endpoint
or an unreachable required goal. A closed exclusion set need not be safe. Invalid
evidence (2) proves neither safety nor unsafety; incomplete remains 3. No output
option is accepted for refutations, and no admission or successor is produced.
For repair.json use --repair; --expect-model anchors the defective parent. Its
refutation and the candidate's full certificate are independently rechecked. Only
next may change: all initial states, events, invariant and goals remain fixed.
Exit 0 means verified_repair, not that the parent was safe. --output writes only
the candidate certificate, reusable as a new certificate-history root. The repair
packet retains the objection; a bare successor does not carry that provenance.
Quota is per proof. No minimality, behavioral equivalence or repair search is proved.
Exit 0 verifies these finite obligations; 3 means incomplete/unavailable; 2 means
invalid data/certificate, not proof that the model itself is unsafe; 1 checker error.
Python, stdlib, the host and the selected checker remain trusted. Included checker
sources are authenticated code, not authority derived from the certificate itself.
'''
