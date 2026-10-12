"""CLI-only staged installation; official archives never run an installer."""
import hashlib
import io
import json
import os
import re
import shutil
import subprocess
import tarfile
import tempfile
import time
import urllib.parse
import urllib.request
from pathlib import Path

from ..scan import metadata
from ..store import guard
from .github import safe_skill

CLI = '/Users/j/.local/bin/lark-cli'
CLI_PATHS = ['.local/lib/node_modules/@larksuite/cli', '.local/bin/lark-cli']


def check(timeout=60):
    try:
        result = subprocess.run([CLI, 'update', '--check', '--json'], capture_output=True, text=True, timeout=timeout)
        data = json.loads(result.stdout)
    except (OSError, ValueError, subprocess.TimeoutExpired) as error:
        raise ValueError('飞书版本没能查到，请稍后重试。') from error
    if result.returncode or not data.get('ok'):
        raise ValueError('飞书版本没能查到，请稍后重试。')
    return {'available': data.get('action') == 'update_available',
            'current_version': data['current_version'], 'latest_version': data['latest_version'],
            'message': 'lark-cli 有新版（含 28 个飞书技能）' if data.get('action') == 'update_available' else '已是最新',
            'skills_status': data.get('skills_status', {})}


def download(url, timeout=45):
    if not url.startswith('https://open.feishu.cn/lark-cli/skills/'):
        raise ValueError('飞书技能下载地址不属于官方来源。')
    with urllib.request.urlopen(url, timeout=timeout) as response:
        if not response.url.startswith('https://open.feishu.cn/lark-cli/skills/'):
            raise ValueError('飞书技能下载跳转到其他来源，已停止。')
        return response.read()


def prepare(sources, temporary, version, deadline=None):
    result, indexes = {}, {}
    def get(url):
        if deadline is None: return download(url)
        left = deadline - time.monotonic()
        if left <= 0: raise ValueError('飞书检查超时，可以稍后重试。')
        return download(url, timeout=min(45, left))
    for name, source in sources.items():
        index_url = source['base_url'].rstrip('/') + '/.well-known/agent-skills/index.json'
        if index_url not in indexes:
            indexes[index_url] = {s['name']: s for s in json.loads(get(index_url))['skills']}
        entry = indexes[index_url].get(name)
        if not entry or entry.get('type') != 'archive' or not re.fullmatch(r'sha256:[0-9a-fA-F]{64}', entry.get('digest', '')):
            raise ValueError('飞书官方技能清单不完整，已停止更新。')
        url = urllib.parse.urljoin(index_url, entry['url'])
        archive = get(url)
        if 'sha256:' + hashlib.sha256(archive).hexdigest() != entry['digest'].lower():
            raise ValueError('飞书技能包校验没通过，已停止更新。')
        destination = Path(temporary) / ('lark-' + name)
        destination.mkdir()
        try:
            with tarfile.open(fileobj=io.BytesIO(archive)) as bundle:
                bundle.extractall(destination, filter='data')
        except tarfile.TarError as error:
            raise ValueError('飞书技能包内容不安全或未读完整，已停止更新。') from error
        safe_skill(destination)
        if metadata((destination / 'SKILL.md').read_text()).get('name') != name:
            raise ValueError('飞书技能包的名称与清单不一致，已停止更新。')
        result[name] = {'path': str(destination), 'digest': entry['digest'], 'url': url, 'cli_version': version}
    return result


def install_cli(home, version, checked):
    guard(home / '.skill-pilot', home)
    if not re.fullmatch(r'\d+\.\d+\.\d+(?:-[A-Za-z0-9.-]+)?', version):
        raise ValueError('飞书版本号不正确。')
    # Package lifecycle code can only see this isolated home and prefix. It
    # never receives an agent root or the user's npm configuration.
    with tempfile.TemporaryDirectory(prefix='skill-pilot-lark-install-') as temporary:
        root = Path(temporary)
        env = {k: v for k, v in os.environ.items() if not k.lower().startswith(('npm_config_', 'pnpm_'))}
        env.update(HOME=str(root), npm_config_prefix=str(root / 'prefix'), npm_config_cache=str(root / 'cache'),
                   npm_config_userconfig=os.devnull, npm_config_globalconfig=os.devnull,
                   XDG_CONFIG_HOME=str(root / '.config'), XDG_STATE_HOME=str(root / '.state'))
        result = subprocess.run(['npm', 'install', '-g', '@larksuite/cli@' + version],
                                cwd=root, env=env, stdin=subprocess.DEVNULL, capture_output=True, timeout=300)
        if result.returncode:
            raise ValueError('飞书工具安装没有完成，技能保持原样。')
        package = root / 'prefix/lib/node_modules/@larksuite/cli'
        if json.loads((package / 'package.json').read_text())['version'] != version:
            raise ValueError('飞书工具版本没有核对通过，技能保持原样。')
        target = checked(home / CLI_PATHS[0])
        if target.exists():
            shutil.rmtree(target)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(package, target, symlinks=True)
        entry = checked(home / CLI_PATHS[1])
        entry.parent.mkdir(parents=True, exist_ok=True)
        if entry.exists() or entry.is_symlink():
            entry.unlink()
        entry.symlink_to('../lib/node_modules/@larksuite/cli/scripts/run.js')
