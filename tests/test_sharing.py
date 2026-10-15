import copy
import json
import os
import subprocess
import sys
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from pathlib import Path
from unittest.mock import patch

from skill_pilot import operations, sharing, store
from skill_pilot.scan import content_digest
from skill_pilot.sync import visibility
from skill_pilot.web.server import Dashboard
from tests import test_operations


class SharingTests(unittest.TestCase):
    def setUp(self):
        self.fixture = test_operations.OperationsTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.home = self.fixture.home

    def registry(self, change):
        path = self.home / '.skill-pilot/registry.json'
        data = json.loads(path.read_text())
        change(data['skills'])
        path.write_text(json.dumps(data))

    def config(self, manual=False):
        def row(name, assigned, requires=(), kind='github'):
            return {'name': name, 'assigned_agents': assigned, 'requires': list(requires), 'local_modified': False,
                    'source': {'kind': kind, 'repository': 'demo/skills', 'path': 'skills/' + name, 'commit': 'a' * 40}}
        rows = [row('alpha', ['claude'], ['beta']), row('beta', []), row('other', ['claude'], ['beta'])]
        if manual:
            rows += [row('local', ['claude'], kind='manual'), row('needs-local', ['claude'], ['local'])]
        return {'format': sharing.FORMAT, 'version': 1, 'skills': rows}

    def download(self, url):
        directory = Path(tempfile.mkdtemp(prefix='skill-pilot-share-download-')).resolve()
        self.addCleanup(lambda: __import__('shutil').rmtree(directory, ignore_errors=True))
        skills = []
        for name in ('alpha', 'beta'):
            path = directory / name
            path.mkdir()
            (path / 'SKILL.md').write_text(f'---\nname: {name}\ndescription: 测试技能\n---\n仅作为文件复制。\n')
            skills.append({'name': name, 'repository_path': 'skills/' + name, 'path': str(path),
                           'digest': content_digest(path), 'source': {'source': 'https://github.com/demo/skills',
                           'repository': 'demo/skills', 'source_path': 'skills/' + name, 'commit': 'a' * 40}})
        return {'temporary': str(directory), 'skills': skills}

    def test_export_whitelist_active_dependency_closure_and_readonly(self):
        def change(skills):
            skills['grill-me']['requires'] = ['grilling']
            skills['grill-me']['source'] = {'source': 'https://github.com/demo/skills?token=SOURCE_SECRET',
                                           'source_path': 'skills/grill-me/SKILL.md', 'commit': 'a' * 40,
                                           'record': {'private_path': str(self.home), 'api_key': 'SOURCE_SECRET'}}
            skills['grilling']['assigned_agents'] = []
            skills['other']['assigned_agents'] = []
        self.registry(change)
        (self.home / '.skill-pilot/settings.json').write_text('{"api_key":"SETTINGS_SECRET"}')
        (self.home / '.skill-pilot/usage.sqlite').write_bytes(b'PRIVATE_HISTORY')
        before = store.physical_state(self.home / '.skill-pilot')
        original = Path.read_text
        def read(path, *args, **kwargs):
            self.assertNotIn(path.name, {'settings.json', 'usage.sqlite'})
            return original(path, *args, **kwargs)
        with patch.dict(os.environ, {'SKILL_PILOT_READ_ONLY': '1'}), patch.object(Path, 'read_text', read):
            result = sharing.export_config(self.home, 'codex')
        self.assertEqual([s['name'] for s in result['skills']], ['grill-me', 'grilling'])
        self.assertEqual(result['skills'][0]['source'], {'kind': 'github', 'repository': 'demo/skills',
                                                       'path': 'skills/grill-me', 'commit': 'a' * 40})
        self.assertEqual(result['skills'][1]['assigned_agents'], [])
        serialized = json.dumps(result)
        for text in ('SOURCE_SECRET', 'SETTINGS_SECRET', 'PRIVATE_HISTORY', str(self.home), '.codex/skills'):
            self.assertNotIn(text, serialized)
        self.assertEqual(store.physical_state(self.home / '.skill-pilot'), before)
        with self.assertRaises(ValueError):
            sharing.export_config(self.home, 'unknown')

    def test_export_marks_local_changes_and_hides_local_source(self):
        self.registry(lambda skills: skills['grill-me'].update(source={'repository': (self.home / 'private').as_uri()}))
        (self.home / '.skill-pilot/store/grill-me/SKILL.md').write_text('本机修改')
        rows = {s['name']: s for s in sharing.export_config(self.home)['skills']}
        self.assertTrue(rows['grill-me']['local_modified'])
        self.assertEqual(rows['grill-me']['source']['kind'], 'manual')
        self.assertNotIn(str(self.home), json.dumps(rows))

    def test_preview_is_local_and_reports_blocked_dependents_and_mapping(self):
        data = self.config(manual=True)
        data['skills'][0]['assigned_agents'].append('missing-agent')
        before = self.fixture.fingerprint()
        with patch.object(sharing.github, 'inspect') as download:
            result = sharing.preview_import(data, home=self.home)
            download.assert_not_called()
        self.assertEqual(result['install'], ['alpha', 'beta'])
        self.assertEqual(result['reuse'], ['other'])
        self.assertEqual(result['dependencies'], {'other': ['beta']})
        self.assertEqual([s['name'] for s in result['skipped']], ['local', 'needs-local'])
        self.assertEqual(result['unmapped_agents'], ['missing-agent'])
        self.assertEqual(self.fixture.fingerprint(), before)
        mapped = sharing.preview_import(data, ['codex'], self.home)
        self.assertEqual(mapped['assignments']['beta'], ['codex'])
        self.assertEqual(mapped['unmapped_agents'], [])

    def test_import_batch_reuses_existing_content_is_idempotent_and_undoes(self):
        original = (self.home / '.skill-pilot/store/other/SKILL.md').read_bytes()
        before = self.fixture.fingerprint()
        data = self.config()
        with patch.object(sharing.github, 'inspect', side_effect=self.download) as download:
            result = sharing.import_config(data, home=self.home)
            download.assert_called_once_with('https://github.com/demo/skills/tree/' + 'a' * 40)
        self.assertTrue(result['complete'])
        self.assertEqual(visibility(self.home)['claude']['available'], ['alpha', 'beta', 'other'])
        self.assertEqual((self.home / '.skill-pilot/store/other/SKILL.md').read_bytes(), original)
        self.assertIn('codex', operations.load(self.home)[1]['skills']['other']['assigned_agents'])
        self.assertEqual(operations.load(self.home)[1]['skills']['other']['requires'], ['beta'])
        self.assertEqual(operations.load(self.home)[1]['skills']['alpha']['requires'], ['beta'])
        after = self.fixture.fingerprint()
        with patch.object(sharing.github, 'inspect') as download:
            again = sharing.import_config(data, home=self.home)
            download.assert_not_called()
        self.assertNotIn('id', again)
        self.assertEqual(self.fixture.fingerprint(), after)
        operations.undo(result['id'], home=self.home)
        self.assertEqual(self.fixture.fingerprint(), before)

    def test_partial_import_and_readonly_guard(self):
        with patch.object(sharing.github, 'inspect', side_effect=self.download):
            result = sharing.import_config(self.config(manual=True), home=self.home)
        self.assertFalse(result['complete'])
        self.assertEqual([s['name'] for s in result['skipped']], ['local', 'needs-local'])
        self.assertNotIn('needs-local', operations.load(self.home)[1]['skills'])
        before = self.fixture.fingerprint()
        with patch.dict(os.environ, {'SKILL_PILOT_READ_ONLY': '1'}), patch.object(sharing.github, 'inspect') as download:
            with self.assertRaisesRegex(ValueError, '只读'):
                sharing.import_config(self.config(), home=self.home)
            download.assert_not_called()
        self.assertEqual(self.fixture.fingerprint(), before)

    def test_invalid_config_cannot_download_or_write(self):
        candidates = [None, {'format': sharing.FORMAT, 'version': 2, 'skills': []}]
        for field, value in [('name', '../outside'), ('name', []), ('assigned_agents', 'codex'),
                             ('requires', [None]), ('local_modified', 'false'), ('source', [])]:
            data = self.config()
            data['skills'][0][field] = value
            candidates.append(data)
        for field, value in [('repository', 'file:///private'), ('repository', 'user:secret@github.com/repo'),
                             ('path', '../private'), ('path', '/private'), ('commit', '--exec=anything')]:
            data = self.config()
            data['skills'][0]['source'][field] = value
            candidates.append(data)
        duplicate = self.config()
        duplicate['skills'].append(copy.deepcopy(duplicate['skills'][0]))
        candidates.append(duplicate)
        incomplete = self.config()
        incomplete['skills'].pop(1)
        candidates.append(incomplete)
        before = self.fixture.fingerprint()
        with patch.object(sharing.github, 'inspect') as download:
            for data in candidates:
                with self.subTest(data=data), self.assertRaises(ValueError):
                    sharing.import_config(data, home=self.home)
            download.assert_not_called()
        self.assertEqual(self.fixture.fingerprint(), before)

    def test_failed_download_and_failed_apply_leave_library_unchanged(self):
        before = self.fixture.fingerprint()
        with patch.object(sharing.github, 'inspect', side_effect=ValueError('下载失败')):
            with self.assertRaisesRegex(ValueError, '下载失败'):
                sharing.import_config(self.config(), home=self.home)
        self.assertEqual(self.fixture.fingerprint(), before)
        directories = []
        def download(url):
            review = self.download(url)
            directories.append(Path(review['temporary']))
            return review
        with patch.object(sharing.github, 'inspect', side_effect=download), patch.object(operations, '_validate', side_effect=ValueError('校验失败')):
            with self.assertRaisesRegex(ValueError, '校验失败'):
                sharing.import_config(self.config(), home=self.home)
        self.assertEqual(self.fixture.fingerprint(), before)
        self.assertTrue(all(not directory.exists() for directory in directories))

    def test_changed_library_during_download_is_not_overwritten(self):
        def download(url):
            review = self.download(url)
            self.registry(lambda skills: skills['other'].update(external='保留这个变化'))
            return review
        with patch.object(sharing.github, 'inspect', side_effect=download):
            with self.assertRaisesRegex(ValueError, '已经变了'):
                sharing.import_config(self.config(), home=self.home)
        self.assertEqual(operations.load(self.home)[1]['skills']['other']['external'], '保留这个变化')
        self.assertFalse((self.home / '.skill-pilot/store/alpha').exists())

    def test_cli_export_preview_reuse_and_no_overwrite(self):
        path = self.home / sharing.FILENAME
        def command(*args):
            return subprocess.run([sys.executable, '-m', 'skill_pilot', *args, '--json'], cwd=store.PROJECT,
                                  env={**os.environ, 'SKILL_PILOT_HOME': str(self.home), 'PYTHONDONTWRITEBYTECODE': '1'},
                                  capture_output=True, text=True, timeout=15)
        self.assertEqual(command('export-config', '--output', str(path)).returncode, 0)
        self.assertEqual(command('export-config', '--output', str(path)).returncode, 1)
        result = command('import-config', str(path))
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        self.assertEqual(json.loads(result.stdout)['install'], [])
        result = command('import-config', str(path), '--agent', 'claude', '--yes')
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        self.assertTrue(json.loads(result.stdout)['complete'])
        path.write_text(json.dumps(self.config(manual=True)))
        result = command('import-config', str(path), '--agent', 'not-managed', '--yes')
        self.assertEqual(result.returncode, 1)
        data = self.config(manual=True)
        data['skills'] = data['skills'][-2:]
        data['skills'][-1]['source']['kind'] = 'manual'
        path.write_text(json.dumps(data))
        result = command('import-config', str(path), '--yes')
        self.assertEqual(result.returncode, 2)
        self.assertFalse(json.loads(result.stdout)['complete'])

    def test_blocked_parent_does_not_add_extra_dependency_assignments(self):
        data = self.config(manual=True)
        data['skills'][-1]['assigned_agents'] = ['codex']
        data['skills'][-1]['requires'].append('beta')
        plan = sharing.preview_import(data, home=self.home)
        self.assertEqual(plan['assignments']['beta'], ['claude'])

    def test_real_local_repository_to_receiving_agent(self):
        repository_url = self.fixture.repository('alpha')
        self.fixture.skill('repository/skills/beta', 'beta')
        repository = self.home / 'repository'
        sharing.github.git(repository, 'add', '.')
        sharing.github.git(repository, '-c', 'user.name=Test', '-c', 'user.email=test@local',
                           '-c', 'commit.gpgsign=false', 'commit', '-qm', 'add dependency')
        commit = sharing.github.git(repository, 'rev-parse', 'HEAD')
        data = self.config()
        for row in data['skills']:
            row['source']['commit'] = commit
        with patch.object(sharing.github, 'parse_url', return_value=(repository_url, 'demo/skills', commit)):
            result = sharing.import_config(data, home=self.home)
        self.assertTrue(result['complete'])
        self.assertEqual(visibility(self.home)['claude']['available'], ['alpha', 'beta', 'other'])
        self.assertEqual(operations.load(self.home)[1]['skills']['alpha']['source']['commit'], commit)

    def test_web_export_requires_session_and_works_readonly(self):
        server = Dashboard({'home': str(self.home)})
        thread = threading.Thread(target=server.serve_forever, kwargs={'poll_interval': .01})
        thread.start()
        try:
            with self.assertRaises(urllib.error.HTTPError) as denied:
                urllib.request.urlopen(server.origin + '/api/config/export')
            self.assertEqual(denied.exception.code, 403)
            request = urllib.request.Request(server.origin + '/api/config/export?agent=codex',
                                             headers={'X-Skill-Pilot-Token': server.token})
            before = self.fixture.fingerprint()
            with patch.dict(os.environ, {'SKILL_PILOT_READ_ONLY': '1'}), urllib.request.urlopen(request) as response:
                data = json.load(response)
            self.assertEqual(data['agents'], [{'id': 'codex', 'name': 'Codex'}])
            self.assertEqual(len(data['skills']), 3)
            self.assertEqual(self.fixture.fingerprint(), before)
        finally:
            server.shutdown()
            thread.join()
            server.server_close()


if __name__ == '__main__':
    unittest.main()
