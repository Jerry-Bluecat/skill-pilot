#!/usr/bin/env python3
"""Exercise the manual cleanup API using make-fake-home and synthetic data only."""
import argparse
import hashlib
import importlib.util
import json
import os
import select
import signal
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT))
from skill_pilot import operations, store


def verify():
    spec = importlib.util.spec_from_file_location('fake_home', PROJECT/'scripts/make-fake-home.py')
    fake = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(fake)
    with tempfile.TemporaryDirectory(prefix='skill-pilot-remove-usage-') as temporary:
        root = Path(temporary).resolve()
        source, home = root/'source', root/'home'
        for name in ['candidate', 'parent', 'dep']:
            path = source/'.codex/skills'/name
            path.mkdir(parents=True)
            (path/'SKILL.md').write_text(f'---\nname: {name}\ndescription: 示例技能\n---\n正文\n')
        (source/'.codex/config.toml').write_text('[skills]\nconfig=[]\n')
        legacy = source/'.skill-pilot/usage.sqlite'
        legacy.parent.mkdir()
        legacy.write_bytes(b'synthetic legacy database')
        fake.make_fake_home(source, home)
        assert not (home/'.skill-pilot/usage.sqlite').exists()
        store.apply(store.preview(home)['plan_id'], home)
        registry = operations.load(home)[1]
        registry['skills']['parent']['requires'] = ['dep']
        (home/'.skill-pilot/registry.json').write_text(json.dumps(registry))
        operations._commit(home, registry, ['parent'], [], 'fixture dependency')
        (home/'.skill-pilot/labels.json').write_text(json.dumps({'groups': [
            {'name': '示例', 'skills': {'parent': ['多智能体分派', '分派任务'], 'dep': ['营销技能路由', '选择技能']}}]}))
        environment = {**os.environ, 'SKILL_PILOT_HOME': str(home), 'BROWSER': '/usr/bin/true',
                       'PYTHONDONTWRITEBYTECODE': '1'}
        process = subprocess.Popen([sys.executable, '-m', 'skill_pilot', 'ui', '--json'], cwd=PROJECT,
                    env=environment, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        identity = hashlib.sha256(str(home).encode()).hexdigest()[:16]
        lock = Path(tempfile.gettempdir())/f'skill-pilot-{os.getuid()}-{identity}.lock'
        calls = []
        try:
            assert select.select([process.stdout], [], [], 15)[0], '模拟看板没有及时启动'
            runtime = json.loads(process.stdout.readline())
            assert runtime['pid'] == process.pid
            from urllib.parse import parse_qs, urlsplit
            url = urlsplit(runtime['url'])
            origin = f'http://127.0.0.1:{url.port}'
            headers = {'X-Skill-Pilot-Token': parse_qs(url.query)['token'][0],
                       'Origin': origin, 'Content-Type': 'application/json'}
            def request(path, body=None, status=200):
                call = urllib.request.Request(origin+path, headers=headers,
                    data=json.dumps(body).encode() if body is not None else None)
                try:
                    with urllib.request.urlopen(call, timeout=15) as response:
                        actual, result = response.status, json.load(response)
                except urllib.error.HTTPError as error:
                    actual, result = error.code, json.load(error)
                calls.append({'method': call.get_method(), 'path': path, 'status': actual})
                assert actual == status, result
                return result
            table = request('/api/table')
            agents = request('/api/agents')
            assert all('last_used' not in row for row in table['skills'])
            assert all(not {'usage_available', 'usage_note'} & row.keys() for row in table['agents']+agents['managed'])
            listing = request('/api/cleanup')
            assert set(listing) == {'revision', 'write_allowed', 'withdrawn'} and not listing['withdrawn']
            preview = request('/api/cleanup/preview', {'skills': ['dep']})
            assert preview['dependency_warnings'] == ['「多智能体分派」还要用「营销技能路由」，撤下后它可能用不了。']
            body = {'skills': ['dep'], 'revision': preview['revision']}
            assert request('/api/cleanup/apply', body)['needs_confirmation'] is True
            request('/api/cleanup/preview', {'skills': ['missing']}, 400)
            request('/api/cleanup/apply', body | {'revision': 'stale', 'confirmed': True}, 409)
            assert request('/api/table')['revision'] == table['revision']
            applied = request('/api/cleanup/apply', body | {'confirmed': True})
            assert applied['id'] and applied['message'] == '撤下了 1 个技能'
            withdrawn = request('/api/cleanup')
            row = withdrawn['withdrawn'][0]
            assert row['name'] == 'dep' and row['previous_agents'] == ['codex'] and row['withdrawn_at']
            assert (home/'.skill-pilot/store/dep/SKILL.md').is_file() and not (home/'.codex/skills/dep').exists()
            undo = request('/api/undo', {'id': applied['id'], 'revision': withdrawn['revision'], 'confirmed': True})
            assert undo['id'] and request('/api/table')['revision'] == table['revision']
            preview = request('/api/cleanup/preview', {'skills': ['dep']})
            request('/api/cleanup/apply', {'skills': ['dep'], 'revision': preview['revision'], 'confirmed': True})
            withdrawn = request('/api/cleanup')
            restored = request('/api/withdrawn/restore', {'skills': ['dep'], 'revision': withdrawn['revision'], 'confirmed': True})
            assert restored['restored'] == ['dep'] and (home/'.codex/skills/dep').is_symlink()
            assert not request('/api/cleanup')['withdrawn']
            request('/api/usage', status=404)
            request('/api/usage-progress', status=404)
            assert legacy.read_bytes() == b'synthetic legacy database'
            assert not (home/'.skill-pilot/usage.sqlite').exists()
            result = {'synthetic_source': True, 'built_with_make_fake_home': True, 'browser_disabled': True,
                'legacy_database_skipped': True, 'cleanup_undo_exact': True, 'restoration_verified': True,
                'dependency_example': preview['dependency_warnings'], 'calls': calls,
                'fields': {'table': sorted(table), 'table.skills[]': sorted(table['skills'][0]),
                    'table.agents[]': sorted(table['agents'][0]), 'agents': sorted(agents),
                    'agents.managed[]': sorted(agents['managed'][0]), 'cleanup': sorted(listing),
                    'cleanup.preview': sorted(preview), 'cleanup.apply': sorted(applied),
                    'cleanup.withdrawn[]': sorted(row), 'undo': sorted(undo), 'withdrawn.restore': sorted(restored)}}
        finally:
            if process.poll() is None:
                process.send_signal(signal.SIGINT)
            try:
                process.communicate(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.communicate(timeout=10)
            lock.unlink(missing_ok=True)
        assert process.returncode == 0, '模拟看板没有正常结束'
        result['own_process_stopped'] = True
        return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='验证移除用量后的后端接口，仅使用临时模拟数据')
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    result = json.dumps(verify(), ensure_ascii=False, indent=2)+'\n'
    if args.output:
        args.output.write_text(result)
    print(result, end='')
