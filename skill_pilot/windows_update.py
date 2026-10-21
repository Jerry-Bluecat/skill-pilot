"""Carry the installed Windows compatibility changes across official updates."""
import json
import os
from pathlib import Path
import subprocess
import tempfile

RECORD = '.skill-pilot-windows.json'


def entries(home):
    return [Path(home) / '.local/bin/skill-pilot.cmd',
            Path(home) / 'AppData/Roaming/Microsoft/Windows/Start Menu/Programs/Skill Pilot.lnk']


def prepare(project, candidate):
    """Merge only recorded compatibility changes; conflicts leave installation intact."""
    from .self_update import safe_path
    record = json.loads((project / RECORD).read_text(encoding='utf-8'))
    baseline = {}
    for name, base in record['base'].items():
        local_path = safe_path(project, name)
        remote_path = safe_path(candidate, name)
        local = local_path.read_text(encoding='utf-8')
        remote = remote_path.read_text(encoding='utf-8') if remote_path.exists() else None
        if base is None:
            if remote is not None and remote != local:
                raise ValueError('新版与 Windows 适配文件重名，已保留当前版本：' + name)
            merged = local
        elif remote is None:
            raise ValueError('新版删除了 Windows 适配需要的文件，已保留当前版本：' + name)
        elif local == base or local == remote:
            merged = remote
        elif remote == base:
            merged = local
        else:
            with tempfile.TemporaryDirectory(prefix='sp-windows-merge-') as temporary:
                paths = [Path(temporary) / n for n in ('local', 'base', 'remote')]
                for path, content in zip(paths, (local, base, remote)):
                    path.write_text(content, encoding='utf-8', newline='\n')
                result = subprocess.run(['git', 'merge-file', '-p', *map(str, paths)],
                                        capture_output=True, timeout=30,
                                        creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
                if result.returncode:
                    raise ValueError('新版与 Windows 适配有冲突，已保留当前版本：' + name)
                merged = result.stdout.decode('utf-8')
        remote_path.parent.mkdir(parents=True, exist_ok=True)
        remote_path.write_text(merged, encoding='utf-8', newline='\n')
        if merged != remote:
            baseline[name] = remote
    (candidate / RECORD).write_text(json.dumps({'base': baseline}, ensure_ascii=False), encoding='utf-8')


def install(project, home):
    import sys
    project, home = Path(project).resolve(), Path(home).resolve()
    if sys.version_info < (3, 12):
        raise ValueError('Windows 版需要 Python 3.12 或更高版本。')
    cli, shortcut = entries(home)
    cli.parent.mkdir(parents=True, exist_ok=True)
    shortcut.parent.mkdir(parents=True, exist_ok=True)
    python = Path(sys.executable).with_name('python.exe')
    pythonw = python.with_name('pythonw.exe')
    if not python.is_file() or not pythonw.is_file():
        raise ValueError('找不到 Python 的 Windows 启动入口。')
    if cli.exists() and 'SkillPilot Windows launcher' not in cli.read_text(encoding='utf-8-sig'):
        raise ValueError('命令入口已被其他程序使用，原入口保持不变。')
    command = ('@echo off\nrem SkillPilot Windows launcher\nset PYTHONUTF8=1\n'
               f'pushd "{project}"\n"{python}" -X utf8 -B -m skill_pilot %*\n'
               'set result=%errorlevel%\npopd\nexit /b %result%\n')
    temporary = cli.with_suffix('.cmd.tmp')
    temporary.write_text(command, encoding='utf-8', newline='\r\n')
    temporary.replace(cli)
    env = {**os.environ, 'SP_SHORTCUT': str(shortcut), 'SP_PYTHONW': str(pythonw),
           'SP_PROJECT': str(project), 'SP_LAUNCHER': str(project / 'scripts/launch-windows.py')}
    script = '''$ErrorActionPreference = 'Stop'
$shell = New-Object -ComObject WScript.Shell
$link = $shell.CreateShortcut($env:SP_SHORTCUT)
$link.TargetPath = $env:SP_PYTHONW
$link.Arguments = '-X utf8 -B "' + $env:SP_LAUNCHER + '"'
$link.WorkingDirectory = $env:SP_PROJECT
$link.Description = 'Skill Pilot'
$link.Save()
'''
    result = subprocess.run(['powershell.exe', '-NoProfile', '-NonInteractive', '-Command', script],
                            env=env, capture_output=True, timeout=20,
                            creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    if result.returncode:
        raise ValueError('开始菜单入口没能更新，请检查目录权限。')
    from .self_update import record_installation
    record_installation(project)
