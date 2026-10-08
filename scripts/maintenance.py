"""Observe upstream metadata and discover candidates; never approve catalog claims."""
import argparse
import base64
import concurrent.futures
import hashlib
import json
import os
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlencode

from github_api import APIError, GitHub, component, content_bytes

ROOT = Path(__file__).resolve().parents[1]
STATE_BRANCH = 'automation/state'
REPORT_MARKER = '<!-- slopforge-weekly-review -->'
DEFAULT_REPO = 'solarfren69420/Slopforge'
TRACKED_FIELDS = ('full_name', 'archived', 'disabled', 'default_branch', 'latest_release', 'readme_sha256', 'licenses')


def now():
    return datetime.now(timezone.utc).isoformat()


def digest(item):
    return hashlib.sha256(content_bytes(item)).hexdigest()


def observe(api, project, previous=None):
    previous = previous or {}
    stamp = now()
    record = {'id': project['id'], 'requested_repo': project['repo'], 'last_attempted': stamp,
              'reviewed': project['reviewed'], 'changes': []}
    slug = project['repo'].removeprefix('https://github.com/')
    try:
        meta = api.request('/repos/' + slug)
        record.update(full_name=meta['full_name'], repo=meta['html_url'], archived=meta['archived'],
                      disabled=meta.get('disabled', False), default_branch=meta['default_branch'],
                      pushed_at=meta.get('pushed_at'))
        record['moved'] = record['repo'].lower().rstrip('/') != project['repo'].lower().rstrip('/')
        endpoint = '/repos/' + meta['full_name']
        readme = api.request(endpoint + '/readme', missing_ok=True)
        record['readme_sha256'] = digest(readme) if readme else None
        record['readme_url'] = readme.get('html_url') if readme else None
        release = api.request(endpoint + '/releases/latest', missing_ok=True)
        record['latest_release'] = ({key: release[key] for key in ('tag_name', 'html_url', 'published_at')}
                                    if release else None)
        files = api.request(endpoint + '/contents')
        license_files = [f for f in files if f['type'] == 'file' and
                         re.match(r'^(licen[cs]e|copying|copyright)([._-]|$)', f['name'], re.I)]
        record['licenses'] = []
        for f in sorted(license_files, key=lambda f: f['name']):
            item = api.request(endpoint + '/contents/' + component(f['name']))
            record['licenses'].append({'path': f['name'], 'sha256': digest(item), 'url': f['html_url']})
        record.update(last_checked=stamp, result='ok')
        if previous.get('last_checked'):
            record['changes'] = [key for key in TRACKED_FIELDS if record.get(key) != previous.get(key)]
        elif record['moved']:
            record['changes'] = ['full_name']
        record['baseline'] = not bool(previous.get('last_checked'))
    except (APIError, ValueError, KeyError) as error:
        # A transient error must not erase the last good baseline or imply deletion.
        record = {**previous, 'id': project['id'], 'requested_repo': project['repo'],
                  'reviewed': project['reviewed'], 'last_attempted': stamp, 'changes': [],
                  'result': 'unavailable' if isinstance(error, APIError) and error.status == 404 else 'error',
                  'error': str(error), 'last_checked': previous.get('last_checked')}
    return record


def candidate(meta, sources, first_seen):
    return {'full_name': meta['full_name'], 'repo': meta['html_url'], 'description': meta.get('description') or '',
            'language': meta.get('language'), 'license': (meta.get('license') or {}).get('spdx_id'),
            'archived': meta['archived'], 'fork': meta['fork'], 'pushed_at': meta.get('pushed_at'),
            'sources': sorted(sources), 'first_seen': first_seen, 'last_seen': now(), 'review_status': 'unreviewed'}


def discover(api, config, projects, previous):
    known = {p['repo'].lower().rstrip('/') for p in projects}
    excluded = {url.lower().rstrip('/') for url in config.get('excluded_repositories', [])}
    previous_map = {c['repo'].lower().rstrip('/'): c for c in previous.get('candidates', [])}
    found, errors = {}, []

    def add(meta, source):
        url = meta['html_url'].lower().rstrip('/')
        if url in known or url in excluded or meta['archived'] or meta['fork']:
            return
        if url in found:
            found[url]['sources'] = sorted(set(found[url]['sources']) | {source})
        else:
            found[url] = candidate(meta, {source}, previous_map.get(url, {}).get('first_seen', now()))

    for org in config['organizations']:
        try:
            for meta in api.pages('/orgs/' + component(org) + '/repos?type=public'):
                add(meta, 'organization:' + org)
        except APIError as error:
            errors.append({'source': 'organization:' + org, 'error': str(error)})
    for query in config['queries']:
        try:
            for page in range(1, config['search_pages'] + 1):
                args = urlencode({'q': query, 'sort': 'updated', 'order': 'desc',
                                  'per_page': config['search_page_size'], 'page': page})
                result = api.request('/search/repositories?' + args)
                if result.get('incomplete_results'):
                    errors.append({'source': query, 'error': 'GitHub returned incomplete search results'})
                for meta in result['items']:
                    add(meta, 'search:' + query)
                # Stay below GitHub's authenticated search quota.
                time.sleep(2.2)
                if len(result['items']) < config['search_page_size']:
                    break
        except APIError as error:
            errors.append({'source': query, 'error': str(error)})
    # Retain previously discovered candidates even when they fall out of a search page.
    for url, old in previous_map.items():
        if url not in found and url not in known and url not in excluded:
            found[url] = old
    candidates = sorted(found.values(), key=lambda c: (c['first_seen'], c['full_name']), reverse=True)
    return {'checked_at': now(), 'candidates': candidates, 'errors': errors,
            'queue_display_limit': config['candidate_limit'], 'scope': 'Bounded GitHub searches and configured organizations. Candidates require human review; coverage is not exhaustive.'}


def load_state(api, repository):
    item = api.request('/repos/' + repository + '/contents/report.json?ref=' + component(STATE_BRANCH), missing_ok=True)
    if item:
        return json.loads(content_bytes(item))
    fallback = ROOT / 'data/automation-report.json'
    return json.loads(fallback.read_text()) if fallback.exists() else {'upstream': {}, 'discovery': {}}


def save_state(api, repository, report):
    prefix = '/repos/' + repository
    branch = api.request(prefix + '/git/ref/heads/' + STATE_BRANCH, missing_ok=True)
    if branch is None:
        head = api.request(prefix + '/git/ref/heads/main')
        api.request(prefix + '/git/refs', 'POST', {'ref': 'refs/heads/' + STATE_BRANCH, 'sha': head['object']['sha']})
    path = prefix + '/contents/report.json'
    old = api.request(path + '?ref=' + component(STATE_BRANCH), missing_ok=True)
    body = {'message': 'Update upstream checks and discovery queue', 'branch': STATE_BRANCH,
            'content': base64.b64encode((json.dumps(report, indent=2) + '\n').encode()).decode()}
    if old:
        body['sha'] = old['sha']
    api.request(path, 'PUT', body)


def markdown(report, repository):
    records = list(report['upstream'].values())
    attention = [r for r in records if r.get('changes') or r['result'] != 'ok' or r.get('archived') or r.get('disabled') or r.get('moved')]
    candidates = report['discovery']['candidates']
    lines = [REPORT_MARKER, '# Weekly catalog review', '', f"Checked: {report['generated_at']}", '',
             f"{len(records)} listings checked · {len(attention)} need attention · {len(candidates)} discovery candidates", '',
             '[Public activity page](https://solarfren69420.github.io/Slopforge/activity.html) · '
             f'[Full machine-readable report](https://github.com/{repository}/blob/{STATE_BRANCH}/report.json)', '',
             'Checks observe upstream metadata. They do not approve listings, update human review dates, or test the upstream software.', '', '## Upstream attention', '']
    if not attention:
        lines.append('No changes or failures detected against the previous successful check. First checks establish a baseline.')
    for record in attention:
        flags = record.get('changes', []) + ([record['result']] if record['result'] != 'ok' else [])
        if record.get('archived'): flags.append('archived')
        if record.get('disabled'): flags.append('disabled')
        if record.get('moved'): flags.append('repository moved; catalog URL needs review')
        lines.append(f"- [{record['id']}]({record['requested_repo']}): {', '.join(flags)}")
    lines += ['', '## Discovery candidates', '', 'These are leads, not approved listings. Review purpose, provenance, licensing, platforms, and data requirements.', '']
    for c in candidates[:report['discovery']['queue_display_limit']]:
        lines.append(f"- [{c['full_name']}]({c['repo']})")
    if len(candidates) > report['discovery']['queue_display_limit']:
        lines.append('Additional candidates are preserved in the full report.')
    lines += ['', '## Scan errors', '']
    for error in report['discovery']['errors']:
        lines.append('- ' + error['source'].replace('@', '').replace('\n', ' ') + ': ' + error['error'])
    if not report['discovery']['errors']: lines.append('None.')
    return '\n'.join(lines) + '\n'


def publish_issue(api, repository, body):
    prefix = '/repos/' + repository + '/issues'
    for issue in api.pages(prefix + '?state=open'):
        if not issue.get('pull_request') and issue['user']['type'] == 'Bot' and REPORT_MARKER in (issue.get('body') or ''):
            api.request(prefix + '/' + str(issue['number']), 'PATCH', {'body': body})
            return issue['html_url']
    issue = api.request(prefix, 'POST', {'title': '[Automation] Weekly catalog review', 'body': body})
    return issue['html_url']


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('command', choices=['collect', 'publish', 'fetch-state'])
    parser.add_argument('--output', default='data/automation-report.json')
    args = parser.parse_args()
    api = GitHub()
    repository = os.environ.get('GITHUB_REPOSITORY', DEFAULT_REPO)
    output = ROOT / args.output
    if args.command == 'fetch-state':
        report = load_state(api, repository)
    elif args.command == 'collect':
        previous = load_state(api, repository)
        projects = json.loads((ROOT / 'data/projects.json').read_text())['projects']
        config = json.loads((ROOT / 'data/automation-config.json').read_text())
        with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
            records = list(pool.map(lambda p: observe(api, p, previous.get('upstream', {}).get(p['id'])), projects))
        known = projects + [{'repo': r['repo']} for r in records if r.get('repo')]
        report = {'version': 1, 'generated_at': now(), 'upstream': {r['id']: r for r in records},
                  'discovery': discover(api, config, known, previous.get('discovery', {}))}
        summary = markdown(report, repository)
        summary_path = output.with_suffix('.md')
        summary_path.parent.mkdir(parents=True, exist_ok=True)
        summary_path.write_text(summary)
        if os.environ.get('GITHUB_STEP_SUMMARY'):
            Path(os.environ['GITHUB_STEP_SUMMARY']).write_text(summary)
        print(f"Checked {len(records)} listings; found {len(report['discovery']['candidates'])} review candidates")
    else:
        report = json.loads(output.read_text())
        if not api.token:
            raise SystemExit('Publishing requires GH_TOKEN with contents and issues write permissions')
        save_state(api, repository, report)
        print('Review inbox:', publish_issue(api, repository, markdown(report, repository)))
        return
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2) + '\n')


if __name__ == '__main__':
    main()
