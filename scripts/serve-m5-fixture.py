"""Isolated dashboard acceptance with actual log parsers and cleanup operations."""
import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from tests.test_cleanup import CleanupTests
from skill_pilot.scan import scan
from skill_pilot.web.server import Dashboard

fixture=CleanupTests();fixture.setUp();home=fixture.home
p=home/'.claude/projects/test/session.jsonl';p.parent.mkdir(parents=True)
p.write_text('\n'.join(json.dumps({'type':'assistant','timestamp':fixture.now.isoformat(),'sessionId':'test','message':{'content':[{'type':'tool_use','name':'Skill','input':{'skill':name}}]}}) for name in ['parent','recent'])+'\n')
p=home/'.codex/sessions/test.jsonl';p.parent.mkdir(parents=True);p.write_text(json.dumps({'timestamp':fixture.now.isoformat(),'type':'session_meta','payload':{'id':'test'}})+'\n')
p=home/'.dsh/sessions/project/test/session.v4.jsonl.zstd';p.parent.mkdir(parents=True)
p.write_bytes(subprocess.run(['node','-e',"const z=require('node:zlib');process.stdout.write(z.zstdCompressSync(Buffer.from(process.argv[1])));",json.dumps({'type':'session','id':'test','createdAt':fixture.now.timestamp()*1000})+'\n'],capture_output=True,check=True).stdout)
# Informational dependency suggestion that must not block the UI.
(home/'.skill-pilot/store/young/SKILL.md').write_text((home/'.skill-pilot/store/young/SKILL.md').read_text()+'optional candidate\n')
before=fixture.fingerprint()
server=Dashboard(scan(home));Path('work/m5-ui-runtime.json').write_text(json.dumps({'home':str(home),'url':server.url}))
print('模拟看板已启动',flush=True)
try:server.serve_forever(poll_interval=.1)
except KeyboardInterrupt:pass
finally:
 server.server_close();Path('work/m5-ui-final-state.json').write_text(json.dumps({'undo_exact':before==fixture.fingerprint()}));fixture.doCleanups()
