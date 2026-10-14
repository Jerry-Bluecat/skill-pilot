#!/usr/bin/env python3
"""Manual CLI withdrawal, listing, restoration and undo in a temporary home."""
import json
import os
import subprocess
import sys
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT))
from tests.test_cleanup import CleanupTests
from skill_pilot.sources import github

fixture = CleanupTests()
fixture.setUp()
home = fixture.home
try:
    env = {**os.environ, 'SKILL_PILOT_HOME': str(home), 'PYTHONDONTWRITEBYTECODE': '1'}
    commands = []
    def cli(*args):
        result = subprocess.run([sys.executable, '-m', 'skill_pilot', *args, '--json'],
            env=env, cwd=PROJECT, stdin=subprocess.DEVNULL, capture_output=True, text=True, check=True, timeout=30)
        commands.append(' '.join(args))
        return json.loads(result.stdout)
    before = fixture.fingerprint()
    assert cli('cleanup', '--list')['withdrawn'] == []
    assert cli('cleanup', 'dsh-only')['skills'] == ['dsh-only']
    assert fixture.fingerprint() == before
    commits = int(github.git(home/'.skill-pilot/store', 'rev-list', '--count', 'HEAD'))
    cleaned = cli('cleanup', 'dsh-only', '--yes')
    assert int(github.git(home/'.skill-pilot/store', 'rev-list', '--count', 'HEAD')) == commits+1
    assert [s['name'] for s in cli('cleanup', '--list')['withdrawn']] == ['dsh-only']
    withdrawn = fixture.fingerprint()
    restored = cli('restore-withdrawn', 'dsh-only')
    cli('undo', restored['id'])
    assert fixture.fingerprint() == withdrawn
    cli('undo', cleaned['id'])
    assert fixture.fingerprint() == before
    print(json.dumps({'commands': commands, 'withdrawn': ['dsh-only'], 'preview_readonly': True,
        'one_commit_per_withdrawal': True, 'withdrawn_list_verified': True,
        'restore_undo_exact': True, 'cleanup_undo_exact': True}, ensure_ascii=False, indent=2))
finally:
    fixture.doCleanups()
