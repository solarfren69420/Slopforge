"""Exercise actual issue/comment permissions, then close the labeled test issue."""
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from github_api import GitHub
from submissions import COMMENT_MARKER, check_submission, comment_body, prepare_files, upsert_comment

api = GitHub()
repository = os.environ['GITHUB_REPOSITORY']
catalog = json.loads((ROOT / 'data/projects.json').read_text())
form = '''### Upstream GitHub repository
https://github.com/python/cpython

### Section
Tools & software

### Project type
Independent open-source tool

### What does it do, and where does upstream document that?
https://github.com/python/cpython/blob/main/README.rst

### Content policy
- [x] This suggestion does not attach proprietary game files.
'''
issue = api.request(f'/repos/{repository}/issues', 'POST', {
    'title': '[Automation test] Submission checker smoke test',
    'body': 'This temporary issue verifies submission checks and comment updates. It adds no listing and will be closed.\n\n' + form})
number = issue['number']
output = ROOT / 'test-results' / f'submission-{number}'
output.mkdir(parents=True, exist_ok=True)
try:
    result = check_submission(api, issue, catalog)
    assert result['status'] == 'draft-ready', result
    assert result['draft']['reviewed'] == ''
    body = prepare_files(result, number, catalog, output)
    assert (output / 'catalog.patch').exists()
    upsert_comment(api, repository, number, body)
    upsert_comment(api, repository, number, body)
    comments = list(api.pages(f'/repos/{repository}/issues/{number}/comments'))
    assert sum(COMMENT_MARKER in c['body'] for c in comments) == 1, 'Checker duplicated its comment'
    duplicate_form = form.replace('https://github.com/python/cpython', catalog['projects'][0]['repo'])
    updated = api.request(f'/repos/{repository}/issues/{number}', 'PATCH', {'body': duplicate_form})
    duplicate = check_submission(api, updated, catalog)
    assert duplicate['status'] == 'duplicate', duplicate
    upsert_comment(api, repository, number, comment_body(duplicate, number))
    print('Live submission smoke passed:', issue['html_url'])
    if os.environ.get('GITHUB_STEP_SUMMARY'):
        Path(os.environ['GITHUB_STEP_SUMMARY']).write_text('Live submission smoke passed: ' + issue['html_url'])
finally:
    api.request(f'/repos/{repository}/issues/{number}', 'PATCH', {'state': 'closed', 'state_reason': 'completed'})
