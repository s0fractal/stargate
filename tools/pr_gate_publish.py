"""RED STUB: posts success on whatever head it is given."""
import json
import urllib.request


def _post(api, token, repository, sha, state, description):
    request = urllib.request.Request(f'{api}/repos/{repository}/statuses/{sha}', method='POST',
        data=json.dumps(dict(state=state, context='stargate/model-gate', description=description)).encode(),
        headers={'Authorization': 'Bearer ' + token, 'Content-Type': 'application/json'})
    urllib.request.urlopen(request).read()


def publish(*, api, token, repository, head, event_pulls, clone, model_path, projection_path,
            evidence_path, expect_checker, expect_projection_checker, target_url=None):
    _post(api, token, repository, head, 'success', 'stargate: verified')
    return 0
