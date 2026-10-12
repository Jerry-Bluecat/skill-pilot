"""Isolated dashboard with one held skill and one repository timeout."""
import json
from pathlib import Path
import shutil
import subprocess
import sys
import time
from unittest.mock import patch

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT))
from tests.test_update_check import UpdateCheckTests
from skill_pilot import operations
from skill_pilot.scan import scan
from skill_pilot.sources import github
from skill_pilot.sources.update_github import Reader
from skill_pilot.web.server import Dashboard

fixture = UpdateCheckTests()
fixture.setUp()
fixture.add_skill()
fixture.add_skill('archived', assigned=False)
fixture.add_skill('zslow')
fixture.fixture.modified()
registry = operations.load(fixture.home)[1]
registry['skills']['zslow']['source'] = {'source': 'https://github.com/example/slow'}
(fixture.home / '.skill-pilot/registry.json').write_text(json.dumps(registry))
release = fixture.home / 'release-scan'
history_calls = fixture.home / 'history-calls'
history_calls.write_text('0')
original_current, original_inspect, original_api = Reader.current, Reader.inspect, github.api

def held(reader, source, commit=None, tree=None):
    if source['path'] == 'zsecond':
        deadline = time.monotonic() + 120
        while not release.exists():
            if time.monotonic() > deadline: raise ValueError('模拟扫描等待超时')
            time.sleep(.02)
    return original_current(reader, source, commit, tree)

def api(endpoint, timeout=45):
    if '/slow/' in endpoint:
        try:
            subprocess.run(['python3', '-c', 'import time; time.sleep(10)'], timeout=min(timeout, 1.2), capture_output=True)
        except subprocess.TimeoutExpired:
            raise ValueError('这个仓库检查超时，可以稍后重试。')
    return original_api(endpoint, timeout=timeout)

def inspect(reader, source, local):
    history_calls.write_text(str(int(history_calls.read_text()) + 1))
    time.sleep(.5)
    return original_inspect(reader, source, local)

with patch.object(Reader, 'current', held), patch.object(Reader, 'inspect', inspect), patch.object(github, 'api', api):
    dashboard = Dashboard(scan(fixture.home))
    (PROJECT / 'work/fix-update-check-ui-runtime.json').write_text(json.dumps({
        'url': dashboard.url, 'home': str(fixture.home), 'release': str(release), 'history_calls': str(history_calls)}))
    print('模拟看板已就绪；一个技能等待释放，另一仓库会超时。', flush=True)
    try: dashboard.serve_forever(poll_interval=.02)
    except KeyboardInterrupt: pass
    finally:
        release.touch(); dashboard.server_close()
        for review in dashboard.update_reviews.values():
            shutil.rmtree(review['temporary'], ignore_errors=True)
        fixture.doCleanups()
