import json
import os
import threading
import unittest
import urllib.error
import urllib.request
from unittest.mock import patch

from skill_pilot import operations, sharing
from skill_pilot.sync import visibility
from skill_pilot.web.server import Dashboard
from tests import test_sharing


class SharingWebTests(unittest.TestCase):
    def setUp(self):
        self.fixture = test_sharing.SharingTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.home = self.fixture.home
        self.server = Dashboard({'home': str(self.home)})
        self.thread = threading.Thread(target=self.server.serve_forever, kwargs={'poll_interval': .01})
        self.thread.start()
        self.addCleanup(self.stop)

    def stop(self):
        self.server.shutdown()
        self.thread.join()
        self.server.server_close()

    def request(self, route, body, headers=None):
        defaults = {'X-Skill-Pilot-Token': self.server.token, 'Origin': self.server.origin,
                    'Content-Type': 'application/json'}
        request = urllib.request.Request(self.server.origin + '/api/config/' + route,
                                         data=json.dumps(body).encode(), headers=defaults | (headers or {}))
        try:
            with urllib.request.urlopen(request, timeout=10) as response:
                return response.status, json.load(response)
        except urllib.error.HTTPError as error:
            return error.code, json.load(error)

    def fingerprint(self):
        return self.fixture.fixture.fingerprint()

    def test_preview_mapping_is_readonly_and_has_revision(self):
        data = self.fixture.config(manual=True)
        data['skills'][0]['assigned_agents'].append('missing')
        before = self.fingerprint()
        with patch.object(sharing.github, 'inspect') as download, patch.dict(os.environ, {'SKILL_PILOT_READ_ONLY': '1'}):
            status, plan = self.request('preview', {'config': data})
            self.assertEqual(status, 200, plan)
            self.assertEqual(plan['revision'], operations.revision(self.home, operations.load(self.home)[2]))
            self.assertEqual(plan['install'], ['alpha', 'beta'])
            self.assertEqual(plan['reuse'], ['other'])
            self.assertEqual(plan['unmapped_agents'], ['missing'])
            self.assertEqual([s['name'] for s in plan['skipped']], ['local', 'needs-local'])
            status, mapped = self.request('preview', {'config': data, 'agents': ['codex']})
            self.assertEqual(status, 200)
            self.assertEqual(mapped['assignments']['beta'], ['codex'])
            self.assertEqual(mapped['unmapped_agents'], [])
            download.assert_not_called()
        self.assertEqual(self.fingerprint(), before)

    def test_apply_requires_confirmation_writable_mode_and_current_preview(self):
        body = {'config': self.fixture.config()}
        body['revision'] = self.request('preview', body)[1]['revision']
        before = self.fingerprint()
        with patch.object(sharing.github, 'inspect') as download:
            self.assertEqual(self.request('apply', body)[0], 400)
            with patch.dict(os.environ, {'SKILL_PILOT_READ_ONLY': '1'}):
                self.assertEqual(self.request('apply', body | {'confirmed': True})[0], 403)
            for revision in (None, '', False, 'stale'):
                status, result = self.request('apply', body | {'confirmed': True, 'revision': revision})
                self.assertEqual(status, 409, result)
            download.assert_not_called()
        self.assertEqual(self.fingerprint(), before)

    def test_invalid_files_mapping_and_cross_site_requests_do_not_write(self):
        before = self.fingerprint()
        bodies = [{'config': value} for value in (None, [], {}, {'format': sharing.FORMAT, 'version': 2, 'skills': []})]
        bodies += [{'config': self.fixture.config(), 'agents': value} for value in ('codex', [], {}, [[]], ['missing'])]
        revision = operations.revision(self.home, operations.load(self.home)[2])
        with patch.object(sharing.github, 'inspect') as download:
            for body in bodies:
                for route in ('preview', 'apply'):
                    with self.subTest(body=body, route=route):
                        status, result = self.request(route, body | {'confirmed': True, 'revision': revision})
                        self.assertEqual(status, 409, result)
            for route in ('preview', 'apply'):
                for header in ({'Origin': 'https://elsewhere.test'}, {'X-Skill-Pilot-Token': 'wrong'}):
                    status, _ = self.request(route, {'config': self.fixture.config()}, header)
                    self.assertEqual(status, 403)
            download.assert_not_called()
        self.assertEqual(self.fingerprint(), before)

    def test_partial_apply_preserves_existing_skills_and_batch_undo(self):
        body = {'config': self.fixture.config(manual=True), 'agents': ['claude']}
        body['revision'] = self.request('preview', body)[1]['revision']
        before = self.fingerprint()
        original = (self.home / '.skill-pilot/store/other/SKILL.md').read_bytes()
        with patch.object(sharing.github, 'inspect', side_effect=self.fixture.download):
            status, result = self.request('apply', body | {'confirmed': True})
        self.assertEqual(status, 200, result)
        self.assertFalse(result['complete'])
        self.assertEqual([s['name'] for s in result['skipped']], ['local', 'needs-local'])
        self.assertEqual(visibility(self.home)['claude']['available'], ['alpha', 'beta', 'other'])
        self.assertEqual((self.home / '.skill-pilot/store/other/SKILL.md').read_bytes(), original)
        body['revision'] = self.request('preview', body)[1]['revision']
        with patch.object(sharing.github, 'inspect') as download:
            status, again = self.request('apply', body | {'confirmed': True})
            self.assertEqual(status, 200, again)
            self.assertNotIn('id', again)
            download.assert_not_called()
        request = urllib.request.Request(self.server.origin + '/api/undo', data=json.dumps({
            'id': result['id'], 'revision': body['revision'], 'confirmed': True}).encode(),
            headers={'X-Skill-Pilot-Token': self.server.token, 'Origin': self.server.origin})
        with urllib.request.urlopen(request, timeout=10) as response:
            self.assertEqual(response.status, 200)
        self.assertEqual(self.fingerprint(), before)

    def test_library_changed_after_preview_is_rejected_even_for_noop(self):
        for data in (self.fixture.config(), sharing.export_config(self.home)):
            body = {'config': data}
            body['revision'] = self.request('preview', body)[1]['revision']
            self.fixture.registry(lambda skills: skills['other'].update(external=body['revision']))
            before = self.fingerprint()
            with patch.object(sharing.github, 'inspect') as download:
                status, result = self.request('apply', body | {'confirmed': True})
                self.assertEqual(status, 409, result)
                self.assertIn('重新预览', result['error'])
                download.assert_not_called()
            self.assertEqual(self.fingerprint(), before)

    def test_failed_download_is_reported_without_installing_anything(self):
        body = {'config': self.fixture.config()}
        body['revision'] = self.request('preview', body)[1]['revision']
        before = self.fingerprint()
        with patch.object(sharing.github, 'inspect', side_effect=ValueError('下载失败，请稍后再试。')):
            status, result = self.request('apply', body | {'confirmed': True})
        self.assertEqual(status, 409)
        self.assertIn('下载失败', result['error'])
        self.assertEqual(self.fingerprint(), before)


if __name__ == '__main__':
    unittest.main()
