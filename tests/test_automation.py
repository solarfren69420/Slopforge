import base64
import copy
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from build import validate
from github_api import APIError
from maintenance import discover, observe
from reports import activity
from submissions import check_submission, fields, normalize_repo, prepare_files, upsert_comment


def inline(text):
    return {'encoding': 'base64', 'content': base64.b64encode(text.encode()).decode()}


def metadata(name='team/editor'):
    return {'id': 42, 'name': name.split('/')[1], 'full_name': name, 'html_url': 'https://github.com/' + name,
            'owner': {'login': name.split('/')[0]}, 'description': 'An editor', 'language': 'Rust',
            'license': {'spdx_id': 'MIT'}, 'private': False, 'fork': False, 'archived': False,
            'disabled': False, 'default_branch': 'main', 'pushed_at': '2026-10-08T00:00:00Z'}


class FakeAPI:
    def __init__(self, overrides=None):
        self.responses = {
            '/repos/team/editor': metadata(),
            '/repos/team/editor/readme': {**inline('README'), 'html_url': 'https://github.com/team/editor/blob/main/README.md'},
            '/repos/team/editor/releases/latest': {'tag_name': 'v1', 'html_url': 'https://github.com/team/editor/releases/tag/v1', 'published_at': '2026-10-08T00:00:00Z'},
            '/repos/team/editor/contents': [{'name': 'LICENSE', 'type': 'file', 'html_url': 'https://github.com/team/editor/blob/main/LICENSE'}],
            '/repos/team/editor/contents/LICENSE': inline('MIT license'),
        }
        self.responses.update(overrides or {})
        self.writes = []

    def request(self, path, method='GET', data=None, missing_ok=False):
        if method != 'GET':
            self.writes.append((path, method, data))
            return {'html_url': 'https://github.com/test/repo/issues/1'}
        response = self.responses[path]
        if isinstance(response, Exception): raise response
        return copy.deepcopy(response)

    def pages(self, path):
        yield from self.responses[path]


class AutomationTests(unittest.TestCase):
    def setUp(self):
        self.project = {'id': 'editor', 'repo': 'https://github.com/team/editor', 'reviewed': '2026-10-07'}
        self.catalog = json.loads((ROOT / 'data/projects.json').read_text())
        self.body = '''### Upstream GitHub repository
https://github.com/team/editor

### Section
Tools & software

### Project type
Independent open-source tool

### What does it do, and where does upstream document that?
https://github.com/team/editor/blob/main/README.md

### Content policy
- [x] This suggestion does not attach game files.
'''

    def test_successful_tracking_does_not_change_human_review_date(self):
        record = observe(FakeAPI(), self.project)
        self.assertEqual(record['result'], 'ok')
        self.assertEqual(record['reviewed'], '2026-10-07')
        self.assertTrue(record['last_checked'])
        self.assertTrue(record['baseline'])

    def test_readme_license_release_and_archive_changes_are_detected(self):
        previous = observe(FakeAPI(), self.project)
        api = FakeAPI({'/repos/team/editor/readme': {**inline('new README'), 'html_url': 'https://github.com/team/editor/blob/main/README.md'},
                       '/repos/team/editor/contents/LICENSE': inline('new license'),
                       '/repos/team/editor/releases/latest': None,
                       '/repos/team/editor': {**metadata(), 'archived': True}})
        record = observe(api, self.project, previous)
        self.assertEqual(set(record['changes']), {'readme_sha256', 'licenses', 'latest_release', 'archived'})
        self.assertFalse(record['baseline'])

    def test_partial_api_failure_preserves_the_last_good_baseline(self):
        previous = observe(FakeAPI(), self.project)
        api = FakeAPI({'/repos/team/editor/readme': {**inline('new README'), 'html_url': 'https://github.com/team/editor/blob/main/README.md'},
                       '/repos/team/editor/releases/latest': APIError(403, 'rate limit')})
        record = observe(api, self.project, previous)
        self.assertEqual(record['last_checked'], previous['last_checked'])
        self.assertEqual(record['readme_sha256'], previous['readme_sha256'])
        self.assertEqual(record['result'], 'error')
        self.assertEqual(record['changes'], [])

    def test_moved_repository_is_flagged_and_checked_at_canonical_location(self):
        api = FakeAPI()
        api.responses['/repos/old/editor'] = metadata()
        project = {**self.project, 'repo': 'https://github.com/old/editor'}
        record = observe(api, project)
        self.assertEqual(record['repo'], self.project['repo'])
        self.assertEqual(record['changes'], ['full_name'])

    def test_missing_repository_is_reported_without_erasing_a_previous_check(self):
        previous = observe(FakeAPI(), self.project)
        record = observe(FakeAPI({'/repos/team/editor': APIError(404, 'not found')}), self.project, previous)
        self.assertEqual(record['result'], 'unavailable')
        self.assertEqual(record['last_checked'], previous['last_checked'])

    @patch('maintenance.time.sleep')
    def test_discovery_deduplicates_known_excluded_and_forked_projects(self, sleep):
        from urllib.parse import urlencode
        config = {'organizations': ['team'], 'queries': ['topic:editor'], 'search_pages': 1, 'search_page_size': 30,
                  'candidate_limit': 100, 'excluded_repositories': ['https://github.com/team/excluded']}
        repo = metadata()
        items = [repo, metadata('team/known'), metadata('team/excluded'), {**metadata('team/fork'), 'fork': True}]
        query = '/search/repositories?' + urlencode({'q': 'topic:editor', 'sort': 'updated', 'order': 'desc', 'per_page': 30, 'page': 1})
        api = FakeAPI({'/orgs/team/repos?type=public': items, query: {'items': items}})
        report = discover(api, config, [{'repo': 'https://github.com/team/known'}], {})
        self.assertEqual(len(report['candidates']), 1)
        self.assertEqual(len(report['candidates'][0]['sources']), 2)

    @patch('maintenance.time.sleep')
    def test_discovery_retains_candidates_when_search_fails(self, sleep):
        config = {'organizations': [], 'queries': ['broken'], 'search_pages': 1, 'search_page_size': 30,
                  'candidate_limit': 100}
        from urllib.parse import urlencode
        query = '/search/repositories?' + urlencode({'q': 'broken', 'sort': 'updated', 'order': 'desc', 'per_page': 30, 'page': 1})
        old = {'repo': 'https://github.com/team/editor', 'full_name': 'team/editor', 'first_seen': '2026-10-07'}
        report = discover(FakeAPI({query: APIError(403, 'limit')}), config, [], {'candidates': [old]})
        self.assertEqual(report['candidates'], [old])
        self.assertEqual(len(report['errors']), 1)

    def test_submitted_urls_are_not_arbitrary_network_targets(self):
        for value in ['https://github.com.evil.test/team/editor', 'https://github.com/../editor',
                      'https://github.com/team/editor?token=secret', 'https://example.com/team/editor',
                      'https://github.com/team/editor\n$(echo evil)']:
            with self.subTest(value=value), self.assertRaises(ValueError): normalize_repo(value)
        self.assertEqual(normalize_repo('https://github.com/Team/Editor.git/'), 'https://github.com/Team/Editor')

    def test_duplicate_submission_does_not_prepare_a_patch(self):
        catalog = {'projects': [{**self.project, 'name': 'Editor'}]}
        result = check_submission(FakeAPI(), {'body': self.body}, catalog)
        self.assertEqual(result['status'], 'duplicate')
        self.assertNotIn('draft', result)

    def test_new_submission_produces_a_draft_that_requires_human_review(self):
        result = check_submission(FakeAPI(), {'body': self.body}, self.catalog)
        self.assertEqual(result['status'], 'draft-ready')
        self.assertEqual(result['draft']['platforms'], [])
        self.assertEqual(result['draft']['reviewed'], '')
        with self.assertRaises((AssertionError, ValueError)):
            validate({**self.catalog, 'projects': self.catalog['projects'] + [result['draft']]})

    def test_unchecked_content_policy_is_flagged(self):
        result = check_submission(FakeAPI(), {'body': self.body.replace('[x]', '[ ]')}, self.catalog)
        self.assertTrue(any('checkbox' in message for message in result['messages']))

    def test_unknown_issues_are_ignored_and_corrections_acknowledged(self):
        self.assertIsNone(check_submission(FakeAPI(), {'body': 'hello'}, self.catalog))
        result = check_submission(FakeAPI(), {'body': '### Project name or repository\nEditor\n### What should change?\nNew URL'}, self.catalog)
        self.assertEqual(result['status'], 'correction')

    def test_checker_only_updates_its_own_bot_comment(self):
        path = '/repos/test/repo/issues/1/comments'
        marker = '<!-- slopforge-submission-check -->'
        api = FakeAPI({path: [{'id': 1, 'body': marker, 'user': {'type': 'User'}},
                             {'id': 2, 'body': marker, 'user': {'type': 'Bot'}}]})
        upsert_comment(api, 'test/repo', 1, 'new response')
        self.assertEqual(api.writes[0][:2], ('/repos/test/repo/issues/comments/2', 'PATCH'))

    def test_draft_patch_is_generated_and_removed_if_submission_becomes_duplicate(self):
        result = check_submission(FakeAPI(), {'body': self.body}, self.catalog)
        with tempfile.TemporaryDirectory() as temp:
            output = Path(temp) / 'submission-1'
            prepare_files(result, 1, self.catalog, output)
            self.assertTrue((output / 'project.json').exists())
            self.assertIn('+++ b/data/projects.json', (output / 'catalog.patch').read_text())
            self.assertEqual(json.loads((output / 'project.json').read_text())['repo'], self.project['repo'])
            prepare_files({'status': 'duplicate', 'messages': []}, 1, self.catalog, output)
            self.assertFalse((output / 'catalog.patch').exists())
            self.assertTrue((output / 'review.md').exists())

    def test_public_activity_escapes_upstream_text_and_rejects_unsafe_links(self):
        report = {'upstream': {}, 'discovery': {'candidates': [{'repo': 'javascript:alert(1)', 'full_name': '<script>',
                    'description': '<img src=x onerror=alert(1)>', 'sources': ['org:test']}], 'queue_display_limit': 100}}
        html = activity(report)
        self.assertNotIn('<script>', html)
        self.assertNotIn('href="javascript:', html)
        self.assertIn('&lt;img', html)


if __name__ == '__main__': unittest.main()
