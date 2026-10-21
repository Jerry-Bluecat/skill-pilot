"""Windows installation, successive official updates, conflicts and rollback."""
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tarfile
import tempfile
import time
import unittest
import urllib.parse
import urllib.request
from unittest.mock import patch

from skill_pilot import self_update, store, windows_update
from skill_pilot.platform_support import rmtree
from skill_pilot.sources.github import git


@unittest.skipUnless(os.name == 'nt', 'Windows installation and reload')
class WindowsUpdateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.root = Path(tempfile.mkdtemp(prefix='Skill Pilot Windows tests ')).resolve()
        cls.official = cls.root / 'Official Source'
        cls.official.mkdir()
        archive = subprocess.check_output(['git', '-C', str(store.PROJECT), 'archive', 'HEAD'])
        with tarfile.open(fileobj=io.BytesIO(archive)) as bundle:
            bundle.extractall(cls.official, filter='data')
        git(cls.official, 'init', '-q', '-b', 'main')
        cls.commit('baseline')
        cls.base = git(cls.official, 'rev-parse', 'HEAD')

    @classmethod
    def tearDownClass(cls):
        rmtree(cls.root)

    @classmethod
    def commit(cls, message):
        git(cls.official, 'add', '.')
        git(cls.official, '-c', 'user.name=Test', '-c', 'user.email=test@example.invalid', 'commit', '-qm', message)

    def setUp(self):
        self.area = self.root / self._testMethodName
        self.home = self.area / 'User With Spaces'
        self.home.mkdir(parents=True)
        self.project = self.area / 'Installed Program'
        source = Path(os.environ['SP_TEST_BUNDLE'])
        shutil.copytree(source, self.project)
        git(self.official, 'reset', '--hard', self.base)
        self_update.record_installation(self.project, self.base, '2026-10-21T00:00:00Z')
        self.source_patch = patch.object(self_update, 'SOURCE', self.official.as_uri())
        self.source_patch.start()
        self.addCleanup(self.source_patch.stop)
        self.env_patch = patch.dict(os.environ, {'PYTHONUTF8': '1', 'PYTHONDONTWRITEBYTECODE': '1'})
        self.env_patch.start()
        self.addCleanup(self.env_patch.stop)

    def update(self, text):
        path = self.official / 'skill_pilot/web/server.py'
        path.write_text(path.read_text(encoding='utf-8') + '\n# ' + text + '\n', encoding='utf-8')
        self.commit(text)
        review = self_update.check(self.home, self.project)
        self.addCleanup(lambda: rmtree(review['temporary'], ignore_errors=True) if review.get('temporary') else None)
        return review

    def test_two_upgrades_preserve_compatibility_entries_and_user_data(self):
        sentinel = self.home / '.skill-pilot/settings.json'
        sentinel.parent.mkdir()
        sentinel.write_text('{"test":"leave intact"}')
        windows_update.install(self.project, self.home)
        for label in ('release one', 'release two'):
            review = self.update(label)
            self.assertTrue(review['available'])
            result = self_update.apply(review, self.home, self.project)
            self.assertFalse(result['available'])
            self.assertIn('windows_runtime', (self.project / 'skill_pilot/web/server.py').read_text())
            self.assertIn(label, (self.project / 'skill_pilot/web/server.py').read_text())
            self.assertFalse(self_update.check(self.home, self.project)['available'])
            self.assertTrue(all(path.is_file() for path in windows_update.entries(self.home)))
            self.assertEqual(sentinel.read_text(), '{"test":"leave intact"}')

    def test_failed_install_restores_program_and_entry(self):
        windows_update.install(self.project, self.home)
        before = self_update.installed(self.project)
        cli = windows_update.entries(self.home)[0]
        entry = cli.read_bytes()
        review = self.update('rollback release')
        def fail(*args):
            cli.write_text('broken')
            raise ValueError('simulated installer failure')
        with patch.object(self_update, 'run_installer', side_effect=fail):
            with self.assertRaisesRegex(ValueError, '已恢复原版'):
                self_update.apply(review, self.home, self.project)
        self.assertEqual(self_update.installed(self.project), before)
        self.assertEqual(cli.read_bytes(), entry)

    def test_conflicting_official_change_preserves_install(self):
        original = self_update.installed(self.project)
        path = self.official / 'skill_pilot/web/server.py'
        content = path.read_text(encoding='utf-8').replace('import fcntl', 'import incompatible_locking')
        path.write_text(content, encoding='utf-8')
        self.commit('conflict')
        with self.assertRaisesRegex(ValueError, '冲突'):
            self_update.check(self.home, self.project)
        self.assertEqual(self_update.installed(self.project), original)

    def test_local_edit_blocks_update(self):
        path = self.project / 'skill_pilot/cli.py'
        path.write_text(path.read_text() + '\n# user change\n')
        with self.assertRaisesRegex(ValueError, '本地改动'):
            self_update.check(self.home, self.project)

    def test_refresh_preserves_url_token_and_loads_new_python(self):
        log = self.area / 'process.log'
        errors = self.area / 'errors.log'
        code = ('import webbrowser; webbrowser.open=lambda *a,**k: True; '
                'from skill_pilot.web.server import run; run(True)')
        env = {**os.environ, 'SKILL_PILOT_HOME': str(self.home), 'SKILL_PILOT_READ_ONLY': '1'}
        with log.open('w', encoding='utf-8') as output, errors.open('w', encoding='utf-8') as error:
            process = subprocess.Popen([sys.executable, '-X', 'utf8', '-B', '-u', '-c', code],
                                       cwd=self.project, env=env, stdout=output, stderr=error,
                                       creationflags=subprocess.CREATE_NO_WINDOW)
        self.addCleanup(lambda: process.kill() if process.poll() is None else None)
        for _ in range(200):
            if log.read_text(encoding='utf-8').strip():
                break
            self.assertIsNone(process.poll(), errors.read_text(encoding='utf-8'))
            time.sleep(.05)
        launch = json.loads(log.read_text(encoding='utf-8').splitlines()[0])
        url = urllib.parse.urlsplit(launch['url'])
        origin = f'{url.scheme}://{url.netloc}'
        token = urllib.parse.parse_qs(url.query)['token'][0]
        def request(path, body=None):
            headers = {'X-Skill-Pilot-Token': token, 'Origin': origin, 'Content-Type': 'application/json'}
            req = urllib.request.Request(origin + path, data=json.dumps(body).encode() if body is not None else None, headers=headers)
            with urllib.request.urlopen(req, timeout=2) as response:
                return json.load(response)
        before = request('/api/status')
        request('/api/heartbeat?page=windows-test', {})
        path = self.project / 'skill_pilot/web/server.py'
        content = path.read_text(encoding='utf-8')
        needle = "'version': self.server.code_version,"
        self.assertIn(needle, content)
        path.write_text(content.replace(needle, "'windows_test_reloaded': True, " + needle), encoding='utf-8')
        self.assertTrue(request('/api/runtime/refresh', {})['changed'])
        for _ in range(200):
            self.assertIsNone(process.poll(), errors.read_text(encoding='utf-8'))
            try:
                after = request('/api/status')
                if after.get('windows_test_reloaded'):
                    break
            except OSError:
                pass
            time.sleep(.05)
        else:
            self.fail('refresh did not load new Python: ' + errors.read_text(encoding='utf-8'))
        self.assertEqual(before['pid'], after['pid'])
        self.assertNotEqual(before['version'], after['version'])
        self.assertTrue(request('/api/heartbeat?page=windows-test', {})['ok'])
        process.terminate()
        process.wait(timeout=10)


if __name__ == '__main__':
    unittest.main()
