from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from datetime import datetime, timezone
import json
from pathlib import Path
import sqlite3
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.request
from unittest.mock import patch

from tests import set_up_home
from skill_pilot import operations, store, usage
from skill_pilot.web.server import Dashboard


class UsageLockTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix='skill-pilot-usage-lock-')
        self.addCleanup(self.temporary.cleanup)
        set_up_home(self, self.temporary.name)
        for name in ['grill-me', 'grilling', 'other']:
            path = self.home / '.codex/skills' / name
            path.mkdir(parents=True)
            (path / 'SKILL.md').write_text(f'---\nname: {name}\ndescription: test\n---\nbody\n')
        store.apply(store.preview(self.home)['plan_id'], self.home)
        self.database = self.home / '.skill-pilot/usage.sqlite'
        self.changes = [{'skill': 'grill-me', 'agent': 'claude', 'enabled': True}]
        self.sessions = self.home / '.codex/sessions'
        self.sessions.mkdir(parents=True)
        self.date = '2026-10-10T10:00:00Z'
        self.now = datetime(2026, 10, 11, tzinfo=timezone.utc)
        self.log('a.jsonl', 'grill-me')

    def log(self, filename, name):
        row = {'timestamp': self.date, 'payload': {'type': 'function_call', 'name': 'exec_command',
                'arguments': json.dumps({'cmd': f'cat ~/.agents/skills/{name}/SKILL.md'})}}
        (self.sessions / filename).write_text(json.dumps(row) + '\n')

    def seed(self):
        return usage.report(self.home, now=self.now)

    def assert_pending_assignment(self):
        start = time.monotonic()
        table = operations.table(self.home)
        preview = operations.preview_assign(self.changes, self.home)
        self.assertLess(time.monotonic() - start, 2)
        self.assertIn('claude', preview['assignments']['grilling'])
        row = next(s for s in table['skills'] if s['name'] == 'grill-me')
        self.assertIn('正在统计', row['last_used']['codex'])
        self.assertEqual(row['last_used']['antigravity'], '统计不到')

    def test_long_exclusive_lock_does_not_block_table_preview_or_apply(self):
        self.seed()
        with closing(sqlite3.connect(self.database)) as writer:
            writer.execute('PRAGMA journal_mode=DELETE')
            writer.execute('BEGIN EXCLUSIVE')
            try:
                self.assert_pending_assignment()
                applied = operations.apply_assign(self.changes, home=self.home)
                self.assertFalse(applied.get('needs_confirmation'))
                self.assertIn('claude', operations.load(self.home)[1]['skills']['grilling']['assigned_agents'])
            finally:
                writer.rollback()
        self.assertEqual(usage.recorded(self.database)['grill-me']['codex'], '2026-10-10')

    def test_corrupt_missing_and_incomplete_ledger_do_not_break_assignment(self):
        self.assert_pending_assignment()
        self.database.write_bytes(b'not a sqlite database')
        self.assert_pending_assignment()
        self.assertEqual(self.database.read_bytes(), b'not a sqlite database')
        self.database.unlink()
        self.seed()
        with closing(sqlite3.connect(self.database)) as writer:
            writer.execute('UPDATE settings SET value="0" WHERE name="complete"')
            writer.commit()
        self.assert_pending_assignment()

    def test_wal_readers_see_committed_data_while_writer_holds_transaction(self):
        self.seed()
        with closing(sqlite3.connect(self.database)) as writer:
            self.assertEqual(writer.execute('PRAGMA journal_mode').fetchone()[0], 'wal')
            writer.execute('BEGIN IMMEDIATE')
            writer.execute('UPDATE calls SET last_used="2026-10-11T10:00:00+00:00"')
            self.assertEqual(usage.recorded(self.database)['grill-me']['codex'], '2026-10-10')
            self.assertIn('claude', operations.preview_assign(self.changes, self.home)['assignments']['grilling'])
            writer.commit()
        self.assertEqual(usage.recorded(self.database)['grill-me']['codex'], '2026-10-11')

    def test_per_file_commit_progress_and_no_partial_dates(self):
        self.log('b.jsonl', 'grilling')
        reached, release = threading.Event(), threading.Event()
        progress = {}
        original = usage.Ledger.scan
        def paused(ledger, path, agent, names):
            result = original(ledger, path, agent, names)
            if path.name == 'b.jsonl':
                reached.set()
                if not release.wait(5):
                    raise AssertionError('test scan not released')
            return result
        with patch.object(usage.Ledger, 'scan', paused), ThreadPoolExecutor() as pool:
            task = pool.submit(usage.report, self.home, None, self.now, progress)
            try:
                self.assertTrue(reached.wait(5))
                self.assertEqual(progress, {'running': True, 'done': 1, 'total': 2})
                with closing(sqlite3.connect(self.database, timeout=.05)) as reader:
                    self.assertEqual(reader.execute('SELECT count(*) FROM scans').fetchone()[0], 1)
                    self.assertEqual(reader.execute('SELECT skill FROM calls').fetchone()[0], 'grill-me')
                self.assert_pending_assignment()
            finally:
                release.set()
            result = task.result(timeout=5)
        self.assertEqual(progress, {'running': False, 'done': 2, 'total': 2})
        self.assertEqual(result['skills'][1]['last_used']['codex'][:10], '2026-10-10')
        self.assertEqual(usage.recorded(self.database)['grilling']['codex'], '2026-10-10')

    def test_failed_scan_is_not_marked_complete(self):
        with patch.object(usage.Ledger, 'scan', side_effect=OSError('interrupted')):
            with self.assertRaises(OSError):
                self.seed()
        self.assertIsNone(usage.recorded(self.database))
        self.assert_pending_assignment()

    def test_cleanup_waits_and_corrupt_usage_has_human_error(self):
        server = Dashboard({'home': str(self.home)})
        thread = threading.Thread(target=server.serve_forever, kwargs={'poll_interval': .05})
        thread.start()
        def get(path):
            request = urllib.request.Request(server.origin + path, headers={'X-Skill-Pilot-Token': server.token})
            try:
                with urllib.request.urlopen(request, timeout=2) as response:
                    return response.status, json.load(response)
            except urllib.error.HTTPError as error:
                return error.code, json.load(error)
        try:
            with server.usage_lock:
                status, result = get('/api/cleanup')
                self.assertEqual(status, 409)
                self.assertIn('完成后再生成名单', result['error'])
                self.assertNotIn('candidates', result)
                self.assertEqual(get('/api/table')[0], 200)
                self.assertEqual(get('/api/usage-progress')[0], 200)
                status, result = get('/api/usage')
                self.assertEqual(status, 409)
                self.assertTrue(result['retry'])
            self.database.write_bytes(b'broken')
            self.assertEqual(get('/api/table')[0], 200)
            status, result = get('/api/cleanup')
            self.assertEqual(status, 409)
            self.assertIn('完成后再生成名单', result['error'])
            self.assertNotIn('candidates', result)
            status, result = get('/api/usage')
            self.assertEqual(status, 409)
            self.assertIn('技能分配仍可照常操作', result['error'])
            self.assertFalse(result['retry'])
            self.database.unlink()
            self.seed()
            with closing(sqlite3.connect(self.database)) as writer:
                writer.execute('PRAGMA journal_mode=DELETE')
                writer.execute('BEGIN EXCLUSIVE')
                status, result = get('/api/usage')
                self.assertEqual(status, 409)
                self.assertTrue(result['retry'])
                self.assertEqual(get('/api/table')[0], 200)
                writer.rollback()
            self.assertEqual(get('/api/usage')[0], 200)
        finally:
            server.shutdown()
            thread.join()
            server.server_close()


if __name__ == '__main__':
    unittest.main()
