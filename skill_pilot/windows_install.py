"""Install Windows desktop and command-line entry points for the current user."""
import os
from pathlib import Path
import subprocess
import shutil


def entries(home):
    return [Path(home) / '.local/bin/skill-pilot.cmd',
            Path(home) / 'AppData/Roaming/Microsoft/Windows/Start Menu/Programs/Skill Pilot.lnk']


def install(project, home):
    import sys
    project, home = Path(project).resolve(), Path(home).resolve()
    if sys.version_info < (3, 12):
        raise ValueError('Windows 版需要 Python 3.12 或更高版本。')
    from .environment import tool_environment
    tools = tool_environment(home)
    git = shutil.which('git', path=tools['PATH'])
    if not git:
        raise ValueError('找不到 Git，请先安装 Git for Windows，再重试。')
    cli, shortcut = entries(home)
    cli.parent.mkdir(parents=True, exist_ok=True)
    shortcut.parent.mkdir(parents=True, exist_ok=True)
    python = Path(sys.executable).with_name('python.exe')
    pythonw = python.with_name('pythonw.exe')
    if not python.is_file() or not pythonw.is_file():
        raise ValueError('找不到 Python 的 Windows 启动入口。')
    if cli.exists() and 'SkillPilot Windows launcher' not in cli.read_text(encoding='utf-8-sig'):
        raise ValueError('命令入口已被其他程序使用，原入口保持不变。')
    search_path = os.pathsep.join(dict.fromkeys([str(home / '.local/bin'), str(python.parent), str(Path(git).parent)]))
    command = ('@echo off\nrem SkillPilot Windows launcher\nchcp 65001 >nul\nset PYTHONUTF8=1\n'
               f'set "PATH={search_path};%PATH%"\n'
               f'pushd "{project}"\n"{python}" -X utf8 -B -m skill_pilot %*\n'
               'set result=%errorlevel%\npopd\nexit /b %result%\n')
    temporary = cli.with_suffix('.cmd.tmp')
    temporary.write_text(command, encoding='utf-8', newline='\r\n')
    temporary.replace(cli)
    env = {**tools, 'SP_SHORTCUT': str(shortcut), 'SP_PYTHONW': str(pythonw),
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
        raise ValueError('开始菜单入口没能更新，请检查目录权限。') from subprocess.CalledProcessError(
            result.returncode, ['powershell.exe'], stderr=result.stderr)
    from .self_update import record_installation
    record_installation(project)
