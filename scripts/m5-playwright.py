"""Use the already-installed browser CLI; every runtime path is temporary."""
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

runtime = Path('work/m5-browser-runtime.json')
if runtime.exists() and Path(json.loads(runtime.read_text())['directory']).is_dir():
    root = Path(json.loads(runtime.read_text())['directory'])
else:
    root = Path(tempfile.mkdtemp(prefix='skill-pilot-m5-browser-')).resolve()
    (root / 'tmp').mkdir()
    runtime.write_text(json.dumps({'directory':str(root)}))
env = {**os.environ,'HOME':str(root),'XDG_CONFIG_HOME':str(root/'.config'),
       'XDG_CACHE_HOME':str(root/'.cache'),'XDG_STATE_HOME':str(root/'.state'),'TMPDIR':str(root/'tmp'),'CFFIXED_USER_HOME':str(root)}
socket_file = root / 'socket-directory.txt'
if not socket_file.exists():
    socket_file.write_text(tempfile.mkdtemp(prefix='sp-m5-socket-',dir='/tmp'))
env['PWTEST_SOCKETS_DIR'] = socket_file.read_text()
args = sys.argv[1:]
if args == ['open']:
    args = ['open',json.loads(Path('work/m5-ui-runtime.json').read_text())['url'],'--browser','chrome']
command = ['node','/Users/j/.npm/_npx/31e32ef8478fbf80/node_modules/@playwright/cli/playwright-cli.js','-s=skill-pilot-m5',*args]
result = subprocess.run(command,cwd=root,env=env,stdin=subprocess.DEVNULL,capture_output=True,text=True)
print(re.sub(r"token=[A-Za-z0-9_-]+","token=[redacted]",result.stdout),end="")
print(re.sub(r"token=[A-Za-z0-9_-]+","token=[redacted]",result.stderr),end="",file=sys.stderr)
raise SystemExit(result.returncode)
