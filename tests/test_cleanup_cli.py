import json
import os
import subprocess
import sys
import unittest

from skill_pilot import store
from tests import test_cleanup


class CleanupCliTests(unittest.TestCase):
    def setUp(self):
        self.fixture = test_cleanup.CleanupTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)

    def command(self, *args):
        return subprocess.run([sys.executable, '-m', 'skill_pilot', *args], cwd=store.PROJECT,
                env={**os.environ, 'SKILL_PILOT_HOME': str(self.fixture.home), 'PYTHONDONTWRITEBYTECODE': '1'},
                capture_output=True, text=True, timeout=15)

    def json_command(self, *args):
        result = self.command(*args, '--json')
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        return json.loads(result.stdout)

    def test_preview_and_list_do_not_write_and_plain_preview_shows_warnings(self):
        before = self.fixture.fingerprint()
        view = self.json_command('cleanup', 'candidate', 'candidate')
        self.assertEqual(view['skills'], ['candidate'])
        self.assertEqual(view['message'], '从所有 agent 撤下 1 个技能')
        self.assertEqual(self.json_command('cleanup', '--list')['withdrawn'], [])
        result = self.command('cleanup', 'dep')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('「多智能体分派」还要用「营销技能路由」', result.stdout)
        self.assertIn('--yes', result.stdout)
        self.assertEqual(self.fixture.fingerprint(), before)

    def test_manual_batch_restore_and_both_undos(self):
        before = self.fixture.fingerprint()
        result = self.json_command('cleanup', 'candidate', 'unknown', 'candidate', '--yes')
        self.assertEqual(result['message'], '撤下了 2 个技能')
        self.assertEqual([r['name'] for r in self.json_command('cleanup', '--list')['withdrawn']], ['candidate', 'unknown'])
        withdrawn = self.fixture.fingerprint()
        restored = self.json_command('restore-withdrawn', 'candidate', 'unknown')
        self.json_command('undo', restored['id'])
        self.assertEqual(self.fixture.fingerprint(), withdrawn)
        self.json_command('undo', result['id'])
        self.assertEqual(self.fixture.fingerprint(), before)

    def test_invalid_selection_modes_and_removed_options_never_write(self):
        before = self.fixture.fingerprint()
        for args in [('cleanup',), ('cleanup', '--yes'), ('cleanup', '--list', 'candidate'),
                     ('cleanup', '--list', '--yes'), ('cleanup', '--keep', 'candidate'), ('usage',),
                     ('cleanup', 'missing'), ('cleanup', 'unassigned', '--yes'),
                     ('cleanup', 'candidate', 'missing', '--yes')]:
            with self.subTest(args=args):
                self.assertIn(self.command(*args).returncode, [1, 2])
        self.assertEqual(self.fixture.fingerprint(), before)
