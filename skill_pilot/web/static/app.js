/* Skill Pilot 看板。
   分段：通用工具 → 页头与导航 → 技能页 → 技能详情 → 安装技能 → 接入新 agent →
        检查更新页 → 清理页 → 操作记录页 → 诊断与备份页 → 设置页 → 启动。
   页面不写死任何具体 agent：名字、顺序、生效方式都来自接口。 */

/* ==================== 通用工具：请求、转义、提示、确认框、按钮忙碌态 ==================== */

const token = new URLSearchParams(location.search).get('token');
const headers = {'X-Skill-Pilot-Token': token};

const $ = id => document.getElementById(id);
const escape = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const clone = value => JSON.parse(JSON.stringify(value));

async function api(path, body) {
  const options = body === undefined
    ? {headers}
    : {method: 'POST', headers: {...headers, 'Content-Type': 'application/json'}, body: JSON.stringify(body)};
  const response = await fetch(path, options);
  let result = null;
  try { result = await response.json(); } catch { /* 没有内容时按下面的默认文案处理 */ }
  if (!response.ok) {
    const error = new Error((result && result.error) || '操作没能完成，请稍后再试。');
    error.retry = Boolean(result && result.retry);
    throw error;
  }
  return result;
}

/* 按钮忙碌态：按下后先禁用并换文案，做完再恢复。 */
async function withBusy(button, label, work) {
  if (!button) return work();
  const original = button.textContent;
  button.disabled = true;
  button.setAttribute('aria-busy', 'true');
  if (label) button.textContent = label;
  try {
    return await work();
  } finally {
    button.removeAttribute('aria-busy');
    button.disabled = false;
    button.textContent = original;
  }
}

/* 确认框：全站唯一的确认方式，不用浏览器自带的弹窗。
   groups 是 [{label, items:[{name, note}]}]，按组列出这次会动到哪些技能。 */
const CONFIRM_FOLD = 8;

function confirmItems(items) {
  return items.map(item => `<li>${nameHtml(item.name)}${item.note ? `<span class="confirm-note-inline">（${escape(item.note)}）</span>` : ''}</li>`).join('');
}

function confirmGroupsHtml(groups) {
  return (groups || []).filter(group => group.items.length).map(group => {
    const shown = group.items.slice(0, CONFIRM_FOLD);
    const rest = group.items.slice(CONFIRM_FOLD);
    return `<div class="confirm-group">
      <p class="confirm-group-title">${escape(group.label)}</p>
      <ul class="confirm-items">${confirmItems(shown)}</ul>
      ${rest.length ? `<div hidden><ul class="confirm-items">${confirmItems(rest)}</ul></div>
        <button type="button" class="link-btn" data-confirm-more>展开其余 ${rest.length} 个</button>` : ''}
    </div>`;
  }).join('');
}

function confirmDialog({title = '确认这次操作', lines = [], groups = [], note = '', okText = '确认'}) {
  const dialog = $('confirm-dialog');
  $('confirm-title').textContent = title;
  $('confirm-body').innerHTML = lines.filter(Boolean).map(line => `<p class="confirm-line">${escape(line)}</p>`).join('')
    + confirmGroupsHtml(groups)
    + (note ? `<p class="confirm-note">${escape(note)}</p>` : '');
  $('confirm-ok').textContent = okText;
  return new Promise(resolve => {
    dialog.addEventListener('close', () => resolve(dialog.returnValue === 'ok'), {once: true});
    dialog.showModal();
  });
}

$('confirm-body').addEventListener('click', event => {
  const button = event.target.closest('[data-confirm-more]');
  if (!button) return;
  button.previousElementSibling.hidden = false;
  button.remove();
});

/* 提示条：成功会自己消失，出错留着让用户看清。
   带撤销的提示，撤销自己也会先弹确认框，用户取消时提示条留着。 */
function toast({text, tone = 'ok', undo = null, sticky = false}) {
  const item = document.createElement('div');
  item.className = 'toast' + (tone === 'error' ? ' toast-error' : '');
  const message = document.createElement('p');
  message.textContent = text;
  item.append(message);
  if (undo) {
    const button = document.createElement('button');
    button.className = 'btn btn-small';
    button.textContent = '撤销';
    button.addEventListener('click', async () => {
      button.disabled = true;
      try {
        const done = await undo(button);
        if (done === false) { button.disabled = false; return; }
        item.remove();
      } catch (error) {
        button.disabled = false;
        toast({text: error.message, tone: 'error', sticky: true});
      }
    });
    item.append(button);
  }
  const close = document.createElement('button');
  close.className = 'toast-close';
  close.textContent = '关闭';
  close.setAttribute('aria-label', '关闭这条提示');
  close.addEventListener('click', () => item.remove());
  item.append(close);
  $('toasts').prepend(item);
  if (!sticky && tone !== 'error') autoDismiss(item, undo ? 20000 : 6000);
}

/* 自动消失：带撤销的提示至少留 20 秒，鼠标移上去或键盘聚焦时暂停。 */
function autoDismiss(item, delay) {
  let timer = setTimeout(() => item.remove(), delay);
  const pause = () => { clearTimeout(timer); timer = null; };
  const resume = () => { if (!timer && item.isConnected) timer = setTimeout(() => item.remove(), delay); };
  item.addEventListener('mouseenter', pause);
  item.addEventListener('mouseleave', resume);
  item.addEventListener('focusin', pause);
  item.addEventListener('focusout', resume);
}

/* 页头任务条：后台在做什么都显示在这里。
   任务刚起的前 700 毫秒不画出来，太快完成的任务就不会闪一下；
   做完直接消失，不显示「完成」那一行（那一行会把下面的内容顶下去）。 */
const tasks = new Map();
const TASK_QUIET_MS = 700;

function setTask(id, task) {
  const startedAt = tasks.get(id)?.startedAt ?? Date.now();
  tasks.set(id, {...task, startedAt});
  renderTasks();
  if (task.quietMs && Date.now() - startedAt < task.quietMs) {
    setTimeout(renderTasks, task.quietMs - (Date.now() - startedAt) + 20);
  }
}

function clearTask(id) {
  tasks.delete(id);
  renderTasks();
}

function renderTasks() {
  const bar = $('task-bar');
  const now = Date.now();
  const entries = [...tasks.entries()]
    .filter(([, task]) => !task.quietMs || now - task.startedAt >= task.quietMs);
  bar.hidden = !entries.length;
  bar.innerHTML = entries.map(([id, task]) => {
    const ratio = typeof task.ratio === 'number' ? task.ratio : null;
    const action = task.retry
      ? `<button class="btn btn-small" data-task-retry="${escape(id)}">重试</button>`
      : task.tone === 'error' ? `<button class="btn btn-small" data-task-dismiss="${escape(id)}">关闭</button>` : '';
    // 有具体进度就画进度条，没有就画一条来回走的细条，表示还在做。
    const track = ratio !== null
      ? `<span class="task-track"><span class="task-fill" data-ratio="${Math.max(0, Math.min(1, ratio))}"></span></span>`
      : task.tone === 'error' ? '' : '<span class="task-track task-track-busy"><span class="task-fill"></span></span>';
    return `<div class="task task-${escape(task.tone || 'busy')}">
      <span class="task-text">${escape(task.text)}</span>
      ${track}
      ${action}
    </div>`;
  }).join('');
  for (const fill of bar.querySelectorAll('[data-ratio]')) {
    fill.style.setProperty('--ratio', fill.dataset.ratio);
  }
}

$('task-bar').addEventListener('click', event => {
  const retryId = event.target.dataset.taskRetry;
  const dismissId = event.target.dataset.taskDismiss;
  if (retryId) {
    const task = tasks.get(retryId);
    clearTask(retryId);
    task?.retry?.();
  } else if (dismissId) {
    clearTask(dismissId);
  }
});

/* 写入过程的统一反馈。确认框点过之后调用：
   - 触发这次写入的按钮（底部操作栏或列表里的那个，不是确认框里的）换文案并禁用；
   - 全站会改动这次写入内容的控件一并禁用，中途重新渲染也保持禁用；
   - 页头任务条显示同一句话；
   - 成功：先恢复控件，再弹绿色提示；失败：先恢复控件，再弹红色提示，
     任务条转成错误样式（写入不给「重试」，让用户看清原因自己决定）。
   返回 work() 的结果；失败返回 null，不往外抛。 */
const WRITE_LOCK_SELECTORS = [
  '#skills-rows input[data-skill]', '#action-bar button', '#skills-refresh', '#skills-install',
  '#cleanup-rows input[data-cleanup]', '#withdrawn-list button', '#withdrawn-refresh', '#withdrawn-check',
  '#updates-list input', '#updates-list select', '#updates-list button', '#updates-check',
  '#log-list button', '#log-refresh', '#detail-body button', '#detail-body select',
  '#new-absorb', '#new-toggle', '#install-dialog input', '#install-dialog button',
  '#agents-managed button', '#agents-suggested button', '#agents-ignored button', '#agents-join-dialog input', '#agents-join-dialog button',
  '#migration-preview', '#migration-apply', '#migration-back', '#migration-agents input',
  '#migration-versions input', '#migration-backups', '#migration-restore', '#migration-backup-list button',
];

let writeBusy = null;

function lockControls(selectors) {
  const changed = [];
  for (const element of document.querySelectorAll(selectors.join(','))) {
    if (element.disabled) continue;
    element.disabled = true;
    changed.push(element);
  }
  return () => { for (const element of changed) element.disabled = false; };
}

/* 正在写入时把各区重画一遍，让新画出来的控件也是禁用的。 */
function renderBusyAreas() {
  renderSkillTable();
  renderSkillsActionBar();
  renderCleanup();
  renderCleanupActionBar();
  renderUpdates();
  renderLog();
  if (state.detail) renderDetail();
}

async function runWrite({button = null, busyText, taskText = busyText, success = null, onError = null, work}) {
  const original = button?.textContent ?? null;
  writeBusy = busyText;
  if (button) {
    button.disabled = true;
    button.setAttribute('aria-busy', 'true');
    button.textContent = busyText;
  }
  // 写入是用户按下的，任务条立刻出现；防闪烁只用在后台任务上。
  setTask('write', {text: taskText});
  // 这里不重画各区：重画会把刚换成「正在…」的按钮换掉。
  // 禁用交给 lockControls；万一中途有重画，各区自己会看 writeBusy 保持禁用。
  const unlock = lockControls(WRITE_LOCK_SELECTORS);

  let result = null;
  let failure = null;
  try {
    result = await work();
  } catch (error) {
    failure = error;
  }

  writeBusy = null;
  unlock();
  if (button) {
    button.removeAttribute('aria-busy');
    button.textContent = original;
  }
  renderBusyAreas();

  if (failure) {
    setTask('write', {text: failure.message, tone: 'error'});
    onError?.(failure);
    toast({text: failure.message, tone: 'error', sticky: true});
    return null;
  }
  clearTask('write');
  const notice = success?.(result);
  if (notice) toast(notice);
  return result;
}

/* 底部固定操作栏：只在有事情可做时出现。 */
function showActionBar({text, note = '', buttons = []}) {
  $('action-summary').textContent = text;
  $('action-note').textContent = note;
  $('action-note').hidden = !note;
  const box = $('action-buttons');
  box.innerHTML = '';
  for (const item of buttons) {
    const button = document.createElement('button');
    button.className = item.kind || 'btn';
    button.textContent = item.label;
    button.disabled = Boolean(item.disabled);
    button.addEventListener('click', () => item.action(button));
    box.append(button);
  }
  const bar = $('action-bar');
  bar.hidden = false;
  document.body.classList.add('has-action-bar');
  requestAnimationFrame(() => bar.classList.add('is-open'));
}

function hideActionBar() {
  const bar = $('action-bar');
  bar.classList.remove('is-open');
  document.body.classList.remove('has-action-bar');
  $('action-buttons').innerHTML = '';
  setTimeout(() => { if (!$('action-bar').classList.contains('is-open')) bar.hidden = true; }, 200);
}

/* 心跳：看板关掉后立刻告诉用户。
   浏览器会放慢甚至暂停后台标签页的计时，所以每个页面带上自己的编号，关闭时再说一声，
   后台据此判断还有没有页面开着，而不是只看心跳间隔。 */
const pageId = Math.random().toString(36).slice(2);
async function heartbeat() {
  try {
    const response = await fetch('/api/heartbeat?page=' + pageId, {method: 'POST', headers});
    if (!response.ok) throw new Error();
    $('connection').hidden = true;
  } catch {
    $('connection').hidden = false;
  }
}

/* 撤销：先确认，再取最新状态，避免用过期版本号。
   button 是触发这次撤销的那个按钮（提示条上的或操作记录里的），由 runWrite 负责忙碌态。
   返回 false 表示用户取消了。 */
async function undoOperation(id, {skills = [], message = '', button = null} = {}) {
  const ok = await confirmDialog({
    title: '撤销这次操作',
    lines: [message ? `要撤销的是：${message}` : '会恢复相应的技能内容、分配入口和工具添加的停用设置。'],
    groups: skills.length ? [{label: `这次操作动过 ${skills.length} 个技能`, items: skills.map(name => ({name}))}] : [],
    note: '后来的操作和这次有重叠时，会提示先撤销后来的操作。撤销本身也会记在操作记录里。',
    okText: '撤销',
  });
  if (!ok) return false;
  const result = await runWrite({
    button,
    busyText: '正在撤销…',
    work: async () => {
      const table = await api('/api/table');
      await api('/api/undo', {id, revision: table.revision, confirmed: true});
      await refreshEverything();
      return true;
    },
    success: () => ({text: '已经撤销这次操作'}),
  });
  return result !== null;
}

/* ==================== 页头与导航：摘要条、页面切换、模式徽标 ==================== */

/* agent 的一切都来自接口：/api/table 给当前表里的 agent（顺序就是显示顺序），
   /api/agents 补齐名字、目录、生效方式、用量和接入建议。页面不认识任何具体 agent。 */
const state = {
  page: 'skills',
  writeAllowed: false,
  inventory: null,
  table: null,
  agents: [],
  agentsView: null,
  catalog: new Map(),
  skillIndex: new Map(),
  openGroups: new Set(),
  usage: null,
  usageIndex: new Map(),
  saved: {},
  draft: {},
  pending: null,
  pendingClick: null,
  autoAdded: new Map(),   // 「技能|agent」→ 需要它的那个技能（预览的 auto_added）
  detail: null,
  filter: 'all',
  cleanup: null,
  cleanupSelected: new Set(),
  cleanupTries: 0,
  logs: [],
};

/* 编号翻名字：先看接口给的目录，再退回表里的名字，都查不到就直接显示编号。 */
function nameOf(id) {
  const key = String(id ?? '');
  return state.catalog.get(key)?.name || state.agents.find(agent => agent.id === key)?.name || key;
}

/* 有些 agent 不在当前表里（操作记录、已撤下的技能），用 /api/agents 的名字兜底。 */
function agentName(id) {
  return nameOf(id);
}

function indexCatalog(view) {
  state.agentsView = view;
  const catalog = new Map();
  for (const item of [...(view?.managed || []), ...(view?.suggested || [])]) {
    if (item?.id) catalog.set(item.id, item);
  }
  state.catalog = catalog;
}

function homePath() {
  return state.table?.home || state.inventory?.home || '';
}

/* 同一个位置在 macOS 上可能写成 /var/… 也可能写成 /private/var/…，
   两个接口给的 home 写法不一定一样，所以两种都匹配。 */
function homeVariants() {
  const variants = new Set();
  for (const home of [state.table?.home, state.inventory?.home]) {
    if (!home) continue;
    variants.add(home);
    if (home.startsWith('/private/')) variants.add(home.slice('/private'.length));
    else if (home.startsWith('/var/') || home.startsWith('/tmp/')) variants.add('/private' + home);
  }
  return [...variants].sort((a, b) => b.length - a.length);
}

/* 技能目录在接口里是相对 home 的，先拼上 home 再缩写成 ~/…。 */
function rootsLabel(roots) {
  return (roots || []).map(root => pathLabel(homePath() + '/' + root)).join('、');
}

function pathLabel(path) {
  const text = String(path ?? '');
  for (const home of homeVariants()) {
    if (text === home) return '~';
    if (text.startsWith(home + '/')) return escape('~' + text.slice(home.length));
  }
  return escape(text);
}

const number = value => Number(value || 0).toLocaleString('zh-CN');

/* 技能的中文名来自本机整理结果（labels.json），没写的就用原名。
   nameHtml 把原名用小号灰字跟在中文名后面，方便和 agent 里看到的名字对上。 */
const titleOf = name => state.skillIndex.get(name)?.title || name;

function nameHtml(name) {
  const title = state.skillIndex.get(name)?.title;
  return title ? `${escape(title)} <span class="skill-id">${escape(name)}</span>` : escape(name);
}

/* 原始时间格式换成大白话日期；跨年才写年份。 */
function friendlyDate(value) {
  if (!value) return '';
  const time = Date.parse(value);
  if (Number.isNaN(time)) return String(value);
  const date = new Date(time);
  const text = `${date.getMonth() + 1} 月 ${date.getDate()} 日`;
  return date.getFullYear() === new Date().getFullYear() ? text : `${date.getFullYear()} 年 ${text}`;
}

/* agent 摘要：一格一个 agent，格数随 agent 数量自动换行。
   第二行平时写生效方式，有没应用的改动时换成本次应用后的数字，格子高度不变。 */
function renderAgentSummary() {
  const box = $('agent-summary');
  if (!state.agents.length) {
    box.innerHTML = '<p class="agent-chip"><span class="agent-line"><span class="agent-name muted">正在读取各 agent 情况…</span></span><span class="agent-note"></span></p>';
    return;
  }
  box.innerHTML = state.agents.map(agent => {
    const after = state.pending?.after?.[agent.id];
    const changed = after && (after.count !== agent.count || after.description_chars !== agent.description_chars);
    const scan = state.inventory?.agents?.find(a => a.id === agent.id);
    const tip = [
      `${agent.name}：${agent.activation_text}`,
      scan && scan.visible_skill_count !== null ? `现在实际能用 ${number(scan.visible_skill_count)} 个技能，说明 ${number(scan.description_chars)} 字` : '',
      changed ? `应用后 ${number(after.count)} 个技能，说明 ${number(after.description_chars)} 字` : '',
    ].filter(Boolean).join('；');
    const second = changed
      ? `<span class="agent-delta">应用后 ${number(after.count)} 个 / ${number(after.description_chars)} 字</span>`
      : escape(agent.activation_text || '');
    return `<div class="agent-chip" title="${escape(tip)}">
      <p class="agent-line"><span class="agent-name">${escape(agent.name)}</span>
        <span class="agent-stats">${number(agent.count)} 个技能 · <span class="agent-word">说明 </span>${number(agent.description_chars)} 字</span></p>
      <p class="agent-note">${second}</p>
    </div>`;
  }).join('');
}

function showPage(page) {
  state.page = page;
  for (const section of document.querySelectorAll('.page-section')) {
    section.hidden = section.id !== 'page-' + page;
  }
  for (const button of document.querySelectorAll('.nav-item')) {
    if (button.dataset.page === page) button.setAttribute('aria-current', 'page');
    else button.removeAttribute('aria-current');
  }
  if (page === 'updates') renderUpdates();
  if (page === 'cleanup') { renderCleanup(); loadCleanup(); }
  if (page === 'log') { renderLog(); refreshLog(); }
  if (page === 'diagnostics') renderDiagnostics();
  if (page === 'settings') { renderAgents(); refreshSettings(); }
  renderActionBar();
  window.scrollTo({top: 0, behavior: 'auto'});
}

document.querySelector('.nav').addEventListener('click', event => {
  const button = event.target.closest('.nav-item');
  if (button) showPage(button.dataset.page);
});

function renderActionBar() {
  if (state.page === 'skills') return renderSkillsActionBar();
  if (state.page === 'updates') return renderUpdatesActionBar();
  if (state.page === 'cleanup') return renderCleanupActionBar();
  return hideActionBar();
}

/* ==================== 技能页：表格、筛选、待应用改动 ==================== */

const STALE_DAYS = 60;
const PREVIEW_DEBOUNCE_MS = 100;
let previewBusy = false;
let previewSequence = 0;
let previewTimer = null;
let assignmentErrors = {};

function daysSince(value) {
  if (!value) return null;
  const time = Date.parse(value.length <= 10 ? value + 'T00:00:00' : value);
  if (Number.isNaN(time)) return null;
  return Math.floor((Date.now() - time) / 86400000);
}

/* 各 agent 里最近的一次使用，合成一句话。统计不到的 agent 不参与比较。 */
function lastUseLabel(name) {
  if (!state.usage) return {text: '还没统计', days: null};
  const coverage = state.usage.coverage || {};
  const available = state.agents.map(agent => agent.id).filter(id => coverage[id]?.available);
  if (!available.length) return {text: '统计不到', days: null};
  const row = state.usageIndex.get(name);
  const dates = available.map(id => row?.last_used?.[id]).filter(Boolean).sort();
  if (!dates.length) return {text: '从没用过', days: null};
  const days = daysSince(dates[dates.length - 1]);
  if (days === null) return {text: '从没用过', days: null};
  if (days <= 0) return {text: '今天用过', days: 0};
  if (days <= STALE_DAYS) return {text: `${days} 天前`, days};
  return {text: `${days} 天没用`, days};
}

function indexUsage(report) {
  state.usage = report;
  state.usageIndex = new Map((report?.skills || []).map(row => [row.name, row]));
}

function skillRows() {
  const query = $('skills-search').value.trim().toLowerCase();
  const filter = state.filter;
  return (state.table?.skills || []).filter(skill => {
    if (query && !(skill.name + ' ' + skill.title + ' ' + skill.summary + ' ' + skill.description).toLowerCase().includes(query)) return false;
    if (filter === 'unassigned') return !(state.draft[skill.name] || []).length;
    if (filter === 'modified') return Boolean(skill.local_modified);
    if (filter === 'dependency') return skill.requires.length > 0;
    if (filter === 'stale') {
      const label = lastUseLabel(skill.name);
      return label.days === null || label.days > STALE_DAYS;
    }
    return true;
  });
}

function emptySkillsText() {
  if ($('skills-search').value.trim()) return '没有找到这个技能，换个词试试。';
  if (state.filter === 'unassigned') return '每个技能都至少给了一个 agent。';
  if (state.filter === 'stale') return '没有很久没用的技能。';
  if (state.filter === 'modified') return '没有你改过的技能。';
  if (state.filter === 'dependency') return '没有带依赖的技能。';
  return '还没有登记任何技能。';
}

/* 这个格子还没应用：草稿和已应用的分配不一样。 */
function cellPending(skill, agent) {
  const assigned = state.draft[skill.name] || [];
  return assigned.includes(agent.id) !== skill.assigned_agents.includes(agent.id);
}

/* 依赖自动带上的格子：后台给的 auto_added 直接说清是哪个技能需要它。 */
function autoAddedBy(skillName, agentId) {
  return state.autoAdded.get(skillName + '|' + agentId) || '';
}

/* 依赖说明的句子，用中文名：“因为 多智能体分派 需要 营销技能路由，已一起勾上给某个 agent”。
   一个 agent 有多条时用“；”连起来；底部操作栏把所有 agent 的合在一起。 */
function autoAddedNote() {
  const parts = [];
  for (const agent of tableAgents()) {
    for (const [key, because] of state.autoAdded) {
      const [skill, agentId] = key.split('|');
      if (agentId !== agent.id) continue;
      parts.push(`因为 ${titleOf(because)} 需要 ${titleOf(skill)}，已一起勾上给 ${agent.name}`);
    }
  }
  return parts.join('；');
}

/* 格子下方的说明：有草稿看预览给的 cell_notes，没草稿看表里带的。 */
function cellNote(skill, agent) {
  const notes = state.pending ? state.pending.cell_notes?.[skill.name] : skill.cell_notes;
  return notes?.[agent.id] || '';
}

function tableAgents() {
  return state.agents;
}

function skillRowHtml(skill) {
  const assigned = state.draft[skill.name] || [];
  const locked = Boolean(writeBusy) || !state.table.write_allowed;
  const tags = [
    skill.local_modified ? '<span class="tag tag-warn">你改过</span>' : '',
    skill.requires.length ? '<span class="tag tag-quiet">有依赖</span>' : '',
  ].join('');
  const cells = tableAgents().map(agent => {
    const error = assignmentErrors[skill.name + '|' + agent.id];
    const note = cellNote(skill, agent);
    const pending = cellPending(skill, agent);
    const because = autoAddedBy(skill.name, agent.id);
    const mark = !pending ? '' : because
      ? `<small class="cell-mark cell-auto">自动带上</small>
        <small class="cell-note">因为 ${escape(titleOf(because))} 需要它</small>`
      : '<small class="cell-mark">待应用</small>';
    return `<td class="cell-check${pending ? ' cell-pending' : ''}">
      <label class="check-hit"><input type="checkbox" data-skill="${escape(skill.name)}" data-agent="${escape(agent.id)}"
        aria-label="${escape(agent.name + ' 使用 ' + titleOf(skill.name))}"
        ${assigned.includes(agent.id) ? 'checked' : ''} ${locked ? 'disabled' : ''}></label>
      ${mark}
      ${note ? `<small class="cell-note">${escape(note)}</small>` : ''}
      ${error ? `<small class="cell-note cell-error">${escape(error)}</small>` : ''}
    </td>`;
  }).join('');
  return `<tr data-skill-row="${escape(skill.name)}"${assigned.length ? '' : ' class="is-idle"'}>
    <td class="col-name">
      <div class="skill-line"><strong>${nameHtml(skill.name)}</strong>${tags}</div>
      <p class="skill-desc" title="${escape(skill.description)}">${escape(skill.summary || skill.description)}</p>
    </td>
    ${cells}
    <td class="col-last">${escape(lastUseLabel(skill.name).text)}</td>
    <td class="col-num">${number(skill.description_chars)}</td>
  </tr>`;
}

/* 分组：在用的技能多的组排在前面，还没整理的放到最后的「未分组」。
   组内已分配的在前、没分给任何 agent 的在后；都按已应用的分配排，勾选时不会跳。 */
function groupedRows(rows) {
  const byName = new Map(rows.map(skill => [skill.name, skill]));
  const listed = new Set();
  const idle = skill => ((state.saved[skill.name] || []).length ? 0 : 1);
  const inUse = group => group.skills.filter(skill => !idle(skill)).length;
  const groups = (state.table.groups || []).map(group => {
    group.skills.forEach(name => listed.add(name));
    return {name: group.name, skills: group.skills.map(name => byName.get(name)).filter(Boolean)};
  }).sort((a, b) => inUse(b) - inUse(a));
  groups.push({name: '未分组', skills: rows.filter(skill => !listed.has(skill.name))});
  return groups.filter(group => group.skills.length)
    .map(group => ({...group, skills: [...group.skills].sort((a, b) => idle(a) - idle(b))}));
}

/* 组标题行：各 agent 一栏写这一组分到了几个。搜索或筛选时各组都展开，不能收起。 */
function groupRowHtml(group, open, forced) {
  const inUse = group.skills.filter(skill => (state.draft[skill.name] || []).length).length;
  const counts = tableAgents().map(agent => {
    const count = group.skills.filter(skill => (state.draft[skill.name] || []).includes(agent.id)).length;
    return `<td class="cell-check group-count">${count || '—'}</td>`;
  }).join('');
  return `<tr class="group-row" data-group-row="${escape(group.name)}">
    <td class="col-name"><button type="button" class="group-toggle" aria-expanded="${open}" ${forced ? 'disabled' : ''}>
      <span class="group-arrow" aria-hidden="true"></span><strong>${escape(group.name)}</strong>
      <span class="group-meta">${group.skills.length} 个${inUse < group.skills.length ? `，${inUse} 个在用` : ''}</span>
    </button></td>
    ${counts}
    <td class="col-last"></td><td class="col-num"></td>
  </tr>`;
}

function renderSkillTable() {
  const agents = tableAgents();
  $('skills-head').innerHTML = '<th class="col-name">技能</th>'
    + agents.map(agent => `<th class="cell-check">${escape(agent.name)}</th>`).join('')
    + '<th class="col-last">最近使用</th><th class="col-num">说明字数</th>';

  const columns = agents.length + 3;
  if (!state.table) {
    $('skills-rows').innerHTML = `<tr><td class="empty" colspan="${columns}">正在读取技能列表…</td></tr>`;
    return;
  }
  const rows = skillRows();
  const total = state.table.skills.length;
  const forced = Boolean($('skills-search').value.trim()) || state.filter !== 'all';
  const groups = groupedRows(rows);
  const grouped = Boolean(state.table.groups?.length);
  const allOpen = groups.every(group => state.openGroups.has(group.name));
  $('skills-count').textContent = forced
    ? `找到 ${rows.length} 个，共 ${total} 个技能。点一行看详情，勾选框直接改分配。`
    : grouped ? `共 ${total} 个技能，分成 ${groups.length} 组。点组名展开，点一行看详情，勾选框直接改分配。`
    : `共 ${total} 个技能。点一行看详情，勾选框直接改分配。`;
  $('labels-hint').hidden = grouped || state.table.llm_configured;
  $('skills-expand').hidden = forced || !groups.length || !grouped;
  $('skills-expand').textContent = allOpen ? '全部收起' : '全部展开';
  $('skills-rows').innerHTML = (!grouped ? rows.map(skillRowHtml).join('') : groups.map(group => {
    const open = forced || state.openGroups.has(group.name);
    return groupRowHtml(group, open, forced) + (open ? group.skills.map(skillRowHtml).join('') : '');
  }).join('')) || `<tr><td class="empty" colspan="${columns}">${escape(emptySkillsText())}</td></tr>`;
  renderSkillsNote();
}

/* 页脚说明：共用目录的提醒来自接口 notes；统计不到的只写是哪几个 agent，
   技术口径（usage_note）不往这里搬。 */
function renderSkillsNote() {
  const parts = [...(state.table?.notes || [])];
  const coverage = state.usage?.coverage || {};
  if (state.usage) {
    const missing = state.agents.filter(agent => coverage[agent.id] && !coverage[agent.id].available);
    if (missing.length && missing.length === state.agents.length) parts.push('各 agent 的用量都统计不到，多半是还没有使用记录。');
    else if (missing.length) parts.push(`${missing.map(agent => agent.name).join('、')} 暂时统计不到用量。`);
    parts.push('“最近使用”取各 agent 里最近的一次；每个 agent 各自的情况在详情里。');
  } else {
    parts.push('用量还在后台统计，统计完“最近使用”会自动更新。');
  }
  if (state.inventory?.count_basis) parts.push(state.inventory.count_basis + '“字数”按字符粗算，不代表实际模型用量。');
  $('skills-note').textContent = parts.join(' ');
}

function pendingChanges() {
  if (!state.table) return [];
  return state.table.skills.flatMap(skill => state.agents
    .filter(agent => (state.draft[skill.name] || []).includes(agent.id) !== skill.assigned_agents.includes(agent.id))
    .map(agent => ({skill: skill.name, agent: agent.id, enabled: (state.draft[skill.name] || []).includes(agent.id)})));
}

/* 底部操作栏：主句说清改了几处、要按「应用」才生效，副句放预览的提示和依赖说明。 */
function renderSkillsActionBar() {
  const changes = pendingChanges();
  if (!changes.length || !state.table) return hideActionBar();
  const note = [
    state.pending?.message || '',
    autoAddedNote(),
    ...(state.pending?.dependency_warnings || []),
  ].filter(Boolean).join('；');
  showActionBar({
    text: `改了 ${changes.length} 处，按「应用」后才生效`,
    note,
    buttons: [
      {label: '取消', kind: 'btn', action: () => discardPending()},
      {label: '应用', kind: 'btn btn-primary', disabled: previewBusy || Boolean(writeBusy) || !state.table.write_allowed, action: button => applyAssignment(button)},
    ],
  });
}

/* 勾选：先改草稿并立刻重画（不等网络），再合并着发预览请求。
   每次勾选都会让在途的预览结果作废，所以旧结果永远不会盖掉新的勾选；
   100 毫秒内的连续勾选还会合并成一次请求。 */
function invalidatePreview() {
  return ++previewSequence;
}

function schedulePreview() {
  clearTimeout(previewTimer);
  previewTimer = setTimeout(runPreview, PREVIEW_DEBOUNCE_MS);
}

async function runPreview() {
  // 这次请求认领当前的序号；期间只要有人再勾选，序号就会变，结果直接作废。
  const sequence = previewSequence;
  previewBusy = true;
  renderSkillsActionBar();
  try {
    const result = await api('/api/assignment/preview', {changes: pendingChanges()});
    if (sequence !== previewSequence) return;
    state.pending = result;
    state.draft = result.assignments;
    state.autoAdded = new Map((result.auto_added || []).map(item => [item.skill + '|' + item.agent, item.because]));
  } catch (error) {
    if (sequence !== previewSequence) return;
    const clicked = state.pendingClick;
    if (clicked && clicked.sequence === sequence) {
      const assigned = new Set(state.draft[clicked.skill] || []);
      if (clicked.enabled) assigned.delete(clicked.agent); else assigned.add(clicked.agent);
      state.draft[clicked.skill] = [...assigned];
      assignmentErrors[clicked.skill + '|' + clicked.agent] = '这次勾选没改成：' + error.message;
    }
    toast({text: error.message, tone: 'error'});
  } finally {
    // 只有最新那次请求负责收起忙碌态；被作废的旧请求什么都不动。
    if (sequence === previewSequence) previewBusy = false;
    renderSkillTable();
    renderAgentSummary();
    renderSkillsActionBar();
  }
}

function discardPending() {
  clearTimeout(previewTimer);
  invalidatePreview();
  previewBusy = false;
  state.draft = clone(state.saved);
  state.pending = null;
  state.pendingClick = null;
  state.autoAdded = new Map();
  assignmentErrors = {};
  renderSkillTable();
  renderAgentSummary();
  renderSkillsActionBar();
}

/* 分配确认：按 agent 列出具体技能名，依赖自动带上的单独标注。 */
function assignmentGroups(changes) {
  const groups = [];
  for (const agent of tableAgents()) {
    const added = changes.filter(c => c.agent === agent.id && c.enabled)
      .map(c => ({name: c.skill, note: autoAddedBy(c.skill, agent.id) ? '因依赖自动加上' : ''}));
    const removed = changes.filter(c => c.agent === agent.id && !c.enabled).map(c => ({name: c.skill}));
    if (added.length) groups.push({label: `给 ${agent.name} 加上 ${added.length} 个`, items: added});
    if (removed.length) groups.push({label: `从 ${agent.name} 撤下 ${removed.length} 个`, items: removed});
  }
  return groups;
}

async function applyAssignment(button) {
  const plan = state.pending;
  if (!plan) return;
  const changes = pendingChanges();
  const warnings = [...(plan.dependency_warnings || []), ...(plan.path_warnings || []).map(w => '受影响的文件：' + w.file)];
  const ok = await confirmDialog({
    title: '应用这些分配改动',
    lines: [plan.message, ...warnings],
    groups: assignmentGroups(changes),
    note: '完成后可以在操作记录里撤销。',
    okText: '应用',
  });
  if (!ok) return;
  await runWrite({
    button,
    busyText: '正在应用…',
    work: async () => {
      const result = await api('/api/assignment/apply', {changes, revision: state.table.revision, confirmed: true});
      state.pending = null;
      await refreshEverything();
      return result;
    },
    success: result => ({
      text: '分配已经应用',
      undo: undoButton => undoOperation(result.id, {skills: plan.changed || [], message: result.message, button: undoButton}),
    }),
  });
}

/* 勾选立刻生效在草稿上，任何时候都不锁、不等；预览在后台跟上。 */
$('skills-rows').addEventListener('change', event => {
  const input = event.target.closest('input[data-skill]');
  if (!input || writeBusy || !state.table?.write_allowed) return;
  const name = input.dataset.skill;
  const agent = input.dataset.agent;
  const selected = new Set(state.draft[name] || []);
  if (input.checked) selected.add(agent); else selected.delete(agent);
  state.draft[name] = [...selected];
  delete assignmentErrors[name + '|' + agent];
  // 先作废在途的预览结果，再记下这一次勾选；这样第二个勾不会被第一个请求的返回盖掉。
  const sequence = invalidatePreview();
  state.pendingClick = {skill: name, agent, enabled: input.checked, sequence};
  renderSkillTable();
  renderAgentSummary();
  renderSkillsActionBar();
  schedulePreview();
});

$('skills-rows').addEventListener('click', event => {
  const group = event.target.closest('[data-group-row]');
  if (group) {
    if (group.querySelector('.group-toggle').disabled) return;
    const name = group.dataset.groupRow;
    if (state.openGroups.has(name)) state.openGroups.delete(name); else state.openGroups.add(name);
    renderSkillTable();
    return;
  }
  if (event.target.closest('input, button, select, label')) return;
  const row = event.target.closest('[data-skill-row]');
  if (row) openDetail(row.dataset.skillRow);
});

$('skills-search').addEventListener('input', renderSkillTable);
$('skills-expand').addEventListener('click', () => {
  const names = groupedRows(skillRows()).map(group => group.name);
  const allOpen = names.every(name => state.openGroups.has(name));
  state.openGroups = allOpen ? new Set() : new Set(names);
  renderSkillTable();
});
$('skills-filters').addEventListener('click', event => {
  const button = event.target.closest('.seg');
  if (!button) return;
  state.filter = button.dataset.filter;
  for (const seg of document.querySelectorAll('.seg')) seg.setAttribute('aria-pressed', String(seg === button));
  renderSkillTable();
});

$('skills-refresh').addEventListener('click', event => withBusy(event.currentTarget, '正在盘点…', async () => {
  await refreshInventory();
  await refreshTable();
  renderSkillTable();
}));

/* 新技能横幅：发现没收进仓库的，先在这里提醒。 */
function renderNewSkills() {
  const list = state.table?.new_skills || [];
  $('new-banner').hidden = !list.length;
  if (!list.length) return;
  $('new-text').textContent = `发现 ${list.length} 个新技能还没收进仓库`;
  $('new-list').innerHTML = list.map(s => `<p>${escape(s.name)} <span class="mono muted">${pathLabel(s.relative)}</span></p>`).join('');
}

/* 新 agent 横幅：接口发现还没接入的 agent 时，指路到设置里的 agent 一栏。
   只看 suggested：已经忽略的不再提醒。 */
function renderAgentBanner() {
  // 只看 suggested，而且只说还没被忽略的那些（ignored 现在可能是对象，也可能还是编号）。
  const ignored = new Set((state.agentsView?.ignored || [])
    .map(item => (item && typeof item === 'object') ? item.id : item));
  const list = (state.agentsView?.suggested || []).filter(item => !ignored.has(item.id));
  $('agent-banner').hidden = !list.length;
  $('agent-text').textContent = list.length ? `发现新 agent：${list.map(item => item.name).join('、')}` : '';
}

$('agent-look').addEventListener('click', () => showPage('settings'));

$('new-toggle').addEventListener('click', event => {
  const list = $('new-list');
  list.hidden = !list.hidden;
  event.currentTarget.setAttribute('aria-expanded', String(!list.hidden));
});

$('new-absorb').addEventListener('click', async event => {
  const button = event.currentTarget;
  const list = state.table.new_skills;
  const names = list.map(s => s.name);
  const ok = await confirmDialog({
    title: '收编新技能',
    lines: ['会把这些新装的技能收进统一仓库，保持原来的可见范围。'],
    groups: [{label: `收进仓库 ${names.length} 个`, items: names.map(name => ({name}))}],
    note: '可以在操作记录里撤销。',
    okText: '收编',
  });
  if (!ok) return;
  const result = await runWrite({
    button,
    busyText: '正在收编…',
    work: async () => {
      const written = await api('/api/absorb', {all: true, revision: state.table.revision, confirmed: true});
      await refreshEverything();
      return written;
    },
    success: written => (written.conflicts?.length ? null : {
      text: '新技能已经收进仓库',
      undo: undoButton => undoOperation(written.id, {skills: names, message: written.message, button: undoButton}),
    }),
  });
  if (result?.conflicts?.length) {
    toast({text: '有同名技能需要先对比，请到安装技能里查看差异。', tone: 'error', sticky: true});
    openInstall();
    await showIncomingConflicts(result, null);
  }
});

/* 重新加载数据。 */
async function refreshInventory() {
  try {
    state.inventory = await api('/api/scan');
    renderDiagnostics();
  } catch (error) {
    toast({text: '技能清单没能读出来：' + error.message, tone: 'error', sticky: true});
  }
}

async function refreshTable(preserveDraft = false) {
  const table = await api('/api/table');
  const keepDraft = preserveDraft && table.revision === state.table?.revision;
  const draft = state.draft, pending = state.pending;
  state.table = table;
  state.skillIndex = new Map(table.skills.map(s => [s.name, s]));
  state.saved = Object.fromEntries(table.skills.map(s => [s.name, [...s.assigned_agents]]));
  state.draft = clone(state.saved);
  state.pending = null;
  state.autoAdded = new Map();
  if (keepDraft) { state.draft = draft; state.pending = pending; }
  state.agents = table.agents || [];
  $('mode-badge').textContent = table.write_allowed ? '可以管理技能' : '只读预览';
  $('skills-install').disabled = !table.write_allowed;
  renderNewSkills();
  renderAgentBanner();
  renderAgentSummary();
  renderSkillTable();
  if (state.detail) renderDetail();
  renderActionBar();
  renderLabelCounts();
  if (table.write_allowed && table.llm_configured && table.labels_pending > 0 && !labelsAutoAttempted && !labelsRunning) {
    labelsAutoAttempted = true;
    startLabels('missing');
  }
}

/* agent 目录与接入建议。页面里翻名字、设置页那一栏、新 agent 横幅都看它。 */
async function refreshAgents() {
  indexCatalog(await api('/api/agents'));
  renderAgentBanner();
  renderAgents();
}

/* ==================== 设置与中文名：只改变显示，不锁技能操作 ==================== */

const LLM_DEFAULTS = {
  deepseek: ['https://api.deepseek.com', 'deepseek-chat'],
  qwen: ['https://dashscope.aliyuncs.com/compatible-mode/v1', 'qwen-plus'],
  kimi: ['https://api.moonshot.cn/v1', 'moonshot-v1-32k'],
  glm: ['https://open.bigmodel.cn/api/paas/v4', 'glm-4-flash'],
  openai: ['https://api.openai.com/v1', 'gpt-4o-mini'],
  other: ['', ''],
};

let llmSettings = {};
let labelsAutoAttempted = false;
let labelsRunning = false;

function renderLabelCounts() {
  const table = state.table;
  if (!table) return;
  const remaining = table.labels_pending;
  $('labels-count').textContent = `已整理 ${table.skills.length - remaining} 个，还有 ${remaining} 个没有中文名`;
  $('labels-missing').hidden = !remaining;
  $('labels-missing').textContent = `给剩下的 ${remaining} 个起名`;
  for (const id of ['labels-missing', 'labels-all']) {
    $(id).disabled = !table.write_allowed || !table.llm_configured || labelsRunning;
  }
}

async function refreshSettings() {
  try {
    llmSettings = (await api('/api/settings')).llm;
    const provider = llmSettings.provider || 'deepseek';
    $('llm-provider').value = provider in LLM_DEFAULTS ? provider : 'other';
    const defaults = LLM_DEFAULTS[$('llm-provider').value];
    $('llm-base-url').value = llmSettings.base_url || defaults[0];
    $('llm-model').value = llmSettings.model || defaults[1];
    $('llm-key').placeholder = llmSettings.has_key ? `已保存，末尾 ${llmSettings.key_tail}；不改就留空` : '粘贴服务商提供的 key';
    $('llm-clear').hidden = !llmSettings.has_key;
    for (const input of $('llm-form').querySelectorAll('input, select, button')) input.disabled = !state.table?.write_allowed;
    renderLabelCounts();
  } catch (error) {
    toast({text: error.message, tone: 'error'});
  }
}

function llmBody() {
  return {provider: $('llm-provider').value, base_url: $('llm-base-url').value, model: $('llm-model').value};
}

$('llm-provider').addEventListener('change', () => {
  [$('llm-base-url').value, $('llm-model').value] = LLM_DEFAULTS[$('llm-provider').value];
});

$('labels-settings').addEventListener('click', () => showPage('settings'));

/* 保存并试一下：连得上就接着给没有中文名的技能起名。 */
$('llm-form').addEventListener('submit', event => {
  event.preventDefault();
  withBusy($('llm-save'), '正在保存并测试…', async () => {
    const unlock = lockControls(['#llm-form input', '#llm-form select', '#llm-clear']);
    labelsAutoAttempted = true;
    try {
      await api('/api/settings/llm', {...llmBody(), api_key: $('llm-key').value});
      $('llm-key').value = '';
      const result = await api('/api/settings/llm/test', {});
      $('llm-message').textContent = result.message;
      toast({text: result.message, tone: result.ok ? 'ok' : 'error'});
      await refreshTable(true);
      if (result.ok && state.table.labels_pending) startLabels('missing');
    } catch (error) {
      $('llm-message').textContent = error.message;
      toast({text: error.message, tone: 'error'});
    } finally {
      unlock();
      await refreshSettings();
    }
  });
});

$('llm-clear').addEventListener('click', async event => {
  const ok = await confirmDialog({
    title: '删除已保存的 key？',
    lines: ['删除后不会再自动给技能起名，已经整理好的中文名会保留。'],
    okText: '删除 key',
  });
  if (!ok) return;
  await withBusy(event.currentTarget, '正在删除…', async () => {
    try {
      await api('/api/settings/llm', {...llmBody(), clear_key: true});
      $('llm-key').value = '';
      await refreshTable(true);
      await refreshSettings();
      toast({text: '已删除 key。'});
    } catch (error) {
      toast({text: error.message, tone: 'error'});
    }
  });
});

/* 起中文名在后台跑，进度显示在页头任务条上。 */
async function startLabels(mode) {
  if (labelsRunning) return;
  labelsRunning = true;
  labelsAutoAttempted = true;
  renderLabelCounts();
  setTask('labels', {text: '正在准备技能名单…'});
  try {
    const progress = await api('/api/labels/progress');
    if (!progress.running) await api('/api/labels/run', {mode});
    pollLabels();
  } catch (error) {
    labelsRunning = false;
    renderLabelCounts();
    setTask('labels', {text: error.message, tone: 'error', retry: () => startLabels('missing')});
  }
}

async function pollLabels() {
  try {
    const progress = await api('/api/labels/progress');
    if (progress.running) {
      setTask('labels', progress.total
        ? {text: `正在给技能起中文名（已整理 ${progress.done}/${progress.total}）`, ratio: progress.done / progress.total}
        : {text: '正在准备技能名单…'});
      setTimeout(pollLabels, 1000);
      return;
    }
    labelsRunning = false;
    await refreshTable(true);
    if (progress.error) throw new Error(progress.error);
    clearTask('labels');
    toast({text: progress.message});
  } catch (error) {
    labelsRunning = false;
    renderLabelCounts();
    setTask('labels', {text: error.message, tone: 'error', retry: () => startLabels('missing')});
    toast({text: error.message, tone: 'error'});
  }
}

$('labels-missing').addEventListener('click', () => startLabels('missing'));

$('labels-all').addEventListener('click', async () => {
  const ok = await confirmDialog({
    title: '重新整理全部中文名？',
    lines: ['会替换现在全部中文名和分组，原来的会留一份备份。'],
    okText: '重新整理全部',
  });
  if (ok) startLabels('all');
});

async function refreshLog() {
  try {
    state.logs = await api('/api/log');
    renderLog();
  } catch (error) {
    toast({text: error.message, tone: 'error', sticky: true});
  }
}

async function refreshEverything() {
  // /api/agents 比较慢（要重新盘点一遍），放在最后只等前三个：
  // 写操作的完成提示不用陪它等，agent 那一栏结果回来自己会重画。
  await Promise.all([refreshTable(), refreshInventory()]);
  await refreshLog();
  refreshAgents().catch(error => toast({text: error.message, tone: 'error', sticky: true}));
}

/* ==================== 设置页的 agent 一栏：接入新 agent、不再管理 ==================== */

/* 正在管理的 agent 一行一个；下面是接口发现的新 agent 和已经忽略的。
   忽略名单后台会改成对象数组（带名字、目录、技能数、原因）；还是编号数组时跳过不显示。 */
function ignoredAgents(view) {
  return (view?.ignored || []).filter(item => item && typeof item === 'object');
}

function renderAgents() {
  const view = state.agentsView;
  const managed = view?.managed || [];
  const suggested = view?.suggested || [];
  const ignored = ignoredAgents(view);
  $('agents-empty').hidden = !view || managed.length > 0;
  $('agents-empty-link').hidden = $('agents-empty').hidden;
  $('agents-managed').innerHTML = managed.map(agent => {
    const shared = (agent.shared_with || []).map(agentName);
    const info = [
      agent.activation_text || '',
      agent.usage_available ? '能统计用量' : (agent.usage_note || '统计不到用量'),
      shared.length ? `和 ${shared.join('、')} 共用技能目录` : '',
    ].filter(Boolean).join('；');
    const leave = agent.can_leave
      ? `<button class="btn btn-small" data-agent-leave="${escape(agent.id)}">不再管理</button>`
      : '<span class="item-note">至少要留一个</span>';
    return `<div class="item-row">
      <div>
        <div class="item-title">${escape(agent.name)}</div>
        <div class="item-note">${rootsLabel(agent.skill_roots)}</div>
        <div class="item-note">${escape(info)}</div>
      </div>
      <span class="item-end">${leave}</span>
    </div>`;
  }).join('');

  const row = (agent, action) => `<div class="item-row">
    <div>
      <div class="item-title">${escape(agent.name)}${agent.ignored ? ' <span class="tag tag-quiet">已忽略</span>' : ''}</div>
      <div class="item-note">${rootsLabel(agent.skill_roots)}${agent.skill_count === undefined ? '' : ` · ${number(agent.skill_count)} 个技能`}</div>
      <div class="item-note">${escape(agent.reason || '')}</div>
    </div>
    <span class="item-end">${action}</span>
  </div>`;
  const joinButton = agent => `<button class="btn btn-small btn-primary" data-agent-join="${escape(agent.id)}">接入</button>`;

  $('agents-suggested-box').hidden = !suggested.length;
  $('agents-suggested').innerHTML = suggested.map(agent => row(agent,
    `${joinButton(agent)}<button class="btn btn-small" data-agent-ignore="${escape(agent.id)}">忽略</button>`)).join('');
  $('agents-ignored-box').hidden = !ignored.length;
  $('agents-ignored').innerHTML = ignored.map(agent => row({...agent, ignored: true}, joinButton(agent))).join('');
}

$('agents-migration-link').addEventListener('click', () => showPage('diagnostics'));

/* 不再管理：先预览，确认框里说明会失去哪些技能，再写入。 */
async function leaveAgent(id) {
  let plan;
  try {
    plan = await api('/api/agents/leave/preview', {agent: id});
  } catch (error) {
    toast({text: error.message, tone: 'error', sticky: true});
    return;
  }
  const lost = plan.lost_skills || [];
  const ok = await confirmDialog({
    title: `不再管理 ${nameOf(id)}？`,
    lines: [plan.message],
    groups: lost.length ? [{label: `${nameOf(id)} 以后看不到这几个技能`, items: lost.map(name => ({name}))}] : [],
    note: '以后可以在设置里重新接入。',
    okText: '不再管理',
  });
  if (!ok) return;
  await runWrite({
    button: document.querySelector(`[data-agent-leave="${id}"]`),
    busyText: '正在处理…',
    work: async () => {
      const result = await api('/api/agents/leave/apply', {agent: id, plan_id: plan.plan_id, revision: plan.revision, confirmed: true});
      await refreshEverything();
      return result;
    },
    success: result => ({
      text: result.message || `不再管理 ${nameOf(id)}`,
      undo: undoButton => undoOperation(result.id, {skills: lost, message: result.message, button: undoButton}),
    }),
  });
}

/* 忽略建议：不弹确认框，写完在提示条上给撤销。 */
async function ignoreAgent(id) {
  const button = document.querySelector(`[data-agent-ignore="${id}"]`);
  await runWrite({
    button,
    busyText: '正在忽略…',
    work: async () => {
      const plan = await api('/api/agents/ignore/preview', {agent: id});
      const result = await api('/api/agents/ignore/apply', {agent: id, plan_id: plan.plan_id, revision: plan.revision, confirmed: true});
      await refreshEverything();
      return result;
    },
    success: result => ({
      text: result.message || `已忽略 ${nameOf(id)}`,
      undo: undoButton => undoOperation(result.id, {message: result.message, button: undoButton}),
    }),
  });
}

$('agents-managed').addEventListener('click', event => {
  const button = event.target.closest('[data-agent-leave]');
  if (button) leaveAgent(button.dataset.agentLeave);
});

/* 新发现的（可接入、可忽略）和没在管理的（只能重新接入）两栏共用这一套按钮。 */
for (const id of ['agents-suggested', 'agents-ignored']) {
  $(id).addEventListener('click', event => {
    const join = event.target.closest('[data-agent-join]');
    const ignore = event.target.closest('[data-agent-ignore]');
    if (join) openJoin(join.dataset.agentJoin);
    else if (ignore) ignoreAgent(ignore.dataset.agentIgnore);
  });
}

/* 接入：连同“必须一起选”的 agent 一起预览，然后打开核对框。 */
const JOIN_ACTIONS = [
  ['linked', '已经在用统一仓库', '直接登记分配。'],
  ['link', '内容一致，改成统一管理', '改为使用仓库里的那份。'],
  ['import', '收进统一仓库', '仓库里还没有，收进来。'],
  ['choose', '内容不同，需要你选', '每一条单独选，默认保留仓库里的版本。'],
  ['skipped', '原样留着', '这些内容不动。'],
];

let joinPlan = null;

async function openJoin(id) {
  let plan;
  try {
    plan = await api('/api/agents/join/preview', {agents: joinIds(id)});
  } catch (error) {
    toast({text: error.message, tone: 'error', sticky: true});
    return;
  }
  joinPlan = plan;
  renderJoin(plan);
  $('agents-join-dialog').showModal();
}

/* 同组共用一个目录的 agent 要一起接入。 */
function joinIds(id) {
  const group = (state.agentsView?.must_select_together || []).find(item => item.includes(id));
  return group ? [...group] : [id];
}

function joinRows(plan, action) {
  return plan.skills.filter(skill => skill.action === action);
}

function joinChoiceRow(skill) {
  const options = skill.options.map(option => `<p class="join-option"><label class="check">
    <input type="radio" name="join-choice-${escape(skill.name)}" data-join-choice="${escape(skill.name)}" value="${escape(option.id)}" ${option.id === skill.default ? 'checked' : ''}>
    ${option.origin === 'store' ? '用统一仓库里的（默认）' : '用这个 agent 里的'}</label>
    <span class="mono">${pathLabel(option.path)}</span></p>`).join('');
  return `<details class="fold fold-inner join-choice" data-join-row="${escape(skill.name)}">
    <summary>${escape(skill.name)} <span class="tag tag-quiet">内容不同</span></summary>
    <p class="item-note">${escape(skill.reason)}</p>
    ${options}
    ${skill.comparison ? `<details class="fold fold-inner"><summary data-join-compare="${escape(skill.name)}">看看差别</summary><pre></pre></details>` : ''}
    <p class="item-note" data-join-warn hidden>选了这一份，会更新所有 agent 用的这份技能。</p>
    <p class="item-note">${(skill.entries || []).map(pathLabel).join('、')}</p>
  </details>`;
}

function renderJoin(plan) {
  $('join-summary').textContent = (plan.profiles || []).map(profile => `${profile.name}（${rootsLabel(profile.skill_roots)}）`).join('；')
    || '这次没有要接入的 agent。';
  $('join-counts').innerHTML = JOIN_ACTIONS.map(([action, label, note]) => {
    const count = joinRows(plan, action).length;
    return count ? `<p><strong>${escape(label)}：${count} 个</strong><span class="item-note"> ${escape(note)}</span></p>` : '';
  }).join('') || '<p class="item-note">没有读到任何技能。</p>';
  $('join-choices').innerHTML = joinRows(plan, 'choose').map(joinChoiceRow).join('');
  const skipped = plan.skipped || [];
  $('join-skipped-box').hidden = !skipped.length;
  $('join-skipped').innerHTML = skipped.map(item => `<p class="mono">${pathLabel(item.path)} · ${escape(item.reason)}</p>`).join('');
  $('join-message').textContent = `${(plan.skills || []).length} 个技能会登记给 ${(plan.agents || []).map(agentName).join('、')}。`;
  $('join-apply').disabled = false;
}

$('join-close').addEventListener('click', () => $('agents-join-dialog').close());

$('join-choices').addEventListener('change', event => {
  const input = event.target.closest('[data-join-choice]');
  if (!input) return;
  const row = input.closest('[data-join-row]');
  if (row) row.querySelector('[data-join-warn]').hidden = input.value === 'store';
});

$('join-choices').addEventListener('click', async event => {
  const name = event.target.dataset.joinCompare;
  if (!name) return;
  const pre = event.target.parentElement.querySelector('pre');
  if (pre.textContent) return;
  const skill = (joinPlan?.skills || []).find(item => item.name === name);
  pre.textContent = skill?.comparison || '两份内容没有文本差别。';
});

$('join-apply').addEventListener('click', async event => {
  if (!joinPlan) return;
  const choices = Object.fromEntries([...document.querySelectorAll('[data-join-choice]:checked')].map(input => [input.dataset.joinChoice, input.value]));
  await runWrite({
    button: event.currentTarget,
    busyText: '正在接入…',
    onError: error => { $('join-message').textContent = error.message; },
    work: async () => {
      const result = await api('/api/agents/join/apply', {agents: joinPlan.agents, plan_id: joinPlan.plan_id, revision: joinPlan.revision, choices, confirmed: true});
      $('agents-join-dialog').close();
      joinPlan = null;
      await refreshEverything();
      return result;
    },
    success: result => ({
      text: result.message || '新 agent 已经接入',
      undo: undoButton => undoOperation(result.id, {message: result.message, button: undoButton}),
    }),
  });
});

/* ==================== 技能详情：右侧面板 ==================== */

function entriesFor(name) {
  const rows = [];
  for (const root of state.inventory?.roots || []) {
    if (root.category !== 'user') continue;
    for (const skill of root.skills || []) {
      if (skill.name === name) rows.push({root, skill});
    }
  }
  return rows;
}

function renderDetail() {
  const skill = state.table?.skills.find(s => s.name === state.detail);
  if (!skill) { closeDetail(); return; }
  $('detail-title').textContent = skill.title || skill.name;
  const usage = state.usageIndex.get(skill.name);
  const coverage = state.usage?.coverage || {};

  const usageRows = state.agents.map(agent => {
    const available = state.usage ? coverage[agent.id]?.available : null;
    const last = !state.usage ? '还没统计' : available ? (usage?.last_used?.[agent.id] || '没有使用记录') : '统计不到';
    const count = !state.usage || !available ? '—' : number(usage?.sessions_30d?.[agent.id] || 0);
    return `<tr><th>${escape(agent.name)}</th><td>${escape(last)}</td><td class="num">${escape(count)}</td>
      <td>${(state.draft[skill.name] || []).includes(agent.id) ? '已分配' : '没分配'}</td></tr>`;
  }).join('');

  const disabledFor = state.agents.filter(agent => (state.inventory?.disabled?.[agent.id]?.names || []).includes(skill.name));
  const entries = entriesFor(skill.name).map(({root, skill: entry}) => {
    const manual = (entry.manual_only_for || []).map(agentName);
    const status = [
      entry.broken ? '链接已失效' : entry.kind === 'link' ? '链接到统一仓库' : '存放完整文件',
      (root.readers || []).map(agentName).join(' / '),
      manual.length ? `${manual.join('、')} 只允许手动调用` : '',
      entry.model_invocable === false ? '只允许手动调用' : '',
      entry.name_mismatch ? '名称与文件夹名称不同' : '',
      entry.warning || '',
    ].filter(Boolean).join(' · ');
    return `<li>
      <p class="entry-path">${pathLabel(entry.path)}</p>
      <p class="entry-status">${escape(status)}</p>
    </li>`;
  }).join('');

  const options = (state.table?.skills || [])
    .filter(s => s.name !== skill.name && !skill.requires.includes(s.name))
    .map(s => `<option value="${escape(s.name)}">${escape(s.title ? `${s.title}（${s.name}）` : s.name)}</option>`).join('');

  $('detail-body').innerHTML = `
    ${skill.title ? `<p class="detail-id">${escape(skill.name)}</p>` : ''}
    <div class="detail-tags">
      ${skill.local_modified ? '<span class="tag tag-warn">你改过</span>' : '<span class="tag tag-quiet">和刚装进来时一样</span>'}
      ${skill.source_label ? `<span class="tag tag-quiet">${escape(skill.source_label)}</span>` : ''}
      ${disabledFor.length ? `<span class="tag tag-warn">${escape(disabledFor.map(agent => agent.name).join('、'))} 里停用了</span>` : ''}
    </div>
    ${skill.summary ? `<p class="detail-summary">${escape(skill.summary)}</p>
    <h3 class="sub-title">原文说明</h3>
    <p class="item-note">agent 看到的是这段原文，“说明字数”也按它算。</p>` : ''}
    <p class="detail-desc">${escape(skill.description)}</p>
    <dl class="detail-list">
      <dt>来源</dt><dd>${escape(skill.source_label || '没记录')}</dd>
      <dt>存放位置</dt><dd class="mono">${pathLabel(homePath() + '/.skill-pilot/store/' + skill.name)}</dd>
      <dt>说明字数</dt><dd>${number(skill.description_chars)} 字</dd>
      <dt>本机改动</dt><dd>${skill.local_modified ? '你改过这份技能，更新时会问你要哪一份' : '没有改过'}</dd>
    </dl>

    <h3 class="sub-title">各 agent 使用情况</h3>
    <table class="detail-table">
      <thead><tr><th>agent</th><th>最近使用</th><th class="num">近 30 天</th><th>分配</th></tr></thead>
      <tbody>${usageRows}</tbody>
    </table>
    ${state.usage ? '' : '<p class="item-note">用量还没统计，暂时看不到使用情况。</p>'}

    <h3 class="sub-title">各 agent 里的入口</h3>
    ${entries ? `<ul class="entry-list">${entries}</ul>` : '<p class="item-note">没找到这个技能在 agent 目录里的入口。</p>'}

    <h3 class="sub-title">需要的技能</h3>
    <ul class="dep-list">
      ${skill.requires.map(name => `<li><span>${nameHtml(name)}</span>
        <button class="btn btn-small" data-dep-remove="${escape(skill.name)}" data-dep-name="${escape(name)}">删除</button></li>`).join('')
        || '<li><span class="item-note">暂时不需要别的技能。</span></li>'}
    </ul>
    <p class="row-wrap">
      <select id="dep-select" class="input" aria-label="选择要添加的技能">${options}</select>
      <button class="btn btn-small" id="dep-add" data-dep-add="${escape(skill.name)}">添加需要的技能</button>
    </p>
    <p class="item-note">添加时会把被需要的技能一起分配给用它的 agent；删除关系时保留现有分配。</p>`;
}

function openDetail(name) {
  state.detail = name;
  renderDetail();
  const panel = $('detail-panel');
  panel.hidden = false;
  $('panel-scrim').hidden = false;
  requestAnimationFrame(() => panel.classList.add('is-open'));
}

function closeDetail() {
  const panel = $('detail-panel');
  panel.classList.remove('is-open');
  setTimeout(() => {
    panel.hidden = true;
    $('panel-scrim').hidden = true;
    state.detail = null;
  }, 200);
}

$('detail-close').addEventListener('click', closeDetail);
$('panel-scrim').addEventListener('click', closeDetail);
document.addEventListener('keydown', event => {
  if (event.key !== 'Escape' || document.querySelector('dialog[open]')) return;
  if (!$('detail-panel').hidden) closeDetail();
});

$('detail-body').addEventListener('click', async event => {
  const button = event.target.closest('button');
  if (!button) return;
  const addName = button.dataset.depAdd;
  const removeName = button.dataset.depRemove;
  if (addName) {
    const requires = $('dep-select')?.value;
    if (!requires) return;
    const ok = await confirmDialog({
      title: '添加需要的技能',
      lines: [`${titleOf(addName)} 需要 ${titleOf(requires)}。需要它的 agent 会一起分到这个技能。`],
      groups: [{label: '这次会动到', items: [{name: addName}, {name: requires}]}],
      note: '可以撤销。', okText: '添加',
    });
    if (!ok) return;
    await decideDependency(addName, requires, true, button);
  } else if (removeName) {
    const ok = await confirmDialog({
      title: '删除这条依赖',
      lines: [`不再认为 ${titleOf(removeName)} 需要 ${titleOf(button.dataset.depName)}。现有的分配保持不变。`],
      groups: [{label: '这次会动到', items: [{name: removeName}, {name: button.dataset.depName}]}],
      note: '可以撤销。', okText: '删除',
    });
    if (!ok) return;
    await decideDependency(removeName, button.dataset.depName, false, button);
  }
});

async function decideDependency(skill, requires, confirmed, button) {
  await runWrite({
    button,
    busyText: '正在处理…',
    work: async () => {
      await api('/api/dependencies', {decisions: [{skill, requires, confirmed}], revision: state.table.revision, confirmed: true});
      await refreshEverything();
      return true;
    },
    success: () => ({text: confirmed ? '已经加上需要的技能' : '已经删掉这条依赖'}),
  });
}

/* ==================== 安装技能：对话框 ==================== */

let installReview = null;

function openInstall() {
  installReview = null;
  $('install-url').value = '';
  $('install-message').textContent = '';
  $('install-skills').innerHTML = '';
  $('incoming-conflicts').hidden = true;
  $('incoming-comparisons').innerHTML = '';
  $('install-apply').disabled = true;
  $('install-agents').innerHTML = state.agents
    .map(a => `<label class="check"><input type="checkbox" data-install-agent="${escape(a.id)}"> ${escape(a.name)}</label>`).join('');
  $('install-dialog').showModal();
}

$('skills-install').addEventListener('click', openInstall);

$('install-dialog').querySelector('form').addEventListener('submit', event => {
  event.preventDefault();
  $('install-inspect').click();
});
$('install-close').addEventListener('click', () => $('install-dialog').close());

$('install-inspect').addEventListener('click', event => withBusy(event.currentTarget, '正在读取…', async () => {
  const url = $('install-url').value.trim();
  if (!url) { $('install-message').textContent = '请先粘贴技能仓库的链接。'; return; }
  $('install-message').textContent = '正在读取仓库…';
  $('install-skills').innerHTML = '';
  try {
    installReview = await api('/api/install/inspect', {url});
    $('install-skills').innerHTML = installReview.skills.map(s => `<div>
      <label class="check"><input type="checkbox" data-install-skill="${escape(s.name)}"> ${escape(s.name)}</label>
      <p class="item-note">${escape((s.description || '').slice(0, 160))}</p>
      ${installReview.conflicts.some(c => c.name === s.name) ? '<p class="item-note">仓库里已有同名技能，安装时会转入对比。</p>' : ''}
    </div>`).join('') || '<p class="item-note">这个仓库里没找到技能。</p>';
    $('install-message').textContent = `找到 ${installReview.skills.length} 个技能。请勾选要安装的。`;
    $('install-apply').disabled = !installReview.skills.length;
  } catch (error) {
    $('install-message').textContent = error.message;
  }
}));

async function showIncomingConflicts(result, reviewId) {
  $('incoming-conflicts').hidden = false;
  $('incoming-comparisons').innerHTML = '';
  for (const conflict of result.conflicts || []) {
    const incoming = state.table?.new_skills?.find(s => s.name === conflict.name);
    try {
      const comparison = await api('/api/incoming/compare', {name: conflict.name, review_id: reviewId, relative: incoming?.relative});
      const item = document.createElement('details');
      item.className = 'fold fold-inner';
      item.open = true;
      const summary = document.createElement('summary');
      summary.textContent = conflict.name;
      const pre = document.createElement('pre');
      pre.textContent = comparison.comparison;
      item.append(summary, pre);
      $('incoming-comparisons').append(item);
    } catch (error) {
      toast({text: error.message, tone: 'error', sticky: true});
    }
  }
}

$('install-apply').addEventListener('click', async event => {
  const button = event.currentTarget;
  const skills = [...document.querySelectorAll('[data-install-skill]:checked')].map(input => input.dataset.installSkill);
  const agents = [...document.querySelectorAll('[data-install-agent]:checked')].map(input => input.dataset.installAgent);
  if (!skills.length) { $('install-message').textContent = '请至少勾选一个技能。'; return; }
  const ok = await confirmDialog({
    title: '安装技能',
    lines: [agents.length ? `分配给：${agents.map(agentName).join('、')}` : '暂时不分配给任何 agent。'],
    groups: [{label: `安装 ${skills.length} 个技能`, items: skills.map(name => ({name}))}],
    note: '可以在操作记录里撤销。', okText: '安装',
  });
  if (!ok) return;
  const result = await runWrite({
    button,
    busyText: '正在安装…',
    onError: error => { $('install-message').textContent = error.message; },
    work: async () => {
      const written = await api('/api/install/apply', {review_id: installReview.id, skills, agents, revision: state.table.revision, confirmed: true});
      if (!written.conflicts?.length) {
        $('install-dialog').close();
        await refreshEverything();
      }
      return written;
    },
    success: written => (written.conflicts?.length ? null : {
      text: '技能已经装好',
      undo: undoButton => undoOperation(written.id, {skills, message: written.message, button: undoButton}),
    }),
  });
  if (result?.conflicts?.length) {
    $('install-message').textContent = '有同名技能需要先对比，请看下面的差别。';
    await showIncomingConflicts(result, installReview.id);
  }
});

/* ==================== 检查更新页 ==================== */

const updateState = {
  review: null,
  seen: new Set(),
  selected: new Set(),
  choices: new Map(),
  open: new Set(),
  merges: new Map(),
  explanations: new Map(),
  notices: new Map(),
  busy: false,
};

const sourceKind = name => updateState.review?.skills.find(s => s.name === name)?.source?.kind;
const shownInUpdates = row => row.has_update || ['已更新', '已保留我的'].includes(row.status);

async function refreshUpdates() {
  try {
    const review = await api('/api/updates/progress');
    renderUpdates(review);
  } catch (error) {
    setTask('updates', {text: error.message, tone: 'error', retry: () => refreshUpdates()});
  }
}

function renderUpdates(review) {
  if (review === undefined) review = updateState.review;
  if (!review) {
    $('updates-summary').textContent = '还没有检查过。按下上面的按钮开始，检查不会改动任何文件。';
    $('updates-other-box').hidden = true;
    renderUpdatesActionBar();
    return;
  }
  if (review.id !== updateState.review?.id) {
    updateState.seen = new Set();
    updateState.selected = new Set();
    updateState.choices = new Map();
    updateState.open = new Set();
    updateState.merges = new Map();
    updateState.notices = new Map();
    updateState.explanations = new Map();
  }
  updateState.review = review;

  if (review.running) {
    setTask('updates', {
      text: `正在检查更新（已查 ${review.done}/${review.total} 个技能）${review.current?.length ? '，正在查 ' + review.current.join('、') : ''}`,
      ratio: review.total ? review.done / review.total : null,
    });
  } else {
    clearTask('updates');
  }

  for (const row of review.skills) {
    if (!updateState.choices.has(row.name)) updateState.choices.set(row.name, 'upstream');
    if (row.has_update && !updateState.seen.has(row.name)) {
      updateState.seen.add(row.name);
      updateState.selected.add(row.name);
    }
  }

  const parts = [];
  if (review.running) {
    parts.push(`正在检查，已经查了 ${review.done}/${review.total} 个技能。`);
  } else {
    const rows = review.skills;
    const updated = rows.filter(row => ['已更新', '已保留我的'].includes(row.status)).length;
    const updating = rows.filter(row => row.has_update).length;
    const latest = rows.filter(row => row.status === '已是最新').length;
    const failed = rows.filter(row => row.error).length;
    const seen = rows.filter(row => row.status === '这一版已看过').length;
    // 剩下的都是「不检查」的：自制、没有来源等。用减法保证数字能加总。
    const skipped = Math.max(0, rows.length - updated - updating - latest - failed - seen);
    const bits = [`共 ${rows.length} 个技能`, `有更新 ${updating} 个`, `已是最新 ${latest} 个`, `没查成 ${failed} 个`];
    if (updated) bits.push(`这次已更新 ${updated} 个`);
    if (seen) bits.push(`这一版已看过 ${seen} 个`);
    if (skipped) bits.push(`另有 ${skipped} 个不检查（自制或没有来源）`);
    parts.push(`检查完成：${bits.join('，')}。`);
  }
  if (review.lark?.message) parts.push(`飞书工具：${review.lark.message}。`);
  if (!review.write_allowed) parts.push('当前是只读模式，只能查看。');
  $('updates-summary').textContent = parts.join(' ');

  const visible = review.skills.filter(shownInUpdates);
  $('updates-list').innerHTML = visible.map(updateRowHtml).join('')
    || `<p class="empty">${escape(review.running ? '正在逐个检查，结果会一条条出现。' : review.total ? '所有技能都已经是最新的。' : '没有需要检查的技能。')}</p>`;

  const other = review.skills.filter(row => !shownInUpdates(row));
  $('updates-other-box').hidden = !other.length && !review.lark;
  $('updates-other').innerHTML = (review.lark ? `<p><strong>飞书工具</strong> · ${escape(review.lark.message || '')}</p>` : '')
    + other.map(row => `<p><strong>${nameHtml(row.name)}</strong> · ${escape(row.status)}${row.error ? ' · ' + escape(row.error) : ''}</p>`).join('');

  $('updates-check').disabled = review.running || updateState.busy || Boolean(writeBusy);
  renderUpdatesActionBar();
}

/* “让 Codex 解释 / 交给 Codex 合并”这两件事实际是交给 Codex 这个工具做的，
   和被管理的 agent 无关，所以名字照写 Codex。 */
function updateRowHtml(row) {
  const review = updateState.review;
  const choice = updateState.choices.get(row.name) || 'upstream';
  const merge = updateState.merges.get(row.name);
  const notice = updateState.notices.get(row.name);
  const explanation = updateState.explanations.get(row.name);
  const done = ['已更新', '已保留我的'].includes(row.status);
  const canAct = review.write_allowed && !done && !row.blocked_reason && !updateState.busy && !writeBusy;
  const tag = row.baseline_uncertain ? '<span class="tag tag-warn">改动情况不确定</span>'
    : row.local_modified ? '<span class="tag tag-warn">你改过</span>'
    : '<span class="tag tag-quiet">本机没改过</span>';
  return `<article class="update-row${done ? ' is-done' : ''}" data-update-row="${escape(row.name)}">
    <div class="update-head">
      <label class="check"><input type="checkbox" data-update-skill="${escape(row.name)}"
        ${updateState.selected.has(row.name) ? 'checked' : ''} ${canAct && !row.blocked_reason ? '' : 'disabled'}
        aria-label="${escape('更新 ' + row.name)}"></label>
      <span class="update-title"><strong>${nameHtml(row.name)}</strong>${tag}</span>
      <span class="update-meta item-end">${escape(row.status)}</span>
    </div>
    <p class="update-meta">来源：${escape(row.source?.label || '没记录')}${row.updated_at ? ' · 上游更新：' + escape(friendlyDate(row.updated_at)) : ''}</p>
    ${row.has_update ? `<p class="update-summary">${number(row.file_count)} 个文件有变化，新增 ${number(row.added_lines)} 行，删除 ${number(row.removed_lines)} 行</p>` : ''}
    ${row.blocked_reason ? `<div class="risk-block"><p>${escape(row.blocked_reason)}</p></div>` : ''}
    ${row.script_files?.length ? `<div class="risk-block">
      <p><strong>脚本或执行权限有变化，请先看</strong></p>
      <p>${row.script_files.map(escape).join('、')}</p>
      ${(row.risk_hits || []).map(hit => `<p class="risk-line">${escape(hit.file)}：${escape(hit.line)}</p>`).join('')}
    </div>` : ''}
    ${row.has_update ? `<div class="update-links">
      <button class="link-btn" data-update-diff="${escape(row.name)}">${updateState.open.has(row.name) ? '收起完整对比' : '看完整对比'}</button>
      <button class="link-btn" data-update-explain="${escape(row.name)}" ${canAct ? '' : 'disabled'}>让 Codex 解释</button>
      ${row.local_modified !== false ? `<button class="link-btn" data-update-merge="${escape(row.name)}" ${canAct ? '' : 'disabled'}>交给 Codex 合并</button>` : ''}
      <span class="item-end">
        ${row.local_modified !== false ? `<label class="check">这份怎么处理
          <select class="input" data-update-choice="${escape(row.name)}" ${canAct ? '' : 'disabled'}>
            <option value="upstream" ${choice === 'upstream' ? 'selected' : ''}>用上游的</option>
            <option value="keep" ${choice === 'keep' ? 'selected' : ''}>保留我的</option>
            ${merge ? `<option value="merge" ${choice === 'merge' ? 'selected' : ''}>采用已核对的合并结果</option>` : ''}
          </select></label>` : ''}
        <button class="btn btn-small" data-update-one="${escape(row.name)}" ${canAct ? '' : 'disabled'}>
          ${row.source?.kind === 'lark' ? '更新整组飞书技能' : '只更新这一个'}</button>
      </span>
    </div>` : ''}
    ${row.baseline_uncertain && row.has_update ? '<p class="item-note">无法判断你是否改过这份技能，默认用上游的。</p>' : ''}
    ${explanation ? `<div class="update-extra"><p>${escape(explanation)}</p></div>` : ''}
    ${notice ? `<div class="update-extra">${notice.html ? notice.html : `<p class="item-note">${escape(notice.text)}</p>`}</div>` : ''}
    ${updateState.open.has(row.name) && row.has_update ? `<details class="fold fold-inner" open><summary>完整对比</summary>
      <div class="comparisons">
        ${row.local_modified !== false && row.your_changes ? `<div><h4>你的改动</h4><pre>${escape(row.your_changes.comparison || '没有文本变化')}</pre></div>` : ''}
        <div><h4>${row.baseline_uncertain ? '上游当前版本与本机的差别' : '上游的改动'}</h4><pre>${escape(row.comparison || '内容相同')}</pre></div>
      </div>
    </details>` : ''}
  </article>`;
}

function renderUpdatesActionBar() {
  if (state.page !== 'updates') return;
  const review = updateState.review;
  if (!review) return hideActionBar();
  const count = updateState.selected.size;
  const ready = review.write_allowed && !updateState.busy && !writeBusy;
  showActionBar({
    text: count ? `将更新选中的 ${count} 个技能` : '还没有勾选要更新的技能',
    note: review.update_count ? `这次查出 ${review.update_count} 个技能有新版本。完成后可以在操作记录里撤销。` : '',
    buttons: [
      {label: '全部更新', kind: 'btn', disabled: !ready || !review.update_count,
       action: button => applyUpdates(review.skills.filter(s => s.has_update && !s.blocked_reason).map(s => s.name), button)},
      {label: count ? `更新选中的 ${count} 个` : '更新选中的', kind: 'btn btn-primary',
       disabled: !ready || !count, action: button => applyUpdates([...updateState.selected], button)},
    ],
  });
}

$('updates-list').addEventListener('change', async event => {
  const checkbox = event.target.closest('[data-update-skill]');
  if (checkbox) {
    const name = checkbox.dataset.updateSkill;
    if (checkbox.checked) updateState.selected.add(name); else updateState.selected.delete(name);
    if (sourceKind(name) === 'lark') {
      for (const row of updateState.review.skills) {
        if (row.source?.kind !== 'lark' || !shownInUpdates(row)) continue;
        if (checkbox.checked) updateState.selected.add(row.name); else updateState.selected.delete(row.name);
      }
      renderUpdates();
    }
    renderUpdatesActionBar();
    return;
  }
  const select = event.target.closest('[data-update-choice]');
  if (!select) return;
  const name = select.dataset.updateChoice;
  updateState.choices.set(name, select.value);
  if (select.value !== 'keep') return;
  updateState.busy = true;
  updateState.notices.set(name, {text: '正在找你改过的地方…'});
  renderUpdates();
  try {
    const result = await api('/api/updates/calibrate', {review_id: updateState.review.id, name});
    updateState.notices.set(name, {text: result.comparison || '没有发现你改过的地方。'});
  } catch (error) {
    updateState.choices.set(name, 'upstream');
    updateState.notices.set(name, {text: error.message});
    toast({text: error.message, tone: 'error', sticky: true});
  } finally {
    updateState.busy = false;
    renderUpdates();
  }
});

$('updates-list').addEventListener('click', async event => {
  const button = event.target.closest('button');
  if (!button) return;
  const diffName = button.dataset.updateDiff;
  const explainName = button.dataset.updateExplain;
  const mergeName = button.dataset.updateMerge;
  const oneName = button.dataset.updateOne;
  if (diffName) {
    if (updateState.open.has(diffName)) updateState.open.delete(diffName); else updateState.open.add(diffName);
    renderUpdates();
    return;
  }
  if (oneName) { await applyUpdates([oneName], button); return; }
  if (explainName) {
    await withBusy(button, '正在解释…', async () => {
      try {
        const result = await api('/api/updates/explain', {review_id: updateState.review.id, name: explainName});
        updateState.explanations.set(explainName, result.explanation);
      } catch (error) {
        toast({text: error.message, tone: 'error', sticky: true});
      }
      renderUpdates();
    });
    return;
  }
  if (mergeName) {
    await withBusy(button, '正在合并…', async () => {
      try {
        const result = await api('/api/updates/merge', {review_id: updateState.review.id, name: mergeName});
        updateState.merges.set(mergeName, {id: result.merge_id, accepted: false});
        updateState.notices.set(mergeName, {html: `
          <h3 class="sub-title">合并预览</h3>
          <p>${escape(result.explanation)}</p>
          ${result.script_files?.length ? `<div class="risk-block"><p><strong>合并后脚本或执行权限有变化</strong></p><p>${result.script_files.map(escape).join('、')}</p></div>` : ''}
          <details class="fold fold-inner" open><summary>合并后与本机的差别</summary><pre>${escape(result.comparison || '内容相同')}</pre></details>
          <p><button class="btn btn-small" data-update-accept="${escape(mergeName)}">我已看过这份合并结果</button></p>`});
      } catch (error) {
        toast({text: error.message, tone: 'error', sticky: true});
      }
      renderUpdates();
    });
    return;
  }
  const acceptName = button.dataset.updateAccept;
  if (acceptName) {
    const ok = await confirmDialog({
      title: '采用这份合并结果',
      lines: ['这份合并结果会加入待更新名单。', '按下“更新选中的”之后才会真正写入。'],
      note: '可以撤销。', okText: '采用',
    });
    if (!ok) return;
    updateState.merges.get(acceptName).accepted = true;
    updateState.choices.set(acceptName, 'merge');
    updateState.selected.add(acceptName);
    renderUpdates();
  }
});

async function applyUpdates(names, button = null) {
  const review = updateState.review;
  if (!review || updateState.busy || !names.length) return null;
  let confirmLark = false;
  if (names.some(name => sourceKind(name) === 'lark')) {
    confirmLark = true;
    names = [...new Set([...names, ...review.skills.filter(s => s.has_update && s.source?.kind === 'lark').map(s => s.name)])];
    const ok = await confirmDialog({
      title: '一起更新飞书技能',
      lines: ['飞书技能要整组一起更新，会同时升级 lark-cli 和全部飞书技能。'],
      note: '可以撤销。', okText: '一起更新',
    });
    if (!ok) return;
  }
  const choices = {};
  const mergeIds = {};
  for (const name of names) {
    const choice = updateState.choices.get(name) || 'upstream';
    choices[name] = choice;
    if (choice === 'merge') {
      const merge = updateState.merges.get(name);
      if (!merge?.accepted) { toast({text: `${name}：请先生成合并结果，并确认已看过。`, tone: 'error', sticky: true}); return; }
      mergeIds[name] = merge.id;
    }
  }
  const preview = names.map(name => {
    const choice = choices[name];
    const note = choice === 'keep' ? '保留我的' : choice === 'merge' ? '用已核对的合并结果' : '';
    return {name, note};
  });
  const ok = await confirmDialog({
    title: '更新这些技能',
    lines: [confirmLark ? '飞书技能整组一起更新。' : '分配保持原样。'],
    groups: [{label: `更新 ${names.length} 个技能`, items: preview}],
    note: '完成后可以在操作记录里撤销。', okText: '更新',
  });
  if (!ok) return;
  // 只置防重入标记，不在这里重画：重画会把刚拿到的那颗按钮换成新节点，
  // 后面 runWrite 的「正在更新…」就写到旧节点上了。
  updateState.busy = true;
  const result = await runWrite({
    button,
    busyText: '正在更新…',
    work: async () => {
      const written = await api('/api/updates/apply', {
        review_id: review.id, skills: names, choices, merge_ids: mergeIds,
        confirm_lark_cli: confirmLark, confirmed: true,
      });
      await refreshEverything();
      await refreshUpdates();
      return written;
    },
    success: written => ({
      text: written.message || '更新完成',
      undo: undoButton => undoOperation(written.id, {skills: names, message: written.message, button: undoButton}),
    }),
  });
  updateState.busy = false;
  renderUpdates();
  return result;
}

async function checkUpdates(withdrawn = false) {
  $('updates-check').disabled = true;
  setTask('updates', {text: '正在准备检查名单…'});
  try {
    const review = await api('/api/updates/check', {withdrawn});
    renderUpdates(review);
  } catch (error) {
    $('updates-check').disabled = false;
    setTask('updates', {text: error.message, tone: 'error', retry: () => checkUpdates(withdrawn)});
  }
}

$('updates-check').addEventListener('click', () => {
  if (updateState.review?.running) return;
  checkUpdates(false);
});
$('withdrawn-check').addEventListener('click', () => {
  showPage('updates');
  toast({text: '正在检查已经撤下的技能。'});
  checkUpdates(true);
});
setInterval(() => { if (updateState.review?.running && !updateState.busy) refreshUpdates(); }, 1200);

/* ==================== 清理页 ==================== */

function lastUseText(row) {
  if (!row.last_used_at) return '没有使用记录';
  const days = daysSince(row.last_used_at);
  return days === null ? '没有使用记录' : days <= 0 ? '今天用过' : `${days} 天前`;
}

/* 覆盖说明：只列这次统计里出现的 agent，顺序按表里的顺序。 */
function coverageText(coverage) {
  const ids = [...state.agents.map(agent => agent.id), ...Object.keys(coverage)]
    .filter((id, index, list) => coverage[id] && list.indexOf(id) === index);
  return ids.map(id => `${agentName(id)}：${coverage[id].message}`).join('\n');
}

/* 可省字数：按表里的 agent 顺序列出这次统计到的每个 agent。 */
function renderCleanupSavings(view) {
  if (!view.candidates.length) return '';
  const done = new Set();
  const ids = [...state.agents.map(agent => agent.id), ...Object.keys(view.coverage || {})]
    .filter(id => view.coverage?.[id] && !done.has(id) && done.add(id));
  return ids.map(id => `<span class="saving">${escape(agentName(id))}：可省 ${number(view.savings?.[id] || 0)} 字说明</span>`).join('');
}

function renderCleanup() {
  const view = state.cleanup;
  if (state.page !== 'cleanup') return;
  if (!view) {
    $('cleanup-savings').innerHTML = '';
    $('cleanup-rows').innerHTML = '<tr><td class="empty" colspan="5">正在生成清理名单…</td></tr>';
    $('withdrawn-list').innerHTML = '<p class="item-note">正在读取…</p>';
    renderCleanupActionBar();
    return;
  }
  $('cleanup-savings').innerHTML = renderCleanupSavings(view);

  $('cleanup-rows').innerHTML = view.candidates.map(row => `<tr>
    <td class="col-check"><label class="check-hit"><input type="checkbox" data-cleanup="${escape(row.name)}"
      aria-label="${escape('清理 ' + row.name)}" ${state.cleanupSelected.has(row.name) ? 'checked' : ''} ${view.write_allowed && !writeBusy ? '' : 'disabled'}></label></td>
    <td><strong>${nameHtml(row.name)}</strong></td>
    <td>${escape((row.assigned_agents || []).map(id => agentName(id)).join('、') || '没分配')}</td>
    <td class="col-last">${escape(lastUseText(row))}</td>
    <td class="col-num">${number(row.description_chars)}</td>
  </tr>`).join('') || '<tr><td class="empty" colspan="5">没有需要清理的技能。60 天内都用过。</td></tr>';

  $('cleanup-status').textContent = view.checked_at
    ? `名单生成于 ${new Date(view.checked_at).toLocaleString('zh-CN')}，共 ${view.candidates.length} 个候选。` + (view.excluded?.length ? `另有 ${view.excluded.length} 个暂时不动。` : '')
    : '';
  $('cleanup-status').title = coverageText(view.coverage || {});

  $('withdrawn-list').innerHTML = view.withdrawn.map(row => `<div class="item-row">
    <div>
      <div class="item-title">${nameHtml(row.name)}</div>
      <div class="item-note">原来分配给 ${escape((row.previous_agents || []).map(id => agentName(id)).join('、') || '没有记录')}${row.withdrawn_at ? ' · ' + escape(new Date(row.withdrawn_at).toLocaleDateString('zh-CN')) : ''}</div>
    </div>
    <span class="item-end"><button class="btn btn-small" data-restore-withdrawn="${escape(row.name)}" ${view.write_allowed && !writeBusy ? '' : 'disabled'}>恢复原分配</button></span>
  </div>`).join('') || '<p class="empty">还没有已撤下的技能。</p>';
  renderCleanupActionBar();
}

function renderCleanupActionBar() {
  if (state.page !== 'cleanup') return;
  const view = state.cleanup;
  if (!view || !view.candidates.length) return hideActionBar();
  const count = state.cleanupSelected.size;
  const keep = view.candidates.length - count;
  showActionBar({
    text: count ? `将从所有 agent 撤下 ${count} 个技能` : '这次不撤下任何技能',
    note: keep ? `取消勾选的 ${keep} 个会记为今天留下。清理只从 agent 撤下，文件留在仓库，可以在操作记录里撤销。`
               : '文件留在仓库，可以在操作记录里撤销。',
    buttons: [{
      label: count ? `清理选中的 ${count} 个` : '清理选中的',
      kind: 'btn btn-primary',
      disabled: !view.write_allowed || !view.candidates.length || Boolean(writeBusy),
      action: button => applyCleanup(button),
    }],
  });
}

async function loadCleanup({force = false} = {}) {
  if (state.cleanup && !force) return;
  setTask('cleanup', {text: '正在统计用量，然后生成清理名单…'});
  try {
    state.cleanup = await api('/api/cleanup');
    state.cleanupSelected = new Set(state.cleanup.candidates.map(row => row.name));
    state.cleanupTries = 0;
    clearTask('cleanup');
    renderCleanup();
  } catch (error) {
    if (error.retry && state.cleanupTries < 60) {
      state.cleanupTries++;
      setTask('cleanup', {text: '正在统计用量，完成后再生成名单…'});
      renderCleanup();
      setTimeout(() => loadCleanup({force: true}), 2000);
      return;
    }
    setTask('cleanup', {text: error.message, tone: 'error', retry: () => { state.cleanupTries = 0; loadCleanup({force: true}); }});
    renderCleanup();
  }
}

async function applyCleanup(button) {
  const view = state.cleanup;
  if (!view) return;
  const cleaned = view.candidates.filter(row => state.cleanupSelected.has(row.name)).map(row => row.name);
  const keep = view.candidates.filter(row => !state.cleanupSelected.has(row.name)).map(row => row.name);
  const warnings = [...new Set(view.candidates.filter(row => state.cleanupSelected.has(row.name))
    .flatMap(row => (row.path_warnings || []).map(w => '受影响的文件：' + w.file)))];
  const ok = await confirmDialog({
    title: '清理这些技能',
    lines: [`将从所有 agent 撤下这 ${cleaned.length} 个技能。`,
            keep.length ? `取消勾选的 ${keep.length} 个会记为今天留下。` : '',
            ...warnings],
    groups: [{label: '要撤下的技能', items: cleaned.map(name => ({name}))}],
    note: '文件留在仓库，可以在操作记录里撤销。', okText: '清理',
  });
  if (!ok) return;
  await runWrite({
    button,
    busyText: '正在清理…',
    work: async () => {
      const written = await api('/api/cleanup/apply', {
        keep, candidates: view.candidates.map(row => row.name), revision: view.revision, confirmed: true,
      });
      await loadCleanupForce();
      await refreshEverything();
      return written;
    },
    success: written => ({
      text: written.message || '清理完成',
      undo: undoButton => undoOperation(written.id, {skills: cleaned, message: written.message, button: undoButton}),
    }),
  });
}

async function loadCleanupForce() {
  state.cleanup = null;
  await loadCleanup({force: true});
}

$('cleanup-rows').addEventListener('change', event => {
  const name = event.target.dataset.cleanup;
  if (!name) return;
  if (event.target.checked) state.cleanupSelected.add(name); else state.cleanupSelected.delete(name);
  renderCleanupActionBar();
});

$('cleanup-rows').addEventListener('click', event => {
  const row = event.target.closest('tr');
  if (row && !event.target.closest('input')) row.querySelector('input')?.click();
});

$('withdrawn-refresh').addEventListener('click', event => withBusy(event.currentTarget, '正在刷新…', loadCleanupForce));

$('withdrawn-list').addEventListener('click', async event => {
  const button = event.target.closest('button');
  const name = button?.dataset.restoreWithdrawn;
  if (!name) return;
  const row = state.cleanup.withdrawn.find(item => item.name === name);
  const back = (row?.previous_agents || []).map(agentName).join('、') || '原来的 agent';
  const ok = await confirmDialog({
    title: '恢复这个技能',
    lines: [`会把它重新分配给${back}。`],
    groups: [{label: '要恢复的技能', items: [{name}]}],
    note: '可以在操作记录里撤销。', okText: '恢复',
  });
  if (!ok) return;
  await runWrite({
    button,
    busyText: '正在恢复…',
    work: async () => {
      const written = await api('/api/withdrawn/restore', {skills: [name], revision: state.cleanup.revision, confirmed: true});
      await loadCleanupForce();
      await refreshEverything();
      return written;
    },
    success: written => ({
      text: '已经恢复原来的分配',
      undo: undoButton => undoOperation(written.id, {skills: [name], message: written.message, button: undoButton}),
    }),
  });
});

/* ==================== 操作记录页 ==================== */

function renderLog() {
  if (state.page !== 'log') return;
  $('log-list').innerHTML = state.logs.map(record => `<li class="${record.undone ? 'is-undone' : ''}">
    <span class="log-time">${escape(new Date(record.time).toLocaleString('zh-CN'))}</span>
    <div class="log-body">
      <p>${escape(record.message)}</p>
      <p class="item-note">影响：${escape((record.agents || []).map(id => agentName(id)).join('、') || '技能仓库')}${record.undone ? ' · 已撤销' : record.undo_of ? ' · 这是一次撤销' : ''}</p>
      ${(record.skills || []).length ? `<details class="fold fold-inner"><summary>影响 ${record.skills.length} 个技能</summary>
        <p class="item-note">${record.skills.map(escape).join('、')}</p></details>` : ''}
    </div>
    <span class="log-end">${record.undone || record.undo_of || !state.table?.write_allowed || writeBusy ? ''
      : `<button class="btn btn-small" data-undo="${escape(record.id)}">撤销</button>`}</span>
  </li>`).join('') || '<li><p class="empty">还没有操作记录。做过分配、更新、清理之后会显示在这里。</p></li>';
}

$('log-refresh').addEventListener('click', event => withBusy(event.currentTarget, '正在刷新…', refreshLog));

$('log-list').addEventListener('click', async event => {
  const button = event.target.closest('[data-undo]');
  if (!button) return;
  const id = button.dataset.undo;
  const record = state.logs.find(item => item.id === id);
  await undoOperation(id, {skills: record?.skills || [], message: record?.message || '', button});
});

/* ==================== 诊断与备份页 ==================== */

const CATEGORIES = {user: '用户技能', builtin: '软件内置', plugin: '插件技能', plugin_cache: '插件或市场缓存',
                    vendor: '下载的候选库', unknown_agent: '疑似新 agent', ignored: '已忽略',
                    backup_temp: '备份或临时目录', reference: '参考资料'};

/* 扫描条目里的 agent 编号翻成名字，再写成一句给人看的话。 */
function manualOnlyText(skill) {
  const names = (skill.manual_only_for || []).map(agentName);
  return names.length ? `<p class="item-note">${escape(names.join('、') + ' 只允许手动调用')}</p>` : '';
}

function disabledText(skill, data = state.inventory) {
  const names = Object.entries(data?.disabled || {})
    .filter(([, value]) => (value?.names || []).includes(skill.name))
    .map(([id]) => agentName(id));
  return names.length ? `<p class="item-note">${escape(names.join('、') + ' 已停用')}</p>` : '';
}

function renderDiagnostics() {
  if (state.page !== 'diagnostics' || !state.inventory) return;
  const data = state.inventory;
  renderMigrationStatus();

  $('conflict-count').textContent = data.conflicts.length ? `${data.conflicts.length} 组` : '没有';
  $('conflict-list').innerHTML = data.conflicts.map(conflict => `<details class="fold fold-inner">
    <summary>${escape(conflict.name)}<span class="tag tag-quiet">${conflict.versions.length} 种内容</span></summary>
    ${conflict.versions.map((version, index) => `<div class="version">
      <p><strong>第 ${index + 1} 份</strong>${version.copies[0].version ? ' · 版本 ' + escape(version.copies[0].version) : ''}</p>
      ${version.copies.map(copy => `<p class="mono">${pathLabel(copy.path)}</p>`).join('')}
    </div>`).join('')}
  </details>`).join('') || '<p class="empty">没有发现同名不同内容的技能。</p>';

  const rootSelect = $('root-filter');
  const current = rootSelect.value;
  rootSelect.innerHTML = '<option value="">全部用户技能目录</option>'
    + data.roots.map(root => `<option value="${escape(root.path)}">${pathLabel(root.path)}（${root.entry_count} 个入口）</option>`).join('');
  rootSelect.value = current;

  const search = $('inventory-search')?.value.toLowerCase() || '';
  const includeReadonly = $('include-readonly').checked;
  const chosen = rootSelect.value;
  const rows = data.roots
    .filter(root => (!chosen || root.path === chosen) && (includeReadonly || root.category === 'user'))
    .flatMap(root => (root.skills || []).map(skill => ({skill, root})))
    .filter(({skill}) => (skill.name + ' ' + skill.description).toLowerCase().includes(search));
  $('inventory-count').textContent = `显示 ${rows.length} 个目录入口。同一个技能在不同目录里会各列一行。`;
  $('inventory-rows').innerHTML = rows.map(({skill, root}) => `<tr>
    <td><div class="skill-line"><strong>${escape(skill.name)}</strong>${skill.name_mismatch ? '<span class="tag tag-quiet">名称与文件夹名称不同</span>' : ''}</div>
      <p class="skill-desc" title="${escape(skill.description)}">${escape(skill.description)}</p></td>
    <td><p class="mono">${pathLabel(skill.path)}</p>${skill.link_target ? `<p class="item-note">指向 ${pathLabel(skill.link_target)}</p>` : ''}
      <p class="item-note">${escape((root.readers || []).map(agentName).join(' / '))} · ${escape(CATEGORIES[root.category] || root.category)}</p></td>
    <td>${escape(skill.broken ? '链接已失效' : skill.kind === 'link' ? '链接到另一位置' : '存放完整文件')}
      ${manualOnlyText(skill)}${disabledText(skill, data)}
      ${skill.model_invocable === false ? '<p class="item-note">只允许手动调用</p>' : ''}
      ${skill.warning ? `<p class="item-note">${escape(skill.warning)}</p>` : ''}</td>
    <td class="col-num">${number(skill.description_chars)}</td>
  </tr>`).join('') || '<tr><td class="empty" colspan="4">没有符合条件的技能。</td></tr>';

  $('root-list').innerHTML = data.roots.map(root => `<tr>
    <td class="mono">${pathLabel(root.path)}${root.exists ? '' : '<p class="item-note">目录还不存在</p>'}
      ${root.unresolved_links.length ? `<p class="item-note">另有 ${root.unresolved_links.length} 个目录链接已失效。</p>` : ''}</td>
    <td>${escape(CATEGORIES[root.category] || root.category)}</td>
    <td class="col-num">${number(root.entry_count)}</td>
    <td class="col-num">${number(root.broken_count)}</td>
  </tr>`).join('');

  $('agent-list').innerHTML = data.agents.map(agent => `<details class="fold fold-inner">
    <summary>${escape(agent.name)}
      <span class="tag tag-quiet">${agent.status === 'ignored' ? '已忽略' : agent.status === 'discovered' ? '已发现，还没接入' : '有盘点档案'}</span></summary>
    <p>${escape(agent.visibility_note || '')}</p>
    ${(agent.skill_roots?.length ? agent.skill_roots : agent.evidence || []).map(path => `<p class="mono">${pathLabel(path)}</p>`).join('')}
    ${agent.usage ? `<p class="item-note">使用记录：${escape(agent.usage)}</p>` : ''}
  </details>`).join('');

  $('discovery-note').textContent = data.discovery_note;
  $('candidate-list').innerHTML = data.candidates.filter(c => !c.default_hidden).map(candidate => `<details class="fold fold-inner">
    <summary>${escape(CATEGORIES[candidate.category] || candidate.category)}
      <span class="tag tag-quiet">${candidate.entry_count} 个目录入口</span></summary>
    <p class="mono">${pathLabel(candidate.path)}</p>
    <p>${candidate.skills.map(s => escape(s.name)).join('、')}</p>
  </details>`).join('')
  + (data.errors.length ? `<details class="fold fold-inner"><summary>有 ${data.errors.length} 个位置没读完整</summary>
      <p class="item-note">系统限制或文件读取失败，已保留为“未知”，不会当作空目录。</p>
      ${data.errors.map(error => `<p class="mono">${pathLabel(error.path)}<br>${escape(error.message)}</p>`).join('')}
    </details>` : '');
}

$('include-readonly').addEventListener('change', () => {
  if ($('include-readonly').checked === false && $('root-filter').value) {
    const root = state.inventory.roots.find(r => r.path === $('root-filter').value);
    if (root && root.category !== 'user') $('root-filter').value = '';
  }
  renderDiagnostics();
});
$('inventory-search').addEventListener('input', renderDiagnostics);
$('root-filter').addEventListener('change', () => {
  const root = state.inventory?.roots.find(r => r.path === $('root-filter').value);
  if (root && root.category !== 'user') $('include-readonly').checked = true;
  renderDiagnostics();
});

/* 迁移与还原：内容照旧，入口改到诊断页。
   已经迁移过就只留“已有备份”；还没迁移时，可选 agent 从 /api/agents 的建议来。 */
let migrationPlan = null;
let backupId = null;

function migrationChoices() {
  const suggested = state.agentsView?.suggested;
  if (suggested?.length) return suggested.map(item => ({id: item.id, name: item.name}));
  return (migrationPlan?.agent_catalog || []).map(item => ({id: item.id, name: item.name}));
}

function renderMigrationChoices() {
  $('migration-agents').innerHTML = migrationChoices()
    .map(item => `<label class="check"><input type="checkbox" data-migration-agent="${escape(item.id)}" checked> ${escape(item.name)}</label>`).join('');
  const groups = state.agentsView?.must_select_together || [];
  $('migration-groups').textContent = groups.map(group => {
    const names = group.map(agentName);
    return names.length > 1 ? `${names.join(' 和 ')} 共用一个技能目录，要一起接入。` : '';
  }).filter(Boolean).join(' ');
}

/* 共用一个目录的 agent：勾一个就一起勾上，取消时一起取消。 */
$('migration-agents').addEventListener('change', event => {
  const id = event.target.dataset.migrationAgent;
  if (!id) return;
  for (const group of state.agentsView?.must_select_together || []) {
    if (!group.includes(id)) continue;
    for (const other of group) {
      const input = document.querySelector(`[data-migration-agent="${other}"]`);
      if (input) input.checked = event.target.checked;
    }
  }
});

function migrationError(error) {
  $('migration-error').hidden = false;
  $('migration-error').textContent = error.message;
}

function migrationStep(step) {
  for (const id of ['select', 'review', 'complete']) $('migration-' + id).hidden = id !== step;
  $('migration-error').hidden = true;
}

/* 已经完成首次迁移后，第 1、2 步收起，只留一句说明和“已有备份”。 */
function renderMigrationStatus() {
  const managed = state.agentsView?.managed || [];
  const migrated = managed.length > 0;
  $('migration-done').hidden = !migrated;
  if (migrated) {
    for (const id of ['select', 'review', 'complete']) $('migration-' + id).hidden = true;
    $('migration-done-text').textContent = '已经完成首次迁移；以后接入新 agent，请到设置里的 agent 一栏。';
  } else {
    renderMigrationChoices();
    migrationStep('select');
  }
}

$('migration-preview').addEventListener('click', event => withBusy(event.currentTarget, '正在核对…', async () => {
  try {
    const agents = [...document.querySelectorAll('[data-migration-agent]:checked')].map(input => input.dataset.migrationAgent);
    if (!agents.length) throw new Error('请至少选择一个 agent。');
    migrationPlan = await api('/api/migration/plan?agents=' + agents.join(','));
    renderMigrationReview(migrationPlan);
    migrationStep('review');
  } catch (error) {
    migrationError(error);
  }
}));

function renderMigrationReview(plan) {
  $('migration-mode').textContent = plan.write_allowed
    ? '当前操作模拟目录。迁移前会完整备份，完成后可以一键还原。'
    : '只读模式下可以预览，不能迁移。';
  $('migration-summary').textContent = `共 ${plan.skills.length} 个技能，${plan.conflicts.length} 组内容需要核对。相同内容会直接合并，原来的技能入口会保留。`;
  $('migration-counts').innerHTML = (plan.agents || []).map(id => {
    const before = plan.before[id];
    const after = plan.after[id];
    if (!before || !after) return '';
    return `<details class="fold fold-inner"><summary>${escape(agentName(id))}：可调用 ${before.available.length} → ${after.available.length} 个；自动可用 ${before.automatic.length} → ${after.automatic.length} 个</summary>
      <p class="item-note">迁移前：${escape(before.available.join('、'))}</p>
      <p class="item-note">迁移后：${escape(after.available.join('、'))}</p></details>`;
  }).join('') || '<p class="item-note">没有需要核对的 agent。</p>';
  $('migration-versions').innerHTML = plan.conflicts.map(skill => `<details class="fold fold-inner" open>
    <summary>${escape(skill.name)}<span class="tag tag-quiet">${escape(skill.reason)}</span></summary>
    ${skill.options.map((option, index) => `<p><label class="check">
      <input type="radio" name="choice-${escape(skill.name)}" data-choice="${escape(skill.name)}" value="${escape(option.id)}" ${option.id === skill.default ? 'checked' : ''}>
      第 ${index + 1} 份${option.version ? ' · 版本 ' + escape(option.version) : ''}${option.id === skill.default ? ' · 默认选择' : ''}</label></p>
      <p class="mono">${option.paths.map(pathLabel).join('<br>')}</p>`).join('')}
    <details class="fold fold-inner"><summary data-compare="${escape(skill.name)}">查看完整差异</summary><pre></pre></details>
  </details>`).join('') || '<p class="item-note">没有同名不同内容的技能。</p>';
  $('migration-names').innerHTML = plan.skills.filter(s => s.name_mismatch)
    .map(s => `<p>${escape(s.name)}：${s.entries.map(escape).join('、')}</p>`).join('') || '<p class="item-note">所有名称都一致。</p>';
  $('migration-skipped').innerHTML = plan.skipped
    .map(s => `<p class="mono">${pathLabel(s.path)} · ${escape(s.reason)}</p>`).join('') || '<p class="item-note">没有跳过的目录。</p>';
  $('migration-apply').disabled = !plan.write_allowed;
}

$('migration-versions').addEventListener('click', async event => {
  const name = event.target.dataset.compare;
  if (!name) return;
  const pre = event.target.parentElement.querySelector('pre');
  if (pre.textContent) return;
  try {
    const query = new URLSearchParams({agents: migrationPlan.agents.join(','), plan_id: migrationPlan.plan_id, name});
    pre.textContent = (await api('/api/migration/compare?' + query)).comparison;
  } catch (error) {
    migrationError(error);
  }
});

$('migration-back').addEventListener('click', () => migrationStep('select'));

$('migration-apply').addEventListener('click', async event => {
  const button = event.currentTarget;
  if (!migrationPlan?.write_allowed) return;
  const ok = await confirmDialog({
    title: '开始迁移',
    lines: ['会先备份，再把选中的内容收进统一仓库。每个 agent 原来能调用的技能名单会保留。'],
    note: '完成后可以一键还原。', okText: '迁移',
  });
  if (!ok) return;
  await runWrite({
    button,
    busyText: '正在迁移…',
    onError: migrationError,
    work: async () => {
      const choices = Object.fromEntries([...document.querySelectorAll('[data-choice]:checked')].map(input => [input.dataset.choice, input.value]));
      const result = await api('/api/migration/apply', {confirmed: true, agents: migrationPlan.agents, plan_id: migrationPlan.plan_id, choices});
      backupId = result.backup_id;
      $('migration-result').textContent = '迁移完成';
      $('migration-result-detail').textContent = result.message;
      migrationStep('complete');
      await refreshEverything();
      await refreshMigrationStatus();
      return result;
    },
    success: () => ({text: '迁移完成，可以一键还原'}),
  });
});

async function restoreBackup(id, button = null) {
  const ok = await confirmDialog({
    title: '还原到这份备份',
    lines: ['会把这些 agent 的技能目录和统一仓库恢复到备份时的状态。'],
    note: '还原本身也会记在操作记录里。', okText: '还原',
  });
  if (!ok) return;
  await runWrite({
    button,
    busyText: '正在还原…',
    onError: migrationError,
    work: async () => {
      const result = await api('/api/restore', {confirmed: true, backup_id: id});
      $('migration-result').textContent = '已还原到迁移前';
      $('migration-result-detail').textContent = result.message;
      migrationStep('complete');
      await refreshEverything();
      await refreshMigrationStatus();
      return result;
    },
    success: () => ({text: '已经还原到备份时的状态'}),
  });
}

$('migration-restore').addEventListener('click', event => restoreBackup(backupId, event.currentTarget));

$('migration-backups').addEventListener('click', event => withBusy(event.currentTarget, '正在读取…', async () => {
  try {
    const saved = await api('/api/backups');
    $('migration-backup-list').innerHTML = saved.map(backup => `<div class="item-row">
      <span class="mono">${escape(backup.backup_id)}</span>
      <span class="item-end"><button class="btn btn-small" data-restore-backup="${escape(backup.backup_id)}" ${state.writeAllowed ? '' : 'disabled'}>还原这份备份</button></span>
    </div>`).join('') || '<p class="item-note">还没有迁移备份。</p>';
  } catch (error) {
    migrationError(error);
  }
}));

$('migration-backup-list').addEventListener('click', event => {
  const button = event.target.closest('[data-restore-backup]');
  if (button) restoreBackup(button.dataset.restoreBackup, button);
});

/* 迁移与还原的按钮状态看 /api/status；右上角模式标记只认 /api/table 的 write_allowed。 */
async function refreshMigrationStatus() {
  try {
    const status = await api('/api/status');
    state.writeAllowed = !status.read_only;
    $('migration-mode').textContent = state.writeAllowed ? '迁移前会备份，迁移完成后可以一键还原。' : '只读模式下可以预览，不能迁移。';
    $('migration-apply').disabled = !state.writeAllowed;
  } catch (error) {
    migrationError(error);
  }
}

/* ==================== 启动 ==================== */

async function loadUsage() {
  // 第一次统计可能要几分钟；前 700 毫秒不画出来，很快完成时不闪一下。
  setTask('usage', {text: '正在统计用量（第一次需要几分钟）', quietMs: TASK_QUIET_MS});
  const timer = setInterval(async () => {
    if (tasks.get('usage')?.tone !== 'busy') return;
    try {
      const progress = await api('/api/usage-progress');
      if (progress.running) {
        setTask('usage', {
          text: `正在统计用量（第 ${number(progress.done)}/${number(progress.total)} 个会话）`,
          ratio: progress.total ? progress.done / progress.total : null,
          quietMs: TASK_QUIET_MS,
        });
      }
    } catch { /* 统计接口偶发失败不打断页面 */ }
  }, 1000);
  try {
    indexUsage(await api('/api/usage'));
    // 做完直接消失：不再显示「用量统计完成」那一行，免得把表格顶下去又弹回来。
    clearTask('usage');
    renderSkillTable();
    if (state.detail) renderDetail();
  } catch (error) {
    clearTask('usage');
    if (error.retry) {
      setTask('usage', {text: '用量正在统计，稍后自动重试', tone: 'busy'});
      setTimeout(loadUsage, 2000);
    } else {
      setTask('usage', {text: '用量暂时读不到，技能分配仍可照常操作。', tone: 'error', retry: () => { clearTask('usage'); loadUsage(); }});
    }
  } finally {
    clearInterval(timer);
  }
}

function renderFooter() {
  const generated = state.inventory?.generated_at;
  $('footer-note').textContent = '关掉全部看板页面后，程序会在 30 秒内退出；正在检查更新或起中文名时，会等任务完成。'
    + (generated ? `盘点时间：${new Date(generated).toLocaleString('zh-CN')}。` : '');
}

async function start() {
  heartbeat();
  setInterval(heartbeat, 10000);
  document.addEventListener('visibilitychange', () => { if (!document.hidden) heartbeat(); });
  addEventListener('pagehide', () => {
    fetch('/api/heartbeat?closing=1&page=' + pageId, {method: 'POST', headers, keepalive: true}).catch(() => {});
  });
  renderAgentSummary();
  renderSkillTable();
  renderTasks();
  try {
    await Promise.all([refreshInventory(), refreshTable()]);
    renderFooter();
  } catch (error) {
    toast({text: '技能清单没能读出来：' + error.message + ' 关掉页面重新打开看板再试。', tone: 'error', sticky: true});
  }
  await refreshLog();
  await refreshAgents().catch(() => {});
  renderMigrationStatus();
  refreshMigrationStatus();
  loadUsage();
  refreshUpdates();
  showPage('skills');
}

start();
