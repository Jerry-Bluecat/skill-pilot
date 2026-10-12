"""Synthetic dashboard: hold a WAL write transaction until browser acceptance releases it."""
import json
from pathlib import Path
import sys
import threading
import time
from unittest.mock import patch

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT))
from tests.test_usage_lock import UsageLockTests
from skill_pilot import usage
from skill_pilot.scan import scan
from skill_pilot.web.server import Dashboard

fixture = UsageLockTests()
fixture.setUp()
fixture.log('b.jsonl', 'grilling')
control = fixture.home / 'release-scan'
original = usage.Ledger.scan

def held_scan(ledger, path, agent, names):
    result = original(ledger, path, agent, names)
    if path.name == 'b.jsonl':
        deadline = time.monotonic() + 180
        while not control.exists():
            if time.monotonic() > deadline:
                raise OSError('browser acceptance did not release scan')
            time.sleep(.05)
    return result

with patch.object(usage.Ledger, 'scan', held_scan):
    server = Dashboard(scan(fixture.home))
    runtime = {'url': server.url, 'home': str(fixture.home), 'release': str(control),
               'database': str(fixture.database)}
    (PROJECT / 'work/fix-usage-lock-ui-runtime.json').write_text(json.dumps(runtime))
    print('模拟看板已就绪；第二份记录持有写锁，等待验收释放。', flush=True)
    try:
        server.serve_forever(poll_interval=.05)
    except KeyboardInterrupt:
        pass
    finally:
        control.touch()
        server.server_close()
        fixture.doCleanups()
