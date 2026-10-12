#!/usr/bin/env python3
"""Independent one-off 30-day recount. No production parsers; no transcript output."""
import json
import re
import shlex
import sqlite3
import subprocess
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

PROJECT=Path(__file__).resolve().parents[1]
home=Path('/Users/j')
runtime=json.loads((PROJECT/'work/m5-real-runtime.json').read_text())
db=sqlite3.connect('file:'+str(Path(runtime['directory'])/'usage.sqlite')+'?mode=ro',uri=True)
db.row_factory=sqlite3.Row
usage=json.loads((PROJECT/'work/real-usage.json').read_text())
cutoff=(datetime.fromisoformat(usage['checked_at'])-timedelta(days=30)).isoformat()
registry=json.loads((home/'.skill-pilot/registry.json').read_text())['skills']
aliases={n:n for n in registry};entries={}
for n,s in registry.items():
 for e in s.get('entries',[])+s.get('withdrawn_entries',[]):entries[e]=n;aliases[Path(e).name]=n
for s in json.loads((PROJECT/'work/real-migration-preview.json').read_text())['skills']:
 if s['name'] in registry:
  for e in s['entries']:entries[e]=s['name'];aliases[Path(e).name]=s['name']


def date(v):
 if isinstance(v,(int,float)):return datetime.fromtimestamp(v/1000 if v>1e11 else v,timezone.utc).isoformat()
 try:return datetime.fromisoformat(str(v).replace('Z','+00:00')).astimezone(timezone.utc).isoformat()
 except (ValueError,TypeError):return None


def named(v):return aliases.get(str(v).strip().lstrip('/'))


def paths(text):
 result=set()
 for root,tail in re.findall(r'(\.(?:codex/skills|agents/skills|claude/skills|gemini/config/skills|dsh/skills|skill-pilot/store))/([\w.-]+(?:/[\w.-]+)*)/SKILL\.md',str(text)):
  e=root+'/'+tail
  if e in entries:result.add(entries[e])
  elif '/' not in tail or root=='.codex/skills' and tail.startswith('community/') and tail.count('/')==1:
   if n:=named(Path(tail).name):result.add(n)
 if 'Developer/vendor/stop-that-shit-local/skills/stss/SKILL.md' in str(text) and 'stss' in registry:result.add('stss')
 return result


def shell(command):
 if isinstance(command,list):command=command[-1] if len(command)>2 and command[1] in ['-c','-lc'] else ' '.join(command)
 result=set()
 command=re.sub(r'(?:^|\n)\s*cat[^\n]*<<-?\s*["\x27]?([A-Za-z0-9_]+)["\x27]?[^\n]*\n.*?\n\1(?:\n|$)', '\n', str(command), flags=re.S)
 for part in re.split(r'&&|;|\n',str(command)):
  try:words=shlex.split(part)
  except ValueError:continue
  if not words:continue
  if words[0] in ['cat','sed','head','tail','rg','grep','less','more','bat'] and not (words[0]=='sed' and any(w.startswith('-i') for w in words[1:])):
   args_before_output=words[1:words.index('>')] if '>' in words else words[1:words.index('>>')] if '>>' in words else words[1:]
   result|=paths(' '.join(args_before_output))
 for match in re.finditer(r'(["\x27])([^"\x27]+/SKILL\.md)\1\)\.(read_text|read_bytes)\(',str(command)):result|=paths(match[2])
 for match in re.finditer(r'open\((["\x27])([^"\x27]+/SKILL\.md)\1\s*(?:\)|,\s*["\x27]r[b+t]*["\x27])',str(command)):result|=paths(match[2])
 return result


def args(v):
 if isinstance(v,str):
  try:return json.loads(v)
  except ValueError:return v
 return v or {}


def read(tool,v):
 tool=str(tool).rsplit('__',1)[-1].lower();v=args(v)
 if tool in ['read','read_file','view_file','read_text_file'] and isinstance(v,dict):return paths(v.get('file_path',v.get('path',v.get('AbsolutePath',''))))
 if tool in ['bash','exec_command','shell','local_shell_call','run_command','terminal'] and isinstance(v,dict):
  v=v.get('action',v)
  return shell(v.get('cmd',v.get('command',''))) if isinstance(v,dict) else set()
 if tool in ['exec','functions.exec'] and isinstance(v,str):
  result=set()
  for match in re.finditer(r'["\x27]?(cmd|command)["\x27]?\s*:\s*("(?:\\.|[^"\\])*"|\x27(?:\\.|[^\x27\\])*\x27)',v):
   literal=match[2]
   try:command=json.loads(literal) if literal[0]=='"' else literal[1:-1]
   except ValueError:command=literal[1:-1]
   result|=shell(command)
  return result
 return set()


calls={};sessions=defaultdict(set);versions=defaultdict(dict)
def add(agent,session,names,t):
 if t and t>=cutoff:
  for n in names:
   key=agent,session,n
   calls[key]=max(t,calls.get(key,t))

for scan in db.execute('SELECT * FROM scans ORDER BY path').fetchall():
 p=Path(scan['path']);agent=scan['agent']
 if not p.exists():raise RuntimeError('A scanned log was deleted during the independent check')
 session=p.parent.name if agent=='dsh' else p.stem
 if agent=='dsh':
  node="""const fs=require('node:fs'),z=require('node:zlib');let b=fs.readFileSync(process.argv[1]).subarray(0,Number(process.argv[2])),i=0,text='',r=[];while(i<b.length){let d=z.zstdDecompressSync(b.subarray(i),{info:true});i+=d.engine.bytesWritten;text+=d.buffer.toString();}for(let line of text.split('\\n')){if(!line)continue;let v=JSON.parse(line);if(v.type==='session'||v.type==='tool/call'&&['skill','read','read_file','bash','shell','terminal'].includes(v.data?.name))r.push(v);}process.stdout.write(JSON.stringify(r));"""
  rows=json.loads(subprocess.run(['node','-e',node,str(p),str(scan['offset'])],capture_output=True,text=True,check=True).stdout)
  for r in rows:
   if r['type']=='session':session=r['id'];continue
   d=r['data'];v=args(d.get('arguments'));found={named(v.get('name',v.get('skill','')))} if d['name']=='skill' else read(d['name'],v)
   add(agent,session,found-{None},date(r.get('time')))
  versions[str(p.parent)][p.name]=session
 else:
  with p.open('rb') as f:
   while f.tell()<scan['offset']:
    line=f.readline()
    if b'"session_meta"' in line:
     r=json.loads(line);session=r.get('payload',{}).get('id',session)
    stamp=re.search(rb'"timestamp"\s*:\s*"([^"\\]+)"',line[:500])
    t=date(stamp[1].decode()) if stamp else None
    if agent=='claude':
     if b'SKILL.md' not in line and b'"Skill"' not in line and b'"user"' not in line[:300]:continue
     t=date(json.loads(line).get('timestamp'))
    if not t or t<cutoff:continue
    if b'SKILL.md' not in line and b'"Skill"' not in line and not (agent=='claude' and b'"user"' in line[:300]):continue
    r=json.loads(line);found=set()
    if agent=='codex':
     v=r.get('payload',{});kind=v.get('type')
     if kind=='local_shell_call':found=read('local_shell_call',v)
     elif kind in ['function_call','custom_tool_call']:found=read(v.get('name'),v.get('arguments',v.get('input')))
    else:
     session=r.get('sessionId',session);content=r.get('message',{}).get('content',[])
     if r.get('type')=='assistant' and isinstance(content,list):
      for block in content:
       if not isinstance(block,dict) or block.get('type')!='tool_use':continue
       v=block.get('input',{})
       if block.get('name')=='Skill':
        if n:=named(v.get('skill','')):found.add(n)
       else:found|=read(block.get('name'),v)
     elif r.get('type')=='user':
      texts=[content] if isinstance(content,str) else [b.get('text','') for b in content if isinstance(b,dict) and b.get('type')=='text']
      for text in texts:
       m=re.match(r'^\s*/([\w.:-]+)(?:\s|$)',text) or re.search(r'<command-name>/([\w.:-]+)</command-name>',text)
       if m and (n:=named(m[1])):found.add(n)
    add(agent,session,found,t)
expected={(r['agent'],r['session'],r['skill']):r['last_used'] for r in db.execute('SELECT * FROM calls WHERE last_used>=?',(cutoff,))}
missing=sorted(set(expected)-set(calls));extra=sorted(set(calls)-set(expected))
# Session identities remain private. Evidence includes only agents, skill names and totals.
sanitize=lambda items:[{'agent':a,'skill':n} for a,s,n in items]
result={'match':calls==expected,'cutoff':cutoff,'independent_session_skill_pairs':len(calls),'ledger_session_skill_pairs':len(expected),
        'missing':sanitize(missing),'extra':sanitize(extra),'timestamp_mismatches':sum(expected[k]!=calls[k] for k in expected.keys()&calls.keys()),
        'agent_counts':{a:sum(key[0]==a for key in calls) for a in ['claude','codex','dsh']},
        'dsh_dual_version_sessions':sum(len(v)>1 for v in versions.values()),'dsh_dual_version_identity_match':all(len(set(v.values()))==1 for v in versions.values() if len(v)>1)}
(PROJECT/'work/m5-independent-usage.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
print(json.dumps(result,ensure_ascii=False))
raise SystemExit(0 if result['match'] and result['dsh_dual_version_identity_match'] else 1)
