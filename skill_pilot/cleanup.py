"""60-day eligibility, keep records, withdrawal and reversible restoration."""
import json
import sqlite3
import tarfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

from . import operations, usage
from .scan import metadata
from .sync import reconcile_assignments
from .usage.common import timestamp


def installations(home, registry, usage_rows):
    names = usage.mapping(home,registry)
    lock_path = home/'.agents/.skill-lock.json'
    lock = json.loads(lock_path.read_text()).get('skills',{}) if lock_path.exists() else {}
    locked = {}
    for alias, item in lock.items():
        name, date = names.name(alias), timestamp(item.get('installedAt'))
        if name and date:
            if name not in locked or date < locked[name]['date']:
                locked[name] = {'date':date,'evidence':'.agents/.skill-lock.json installedAt'}
    originals = {}
    # The first migration archive preserves original file times, unlike the rebuilt store.
    backups = sorted((home/'.skill-pilot/backups').glob('*/manifest.json'))
    for manifest in backups:
        data = json.loads(manifest.read_text())
        if '.skill-pilot/registry.json' in data.get('existing',[]):
            continue
        archive_path = manifest.parent/'files.tar'
        if not archive_path.exists():
            continue
        with tarfile.open(archive_path) as archive:
            roots = {}
            for member in archive.getmembers():
                if member.isfile() and member.name.endswith('/SKILL.md'):
                    name = names.path(member.name)
                    if name:
                        roots[str(Path(member.name).parent)] = name
            for member in archive.getmembers():
                if not (member.isfile() or member.isdir()):
                    continue
                for root, name in roots.items():
                    if member.name == root or member.name.startswith(root+'/'):
                        date = timestamp(member.mtime)
                        if date and (name not in originals or date < originals[name]['date']):
                            originals[name] = {'date':date,'evidence':'迁移备份 '+manifest.parent.name+'/'+member.name+' 原文件时间'}
        break
    rows = {r['name']:r for r in usage_rows}
    result = {}
    for name, skill in registry['skills'].items():
        if name in locked:
            result[name] = locked[name]
        elif name in originals:
            result[name] = originals[name]
        elif skill.get('installation_evidence'):
            result[name] = {'date':timestamp(skill.get('installed_at')),'evidence':skill['installation_evidence']}
        elif rows.get(name,{}).get('first_seen'):
            result[name] = {'date':rows[name]['first_seen'],'evidence':'agent 日志中第一次出现（仅用于安装时间）'}
        else:
            result[name] = {'date':None,'evidence':'没有可靠证据，视为刚装'}
    return result


def preview(home=None, database=None, now=None, usage_data=None):
    home, registry, agents = operations.load(home)
    now = now or datetime.now(timezone.utc)
    cutoff = (now-timedelta(days=60)).isoformat()
    try:
        data = usage_data if usage_data is not None else usage.report(home,database,now)
    except sqlite3.Error:
        raise ValueError('正在统计，完成后再生成名单。') from None
    used = {s['name']:s for s in data['skills']}
    installed = installations(home,registry,data['skills'])
    recent = {n for n,s in registry['skills'].items() if
              any(t >= cutoff for t in used.get(n,{}).get('last_used',{}).values()) or
              (timestamp(s.get('kept_at')) or '') >= cutoff}
    protected = set()
    def depend(name, visiting):
        if name in visiting or name not in registry['skills']:
            return
        for dependency in registry['skills'][name].get('requires',[]):
            protected.add(dependency)
            depend(dependency,visiting|{name})
    for name in recent:
        depend(name,set())
    candidates, excluded, withdrawn = [], [], []
    for name, skill in sorted(registry['skills'].items()):
        description = metadata((home/'.skill-pilot/store'/name/'SKILL.md').read_text()).get('description','')
        record = used.get(name,{})
        row = {'name':name,'assigned_agents':skill['assigned_agents'],'description_chars':len(description),
               'last_used':record.get('last_used',{}),'last_agent':record.get('last_agent'),
               'last_used_at':record.get('last_used_at'),'installed_at':installed[name]['date'],
               'installation_evidence':installed[name]['evidence'],'kept_at':skill.get('kept_at'),
               'path_warnings':operations.path_warnings(skill.get('entries',[]))}
        if skill.get('withdrawn'):
            withdrawn.append({**row,'previous_agents':skill.get('withdrawn_agents',[]),'withdrawn_at':skill.get('withdrawn_at')})
        reasons = []
        if not skill['assigned_agents']:
            reasons.append('尚未分配')
        if not installed[name]['date'] or installed[name]['date'] > cutoff:
            reasons.append('入库未满 60 天或时间缺证据')
        if any(not data['coverage'].get(a,{}).get('available') for a in skill['assigned_agents']):
            reasons.append('分配给了统计不到的 agent')
        if any(t >= cutoff for t in row['last_used'].values()):
            reasons.append('60 天内用过')
        if (timestamp(skill.get('kept_at')) or '') >= cutoff:
            reasons.append('60 天内选择过留下')
        if name in protected:
            reasons.append('近期使用技能的依赖')
        (excluded if reasons else candidates).append({**row,'reasons':reasons})
    return {'candidates':candidates,'excluded':excluded,'withdrawn':withdrawn,'coverage':data['coverage'],
            'savings':{a:sum(s['description_chars'] for s in candidates if a in s['assigned_agents']) for a in agents},
            'revision':operations.revision(home,agents),'checked_at':now.isoformat(),
            'write_allowed':operations.write_allowed(home),'ledger':data.get('ledger'),
            'scanned_bytes':data.get('scanned_bytes',0)}


def apply(keep=None, confirmed=False, home=None, database=None, expected=None, candidate_names=None):
    if not confirmed:
        raise ValueError('清理需要用户明确同意，请先查看名单，再加 --yes 执行。')
    home, registry, agents = operations.load(home)
    # Reject out-of-scope writes before scanning or creating a ledger.
    operations.guard(home/'.skill-pilot',home)
    view = preview(home,database)
    offered = {s['name'] for s in view['candidates']}
    if expected and expected != view['revision']:
        raise ValueError('目录内容已经变了，请刷新清理名单。')
    if candidate_names is not None and set(candidate_names) != offered:
        raise ValueError('用量或清理名单已经变了，请刷新后再选择。')
    keep = set(keep or [])
    if not keep <= offered:
        raise ValueError('要留下的技能不在本次清理名单里，请刷新后再选择。')
    selected = sorted(offered-keep)
    if not offered:
        return {'message':'没有符合条件的清理技能。'}
    plan = operations.assignment_plan(registry,agents,[{'skill':n,'agent':a,'enabled':False}
                for n in selected for a in registry['skills'][n]['assigned_agents']],home)
    now = datetime.now(timezone.utc).isoformat()
    def mutate(current, checked):
        for name in selected:
            skill = current['skills'][name]
            skill.update(withdrawn=True,withdrawn_at=now,withdrawn_agents=list(skill['assigned_agents']),
                         withdrawn_entries=list(skill['entries']),assigned_agents=[])
        for name in keep:
            current['skills'][name]['kept_at'] = now
        reconcile_assignments(current,home,checked,selected)
        return sorted(offered), [], {'withdrawn':selected,'kept':sorted(keep),
                                    'path_warnings':plan['path_warnings'],'dependency_warnings':plan['dependency_warnings']}
    return operations._run(home,registry,agents,view['revision'],f'清理撤下了 {len(selected)} 个技能，留下 {len(keep)} 个',mutate)


def restore(names, home=None, expected=None):
    home, registry, agents = operations.load(home)
    operations.guard(home/'.skill-pilot',home)
    names = sorted(set(names))
    if not names or any(n not in registry['skills'] or not registry['skills'][n].get('withdrawn') for n in names):
        raise ValueError('请选择已撤下的技能。')
    changes = [{'skill':n,'agent':a,'enabled':True} for n in names for a in registry['skills'][n].get('withdrawn_agents',[])]
    plan = operations.assignment_plan(registry,agents,changes,home)
    def mutate(current, checked):
        current.update(plan['registry'])
        for name in names:
            current['skills'][name].pop('withdrawn',None)
            current['skills'][name].pop('withdrawn_at',None)
        changed = sorted(set(names)|set(plan['changed']))
        reconcile_assignments(current,home,checked,changed,{n:current['skills'][n]['withdrawn_entries'] for n in names})
        return changed, [], {'restored':names,'reasons':plan['reasons']}
    return operations._run(home,registry,agents,expected or operations.revision(home,agents),f'恢复了 {len(names)} 个已撤下的技能',mutate)
