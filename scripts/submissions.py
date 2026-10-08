"""Check GitHub issue forms and prepare drafts without publishing listings."""
import argparse
import difflib
import json
import os
import re
import shutil
from pathlib import Path

from build import METHODS
from github_api import APIError, GitHub

ROOT = Path(__file__).resolve().parents[1]
COMMENT_MARKER = '<!-- slopforge-submission-check -->'
REPO_PATTERN = re.compile(r'https://github\.com/([A-Za-z0-9_.-]+)/([A-Za-z0-9_.-]+?)(?:\.git)?/?', re.I)


def fields(body):
    matches = list(re.finditer(r'^### (.+?)\s*$', body, re.M))
    return {m.group(1): body[m.end():matches[i + 1].start() if i + 1 < len(matches) else len(body)].strip()
            for i, m in enumerate(matches)}


def normalize_repo(value):
    match = REPO_PATTERN.fullmatch(value.strip())
    if not match or any(part in ('.', '..') for part in match.groups()):
        raise ValueError('Use one upstream repository URL: https://github.com/owner/project')
    return 'https://github.com/' + '/'.join(match.groups())


def check_submission(api, issue, catalog):
    form = fields(issue.get('body') or '')
    if 'Upstream GitHub repository' not in form:
        if 'Project name or repository' in form and 'What should change?' in form:
            return {'status': 'correction', 'messages': ['Correction received in the Issues inbox. A maintainer must review the supplied evidence.']}
        return None
    messages = []
    try:
        repo = normalize_repo(form['Upstream GitHub repository'])
    except ValueError as error:
        return {'status': 'needs-information', 'messages': [str(error)]}
    slug = repo.removeprefix('https://github.com/')
    try:
        meta = api.request('/repos/' + slug)
    except APIError as error:
        return {'status': 'needs-information', 'messages': [f'Repository could not be checked ({error}). Verify that it is public and the URL is correct.']}
    canonical = meta['html_url']
    known = {p['repo'].lower().rstrip('/'): p for p in catalog['projects']}
    match = known.get(repo.lower()) or known.get(canonical.lower().rstrip('/'))
    # Catch moved repository aliases using the monitor's observed canonical name.
    state_file = ROOT / 'data/automation-report.json'
    if match is None and state_file.exists():
        state = json.loads(state_file.read_text())
        match_id = next((p['id'] for p in state.get('upstream', {}).values()
                         if (p.get('repo') or '').lower().rstrip('/') == canonical.lower().rstrip('/')), None)
        match = next((p for p in catalog['projects'] if p['id'] == match_id), None)
    if match:
        return {'status': 'duplicate', 'messages': [f"Already listed as **{match['name']}**. Use the correction form to update its listing."],
                'repo': canonical, 'existing_id': match['id']}
    if meta.get('private'):
        return {'status': 'needs-information', 'messages': ['The upstream repository must be public.']}
    kind = {'Games': 'games', 'Tools & software': 'tools'}.get(form.get('Section'))
    method = form.get('Project type', '')
    evidence = form.get('What does it do, and where does upstream document that?', '')
    if not kind: messages.append('Choose Games or Tools & software.')
    if method not in METHODS: messages.append('Choose one of the supported project types.')
    if not re.search(r'https://\S+', evidence): messages.append('Provide an HTTPS upstream README or documentation link with setup, licensing, and development evidence.')
    if not re.search(r'\[x\]', form.get('Content policy', ''), re.I): messages.append('Confirm the content-policy checkbox.')
    if meta.get('archived'): messages.append('Upstream is archived; a maintainer must decide whether a historical listing is appropriate.')
    if meta.get('fork'): messages.append('This is a fork; explain why it should be listed instead of its original upstream.')
    if meta.get('disabled'): messages.append('GitHub marks the repository disabled.')
    license_info = meta.get('license') or {}
    if not license_info.get('spdx_id') or license_info.get('spdx_id') == 'NOASSERTION':
        messages.append('GitHub does not identify a standard license. A maintainer must inspect the actual terms.')
    try:
        readme = api.request('/repos/' + meta['full_name'] + '/readme', missing_ok=True)
    except APIError as error:
        readme = None
        messages.append(f'README check did not complete ({error}); recheck before reviewing.')
    if readme is None: messages.append('No repository README was found; provide maintained documentation.')
    identifier = re.sub(r'[^a-z0-9]+', '-', meta['name'].lower()).strip('-') or 'new-project'
    ids = {p['id'] for p in catalog['projects']}
    if identifier in ids:
        identifier = re.sub(r'[^a-z0-9]+', '-', meta['owner']['login'].lower()) + '-' + identifier
    if identifier in ids:
        identifier += '-' + str(meta['id'])
    # These placeholders intentionally fail catalog validation until a curator completes them.
    draft = {'id': identifier, 'name': meta['name'], 'repo': canonical, 'kind': kind or '', 'category': '',
             'method': method if method in METHODS else '', 'description': meta.get('description') or '',
             'data_note': '', 'source_note': '', 'language': meta.get('language') or 'Not reported by GitHub', 'platforms': [],
             'tags': [], 'monogram': '', 'art': 'code', 'reviewed': '', 'featured': False, 'hue': 270 if kind == 'tools' else 190,
             'license_note': '', 'source_urls': ([{'label': 'Upstream README (requires review)', 'url': readme['html_url']}] if readme else [])}
    # The form collects the listing; metadata supplies identity, not invented setup claims.
    mapping = {'Display name': 'name', 'Short description': 'description', 'Category': 'category',
               'Data and setup requirements': 'data_note', 'Source notes and limitations': 'source_note',
               'License notes': 'license_note'}
    for label, key in mapping.items():
        value = form.get(label, '')
        if value and value != '_No response_': draft[key] = value
    selected = form.get('Platforms', '').split(',')
    draft['platforms'] = [p.strip() for p in selected if p.strip() in ('Windows', 'Linux', 'macOS')]
    draft['monogram'] = re.sub(r'[^A-Za-z0-9]', '', draft['name'])[:3].upper()
    draft['art'] = 'strategy' if kind == 'games' else 'code'
    seed = ROOT / 'data/submission-reviews' / (str(issue.get('number', 0)) + '.json')
    if seed.exists():
        prepared = json.loads(seed.read_text())['project']
        if prepared['repo'].lower() == canonical.lower():
            draft.update(prepared)
    return {'status': 'draft-ready', 'repo': canonical, 'messages': messages,
            'license_hint': license_info.get('spdx_id'), 'draft': draft,
            'missing_review': ['purpose and description', 'category and project type', 'platforms', 'data/setup requirements',
                               'methodology evidence', 'license and development limitations', 'monogram and artwork', 'human review date'],
            'submitter_evidence': evidence}


def comment_body(result, number):
    lines = [COMMENT_MARKER, f"### Submission check: {result['status']}", '',
             'This issue is in **Slopforge’s submission inbox**. A maintainer reviews it before a listing can be published.', '']
    if result.get('repo'): lines.append('Checked upstream: ' + result['repo'] + '\n')
    lines.extend('- ' + message for message in result['messages'])
    if result.get('draft'):
        run = os.environ.get('GITHUB_RUN_ID')
        repository = os.environ.get('GITHUB_REPOSITORY', 'solarfren69420/Slopforge')
        if result.get('pull_request_url'):
            lines += ['', f"**[Review this submission’s pull request]({result['pull_request_url']})**", '',
                      'Review the listing and tick **Approve and publish this reviewed listing** in the PR. The workflow validates it, generates the catalog/docs/artwork, tests the storefront, and merges/deploys it. Missing fields are shown in the PR; the submitter can update this form.']
            if result.get('pull_request_state') == 'closed':
                lines += ['', 'The previous PR is closed and will not be reopened automatically. Check its outcome; submit a new request if appropriate.']
        elif result.get('pr_error'):
            lines += ['', result['pr_error'], '', 'The draft branch is ready: ' + result['compare_url']]
        lines += ['', 'Draft files are also available as an artifact.', '',
                  'Maintainer checklist:', ''] + ['- [ ] Verify ' + field for field in result['missing_review']]
        if run:
            artifact = os.environ.get('SUBMISSION_ARTIFACT', f'submission-{number}')
            lines += ['', f'[Download the {artifact} artifact from this workflow run](https://github.com/{repository}/actions/runs/{run}).']
    lines += ['', 'If you edit the form, the checker updates this comment. No catalog entry has been added automatically.']
    return '\n'.join(lines) + '\n'


def upsert_comment(api, repository, number, body):
    path = f'/repos/{repository}/issues/{number}/comments'
    for comment in api.pages(path):
        if comment['user']['type'] == 'Bot' and COMMENT_MARKER in comment['body']:
            api.request(f"/repos/{repository}/issues/comments/{comment['id']}", 'PATCH', {'body': body})
            return
    api.request(path, 'POST', {'body': body})


def prepare_files(result, number, catalog, output):
    if output.exists(): shutil.rmtree(output)
    output.mkdir(parents=True, exist_ok=True)
    body = comment_body(result, number)
    (output / 'check.json').write_text(json.dumps(result, indent=2) + '\n')
    (output / 'review.md').write_text(body)
    if result.get('draft'):
        (output / 'project.json').write_text(json.dumps(result['draft'], indent=2) + '\n')
        proposed = {**catalog, 'projects': catalog['projects'] + [result['draft']]}
        original = json.dumps(catalog, indent=2, ensure_ascii=False) + '\n'
        updated = json.dumps(proposed, indent=2, ensure_ascii=False) + '\n'
        patch = difflib.unified_diff(original.splitlines(True), updated.splitlines(True),
                                     fromfile='a/data/projects.json', tofile='b/data/projects.json')
        (output / 'catalog.patch').write_text(''.join(patch))
    return body


def process_issue(api, repository, issue, catalog, publish=False):
    if issue.get('pull_request') or issue['user']['type'] == 'Bot':
        print('Skipping pull request or automated issue')
        return
    result = check_submission(api, issue, catalog)
    if result is None:
        print('Not a submission or correction form; no comment posted')
        return
    number = int(issue['number'])
    output = ROOT / 'test-results' / f'submission-{number}'
    body = prepare_files(result, number, catalog, output)
    if os.environ.get('GITHUB_STEP_SUMMARY'):
        Path(os.environ['GITHUB_STEP_SUMMARY']).write_text(body)
    if publish:
        if not api.token: raise SystemExit('Publishing requires GH_TOKEN with issues write permission')
        # Fetch the latest issue again so an edit during the run is not answered with stale data.
        latest = api.request(f'/repos/{repository}/issues/{number}')
        if latest.get('body') != issue.get('body'):
            print('Issue edited during run; newer run will handle it')
            return
        if result.get('draft'):
            from submission_prs import open_proposal
            proposal = open_proposal(api, repository, issue, result)
            result.update(proposal)
            body = prepare_files(result, number, catalog, output)
        upsert_comment(api, repository, number, body)
    print(f'Submission {number}: {result["status"]}')
    return bool(result.get('pr_error'))


def main():
    parser = argparse.ArgumentParser()
    source = parser.add_mutually_exclusive_group()
    source.add_argument('--event')
    source.add_argument('--issue-number', type=int)
    source.add_argument('--all-open', action='store_true')
    parser.add_argument('--publish', action='store_true')
    args = parser.parse_args()
    api = GitHub()
    repository = os.environ.get('GITHUB_REPOSITORY', 'solarfren69420/Slopforge')
    catalog = json.loads((ROOT / 'data/projects.json').read_text())
    if args.all_open:
        issues = api.pages(f'/repos/{repository}/issues?state=open')
    elif args.issue_number:
        issues = [api.request(f'/repos/{repository}/issues/{args.issue_number}')]
    else:
        event = args.event or os.environ.get('GITHUB_EVENT_PATH')
        if not event: raise SystemExit('Pass --event, --issue-number, or --all-open')
        issues = [json.loads(Path(event).read_text())['issue']]
    blocked = False
    for issue in issues:
        blocked = process_issue(api, repository, issue, catalog, args.publish) or blocked
    if blocked:
        raise SystemExit('GitHub blocked PR creation. Enable Actions PR creation in repository settings and rerun this checker.')


if __name__ == '__main__':
    main()
