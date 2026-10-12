const token = new URLSearchParams(location.search).get('token');
const headers = {'X-Skill-Pilot-Token': token};
const $ = id => document.getElementById(id);
const escape = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const categories = {user:'用户技能',builtin:'软件内置',plugin:'插件技能',plugin_cache:'插件或市场缓存',vendor:'下载的候选库',unknown_agent:'疑似新助手',ignored:'已忽略',backup_temp:'备份或临时目录',reference:'参考资料'};
let data;
const pathLabel = path => escape(path.replace(data.home, '~'));

async function heartbeat() {
  try {
    const response = await fetch('/api/heartbeat', {method:'POST',headers});
    if (!response.ok) throw new Error();
  } catch {
    $('connection').textContent = '看板已关闭或连接中断。重新双击 Skill Pilot 即可继续查看。';
    $('connection').classList.add('warn');
  }
}
heartbeat();
setInterval(heartbeat, 10000);

function renderSkills() {
  const search = $('search').value.toLowerCase();
  const root = $('root-filter').value;
  const includeReadonly = $('include-readonly').checked;
  const rows = data.roots.filter(r => (!root || r.path === root) && (includeReadonly || r.category === 'user'))
    .flatMap(r => r.skills.map(s => ({...s,root:r})))
    .filter(s => (s.name + ' ' + s.description).toLowerCase().includes(search));
  $('inventory-count').textContent = `显示 ${rows.length} 个目录入口。相同技能在不同目录中会各列一行。`;
  $('skills').innerHTML = rows.map(s => {
    const disabled = data.codex_disabled.names.includes(s.name) || data.agents.find(a => a.id === 'codex')?.disabled_paths.includes(s.path);
    const state = (s.broken ? '链接已失效' : s.kind === 'link' ? '链接到另一位置' : '存放完整文件') + (s.codex_implicit_invocation===false ? '<small>Codex 只允许手动调用</small>' : '');
    return `<tr><td><div class="skill-name">${escape(s.name)}</div>${s.name_mismatch ? '<small>名称与文件夹名称不同</small>' : ''}<small>${escape(s.description.slice(0,150))}${s.description.length>150?'…':''}</small></td><td><div class="path">${pathLabel(s.path)}</div>${s.link_target ? `<small>指向 ${escape(s.link_target)}</small>` : ''}<small>${escape(s.root.readers.join(' / '))} · ${categories[s.root.category]}</small></td><td>${state}${disabled ? '<small>Codex 已停用</small>' : ''}${s.model_invocable===false ? '<small>只允许手动调用</small>':''}${s.warning ? `<small>${escape(s.warning)}</small>` : ''}</td><td>${s.description_chars.toLocaleString()}</td></tr>`;
  }).join('') || '<tr><td colspan="4">没有符合条件的技能。</td></tr>';
}

function render() {
  $('connection').textContent = `发现 ${data.agents.length} 个助手，${data.conflicts.length} 组版本差异，${data.roots.filter(r=>r.category==='user').reduce((n,r)=>n+r.broken_count,0)} 个用户技能链接失效。`;
  $('cards').innerHTML = data.agents.filter(a=>a.visible_skill_count !== null).map(a=>`<article class="card"><h3>${escape(a.name)}</h3><div class="count">${a.visible_skill_count}<span> 个自动可用技能</span></div><p>说明占用 ${a.description_chars.toLocaleString()} 字${a.manual_only_names?.length?` · 另有 ${a.manual_only_names.length} 个手动调用技能`:''}</p><p class="muted">${escape(a.visibility_note)}</p></article>`).join('');
  $('basis').textContent = data.count_basis + '“字数”按字符粗算，不代表实际模型用量。';
  $('conflict-count').textContent = data.conflicts.length;
  $('root-filter').innerHTML = '<option value="">全部用户技能目录</option>' + data.roots.map(r=>`<option value="${escape(r.path)}">${pathLabel(r.path)} (${r.entry_count})</option>`).join('');
  $('conflict-list').innerHTML = data.conflicts.map(c=>`<details><summary>${escape(c.name)}<small>${c.versions.length} 种内容</small></summary>${c.versions.map((v,i)=>`<div class="version"><strong>第 ${i+1} 份${v.copies[0].version ? ' · 版本 '+escape(v.copies[0].version):''}</strong>${v.copies.map(s=>`<div class="path">${pathLabel(s.path)}</div>`).join('')}</div>`).join('')}</details>`).join('') || '<p class="empty">没有发现同名不同内容的技能。</p>';
  $('agent-list').innerHTML = data.agents.map(a=>`<details><summary>${escape(a.name)}<small>${a.status==='ignored'?'已忽略':a.status==='discovered'?'已发现，尚未接入':'有内置盘点档案'}</small></summary><p>${escape(a.visibility_note)}</p>${(a.skill_roots.length ? a.skill_roots : a.evidence).map(p=>`<div class="path">${pathLabel(p)}</div>`).join('')}${a.usage?`<p>使用记录：${escape(a.usage)}</p>`:''}</details>`).join('');
  $('root-list').innerHTML = data.roots.map(r=>`<tr><td class="path">${pathLabel(r.path)}${r.exists?'':'<small>目录尚不存在</small>'}${r.unresolved_links.length?`<small>另有 ${r.unresolved_links.length} 个目录链接已失效，无法检查内部技能。</small>`:''}</td><td>${categories[r.category]}</td><td>${r.entry_count}</td><td>${r.broken_count}</td></tr>`).join('');
  $('discovery-note').textContent = data.discovery_note;
  $('candidate-list').innerHTML = data.candidates.filter(c=>!c.default_hidden).map(c=>`<details><summary>${categories[c.category]}<small>${c.entry_count} 个目录入口</small></summary><p class="path">${pathLabel(c.path)}</p><p>${c.skills.map(s=>escape(s.name)).join('、')}</p></details>`).join('');
  if(data.errors.length) $('candidate-list').innerHTML += `<details><summary>有 ${data.errors.length} 个位置未完整读取</summary><p>系统限制或文件读取失败，已保留为“未知”，不会当作空目录。</p>${data.errors.map(e=>`<p class="path">${pathLabel(e.path)}<br>${escape(e.message)}</p>`).join('')}</details>`;
  $('footer').textContent = `关掉全部看板页面后，程序会在 30 秒内退出；正在检查更新时会等检查完成。盘点时间：${new Date(data.generated_at).toLocaleString('zh-CN')}。`;
  renderSkills();
}

document.querySelectorAll('nav button').forEach(button=>button.addEventListener('click',()=>{
  document.querySelectorAll('nav button').forEach(b=>b.setAttribute('aria-selected', String(b===button)));
  document.querySelectorAll('main > section').forEach(section=>section.hidden=section.id!==button.dataset.panel);
}));
['search','root-filter','include-readonly'].forEach(id=>$(id).addEventListener('input',renderSkills));
$('root-filter').addEventListener('change',()=>{
  const root=data.roots.find(r=>r.path===$('root-filter').value);
  if(root && root.category!=='user') $('include-readonly').checked=true;
  renderSkills();
});
fetch('/api/scan',{headers}).then(r=>{if(!r.ok) throw new Error();return r.json();}).then(result=>{data=result;render();}).catch(()=>{
  $('connection').textContent='技能清单没能读出来。请关闭页面后重新打开看板。';
  $('connection').classList.add('warn');
});

let migrationPlan, backupId, writeAllowed = false;
const mainAgents = [['codex','Codex'],['claude','Claude'],['antigravity','Antigravity'],['dsh','DSH']];
$('migration-agents').innerHTML = mainAgents.map(([id,name])=>`<label><input type="checkbox" data-agent="${id}" checked> ${name}</label>`).join('');
$('migration-agents').addEventListener('change', event=>{
  const id = event.target.dataset.agent;
  if(id === 'codex' || id === 'dsh') document.querySelector(`[data-agent="${id==='codex'?'dsh':'codex'}"]`).checked = event.target.checked;
});
async function api(path, body) {
  const response = await fetch(path, body === undefined ? {headers} : {method:'POST',headers:{...headers,'Content-Type':'application/json'},body:JSON.stringify(body)});
  const result = await response.json();
  if(!response.ok) throw Object.assign(new Error(result.error || '操作没能完成，请重新预览。'),{retry:result.retry});
  return result;
}
function migrationError(error) {
  $('migration-error').textContent = error.message;
  $('migration-error').hidden = false;
}
function migrationStep(step) {
  ['select','review','complete'].forEach(id=>$(`migration-${id}`).hidden=id!==step);
  $('migration-error').hidden=true;
}
$('migration-preview').addEventListener('click',async()=>{
  $('migration-preview').disabled=true;
  try {
    const agents = [...document.querySelectorAll('[data-agent]:checked')].map(input=>input.dataset.agent);
    if(!agents.length) throw new Error('请至少选择一个助手。');
    migrationPlan = await api('/api/migration/plan?agents='+agents.join(','));
    writeAllowed = migrationPlan.write_allowed;
    $('mode-badge').textContent = writeAllowed ? '模拟目录演练' : '真实目录只读预览';
    $('migration-mode').textContent = writeAllowed ? '当前操作模拟目录。迁移前会完整备份，完成后可以一键还原。' : '只读模式下可以预览，不能迁移。';
    $('migration-summary').textContent = `共 ${migrationPlan.skills.length} 个技能，${migrationPlan.conflicts.length} 组内容需要核对。相同内容会直接合并，原来的技能入口会保留。`;
    $('migration-counts').innerHTML = mainAgents.map(([id,name])=>{
      const before=migrationPlan.before[id], after=migrationPlan.after[id];
      return `<details><summary>${name}：可调用 ${before.available.length} → ${after.available.length} 个；自动可用 ${before.automatic.length} → ${after.automatic.length} 个</summary><p>迁移前：${escape(before.available.join('、'))}</p><p>迁移后：${escape(after.available.join('、'))}</p></details>`;
    }).join('');
    $('migration-versions').innerHTML = migrationPlan.conflicts.map(skill=>`<details open><summary>${escape(skill.name)}<small>${escape(skill.reason)}</small></summary>${skill.options.map((option,index)=>`<p><label><input type="radio" name="choice-${escape(skill.name)}" data-choice="${escape(skill.name)}" value="${escape(option.id)}" ${option.id===skill.default?'checked':''}> 第 ${index+1} 份${option.version?' · 版本 '+escape(option.version):''}${option.id===skill.default?' · 默认选择':''}</label></p><div class="path">${option.paths.map(pathLabel).join('<br>')}</div>`).join('')}<details><summary data-compare="${escape(skill.name)}">查看完整差异</summary><pre style="white-space:pre-wrap;overflow-wrap:anywhere"></pre></details></details>`).join('') || '<p>没有同名不同内容的技能。</p>';
    $('migration-names').innerHTML = migrationPlan.skills.filter(s=>s.name_mismatch).map(s=>`<p>${escape(s.name)}：${s.entries.map(escape).join('、')}</p>`).join('') || '<p>所有名称都一致。</p>';
    $('migration-skipped').innerHTML = migrationPlan.skipped.map(s=>`<p class="path">${pathLabel(s.path)} · ${escape(s.reason)}</p>`).join('');
    $('migration-apply').disabled = !writeAllowed;
    migrationStep('review');
  } catch(error) { migrationError(error); }
  finally { $('migration-preview').disabled=false; }
});
$('migration-versions').addEventListener('click',async event=>{
  const name=event.target.dataset.compare;
  if(!name || event.target.nextElementSibling.textContent) return;
  try {
    const query=new URLSearchParams({agents:migrationPlan.agents.join(','),plan_id:migrationPlan.plan_id,name});
    event.target.nextElementSibling.textContent=(await api('/api/migration/compare?'+query)).comparison;
  } catch(error) {migrationError(error);}
});
$('migration-back').addEventListener('click',()=>migrationStep('select'));
$('migration-apply').addEventListener('click',async()=>{
  if(!writeAllowed || !confirm('会先备份，再把选中的内容收进统一仓库。每个助手原来能调用的技能名单会保留，完成后可以一键还原。确认迁移吗？')) return;
  $('migration-apply').disabled=true;
  try {
    const choices=Object.fromEntries([...document.querySelectorAll('[data-choice]:checked')].map(input=>[input.dataset.choice,input.value]));
    const result=await api('/api/migration/apply',{confirmed:true,agents:migrationPlan.agents,plan_id:migrationPlan.plan_id,choices});
    backupId=result.backup_id;
    $('migration-result').textContent='迁移完成';
    $('migration-result-detail').textContent=result.message;
    $('migration-restore').hidden=false;
    migrationStep('complete');
    data=await api('/api/scan');render();
  } catch(error) {migrationError(error);}
  finally {$('migration-apply').disabled=!writeAllowed;}
});
async function restoreBackup(id) {
  if(!confirm('会把这些助手的技能目录和统一仓库恢复到这份备份时的状态。确认还原吗？')) return;
  try {
    const result=await api('/api/restore',{confirmed:true,backup_id:id});
    $('migration-result').textContent='已还原到迁移前';
    $('migration-result-detail').textContent=result.message;
    $('migration-restore').hidden=true;
    migrationStep('complete');
    data=await api('/api/scan');render();
  } catch(error) {migrationError(error);}
}
$('migration-restore').addEventListener('click',()=>restoreBackup(backupId));
$('migration-backups').addEventListener('click',async()=>{
  try {
    const saved=await api('/api/backups');
    $('migration-backup-list').innerHTML=saved.map(b=>`<p>${escape(b.backup_id)} <button class="badge" data-restore="${escape(b.backup_id)}" ${writeAllowed?'':'disabled'}>还原这份备份</button></p>`).join('') || '<p>还没有迁移备份。</p>';
  } catch(error) {migrationError(error);}
});
$('migration-backup-list').addEventListener('click',event=>{if(event.target.dataset.restore) restoreBackup(event.target.dataset.restore);});
api('/api/status').then(status=>{
  writeAllowed=!status.read_only;
  $('mode-badge').textContent=writeAllowed?'可以管理技能':'只读预览';
  $('migration-mode').textContent=writeAllowed?'迁移前会备份，迁移完成后可一键还原。':'只读模式下可以预览，不能迁移。';
}).catch(migrationError);

let management, draft = {}, pendingPlan, installReview, previewSequence = 0, previewBusy = false, assignmentErrors = {};
function manageError(error) {
  $('manage-error').hidden = false;
  $('manage-error').textContent = error.message;
  $('connection').textContent = error.message;
  $('connection').classList.add('warn');
}
function changes() {
  if (!management) return [];
  return management.skills.flatMap(s=>management.agents.map(a=>({skill:s.name,agent:a.id,enabled:(draft[s.name]||[]).includes(a.id)}))
    .filter(c=>c.enabled!==s.assigned_agents.includes(c.agent)));
}
function renderAssignments() {
  if (!management) return;
  const search=$('assignment-search').value.toLowerCase();
  $('assignment-head').innerHTML='<tr><th>技能与来源</th>'+management.agents.map(a=>`<th>${escape(a.name)}<small>${escape(a.activation)}</small></th>`).join('')+'<th>需要的技能与使用</th></tr>';
  $('assignment-rows').innerHTML=management.skills.filter(s=>(s.name+' '+s.description).toLowerCase().includes(search)||pendingPlan?.reasons.some(r=>r.includes(' 需要 '+s.name+'，'))).map(s=>`<tr><td><strong>${escape(s.name)}</strong><small>${escape(s.description.slice(0,130))}</small><small>来源：${escape(s.source_label)}${s.local_modified?' · 你改过':''}</small></td>${management.agents.map(a=>`<td><input type="checkbox" aria-label="${escape(a.name+' 使用 '+s.name)}" data-assignment-skill="${escape(s.name)}" data-assignment-agent="${escape(a.id)}" ${(draft[s.name]||[]).includes(a.id)?'checked':''} ${management.write_allowed&&!previewBusy?'':'disabled'}><small>${escape(assignmentErrors[s.name+'|'+a.id]||pendingPlan?.reasons.find(r=>r.includes(' 需要 '+s.name+'，')&&r.endsWith('给 '+a.name))?.replace('需要 '+s.name+'，已一起勾上给 '+a.name,'需要它')||'')}</small></td>`).join('')}<td>${s.requires.map(n=>`<small>${escape(n)} <button class="badge" data-dependency-skill="${escape(s.name)}" data-remove-dependency="${escape(n)}" ${management.write_allowed?'':'disabled'}>删除</button></small>`).join('')||'暂无需要的技能'} <button class="badge" data-add-dependency="${escape(s.name)}" ${management.write_allowed?'':'disabled'}>添加需要的技能</button>${management.agents.map(a=>`<small>${escape(a.name)} 最近使用：${escape(s.last_used[a.id])}</small>`).join('')}</td></tr>`).join('');
  $('assignment-counts').innerHTML=management.agents.map(a=>{
    const assigned=management.skills.filter(s=>(draft[s.name]||[]).includes(a.id));
    const chars=assigned.reduce((sum,s)=>sum+s.description_chars,0);
    return `<article class="card"><h3>${escape(a.name)}</h3><div class="count">${a.count}<span> 个技能</span></div><p>应用后 ${assigned.length} 个；描述 ${a.description_chars.toLocaleString()} 字 → ${chars.toLocaleString()} 字</p><p>${escape(a.activation)}</p></article>`;
  }).join('');
  $('pending-summary').textContent=pendingPlan?.message||'还没有待应用的改动。';
  $('pending-reasons').textContent=pendingPlan?.reasons.join('；')||'';
  $('assignment-apply').disabled=previewBusy||!management.write_allowed||!changes().length; $('assignment-discard').disabled=previewBusy; $('manage-refresh').disabled=previewBusy;
}
async function refreshManagement() {
  try {
    management=await api('/api/table');
    $('manage-error').hidden=true;
    draft=Object.fromEntries(management.skills.map(s=>[s.name,[...s.assigned_agents]]));
    pendingPlan=undefined;
    $('mode-badge').textContent=management.write_allowed?'可以管理技能':'只读预览';
    $('new-skills-notice').hidden=!management.new_skills.length;
    $('new-skills-text').textContent=`发现 ${management.new_skills.length} 个新装的技能，收编后会保持原来的可见范围。`;
    $('global-new-skills').hidden=!management.new_skills.length;
    $('global-new-text').textContent=`发现 ${management.new_skills.length} 个新装的技能。`;
    $('new-skills-list').innerHTML=management.new_skills.map(s=>`<p>${escape(s.name)} <small class="path">${escape(s.relative)}</small></p>`).join('');
    $('absorb-all').disabled=!management.write_allowed;
    $('install-open').disabled=!management.write_allowed;
    renderAssignments();
    await refreshLog();
  } catch(error) {manageError(error);}
}
async function refreshLog() {
  try {
    const records=await api('/api/log');
    $('operation-list').innerHTML=records.map(r=>`<div class="version"><strong>${escape(r.message)}</strong><p>${escape(new Date(r.time).toLocaleString('zh-CN'))} · ${escape(r.agents.map(id=>mainAgents.find(a=>a[0]===id)?.[1]||id).join('、')||'技能仓库')}</p>${r.undone?'<small>已撤销</small>':r.undo_of?'':`<button class="badge" data-undo="${escape(r.id)}" ${management?.write_allowed?'':'disabled'}>撤销</button>`}</div>`).join('')||'<p class="empty">还没有操作记录。</p>';
  } catch(error) {manageError(error);}
}
async function showConflicts(result, reviewId) {
  $('incoming-conflicts').hidden=false;
  $('incoming-comparisons').innerHTML='';
  for(const conflict of result.conflicts) {
    const incoming=management.new_skills.find(s=>s.name===conflict.name);
    const comparison=await api('/api/incoming/compare',{name:conflict.name,review_id:reviewId,relative:incoming?.relative});
    const details=document.createElement('details'); details.open=true;
    const summary=document.createElement('summary'); summary.textContent=conflict.name;
    const pre=document.createElement('pre'); pre.style.whiteSpace='pre-wrap'; pre.style.overflowWrap='anywhere'; pre.textContent=comparison.comparison;
    details.append(summary,pre); $('incoming-comparisons').append(details);
  }
  $('incoming-conflicts').scrollIntoView({block:'start'});
}
$('assignment-rows').addEventListener('change',async event=>{
  const name=event.target.dataset.assignmentSkill, agent=event.target.dataset.assignmentAgent;
  if(!name || previewBusy) return;
  const before=structuredClone(draft); assignmentErrors={}; previewBusy=true;
  const selected=new Set(draft[name]); event.target.checked?selected.add(agent):selected.delete(agent); draft[name]=[...selected];
  const sequence=++previewSequence;
  $('assignment-apply').disabled=true;
  renderAssignments();
  try {
    const result=await api('/api/assignment/preview',{changes:changes()});
    if(sequence!==previewSequence) return;
    if(result.revision!==management.revision) throw new Error('目录内容已经变了，请重新盘点后再勾选。');
    pendingPlan=result; draft=result.assignments;
  } catch(error) {if(sequence===previewSequence) {draft=before;assignmentErrors[name+'|'+agent]='这次勾选没改成：'+error.message;manageError(error);}}
  finally {previewBusy=false;renderAssignments();}
});
$('assignment-rows').addEventListener('click',async event=>{
  const button=event.target.closest('button'); if(!button?.dataset.addDependency && !button?.dataset.removeDependency) return;
  if(changes().length) {manageError(new Error('请先应用或取消待分配的改动，再修改需要的技能。'));return;}
  const name=button.dataset.addDependency||button.dataset.dependencySkill, dependency=button.dataset.removeDependency||prompt('输入需要的技能名称（须已在仓库中）：');
  if(!dependency || !confirm(`${name} ${button.dataset.addDependency?'添加':'删除'}需要的技能 ${dependency}？添加时会一起分配给使用它的助手，删除关系时保留现有分配。可以撤销。`)) return;
  button.disabled=true; try {await api('/api/dependencies',{decisions:[{skill:name,requires:dependency.trim(),confirmed:!!button.dataset.addDependency}],revision:management.revision,confirmed:true});await refreshManagement();}
  catch(error) {manageError(error);button.disabled=false;}
});
$('assignment-search').addEventListener('input',renderAssignments);
$('assignment-discard').addEventListener('click',()=>{draft=Object.fromEntries(management.skills.map(s=>[s.name,[...s.assigned_agents]]));pendingPlan=undefined;renderAssignments();});
$('manage-refresh').addEventListener('click',refreshManagement);
$('global-new-open').addEventListener('click',()=>document.querySelector('[data-panel="assignments"]').click());
$('log-refresh').addEventListener('click',refreshLog);
$('assignment-apply').addEventListener('click',async()=>{
  if(!pendingPlan) return;
  const warnings=[...pendingPlan.dependency_warnings,...pendingPlan.path_warnings.map(w=>'受影响的文件：'+w.file)];
  const text=pendingPlan.message+'。完成后可以在操作记录中撤销。'+(warnings.length?'\n\n'+warnings.join('\n'):'');
  if(!confirm(text)) return;
  $('assignment-apply').disabled=true;
  try {await api('/api/assignment/apply',{changes:changes(),revision:management.revision,confirmed:true});await refreshManagement();data=await api('/api/scan');render();}
  catch(error){manageError(error);}
});
$('absorb-all').addEventListener('click',async()=>{
  if(!confirm(`将把 ${management.new_skills.length} 个新装技能收进统一仓库，保持原来的可见范围。可以在操作记录中撤销。`)) return;
  $('absorb-all').disabled=true;
  try {const result=await api('/api/absorb',{all:true,revision:management.revision,confirmed:true});if(result.conflicts) await showConflicts(result);else {await refreshManagement();data=await api('/api/scan');render();}}
  catch(error){manageError(error);} finally {$('absorb-all').disabled=!management.write_allowed;}
});
$('operation-list').addEventListener('click',async event=>{
  const id=event.target.dataset.undo;if(!id) return;
  if(!confirm('将撤销这次操作，并恢复相应的内容、分配入口和工具添加的停用设置。后来的操作有重叠时会提示先撤销后来的操作。')) return;
  event.target.disabled=true;
  try {await api('/api/undo',{id,revision:management.revision,confirmed:true});await refreshManagement();data=await api('/api/scan');render();}
  catch(error){manageError(error);event.target.disabled=false;}
});
$('install-open').addEventListener('click',()=>{
  installReview=undefined;$('install-skills').innerHTML='';$('install-message').textContent='';$('install-apply').disabled=true;
  $('install-agents').innerHTML=management.agents.map(a=>`<label><input type="checkbox" data-install-agent="${escape(a.id)}"> ${escape(a.name)}</label>`).join('');
  $('install-dialog').showModal();
});
$('install-close').addEventListener('click',()=>$('install-dialog').close());
$('install-inspect').addEventListener('click',async()=>{
  $('install-inspect').disabled=true;$('install-message').textContent='正在读取仓库…';
  try {
    installReview=await api('/api/install/inspect',{url:$('install-url').value.trim()});
    $('install-skills').innerHTML=installReview.skills.map(s=>`<p><label><input type="checkbox" data-install-skill="${escape(s.name)}"> ${escape(s.name)}</label><small>${escape(s.description.slice(0,160))}</small>${installReview.conflicts.some(c=>c.name===s.name)?'<small>仓库里已有同名技能，安装时将转入对比。</small>':''}</p>`).join('');
    $('install-message').textContent=`找到 ${installReview.skills.length} 个技能。请勾选要安装的。`;
    $('install-apply').disabled=!installReview.skills.length;
  } catch(error){$('install-message').textContent=error.message;} finally {$('install-inspect').disabled=false;}
});
$('install-apply').addEventListener('click',async()=>{
  const skills=[...document.querySelectorAll('[data-install-skill]:checked')].map(s=>s.dataset.installSkill);
  const agents=[...document.querySelectorAll('[data-install-agent]:checked')].map(a=>a.dataset.installAgent);
  if(!skills.length) {$('install-message').textContent='请至少勾选一个技能。';return;}
  if(!confirm(`将安装 ${skills.length} 个技能，${agents.length?'分配给所选助手':'暂不分配给助手'}。可以在操作记录中撤销。`)) return;
  $('install-apply').disabled=true;
  try {const result=await api('/api/install/apply',{review_id:installReview.id,skills,agents,revision:management.revision,confirmed:true});$('install-dialog').close();if(result.conflicts) await showConflicts(result,installReview.id);else {await refreshManagement();data=await api('/api/scan');render();}}
  catch(error){$('install-message').textContent=error.message;} finally {$('install-apply').disabled=false;}
});
refreshManagement();

let updateReview, updateMerges = {}, updatesBusy = false, updateSequence = 0;
function updateError(error) {
  $('updates-error').hidden=false;
  $('updates-error').textContent=error.message;
}
function renderUpdates(review) {
  if(!review) return;
  if(review.id!==updateReview?.id) { $('updates-list').innerHTML=''; updateMerges={}; }
  updateReview=review;
  const text=`${review.running?'正在检查':'检查完成'}：共 ${review.total} 个技能 / ${review.repositories} 个仓库，已查 ${review.done}，剩 ${review.remaining}。${review.running?'正在查：'+(review.current.join('、')||'准备中')+'。':''}有更新 ${review.update_count}，已是最新 ${review.latest_count}，没查成 ${review.errors.length}。${review.lark?.message||''}${review.write_allowed?'':'当前为只读模式。'}`;
  $('updates-status').textContent=text; $('updates-progress').textContent=text; $('updates-progress').hidden=!review.running;
  $('updates-check').disabled=review.running||updatesBusy; $('withdrawn-check').disabled=review.running||updatesBusy;
  for(const s of review.skills) {
    let row=[...$('updates-list').querySelectorAll('[data-update-row]')].find(e=>e.dataset.updateRow===s.name);
    if((s.has_update||['已更新','已保留我的'].includes(s.status))&&!row) $('updates-list').insertAdjacentHTML('beforeend', `<article class="version" data-update-row="${escape(s.name)}">
      <p data-update-state>${s.baseline_uncertain?'无法判断你是否改过，默认用上游的。':''}</p><h3><label><input type="checkbox" data-update-skill="${escape(s.name)}" ${updateReview.write_allowed&&!s.blocked_reason?'':'disabled'}> ${escape(s.name)}</label> <span class="badge">${s.baseline_uncertain?'改动情况不确定':s.local_modified?'你改过':'本机没改过'}</span></h3>
      <p>来源：${escape(s.source.label)} · 上游更新：${escape(s.updated_at||'官方未提供日期')}</p>
      <p>${s.file_count} 个文件，新增 ${s.added_lines} 行，删除 ${s.removed_lines} 行</p>
      ${s.blocked_reason?`<div class="notice warn">${escape(s.blocked_reason)}</div>`:''}
      ${s.script_files.length?`<div class="notice warn"><strong>脚本或执行权限有变化，请先看</strong><p>${s.script_files.map(escape).join('、')}</p>${(s.risk_hits||[]).map(hit=>`<p><strong>${escape(hit.file)}</strong>：${escape(hit.line)}</p>`).join('')}</div>`:''}
      <details><summary>完整对比</summary><div class="update-comparisons">${s.local_modified?`<div><h3>你的改动</h3><pre>${escape(s.your_changes.comparison||'没有文本变化')}</pre></div>`:''}<div><h3>${s.baseline_uncertain?'上游当前版本与本机的差别':'上游的改动'}</h3><pre>${escape(s.comparison)}</pre></div></div></details>
      <button class="badge" data-update-explain="${escape(s.name)}">让 Codex 用大白话解释这次更新</button><p data-update-explanation></p>
      ${s.local_modified!==false?`<label>处理方式 <select data-update-choice="${escape(s.name)}"><option value="upstream">用上游的（默认）</option><option value="keep">保留我的</option></select></label><button class="badge" data-update-merge="${escape(s.name)}">交给 Codex 合并（可选）</button><div data-update-merged></div>`:''}
      <button class="badge" data-update-one="${escape(s.name)}" ${updateReview.write_allowed&&!s.blocked_reason?'':'disabled'}>${s.source.kind==='lark'?'更新整组飞书技能':'更新'}</button>
    </article>`);
    row??=[...$('updates-list').querySelectorAll('[data-update-row]')].find(e=>e.dataset.updateRow===s.name);
    if(row&&!s.has_update) {
      row.querySelector('[data-update-state]').textContent=s.status;
      row.querySelectorAll('input,select,button').forEach(e=>e.disabled=true);
    }
  }
  $('updates-other').innerHTML=(review.lark?`<p><strong>飞书工具</strong> · ${escape(review.lark.message)}</p>`:'')+review.skills.filter(s=>!s.has_update).map(s=>`<p><strong>${escape(s.name)}</strong> · ${escape(s.status)}${s.error?' · '+escape(s.error):''}</p>`).join('');
  const larkReady=review.skills.filter(s=>s.source?.kind==='lark').length===review.lark?.skill_count;
  for(const button of $('updates-list').querySelectorAll('[data-update-one]')) {
    const skill=review.skills.find(s=>s.name===button.dataset.updateOne);
    button.disabled=updatesBusy||!review.write_allowed||!skill?.has_update||!!skill.blocked_reason||(skill.source.kind==='lark'&&!larkReady);
  }
  $('updates-apply').disabled=updatesBusy||!review.write_allowed||!review.update_count;
  $('updates-all').disabled=$('updates-apply').disabled;
}
async function refreshUpdates() {
  const sequence=++updateSequence;
  try {const review=await api('/api/updates/progress');if(sequence===updateSequence) renderUpdates(review);}
  catch(error) {if(sequence===updateSequence) updateError(error);}
}
async function checkUpdates(withdrawn=false) {
  updateSequence++;
  $('updates-check').disabled=true; $('withdrawn-check').disabled=true; $('updates-error').hidden=true;
  $('updates-progress').hidden=false; $('updates-progress').textContent='正在准备检查名单…';
  try {renderUpdates(await api('/api/updates/check',{withdrawn}));}
  catch(error) {updateError(error);$('updates-progress').hidden=true;$('updates-check').disabled=false;$('withdrawn-check').disabled=false;}
}
$('updates-check').addEventListener('click',()=>checkUpdates());
$('withdrawn-check').addEventListener('click',()=>{
  document.querySelector('[data-panel="updates"]').click();checkUpdates(true);
});
refreshUpdates();
setInterval(()=>{if(updateReview?.running&&!updatesBusy) refreshUpdates();},1000);
$('updates-list').addEventListener('change',async event=>{
  if(event.target.dataset.updateChoice&&event.target.value==='keep') {
    const row=event.target.closest('[data-update-row]'); row.querySelector('[data-update-merged]').textContent='正在找你改过的地方…'; event.target.disabled=true; updatesBusy=true;renderUpdates(updateReview);
    try {const result=await api('/api/updates/calibrate',{review_id:updateReview.id,name:event.target.dataset.updateChoice});row.querySelector('[data-update-merged]').textContent=result.comparison||'没有发现你改过的地方。';}
    catch(error) {event.target.value='upstream';row.querySelector('[data-update-merged]').textContent=error.message;updateError(error);}
    finally {event.target.disabled=false;updatesBusy=false;renderUpdates(updateReview);}
  }
  const name=event.target.dataset.updateSkill;
  if(!name||updateReview.skills.find(s=>s.name===name)?.source.kind!=='lark') return;
  document.querySelectorAll('[data-update-skill]').forEach(input=>{
    if(updateReview.skills.find(s=>s.name===input.dataset.updateSkill)?.source.kind==='lark') input.checked=event.target.checked;
  });
});
$('updates-list').addEventListener('click',async event=>{
  const button=event.target.closest('button');
  if(!button) return;
  const name=button.dataset.updateExplain||button.dataset.updateMerge||button.dataset.updateAccept||button.dataset.updateOne;
  if(button.dataset.updateOne) { await applyUpdates([name]); return; }
  const row=button.closest('[data-update-row]');
  if(button.dataset.updateAccept) {
    if(confirm('把这份合并结果加入待更新名单？按“更新选中的”后才生效，可以撤销。')) {
      updateMerges[name].accepted=true;
      row.querySelector('[data-update-choice]').add(new Option('采用已核对的合并结果','merge',true,true));
      row.querySelector('[data-update-skill]').checked=true;
      button.textContent='已核对合并结果';button.disabled=true;
    }
    return;
  }
  button.disabled=true;
  try {
    if(button.dataset.updateExplain) {
      row.querySelector('[data-update-explanation]').textContent='Codex 正在解释…';
      const result=await api('/api/updates/explain',{review_id:updateReview.id,name});
      row.querySelector('[data-update-explanation]').textContent=result.explanation;
    } else if(button.dataset.updateMerge) {
      row.querySelector('[data-update-merged]').textContent='正在找你改过的地方…随后交给 Codex 合并。';
      const result=await api('/api/updates/merge',{review_id:updateReview.id,name});
      updateMerges[name]={id:result.merge_id,accepted:false};
      row.querySelector('[data-update-merged]').innerHTML=`<h3>合并预览</h3><p>${escape(result.explanation)}</p>${result.script_files.length?`<div class="notice warn"><strong>合并后脚本或执行权限有变化</strong><p>${result.script_files.map(escape).join('、')}</p></div>`:''}<details open><summary>合并后与本机的差别</summary><pre>${escape(result.comparison||'内容相同')}</pre></details><button class="badge" data-update-accept="${escape(name)}">我已看过这份合并结果</button>`;
    }
  } catch(error) {updateError(error);}
  finally {button.disabled=false;}
});
async function applyUpdates(skills) {
  if(updatesBusy) return;
  if(skills.some(name=>updateReview.skills.find(s=>s.name===name)?.source.kind==='lark'))
    skills=[...new Set([...skills,...updateReview.skills.filter(s=>s.has_update&&s.source.kind==='lark').map(s=>s.name)])];
  const choices={},merge_ids={};
  let confirm_lark_cli=false;
  try {
    if(!skills.length) throw new Error('请先勾选要更新的技能。');
    for(const name of skills) {
      const select=[...document.querySelectorAll('[data-update-choice]')].find(e=>e.dataset.updateChoice===name);
      if(select) {
        choices[name]=select.value;
        if(select.value==='merge') {
          if(!updateMerges[name]?.accepted) throw new Error(name+'：请先生成合并结果并确认已看过。');
          merge_ids[name]=updateMerges[name].id;
        }
      }
    }
    if(skills.some(name=>updateReview.skills.find(s=>s.name===name).source.kind==='lark')) {
      if(!confirm('这会同时升级 lark-cli 和整组飞书技能。确认一起更新？可以撤销。')) return;
      confirm_lark_cli=true;
    }
    if(!confirm(`核对并更新选中的 ${skills.length} 个技能？分配保持原样，可以在操作记录撤销。`)) return;
    updatesBusy=true; renderUpdates(updateReview);
    const result=await api('/api/updates/apply',{review_id:updateReview.id,skills,choices,merge_ids,confirm_lark_cli,confirmed:true});
    $('updates-status').textContent=result.message+'。可在操作记录撤销这次更新。';
    await refreshManagement();
    await refreshUpdates();
  } catch(error) {updateError(error);}
  finally {updatesBusy=false;renderUpdates(updateReview);}
}
$('updates-apply').addEventListener('click',()=>applyUpdates([...document.querySelectorAll('[data-update-skill]:checked')].map(e=>e.dataset.updateSkill)));
$('updates-all').addEventListener('click',()=>applyUpdates(updateReview.skills.filter(s=>s.has_update&&!s.blocked_reason).map(s=>s.name)));

let cleanupView, cleanupSelected = new Set();
const agentLabel = id => mainAgents.find(a=>a[0]===id)?.[1] || id;
const lastUse = row => row.last_used_at ? `${agentLabel(row.last_agent)} · ${row.last_used_at.slice(0,10)}` : '没有使用记录';
const coverageText = coverage => Object.entries(coverage).map(([id,r])=>`${agentLabel(id)}：${r.message}`).join('\n');
async function refreshUsage() {
  if($('usage-refresh').disabled) return;
  let retry=false;
  $('usage-status').textContent='正在统计，首次读取历史记录可能需要几分钟。';
  $('usage-refresh').disabled=true;
  $('usage-progress').hidden=false; $('usage-progress').textContent='正在统计用量（第一次需要几分钟）';
  const timer=setInterval(async()=>{try {const p=await api('/api/usage-progress'); if(p.running) $('usage-progress').textContent=`正在统计用量：已读 ${p.done.toLocaleString()} / ${p.total.toLocaleString()} 份记录`;} catch {}},1000);
  try {
    const result=await api('/api/usage');
    $('usage-coverage').style.whiteSpace='pre-line';
    $('usage-coverage').textContent=coverageText(result.coverage);
    $('usage-rows').innerHTML=result.skills.map(s=>`<tr><td>${escape(s.name)}</td><td>${escape(lastUse(s))}</td><td>${escape(Object.entries(s.sessions_30d).map(([a,n])=>`${agentLabel(a)} ${n}`).join('；')||'0')}</td></tr>`).join('');
    $('usage-status').textContent='统计完成。';
    if(management) {
      for(const s of management.skills) {
        const used=result.skills.find(r=>r.name===s.name);
        s.last_used=Object.fromEntries(management.agents.map(a=>[a.id,result.coverage[a.id]?.available ? used?.last_used[a.id]?.slice(0,10)||'没有使用记录' : '统计不到']));
      }
      renderAssignments();
    }
  } catch(error) {$('usage-status').textContent=error.message;retry=error.retry;if(retry) setTimeout(refreshUsage,1000);}
  finally {clearInterval(timer);$('usage-progress').hidden=!retry;$('usage-refresh').disabled=false;}
}
function renderCleanup() {
  if(!cleanupView) return;
  $('cleanup-rows').innerHTML=cleanupView.candidates.map(s=>`<tr><td><input type="checkbox" data-cleanup="${escape(s.name)}" aria-label="清理 ${escape(s.name)}" ${cleanupSelected.has(s.name)?'checked':''}></td><td>${escape(s.name)}</td><td>${escape(s.assigned_agents.map(agentLabel).join('、'))}</td><td>${escape(lastUse(s))}</td><td>${s.description_chars}</td></tr>`).join('')||'<tr><td colspan="5">没有符合条件的清理技能。</td></tr>';
  renderCleanupTotals();
  $('withdrawn-list').innerHTML=cleanupView.withdrawn.map(s=>`<div class="version"><strong>${escape(s.name)}</strong><p>原来分配给 ${escape(s.previous_agents.map(agentLabel).join('、'))}</p><button class="badge" data-restore-withdrawn="${escape(s.name)}" ${cleanupView.write_allowed?'':'disabled'}>恢复原分配</button></div>`).join('')||'<p>还没有已撤下的技能。</p>';
}
function renderCleanupTotals() {
  $('cleanup-savings').innerHTML=Object.keys(cleanupView.coverage).map(a=>`<article class="card"><h3>${escape(agentLabel(a))}</h3><p>本次撤下后可省 ${cleanupView.candidates.filter(s=>cleanupSelected.has(s.name)&&s.assigned_agents.includes(a)).reduce((n,s)=>n+s.description_chars,0).toLocaleString()} 字描述</p></article>`).join('');
  $('cleanup-apply').textContent=`清理选中的 ${cleanupSelected.size} 个`;
  // An all-kept submission still records the user's keep choices.
  $('cleanup-apply').disabled=!cleanupView.write_allowed||!cleanupView.candidates.length;
}
async function refreshCleanup() {
  $('cleanup-status').textContent='正在统计，完成后再生成名单。';
  $('cleanup-rows').innerHTML=''; $('cleanup-apply').disabled=true;
  $('cleanup-refresh').disabled=true;
  try {
    cleanupView=await api('/api/cleanup');
    cleanupSelected=new Set(cleanupView.candidates.map(s=>s.name));
    $('cleanup-coverage').style.whiteSpace='pre-line';
    $('cleanup-coverage').textContent=coverageText(cleanupView.coverage);
    $('cleanup-error').hidden=true;$('withdrawn-error').hidden=true;
    $('cleanup-status').textContent=`共有 ${cleanupView.candidates.length} 个候选。`;
    renderCleanup();
  } catch(error) {$('cleanup-status').textContent=error.message;}
  finally {$('cleanup-refresh').disabled=false;}
}
$('usage-refresh').addEventListener('click',refreshUsage);
$('cleanup-refresh').addEventListener('click',refreshCleanup);
$('withdrawn-refresh').addEventListener('click',refreshCleanup);
$('cleanup-rows').addEventListener('change',event=>{
  const name=event.target.dataset.cleanup;if(!name) return;
  event.target.checked?cleanupSelected.add(name):cleanupSelected.delete(name);renderCleanupTotals();
});
$('cleanup-apply').addEventListener('click',async()=>{
  const keep=cleanupView.candidates.filter(s=>!cleanupSelected.has(s.name)).map(s=>s.name);
  const warnings=cleanupView.candidates.filter(s=>cleanupSelected.has(s.name)).flatMap(s=>s.path_warnings.map(w=>'受影响的文件：'+w.file));
  const text=`将从所有助手撤下 ${cleanupSelected.size} 个技能，文件保留，可在操作记录中撤销。取消勾选的 ${keep.length} 个会记为今天留下。`+(warnings.length?'\n\n'+[...new Set(warnings)].join('\n'):'');
  if(!confirm(text)) return;
  $('cleanup-apply').disabled=true;
  try {
    await api('/api/cleanup/apply',{keep,candidates:cleanupView.candidates.map(s=>s.name),revision:cleanupView.revision,confirmed:true});
    await refreshCleanup();await refreshManagement();data=await api('/api/scan');render();
  } catch(error) {$('cleanup-error').hidden=false;$('cleanup-error').textContent=error.message;}
});
$('withdrawn-list').addEventListener('click',async event=>{
  const name=event.target.dataset.restoreWithdrawn;if(!name) return;
  if(!confirm(`将恢复 ${name} 原来的分配，可以在操作记录中撤销。确认恢复吗？`)) return;
  try {await api('/api/withdrawn/restore',{skills:[name],revision:cleanupView.revision,confirmed:true});await refreshCleanup();await refreshManagement();data=await api('/api/scan');render();}
  catch(error) {$('withdrawn-error').hidden=false;$('withdrawn-error').textContent=error.message;}
});
for(const panel of ['usage','cleanup','withdrawn']) document.querySelector(`[data-panel="${panel}"]`).addEventListener('click',()=>{
  if(panel==='usage') refreshUsage();else refreshCleanup();
});
refreshUsage();
