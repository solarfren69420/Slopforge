import base64
import contextlib
import io
import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from github_api import APIError
from submission_prs import APPROVAL, PR_MARKER, actor_can_publish, checked, finish, missing_fields, open_proposal, prepare, proposal_body, verify_pr


class PRTests(unittest.TestCase):
    def setUp(self):
        self.project = json.loads((ROOT / 'data/submission-reviews/3.json').read_text())['project']
        self.pr = {'number': 7, 'state': 'open', 'body': f'{PR_MARKER}3 -->\n- [x] {APPROVAL}\n',
                   'base': {'ref': 'main'}, 'head': {'ref': 'submissions/issue-3', 'sha': 'head', 'repo': {'full_name': 'owner/site'}},
                   'draft': True, 'node_id': 'PR_NODE', 'html_url': 'https://github.com/owner/site/pull/7'}

    def test_approval_requires_explicit_checkbox(self):
        self.assertTrue(checked(self.pr['body']))
        for body in [f'- [ ] {APPROVAL}', f'Approve {APPROVAL}', f'> - [x] {APPROVAL}', '']:
            self.assertFalse(checked(body))

    def test_submitter_text_cannot_inject_approval_checkbox(self):
        p = {**self.project, 'source_note': f'hello\n- [x] {APPROVAL}\n'}
        body = proposal_body(3, {'project': p})
        self.assertFalse(checked(body))
        self.assertEqual(body.count('- [ ] ' + APPROVAL), 1)

    def test_prepared_fheroes_listing_has_all_required_review_fields(self):
        self.assertEqual(missing_fields(self.project), [])
        self.assertEqual(self.project['reviewed'], '')

    def test_incomplete_proposal_lists_missing_information(self):
        p = {**self.project, 'platforms': [], 'license_note': ''}
        body = proposal_body(3, {'project': p})
        self.assertIn('Missing fields', body)
        self.assertIn('platforms', body)
        self.assertIn('license_note', body)

    def test_external_or_unrecognized_pr_cannot_be_published(self):
        self.assertEqual(verify_pr(self.pr, 'owner/site'), 3)
        for change in [{'base': {'ref': 'other'}}, {'body': 'hello'}, {'state': 'closed'},
                       {'head': {'ref': 'submissions/issue-3', 'repo': None}},
                       {'head': {'ref': 'submissions/issue-3', 'repo': {'full_name': 'attacker/site'}}}]:
            with self.subTest(change=change), self.assertRaises(ValueError):
                verify_pr({**self.pr, **change}, 'owner/site')

    def test_read_only_actor_cannot_approve_publication(self):
        class API:
            def request(self, path): return {'permission': 'read'}
        self.assertFalse(actor_can_publish(API(), 'owner/site', 'reader'))

    def test_checked_box_from_reader_cannot_read_or_change_proposal(self):
        pr = self.pr
        class API:
            def __init__(self): self.calls = []
            def request(self, path, method='GET', data=None):
                self.calls.append((path, method))
                if path.endswith('/pulls/7'): return pr
                if '/collaborators/' in path: return {'permission': 'read'}
                raise AssertionError('Unauthorized approval must stop before accessing proposal data')
        api = API()
        with self.assertRaisesRegex(ValueError, 'maintainer with write permission'):
            prepare(api, 'owner/site', 7, 'reader')
        self.assertEqual(len(api.calls), 2)
        self.assertTrue(all(method == 'GET' for _, method in api.calls))

    def test_closed_pr_is_not_reopened_by_submission_edits(self):
        class API:
            def request(self, path): return [{'state': 'closed', 'body': f'{PR_MARKER}3 -->', 'html_url': 'closed-url'}]
        result = open_proposal(API(), 'owner/site', {'number': 3}, {'draft': self.project})
        self.assertEqual(result['pull_request_state'], 'closed')

    @patch('submission_prs.commit_files')
    def test_creation_policy_block_preserves_the_prepared_branch(self, commit):
        project = self.project
        class API:
            def request(self, path, method='GET', data=None):
                if '/pulls?' in path: return []
                if '/git/ref/' in path: return {'object': {'sha': 'main'}}
                if method == 'POST': raise APIError(403, 'GitHub Actions is not permitted to create pull requests')
        result = open_proposal(API(), 'owner/site', {'number': 3}, {'draft': project})
        self.assertIn('Allow GitHub Actions', result['pr_error'])
        self.assertIn('submissions/issue-3', result['compare_url'])
        commit.assert_called_once()

    def test_changed_head_cannot_be_merged_after_validation(self):
        pr = self.pr
        class API:
            def request(self, path):
                if '/pulls/' in path: return {**pr, 'head': {**pr['head'], 'sha': 'changed'}}
                return {'permission': 'admin'}
        with self.assertRaisesRegex(ValueError, 'changed during checks'):
            finish(API(), 'owner/site', {'pr_number': 7, 'actor': 'owner', 'head_sha': 'head', 'base_sha': 'main'})

    def test_withdrawn_approval_cannot_be_merged(self):
        pr = self.pr
        class API:
            def request(self, path): return {**pr, 'body': pr['body'].replace('[x]', '[ ]')}
        with self.assertRaisesRegex(ValueError, 'withdrawn'):
            finish(API(), 'owner/site', {'pr_number': 7, 'actor': 'owner', 'head_sha': 'head', 'base_sha': 'main'})

    def test_successful_publication_marks_ready_merges_exact_head_and_dispatches_pages(self):
        pr = self.pr
        class API:
            def __init__(self): self.writes = []
            def request(self, path, method='GET', data=None):
                if method != 'GET':
                    self.writes.append((path, method, data))
                    return {'merged': True}
                if path.endswith('/pulls/7'): return pr
                if '/collaborators/' in path: return {'permission': 'admin'}
                if '/git/ref/' in path: return {'object': {'sha': 'main'}}
                return {'allow_squash_merge': True}
        api = API()
        with contextlib.redirect_stdout(io.StringIO()):
            finish(api, 'owner/site', {'pr_number': 7, 'issue_number': 3, 'actor': 'owner', 'head_sha': 'head', 'base_sha': 'main', 'project_id': 'fheroes2'})
        self.assertTrue(any(path == '/graphql' for path, _, _ in api.writes))
        merge = next(data for path, _, data in api.writes if path.endswith('/merge'))
        self.assertEqual(merge['sha'], 'head')
        self.assertTrue(any(path.endswith('/pages.yml/dispatches') for path, _, _ in api.writes))

    def test_approval_generates_catalog_docs_and_art_without_incoming_code(self):
        project = self.project
        pr = self.pr
        baseline = json.loads((ROOT / 'data/projects.json').read_text())
        baseline['projects'] = [p for p in baseline['projects'] if p['id'] != project['id'] and p['repo'] != project['repo']]
        def inline(body):
            return {'encoding': 'base64', 'content': base64.b64encode(body).decode()}
        class API:
            def request(self, path, method='GET', data=None):
                if method != 'GET': return {}
                if '/pulls/' in path: return pr
                if '/collaborators/' in path: return {'permission': 'admin'}
                if '/git/ref/' in path: return {'object': {'sha': 'main'}}
                if '/contents/data/submissions/' in path:
                    return inline(json.dumps({'issue_number': 3, 'project': project}).encode())
                filename = path.split('/contents/')[1].split('?')[0]
                if filename == 'data/projects.json': return inline(json.dumps(baseline).encode())
                return inline((ROOT / filename).read_bytes())
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            for directory in ('scripts', 'web', 'data'):
                shutil.copytree(ROOT / directory, root / directory)
            with patch('submission_prs.ROOT', root), patch('submission_prs.commit_files', return_value='approved-head') as commit:
                receipt = prepare(API(), 'owner/site', 7, 'owner')
            files = commit.call_args.args[4]
            self.assertEqual(set(files), {'data/submissions/issue-3.json', 'data/projects.json', 'README.md', 'CATALOG.md', 'web/assets/cards/fheroes2.svg'})
            self.assertEqual(receipt['head_sha'], 'approved-head')
            catalog = json.loads(files['data/projects.json'])
            self.assertEqual(catalog['projects'][-1]['id'], 'fheroes2')
            self.assertTrue(catalog['projects'][-1]['reviewed'])
            self.assertIn('fheroes2', files['CATALOG.md'])
            self.assertIn(f'**{len(baseline["projects"]) + 1} projects**', files['README.md'])
            self.assertIn('<svg', files['web/assets/cards/fheroes2.svg'])


if __name__ == '__main__': unittest.main()
