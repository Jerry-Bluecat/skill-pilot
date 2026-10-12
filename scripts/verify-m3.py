#!/usr/bin/env python3
"""M3 acceptance confined to a migrated temporary home."""
import argparse
import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

PROJECT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(PROJECT))
from skill_pilot import operations,store
from skill_pilot.sources import github
from skill_pilot.sync import visibility


def fingerprints(home):
    roots=['.codex/skills','.agents/skills','.claude/skills','.gemini/config/skills','.dsh/skills',
           '.codex/config.toml','.agents/.skill-lock.json','.skill-pilot/registry.json','.skill-pilot/agents.json','.skill-pilot/bases']
    return {r:store.physical_state(home/r) for r in roots} | {'store':operations.content_digest(home/'.skill-pilot/store')}


def skill(home,relative,name,body='用于验收'):
    path=home/relative
    path.mkdir(parents=True,exist_ok=True)
    (path/'SKILL.md').write_text(f'---\nname: {name}\ndescription: 无害的验收技能\n---\n{body}\n')
    return path


def verify(home,public_review=None):
    home=Path(home).resolve()
    store.guard(home,home)
    store.check_links(home,home)
    env={**os.environ,'HOME':str(home),'SKILL_PILOT_HOME':str(home),'CODEX_HOME':str(home/'.codex'),
         'XDG_CONFIG_HOME':str(home/'.config'),'XDG_CACHE_HOME':str(home/'.cache'),'XDG_STATE_HOME':str(home/'.state')}
    def cli(*args,expected=0):
        process=subprocess.run([sys.executable,'-m','skill_pilot',*args,'--json'],env=env,cwd=PROJECT,
                               stdin=subprocess.DEVNULL,capture_output=True,text=True,timeout=60)
        assert process.returncode==expected,(process.returncode,process.stdout,process.stderr)
        return json.loads(process.stdout)
    def codex_names():
        process=subprocess.run(['/Applications/ChatGPT.app/Contents/Resources/codex-cli/bin/codex','debug','prompt-input','probe'],
                               cwd=home,env=env,stdin=subprocess.DEVNULL,capture_output=True,text=True,timeout=45,check=True)
        messages=json.loads(process.stdout)
        prompt='\n'.join(c.get('text','') for m in messages for c in m.get('content',[]) if isinstance(c,dict))
        rows=re.findall(r'^- ([^:\n]+): .*?\(file: ([^)]+)\)$',prompt,re.M)
        return sorted({n for n,p in rows if not p.startswith('r2/') and '/.system/' not in p})
    result={'home':str(home),'initial_counts':{a:len(v['available']) for a,v in visibility(home).items()}}
    view=operations.table(home)
    suggestions=view['suggestions']
    required=[s for s in suggestions if s['skill'] in {'grill-me','ascentiz-blog-writer'}]
    assert {(s['skill'],s['requires']) for s in required} >= {('grill-me','grilling'),*[('ascentiz-blog-writer',n) for n in ('natural-text-writing','unslop','stss','ascentiz-blog-editor')]}
    Path(PROJECT/'work/m3-dependency-suggestions.json').write_text(json.dumps(suggestions,ensure_ascii=False,indent=2)+'\n')
    registry=operations.load(home)[1]
    if 'grilling' not in registry['skills']['grill-me']['requires']:
        operations.decide_dependencies([{'skill':'grill-me','requires':'grilling','confirmed':True}],home=home)
    before_visible=visibility(home)
    point=fingerprints(home)
    assigned=cli('assign','grill-me','--agent','claude')
    after_visible=visibility(home)
    assert set(after_visible['claude']['available'])-set(before_visible['claude']['available'])=={'grill-me','grilling'}
    assert all(after_visible[a]==before_visible[a] for a in before_visible if a!='claude')
    blocked=cli('unassign','grilling','--agent','claude',expected=2)
    assert blocked['needs_confirmation'] and blocked['dependency_warnings']
    cli('undo',assigned['id'])
    assert fingerprints(home)==point
    result['dependency_assignment']={'added':['grill-me','grilling'],'other_agents_unchanged':True,'withdrawal_blocked':True,'undo_exact':True}
    path_warning=operations.preview_assign([{'skill':'ascentiz-blog-writer','agent':'codex','enabled':False}],home)
    assert path_warning['path_warnings']
    result['path_reminder']=path_warning['path_warnings']

    repository=home/'m3-test-repository'
    skill(home,'m3-test-repository/skills/m3-dsh-only','m3-dsh-only')
    sentinel=repository/'ran-script'
    (repository/'skills/m3-dsh-only/install.sh').write_text('#!/bin/sh\ntouch '+str(sentinel)+'\n')
    github.git(repository,'init','-q');github.git(repository,'add','.')
    github.git(repository,'-c','user.name=Test','-c','user.email=test@local','-c','commit.gpgsign=false','commit','-qm','fixture')
    cli('install',repository.as_uri(),'--skill','m3-dsh-only','--yes')
    baseline=fingerprints(home)
    config=(home/'.codex/config.toml').read_bytes()
    names_before=codex_names()
    assignment=cli('assign','m3-dsh-only','--agent','dsh')
    assert (home/'.agents/skills/m3-dsh-only').is_symlink()
    assert not (home/'.codex/skills/m3-dsh-only').exists()
    assert 'm3-dsh-only' not in codex_names()
    assert names_before==codex_names()
    updated=(home/'.codex/config.toml').read_bytes()
    fragment=json.loads((home/'.skill-pilot/registry.json').read_text())['codex_config']['fragments']['m3-dsh-only'].encode()
    assert updated.replace(fragment,b'',1)==config
    cli('undo',assignment['id'])
    assert config==(home/'.codex/config.toml').read_bytes()
    assert fingerprints(home)==baseline
    assert not sentinel.exists()
    skill(home,'m3-test-repository/skills/m3-dsh-only','m3-dsh-only','这是另一份不同的内容')
    github.git(repository,'add','.')
    github.git(repository,'-c','user.name=Test','-c','user.email=test@local','-c','commit.gpgsign=false','commit','-qm','different version')
    collision=cli('install',repository.as_uri(),'--skill','m3-dsh-only','--yes',expected=2)
    assert collision['conflicts'] and 'comparison' in collision['conflicts'][0]
    assert collision['conflicts'][0]['same_content'] is False
    result['dsh_only']={'codex_debug_hidden':True,'dsh_shared_link':True,'original_config_bytes_preserved':True,'undo_config_byte_exact':True,'undo_fingerprint_exact':True,'script_not_executed':True}
    result['local_install']={'source_commit':operations.load(home)[1]['skills']['m3-dsh-only']['source']['commit'],'same_name_conflict':True}

    lock_path=home/'.agents/.skill-lock.json'
    lock_original=lock_path.read_bytes()
    lock=json.loads(lock_original)
    lock.setdefault('skills',{})['m3-locked']={'sourceUrl':'https://github.com/test/upstream','sourceType':'github','skillPath':'skills/m3-locked'}
    lock_path.write_text(json.dumps(lock))
    skill(home,'.codex/skills/m3-locked','m3-locked')
    point=fingerprints(home)
    absorbed=cli('absorb','--all','--yes')
    assert operations.load(home)[1]['skills']['m3-locked']['source']['record']==lock['skills']['m3-locked']
    assert (home/'.codex/skills/m3-locked').is_symlink()
    operations.undo(absorbed['id'],home=home)
    assert fingerprints(home)==point
    shutil.rmtree(home/'.codex/skills/m3-locked')
    lock_path.write_bytes(lock_original)
    absorptions=[]
    for name,source in [('m3-verified',{'source':'https://github.com/test/upstream','commit':'test-history-commit','tree_sha':'test-tree'}),('m3-self',{'source':'自制'})]:
        skill(home,'.codex/skills/'+name,name)
        point=fingerprints(home)
        assert any(s['name']==name for s in operations.table(home)['new_skills'])
        with patch.object(github,'verify_source',return_value=source):
            absorbed=operations.absorb(all_skills=True,home=home)
        assert operations.load(home)[1]['skills'][name]['source']==source
        operations.undo(absorbed['id'],home=home)
        assert fingerprints(home)==point
        shutil.rmtree(home/'.codex/skills'/name)
        absorptions.append({'name':name,'source':source,'original_directory_restored':True,'fingerprint_exact':True})
    skill(home,'.codex/skills/m3-conflict','grilling','内容不同')
    point=fingerprints(home)
    assert operations.absorb(all_skills=True,home=home)['conflicts']
    assert fingerprints(home)==point
    shutil.rmtree(home/'.codex/skills/m3-conflict')
    result['absorb']={'lock_inherited':True,'lock_unchanged_by_operations':True,'cases':absorptions,'different_content_comparison':True}

    points,records=[],[]
    for name,agent in [('grilling','antigravity'),('m3-dsh-only','claude'),('grill-me','claude')]:
        points.append(fingerprints(home));records.append(cli('assign',name,'--agent',agent)['id'])
    undos=[]
    for operation,point in reversed(list(zip(records,points))):
        response=cli('undo',operation)
        assert fingerprints(home)==point
        undos.append({'operation':operation,'undo':response['id'],'fingerprint_exact':True})
    result['three_undos']=undos
    result['cli']={'status_counts':{a['id']:a['count'] for a in cli('status')['agents']},
                   'claude_list_count':len(cli('list','--agent','claude')['skills']),
                   'log_records':len(cli('log')),
                   'install_without_yes_rejected':'error' in cli('install',repository.as_uri(),expected=1),
                   'absorb_without_yes_rejected':'error' in cli('absorb','--all',expected=1)}
    if public_review:
        public_home=Path(tempfile.mkdtemp(prefix='skill-pilot-m3-public-home-')).resolve()
        skill(public_home,'.codex/skills/sentinel','sentinel')
        plan=store.preview(public_home);store.apply(plan['plan_id'],public_home)
        review=json.loads(Path(public_review).read_text())
        installed=operations.install(review,['grill-me'],home=public_home)
        assert (public_home/'.skill-pilot/store/grill-me/SKILL.md').is_file()
        assert (public_home/'.skill-pilot/bases/grill-me/SKILL.md').is_file()
        assert operations.load(public_home)[1]['skills']['grill-me']['assigned_agents']==[]
        result['public_install']={'home':str(public_home),'operation':installed['id'],'source':review['skills'][0]['source'],'default_agents_empty':True}
    store.check_links(home,home)
    return result


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('home');parser.add_argument('--public-review');parser.add_argument('--output',required=True)
    args=parser.parse_args()
    result=verify(args.home,args.public_review)
    Path(args.output).write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    print('M3 模拟验收通过：依赖、路径提醒、Codex 实际名单、安装、四类收编、三次撤销和 CLI。')
