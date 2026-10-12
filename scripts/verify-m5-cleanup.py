#!/usr/bin/env python3
"""CLI cleanup / keep / restore / undo against constructed, logged temporary home."""
import json
import os
import subprocess
import sys
from pathlib import Path

PROJECT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(PROJECT))
from tests.test_cleanup import CleanupTests
from skill_pilot.sources import github

fixture=CleanupTests();fixture.setUp();home=fixture.home
try:
 p=home/'.claude/projects/test/only-skills.jsonl';p.parent.mkdir(parents=True)
 p.write_text('\n'.join(json.dumps({'type':'assistant','timestamp':fixture.now.isoformat(),'sessionId':'test',
      'message':{'content':[{'type':'tool_use','name':'Skill','input':{'skill':name}}]}}) for name in ['parent','recent'])+'\n')
 p=home/'.codex/sessions/test.jsonl';p.parent.mkdir(parents=True)
 p.write_text(json.dumps({'timestamp':fixture.now.isoformat(),'type':'session_meta','payload':{'id':'test'}})+'\n')
 p=home/'.dsh/sessions/project/test/session.v4.jsonl.zstd';p.parent.mkdir(parents=True)
 code="const z=require('node:zlib');process.stdout.write(z.zstdCompressSync(Buffer.from(process.argv[1])));"
 p.write_bytes(subprocess.run(['node','-e',code,json.dumps({'type':'session','id':'test','createdAt':fixture.now.timestamp()*1000})+'\n'],capture_output=True,check=True).stdout)
 env={**os.environ,'SKILL_PILOT_HOME':str(home),'HOME':str(home),'CODEX_HOME':str(home/'.codex')}
 commands=[]
 def cli(*args):
  p=subprocess.run([sys.executable,'-m','skill_pilot',*args,'--json'],env=env,cwd=PROJECT,stdin=subprocess.DEVNULL,capture_output=True,text=True,check=True,timeout=60)
  commands.append(' '.join(args));return json.loads(p.stdout)
 before=fixture.fingerprint()
 used=cli('usage');assert used['persistent'] and used['coverage']['dsh']['available']
 view=cli('cleanup','--list');assert {r['name'] for r in view['candidates']}=={'candidate','dsh-only'}
 commits=int(github.git(home/'.skill-pilot/store','rev-list','--count','HEAD'))
 cleaned=cli('cleanup','--yes','--keep','candidate')
 assert int(github.git(home/'.skill-pilot/store','rev-list','--count','HEAD'))==commits+1
 view=cli('cleanup','--list');assert [s['name'] for s in view['withdrawn']]==['dsh-only'] and not view['candidates']
 withdrawn=fixture.fingerprint()
 restored=cli('restore-withdrawn','dsh-only')
 cli('undo',restored['id']);assert fixture.fingerprint()==withdrawn
 cli('undo',cleaned['id']);assert fixture.fingerprint()==before
 result={'commands':commands,'cleaned':['dsh-only'],'kept':['candidate'],'one_commit_per_cleanup':True,
         'withdrawn_list_verified':True,'restore_original_assignment':True,'restore_undo_exact':True,'cleanup_undo_exact':True}
 (PROJECT/'work/m5-cleanup-acceptance.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
 print(json.dumps(result,ensure_ascii=False))
finally:fixture.doCleanups()
