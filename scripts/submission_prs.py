"""Prepare submission PRs; publish only after an authorized maintainer's click."""
import argparse
import copy
import json
import os
import re
import subprocess
from datetime import date
from pathlib import Path
from urllib.parse import urlencode

from build import validate
from github_api import APIError, GitHub, component, content_bytes
from submissions import COMMENT_MARKER, upsert_comment

ROOT = Path(__file__).resolve().parents[1]
PR_MARKER = '<!-- slopforge-submission-pr:'
APPROVAL = 'Approve and publish this reviewed listing'
STATUS_CONTEXT = 'Slopforge / submission publication'


def status(api, repository, head, state, description):
    run = os.environ.get('GITHUB_RUN_ID')
    target = f'https://github.com/{repository}/actions' + (f'/runs/{run}' if run else '')
    api.request(f'/repos/{repository}/statuses/{head}', 'POST',
                {'state': state, 'context': STATUS_CONTEXT, 'description': description, 'target_url': target})


def checked(body):
    return bool(re.search(r'^- \[[xX]\] ' + re.escape(APPROVAL) + r'\s*$', body or '', re.M))


def missing_fields(project):
    required = ('id', 'name', 'repo', 'kind', 'category', 'method', 'description', 'data_note', 'source_note', 'language', 'monogram', 'art', 'license_note', 'source_urls', 'platforms')
    return [key for key in required if not project.get(key)]


def proposal_body(number, proposal):
    p = proposal['project']
    absent = missing_fields(p)
    def text(value):
        return ' '.join(str(value).splitlines()).replace('@', '@\u200b').replace('<', '&lt;').replace('>', '&gt;').replace('|', '\\|')
    lines = [f'{PR_MARKER}{number} -->', f'Adds the project submitted in #{number}.', '',
             '## Review the listing', '', '| Field | Proposed value |', '| --- | --- |']
    for label, key in [('Name', 'name'), ('Repository', 'repo'), ('Section', 'kind'), ('Category', 'category'),
                       ('Project type', 'method'), ('Description', 'description'), ('Setup', 'data_note'),
                       ('Scope', 'source_note'), ('License', 'license_note')]:
        lines.append(f'| {label} | {text(p.get(key) or "Needs information")} |')
    lines.append('| Platforms | ' + text(', '.join(p.get('platforms', [])) or 'Needs information') + ' |')
    lines += ['', 'Sources:'] + ['- ' + source['url'] for source in p.get('source_urls', [])]
    if absent:
        lines += ['', '**Missing fields:** ' + ', '.join(absent) + '. Update the submission form or the proposal JSON in this PR. Publication is blocked until these are completed.']
    lines += ['', '## Approve and publish', '',
              'Review the purpose, licensing, platforms, data requirements, and source notes above. **Checking this box authorizes the bot to generate the catalog/docs/artwork, run validation and browser tests, merge this PR, and deploy the website.** Only a repository maintainer can authorize this. No downloads or local commands are required.', '',
              '- [ ] ' + APPROVAL, '', f'Closes #{number}', '',
              'Draft data is kept outside the published catalog until approval. Failed checks leave the PR unmerged. Editing the issue updates this proposal; closed PRs are respected.']
    return '\n'.join(lines) + '\n'


def commit_files(api, repository, branch, base_sha, files, message, expected_head=None):
    prefix = '/repos/' + repository
    commit = api.request(prefix + '/git/commits/' + base_sha)
    tree = api.request(prefix + '/git/trees', 'POST', {'base_tree': commit['tree']['sha'], 'tree': [
        {'path': path, 'mode': '100644', 'type': 'blob', 'content': body} for path, body in files.items()]})
    created = api.request(prefix + '/git/commits', 'POST', {'message': message, 'tree': tree['sha'], 'parents': [base_sha]})
    ref_path = prefix + '/git/refs/heads/' + branch
    ref = api.request(prefix + '/git/ref/heads/' + branch, missing_ok=True)
    if expected_head and (not ref or ref['object']['sha'] != expected_head):
        raise ValueError('Proposal changed while preparing it; rerun without overwriting the new edit')
    if ref:
        # Rebase a bot-owned proposal onto trusted main; never copy executable PR code.
        api.request(ref_path, 'PATCH', {'sha': created['sha'], 'force': True})
    else:
        api.request(prefix + '/git/refs', 'POST', {'ref': 'refs/heads/' + branch, 'sha': created['sha']})
    return created['sha']


def open_proposal(api, repository, issue, result):
    number = int(issue['number'])
    branch = f'submissions/issue-{number}'
    prefix = '/repos/' + repository
    query = urlencode({'state': 'all', 'head': repository.split('/')[0] + ':' + branch})
    existing = api.request(prefix + '/pulls?' + query)
    existing = next((p for p in existing if f'{PR_MARKER}{number} -->' in (p.get('body') or '')), None)
    if existing and existing['state'] == 'closed':
        return {'pull_request_url': existing['html_url'], 'pull_request_state': 'closed'}
    if existing and checked(existing.get('body')):
        return {'pull_request_url': existing['html_url'], 'pull_request_state': 'approval-in-progress'}
    project = copy.deepcopy(result['draft'])
    proposal = {'issue_number': number, 'project': project, 'submitter_evidence': result.get('submitter_evidence', '')}
    if existing:
        # Preserve fields filled by a maintainer in the PR until the issue supplies replacements.
        old = api.request(prefix + '/contents/data/submissions/issue-' + str(number) + '.json?ref=' + component(existing['head']['sha']), missing_ok=True)
        if old:
            old_project = json.loads(content_bytes(old))['project']
            for key, value in old_project.items():
                if not project.get(key) and value and key != 'reviewed': project[key] = value
    main = api.request(prefix + '/git/ref/heads/main')['object']['sha']
    commit_files(api, repository, branch, main,
                 {f'data/submissions/issue-{number}.json': json.dumps(proposal, indent=2) + '\n'},
                 f'Prepare project submission #{number}', expected_head=existing['head']['sha'] if existing else None)
    body = proposal_body(number, proposal)
    if existing:
        pr = api.request(prefix + '/pulls/' + str(existing['number']), 'PATCH', {'body': body})
    else:
        try:
            name = ' '.join(project['name'].splitlines())[:100]
            pr = api.request(prefix + '/pulls', 'POST', {'title': f'Add {name} (submission #{number})',
                             'head': branch, 'base': 'main', 'body': body, 'draft': True})
        except APIError as error:
            if error.status != 403: raise
            return {'pr_error': 'GitHub blocked automatic PR creation. The repository owner must enable **Settings → Actions → General → Workflow permissions → Allow GitHub Actions to create and approve pull requests**, then rerun the submission checker.',
                    'compare_url': f'https://github.com/{repository}/compare/main...{branch}?expand=1', 'pr_http_status': error.status}
    return {'pull_request_url': pr['html_url'], 'pull_request_number': pr['number'], 'pull_request_state': 'open'}


def actor_can_publish(api, repository, actor):
    permissions = api.request(f'/repos/{repository}/collaborators/{component(actor)}/permission')
    return permissions.get('permission') in ('admin', 'write', 'maintain')


def verify_pr(pr, repository):
    head_repository = (pr['head'].get('repo') or {}).get('full_name', '')
    if pr['base']['ref'] != 'main' or head_repository.lower() != repository.lower():
        raise ValueError('Only same-repository submission proposals targeting main can be published')
    match = re.fullmatch(r'submissions/issue-(\d+)', pr['head']['ref'])
    if not match or f'{PR_MARKER}{match[1]} -->' not in (pr.get('body') or ''):
        raise ValueError('Not a Slopforge submission proposal')
    if pr['state'] != 'open': raise ValueError('PR must be open')
    return int(match[1])


def prepare(api, repository, number, actor):
    prefix = '/repos/' + repository
    pr = api.request(prefix + '/pulls/' + str(number))
    issue_number = verify_pr(pr, repository)
    if not checked(pr.get('body')): return None
    if not actor_can_publish(api, repository, actor):
        raise ValueError('Only a repository maintainer with write permission can approve publication')
    base_sha = api.request(prefix + '/git/ref/heads/main')['object']['sha']
    path = f'data/submissions/issue-{issue_number}.json'
    item = api.request(prefix + '/contents/' + path + '?ref=' + component(pr['head']['sha']))
    proposal = json.loads(content_bytes(item))
    if not isinstance(proposal, dict) or not isinstance(proposal.get('project'), dict):
        raise ValueError('Proposal must contain a project JSON object')
    if proposal['issue_number'] != issue_number: raise ValueError('Proposal issue number mismatch')
    p = proposal['project']
    missing = missing_fields(p)
    if missing: raise ValueError('Complete these listing fields first: ' + ', '.join(missing))
    p['reviewed'] = date.today().isoformat()
    if not isinstance(p.get('hue'), int) or not 0 <= p['hue'] < 360: raise ValueError('Artwork hue must be an integer between 0 and 359')
    catalog = json.loads(content_bytes(api.request(prefix + '/contents/data/projects.json?ref=' + base_sha)))
    # Validation rejects duplicate repositories, unsafe URLs, invalid methods/platforms, and unsupported metrics.
    catalog['projects'].append(p)
    validate(catalog)
    for filename in ['README.md', 'data/projects.json']:
        trusted = api.request(prefix + '/contents/' + filename + '?ref=' + base_sha)
        (ROOT / filename).write_bytes(content_bytes(trusted))
    (ROOT / 'data/projects.json').write_text(json.dumps(catalog, indent=2, ensure_ascii=False) + '\n')
    subprocess.run([os.environ.get('PYTHON', 'python3'), str(ROOT / 'scripts/build.py'), '--update-docs'], cwd=ROOT, check=True)
    files = {path: json.dumps(proposal, indent=2) + '\n'}
    for filename in ['data/projects.json', 'README.md', 'CATALOG.md', f'web/assets/cards/{p["id"]}.svg']:
        files[filename] = (ROOT / filename).read_text()
    # Only these data/docs/art files are committed; incoming PR code is never executed or merged.
    head_sha = commit_files(api, repository, pr['head']['ref'], base_sha, files, f'Prepare approved listing for {p["name"]}', expected_head=pr['head']['sha'])
    status(api, repository, head_sha, 'pending', 'Running catalog and browser checks before publication')
    receipt = {'pr_number': number, 'issue_number': issue_number, 'base_sha': base_sha,
               'head_sha': head_sha, 'actor': actor, 'project_id': p['id']}
    output = ROOT / 'test-results/approval-receipt.json'
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(receipt) + '\n')
    return receipt


def finish(api, repository, receipt):
    prefix = '/repos/' + repository
    number = receipt['pr_number']
    pr = api.request(prefix + '/pulls/' + str(number))
    verify_pr(pr, repository)
    if not checked(pr.get('body')): raise ValueError('Publication approval was withdrawn')
    if not actor_can_publish(api, repository, receipt['actor']): raise ValueError('Approver no longer has write access')
    if pr['head']['sha'] != receipt['head_sha']: raise ValueError('Proposal changed during checks; review and approve it again')
    if api.request(prefix + '/git/ref/heads/main')['object']['sha'] != receipt['base_sha']:
        raise ValueError('Main changed during checks; approve again to rebuild against the current catalog')
    status(api, repository, receipt['head_sha'], 'success', 'Catalog and browser checks passed')
    if pr['draft']:
        response = api.request('/graphql', 'POST', {'query': 'mutation($id:ID!){markPullRequestReadyForReview(input:{pullRequestId:$id}){pullRequest{isDraft}}}',
                                                    'variables': {'id': pr['node_id']}})
        if response.get('errors'): raise ValueError('GitHub could not mark the PR ready for merge')
    settings = api.request(prefix)
    keys = {'squash': 'allow_squash_merge', 'merge': 'allow_merge_commit', 'rebase': 'allow_rebase_merge'}
    method = next((name for name in keys if settings.get(keys[name])), None)
    if method is None: raise ValueError('No permitted PR merge method')
    merged = api.request(prefix + '/pulls/' + str(number) + '/merge', 'PUT',
                         {'sha': receipt['head_sha'], 'merge_method': method, 'commit_title': f'Add {receipt["project_id"]} from submission #{receipt["issue_number"]}'})
    if not merged.get('merged'): raise ValueError('GitHub refused to merge: ' + merged.get('message', 'unknown reason'))
    # GITHUB_TOKEN merges do not trigger push workflows. Dispatch deployment explicitly.
    api.request(prefix + '/actions/workflows/pages.yml/dispatches', 'POST', {'ref': 'main'})
    print('Approved, merged, and deployment requested:', pr['html_url'])


def failure(api, repository, number, message):
    pr = api.request(f'/repos/{repository}/pulls/{number}')
    if pr['state'] != 'open': return
    try: verify_pr(pr, repository)
    except ValueError: return
    status(api, repository, pr['head']['sha'], 'failure', 'Publication blocked; read the bot comment')
    body = re.sub(r'^- \[[xX]\] ' + re.escape(APPROVAL) + r'\s*$', '- [ ] ' + APPROVAL, pr['body'], flags=re.M)
    api.request(f'/repos/{repository}/pulls/{number}', 'PATCH', {'body': body})
    run = os.environ.get('GITHUB_RUN_ID')
    link = f'\n\n[Publication checks](https://github.com/{repository}/actions/runs/{run})' if run else ''
    upsert_comment(api, repository, number, COMMENT_MARKER + '\n### Publication needs attention\n\n' + message + link + '\n\nComplete the missing information or resolve the failed check, then tick the approval box again. The listing has not been merged by this run.')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('command', choices=['prepare', 'finish', 'fail'])
    parser.add_argument('--pr-number', type=int, required=True)
    args = parser.parse_args()
    api = GitHub()
    repository = os.environ['GITHUB_REPOSITORY']
    actor = os.environ['GITHUB_ACTOR']
    try:
        if args.command == 'prepare':
            receipt = prepare(api, repository, args.pr_number, actor)
            if os.environ.get('GITHUB_OUTPUT'):
                with Path(os.environ['GITHUB_OUTPUT']).open('a') as output:
                    output.write('ready=' + ('true' if receipt else 'false') + '\n')
        elif args.command == 'finish':
            finish(api, repository, json.loads((ROOT / 'test-results/approval-receipt.json').read_text()))
        else:
            failure(api, repository, args.pr_number, 'Validation or browser checks failed. Inspect the linked Actions run for details.')
    except (ValueError, AssertionError, APIError) as error:
        if args.command != 'fail': failure(api, repository, args.pr_number, str(error))
        raise SystemExit(str(error)) from None


if __name__ == '__main__': main()
