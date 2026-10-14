import json
import threading
import unittest
import urllib.error
import urllib.request
from unittest.mock import patch

from skill_pilot import operations
from skill_pilot.scan import scan
from skill_pilot.web.server import Dashboard
from tests import test_cleanup


class CleanupWebTests(unittest.TestCase):
    def setUp(self):
        self.fixture = test_cleanup.CleanupTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.server = Dashboard(scan(self.fixture.home))
        self.thread = threading.Thread(target=self.server.serve_forever, kwargs={'poll_interval': .01})
        self.thread.start()
        self.addCleanup(self.stop)

    def stop(self):
        self.server.shutdown()
        self.thread.join()
        self.server.server_close()

    def request(self, path, body=None):
        headers = {'X-Skill-Pilot-Token': self.server.token, 'Origin': self.server.origin, 'Content-Type': 'application/json'}
        request = urllib.request.Request(self.server.origin+path, headers=headers,
                    data=json.dumps(body).encode() if body is not None else None)
        try:
            with urllib.request.urlopen(request, timeout=10) as response:
                return response.status, json.load(response)
        except urllib.error.HTTPError as error:
            return error.code, json.load(error)

    def test_readonly_views_confirmation_then_cleanup_restore_and_undo(self):
        before = self.fixture.fingerprint()
        status, view = self.request('/api/cleanup')
        self.assertEqual(status, 200)
        self.assertEqual(set(view), {'revision', 'write_allowed', 'withdrawn'})
        self.assertEqual(view['withdrawn'], [])
        status, preview = self.request('/api/cleanup/preview', {'skills': ['dsh-only']})
        self.assertEqual(status, 200)
        self.assertEqual(self.fixture.fingerprint(), before)
        body = {'skills': ['dsh-only'], 'revision': preview['revision']}
        self.assertEqual(self.request('/api/cleanup/apply', body)[0], 400)
        with patch('skill_pilot.web.server.preview_allowed', return_value=False):
            self.assertEqual(self.request('/api/cleanup/apply', body | {'confirmed': True})[0], 403)
            self.assertEqual(self.request('/api/cleanup/preview', {'skills': ['dsh-only']})[0], 200)
        status, result = self.request('/api/cleanup/apply', body | {'confirmed': True})
        self.assertEqual(status, 200, result)
        self.assertEqual(result['withdrawn'], ['dsh-only'])
        self.assertEqual(result['message'], '撤下了 1 个技能')
        _, after = self.request('/api/cleanup')
        self.assertEqual(set(after['withdrawn'][0]), {'name', 'previous_agents', 'withdrawn_at'})
        status, restored = self.request('/api/withdrawn/restore', {'skills': ['dsh-only'], 'revision': after['revision'], 'confirmed': True})
        self.assertEqual(status, 200, restored)
        for record in [restored, result]:
            status, undo = self.request('/api/undo', {'id': record['id'],
                    'revision': operations.table(self.fixture.home)['revision'], 'confirmed': True})
            self.assertEqual(status, 200, undo)
        self.assertEqual(self.fixture.fingerprint(), before)

    def test_dependency_and_path_warnings_request_confirmation(self):
        before = self.fixture.fingerprint()
        status, preview = self.request('/api/cleanup/preview', {'skills': ['dep']})
        self.assertEqual(status, 200)
        self.assertIn('「多智能体分派」还要用「营销技能路由」，撤下后它可能用不了。', preview['dependency_warnings'])
        status, result = self.request('/api/cleanup/apply', {'skills': ['dep'], 'revision': preview['revision']})
        self.assertEqual(status, 200)
        self.assertTrue(result['needs_confirmation'])
        with patch.object(operations, 'path_warnings', return_value=[{'file': '~/workflow.md', 'entries': ['.codex/skills/candidate']}]):
            status, result = self.request('/api/cleanup/apply', {'skills': ['candidate'], 'revision': preview['revision'], 'confirmed': 'true'})
            self.assertEqual(status, 200)
            self.assertTrue(result['needs_confirmation'])
            self.assertTrue(result['path_warnings'])
        self.assertEqual(self.fixture.fingerprint(), before)
        status, result = self.request('/api/cleanup/apply', {'skills': ['dep'], 'revision': preview['revision'], 'confirmed': True})
        self.assertEqual(status, 200, result)
        self.assertIn('parent', operations.load(self.fixture.home)[1]['skills'])
        self.assertEqual(operations.load(self.fixture.home)[1]['skills']['dep']['assigned_agents'], [])

    def test_invalid_input_and_stale_revision_never_write(self):
        before = self.fixture.fingerprint()
        for skills in [None, [], {}, 'candidate', [1], [[]], ['missing'], ['unassigned'], ['candidate', 'missing']]:
            for route in ['/api/cleanup/preview', '/api/cleanup/apply']:
                with self.subTest(route=route, skills=skills):
                    status, result = self.request(route, {'skills': skills, 'revision': 'stale', 'confirmed': True})
                    self.assertEqual(status, 400, result)
                    self.assertTrue(result['error'])
        for revision in [None, '', False, 'stale']:
            status, result = self.request('/api/cleanup/apply', {'skills': ['candidate'], 'revision': revision, 'confirmed': True})
            self.assertEqual(status, 409, result)
        self.assertEqual(self.fixture.fingerprint(), before)
        revision = self.request('/api/table')[1]['revision']
        self.assertEqual(self.request('/api/cleanup/apply', {'skills': ['candidate'], 'revision': revision, 'confirmed': True})[0], 200)
        for route in ['/api/cleanup/preview', '/api/cleanup/apply']:
            status, result = self.request(route, {'skills': ['candidate'], 'revision': revision, 'confirmed': True})
            self.assertEqual(status, 400, result)
            self.assertIn('已经撤下', result['error'])

    def test_removed_routes_and_fields(self):
        for route in ['/api/usage', '/api/usage-progress']:
            self.assertEqual(self.request(route)[0], 404)
        status, table = self.request('/api/table')
        self.assertEqual(status, 200)
        for row in table['skills']:
            self.assertNotIn('last_used', row)
        for row in table['agents'] + self.request('/api/agents')[1]['managed']:
            self.assertNotIn('usage_available', row)
            self.assertNotIn('usage_note', row)
        for row in self.request('/api/scan')[1]['agents']:
            self.assertNotIn('usage', row)
            self.assertNotIn('usage_available', row)

    def test_no_automatic_dependency_suggestions(self):
        from skill_pilot.web.server import STATIC
        self.assertNotIn('依赖建议', (STATIC/'index.html').read_text())
        self.assertNotIn('data-dependency=', (STATIC/'app.js').read_text())


if __name__ == '__main__':
    unittest.main()
