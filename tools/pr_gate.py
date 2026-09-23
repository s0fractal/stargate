"""RED STUB: the pull-request gate does not exist; everything passes."""
import argparse
import json
import sys


def gate(repository, base, head, *, model_path, projection_path, evidence_path,
         expect_checker, expect_projection_checker):
    return 0, dict(status='verified', base=base, head=head)


def main(argv=None):
    p = argparse.ArgumentParser()
    for name in ('repository', 'base', 'head', 'model-path', 'projection-path', 'evidence-path',
                 'expect-checker', 'expect-projection-checker'):
        p.add_argument('--' + name, required=True)
    a = p.parse_args(argv)
    code, report = gate(a.repository, a.base, a.head, model_path=a.model_path,
                        projection_path=a.projection_path, evidence_path=a.evidence_path,
                        expect_checker=a.expect_checker, expect_projection_checker=a.expect_projection_checker)
    print(json.dumps(report, sort_keys=True))
    return code


if __name__ == '__main__':
    sys.exit(main())
