"""Run the full suite while another isolated launcher holds its instance lock."""
import hashlib
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import time
import urllib.request

project = Path(__file__).resolve().parents[1]
with tempfile.TemporaryDirectory(prefix='skill-pilot-timeout-suite-') as temporary:
    root = Path(temporary)
    for name in ('observer-home', 'observer-runtime', 'suite-home', 'suite-runtime'):
        (root / name).mkdir()
    env = {**os.environ, 'PYTHONDONTWRITEBYTECODE': '1'}
    observer_env = {**env, 'HOME': str(root / 'observer-home'),
                    'SKILL_PILOT_HOME': str(root / 'observer-home'), 'TMPDIR': str(root / 'observer-runtime')}
    observer_log = root / 'observer.log'
    with observer_log.open('w') as output:
        observer = subprocess.Popen([sys.executable, '-u', '-c',
            'from unittest.mock import patch; from skill_pilot.web import server; '
            'server.webbrowser.open=lambda url: True; server.run(json_output=True)'],
            cwd=project, env=observer_env, stdin=subprocess.DEVNULL, stdout=output, stderr=subprocess.STDOUT)
    suite = None
    try:
        deadline = time.monotonic() + 15
        while not observer_log.read_text():
            if observer.poll() is not None or time.monotonic() > deadline:
                raise RuntimeError('模拟看板没有启动：' + observer_log.read_text())
            time.sleep(.05)
        state = json.loads(observer_log.read_text().splitlines()[0])
        origin, token = state['url'].split('/?token=')
        def request(path, body=None):
            call = urllib.request.Request(origin + path, data=body,
                headers={'X-Skill-Pilot-Token': token, 'Origin': origin})
            with urllib.request.urlopen(call, timeout=2) as response:
                return json.load(response)
        identity = hashlib.sha256(str((root / 'observer-home').resolve()).encode()).hexdigest()[:16]
        lock = root / 'observer-runtime' / f'skill-pilot-{os.getuid()}-{identity}.lock'
        before = lock.read_bytes()
        assert request('/api/status')['pid'] == observer.pid
        command = [sys.executable, '-m', 'unittest', 'discover', '-q']
        started = time.monotonic()
        with (project / 'work/fix-update-timeout-tests.txt').open('w') as output:
            suite = subprocess.Popen(command, cwd=project, stdin=subprocess.DEVNULL, stdout=output,
                stderr=subprocess.STDOUT, env={**env, 'HOME': str(root / 'suite-home'),
                'SKILL_PILOT_HOME': str(root / 'suite-home'), 'TMPDIR': str(root / 'suite-runtime')})
        while suite.poll() is None:
            request('/api/heartbeat', b'{}')
            if time.monotonic() - started > 180:
                raise RuntimeError('全量单测超过三分钟，停止本轮模拟进程。')
            time.sleep(.25)
        result = {'command': 'PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -q',
                  'exit_code': suite.returncode, 'seconds': round(time.monotonic() - started, 3),
                  'other_dashboard_alive': observer.poll() is None and request('/api/status')['pid'] == observer.pid,
                  'other_dashboard_lock_unchanged': lock.read_bytes() == before,
                  'isolated_home_lock_and_random_port': True}
        (project / 'work/fix-update-timeout-tests.json').write_text(json.dumps(result, indent=2) + '\n')
        print(json.dumps(result), flush=True)
        if suite.returncode or not result['other_dashboard_alive'] or not result['other_dashboard_lock_unchanged']:
            raise SystemExit(1)
    finally:
        if suite is not None and suite.poll() is None:
            suite.terminate(); suite.wait(timeout=5)
        if observer.poll() is None:
            observer.send_signal(signal.SIGINT)
            observer.wait(timeout=5)
