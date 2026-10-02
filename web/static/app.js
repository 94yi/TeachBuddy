'use strict';

const $ = (selector, root = document) => root.querySelector(selector);
const $$ = (selector, root = document) => Array.from(root.querySelectorAll(selector));
const state = {
  status: null, templates: [], history: [], knowledge: [], selected: new Set(),
  result: null, dirty: false, messages: [], chatBusy: false, generationBusy: false,
  fileBatch: null, fileItems: [], currentPage: 'lesson', initialized: false,
  leaving: false, requestEpoch: 0,
  resources: { items: [], total: 0, page: 1, pages: 1, loaded: false, loading: false,
    loadId: 0, query: { q: '', subject: '', grade: '' }, attempts: [], importing: false, added: new Map() }
};

function element(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
}

function icon(name, small = true) {
  const node = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
  node.setAttribute('class', small ? 'icon small' : 'icon');
  node.setAttribute('aria-hidden', 'true');
  const use = document.createElementNS('http://www.w3.org/2000/svg', 'use');
  use.setAttribute('href', '#i-' + name);
  node.append(use);
  return node;
}

function notify(message, isError = false) {
  if (state.leaving) return;
  const toast = element('div', 'toast' + (isError ? ' error' : ''), message);
  $('#toast-region').append(toast);
  window.setTimeout(() => toast.remove(), isError ? 9000 : 4500);
}

function setBusy(button, busy) {
  button.disabled = busy;
  button.classList.toggle('is-busy', busy);
  button.setAttribute('aria-busy', String(busy));
}

function showLogin() {
  if ($('#settings-dialog').open) $('#settings-dialog').close();
  if (!$('#login-dialog').open) $('#login-dialog').showModal();
  state.initialized = false;
}

async function api(path, options = {}) {
  if (state.leaving) throw new Error('当前会话已结束。');
  const requestEpoch = state.requestEpoch;
  const init = { credentials: 'same-origin', ...options };
  const method = (init.method || 'GET').toUpperCase();
  const headers = new Headers(init.headers || {});
  if (method !== 'GET' && method !== 'HEAD') headers.set('X-TeachBuddy-Request', '1');
  if (init.body && !(init.body instanceof FormData)) {
    headers.set('Content-Type', 'application/json');
    init.body = JSON.stringify(init.body);
  }
  init.headers = headers;
  let response;
  try {
    response = await fetch(path, init);
  } catch (error) {
    throw new Error('无法连接服务，请检查网络后重试。');
  }
  if (state.leaving || requestEpoch !== state.requestEpoch) throw new Error('当前会话已结束。');
  if (!response.ok) {
    let message = '请求未完成（' + response.status + '），请稍后重试。';
    try {
      const data = await response.json();
      if (typeof data.detail === 'string') message = data.detail;
      else if (Array.isArray(data.detail)) message = data.detail.map(item => item.msg || '输入格式不正确').join('；');
    } catch (_) { /* A proxy may return a non-JSON error. */ }
    if (response.status === 401 && path !== '/api/login') showLogin();
    throw new Error(message);
  }
  if (options.binary) return response;
  if (response.status === 204) return null;
  const data = await response.json();
  if (state.leaving || requestEpoch !== state.requestEpoch) throw new Error('当前会话已结束。');
  return data;
}

function post(path, body, extra = {}) {
  return api(path, { method: 'POST', body, ...extra });
}

function dateLabel(value) {
  if (!value) return '';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return String(value).slice(0, 16);
  return new Intl.DateTimeFormat('zh-CN', { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' }).format(date);
}

function sizeLabel(size) {
  const value = Number(size) || 0;
  if (value < 1024) return value + ' B';
  if (value < 1024 * 1024) return (value / 1024).toFixed(1) + ' KB';
  return (value / 1024 / 1024).toFixed(1) + ' MB';
}

function switchPage(page) {
  if (!['lesson', 'chat', 'knowledge', 'files'].includes(page)) return;
  state.currentPage = page;
  if (page === 'knowledge' && state.initialized && !state.resources.loaded && !state.resources.loading) loadPublicResources();
  $$('[data-page]').forEach(node => { node.hidden = node.dataset.page !== page; });
  $$('[data-nav]').forEach(button => {
    const active = button.dataset.nav === page;
    button.classList.toggle('active', active);
    if (active) button.setAttribute('aria-current', 'page');
    else button.removeAttribute('aria-current');
  });
  const titles = { lesson: '教案工作台', chat: 'AI 讨论', knowledge: '资料库', files: '文件整理' };
  document.title = '教伴 TeachBuddy · ' + titles[page];
}

function updateServiceStatus() {
  const status = state.status || {};
  const configured = Boolean(status.ai_configured);
  $('#ai-mode').disabled = !configured;
  $('#ai-mode-label').classList.toggle('unavailable', !configured);
  $('#ai-mode-hint').textContent = configured ? '按你的想法展开' : '服务尚未配置';
  if (!configured) $('input[name="mode"][value="offline"]').checked = true;
  $('#revise-result').disabled = !configured || state.generationBusy;
  $('#revision-hint').textContent = configured ? 'AI 会根据当前正文与所选资料改稿。' : '配置 AI 服务后可使用改稿；现在可直接编辑正文。';
  $('#chat-unavailable').hidden = configured;
  $('#send-chat').disabled = !configured || state.chatBusy;
  $('#chat-input').disabled = !configured;
  $('#footer-status').textContent = configured ? 'AI 服务已配置 · 模板可用' : '模板可用 · AI 未配置';
  $('#settings-status-dot').classList.toggle('online', configured);
  $('#settings-ai-title').textContent = configured ? 'AI 服务已配置' : '模板模式可用';
  $('#settings-ai-description').textContent = configured ? '教案创作、讨论和改稿可调用已配置的 AI 服务。' : '教案模板无需 AI 配置，随时可以开始备课。';
  $('#settings-model').textContent = status.model || '未配置';
  $('#settings-auth').textContent = status.login_required ? (status.authenticated ? '已登录 · 密码保护' : '需要访问密码') : '未启用访问密码';
  $('#logout-button').hidden = !status.login_required || !status.authenticated;
  const limits = status.limits || {};
  const limitText = limits.max_upload_mb ? '每个文件最多 ' + limits.max_upload_mb + ' MB' : '上传限制由服务器设定';
  const batchLimit = limits.max_total_mb ? ' · 每批最多 ' + limits.max_total_mb + ' MB' : '';
  const countLimit = limits.max_files ? ' · 最多 ' + limits.max_files + ' 个' : '';
  $('#settings-limits').textContent = limitText + batchLimit + countLimit;
  $('#knowledge-limit').textContent = limitText + ' · 保存至服务端';
  $('#files-limit').textContent = limitText + batchLimit + countLimit;
}

async function loadStatus() {
  state.status = await api('/api/status');
  updateServiceStatus();
  if (state.status.login_required && !state.status.authenticated) {
    showLogin();
    return false;
  }
  if ($('#login-dialog').open) $('#login-dialog').close();
  return true;
}

async function loadTemplates(preferredId) {
  const data = await api('/api/templates');
  state.templates = Array.isArray(data.templates) ? data.templates : [];
  const select = $('#lesson-template');
  const previous = preferredId || select.value;
  select.replaceChildren();
  for (const template of state.templates) {
    const option = element('option', '', template.name);
    option.value = template.id;
    select.append(option);
  }
  if (!state.templates.length) {
    const option = element('option', '', '暂无可用模板，请先导入');
    option.value = '';
    select.append(option);
  }
  if (state.templates.some(item => item.id === previous)) select.value = previous;
  updateTemplateActions();
}

function updateTemplateActions() {
  $('#delete-template-button').hidden = !/^[a-f0-9]{32}$/.test($('#lesson-template').value);
}

async function loadHistory() {
  const data = await api('/api/history');
  state.history = Array.isArray(data.items) ? data.items.slice(0, 20) : [];
  renderHistory();
}

function renderHistory() {
  const container = $('#history-list');
  container.replaceChildren();
  if (!state.history.length) {
    container.append(element('div', 'quiet-empty', '还没有教案，从上方创建第一份吧。'));
    return;
  }
  for (const item of state.history) {
    const card = element('div', 'history-card');
    const open = element('button', 'history-open');
    open.type = 'button';
    open.append(element('strong', '', item.title || '未命名教案'));
    const mode = { offline: '模板', ai: 'AI', manual: '编辑保存' }[item.mode] || '教案';
    open.append(element('span', '', dateLabel(item.created_at) + ' · ' + mode));
    open.addEventListener('click', () => {
      if (state.generationBusy) return notify('请等待当前教案生成完成。');
      if (state.dirty && !window.confirm('当前修改尚未保存。是否打开这份历史教案？')) return;
      displayResult(item);
      $('#result-heading').scrollIntoView({ behavior: 'smooth', block: 'center' });
    });
    const remove = element('button', 'icon-button');
    remove.type = 'button';
    remove.setAttribute('aria-label', '删除教案：' + (item.title || '未命名教案'));
    remove.append(icon('trash'));
    remove.addEventListener('click', async () => {
      if (!window.confirm('删除这份教案历史？此操作无法撤销。')) return;
      setBusy(remove, true);
      try {
        await api('/api/history/' + encodeURIComponent(item.id), { method: 'DELETE' });
        await loadHistory();
        notify('教案历史已删除。');
      } catch (error) { notify(error.message, true); setBusy(remove, false); }
    });
    card.append(icon('book'), open, remove);
    container.append(card);
  }
}

async function loadKnowledge() {
  const data = await api('/api/knowledge');
  state.knowledge = Array.isArray(data.items) ? data.items : [];
  const currentIds = new Set(state.knowledge.map(item => item.id));
  state.selected.forEach(id => { if (!currentIds.has(id)) state.selected.delete(id); });
  renderKnowledge();
  if (state.resources.loaded && !state.resources.loading) renderPublicResources();
}

function updateSelectedSources() {
  const count = state.selected.size;
  $$('.selected-source-text').forEach(node => { node.textContent = count ? '已选用 ' + count + ' 份资料' : '未选用资料'; });
  $('#knowledge-selected-count').textContent = '已选择 ' + count + ' 份资料';
}

function renderKnowledge() {
  const container = $('#knowledge-list');
  container.replaceChildren();
  $('#knowledge-count').textContent = state.knowledge.length + ' 份资料 · 最多选用 20 份';
  if (!state.knowledge.length) {
    const empty = element('div', 'resource-empty', '资料库还空着');
    empty.append(element('p', '', '上传一份教学资料，积累自己的教学参考。'));
    container.append(empty);
  }
  for (const item of state.knowledge) {
    const row = element('div', 'resource-row');
    const label = element('label', 'resource-label');
    const checkbox = element('input');
    checkbox.type = 'checkbox';
    checkbox.checked = state.selected.has(item.id);
    checkbox.addEventListener('change', () => {
      if (checkbox.checked && state.selected.size >= 20) {
        checkbox.checked = false;
        notify('一次最多选用 20 份资料，请先取消部分选择。', true);
        return;
      }
      if (checkbox.checked) state.selected.add(item.id);
      else state.selected.delete(item.id);
      updateSelectedSources();
    });
    const info = element('span', 'resource-info');
    info.append(element('strong', '', item.title || '未命名资料'), element('small', '', (Number(item.chars) || 0).toLocaleString('zh-CN') + ' 字 · ' + dateLabel(item.created_at)));
    label.append(checkbox, info);
    const remove = element('button', 'icon-button');
    remove.setAttribute('aria-label', '删除资料：' + (item.title || '未命名资料'));
    remove.append(icon('trash'));
    remove.addEventListener('click', async () => {
      if (!window.confirm('从资料库删除「' + (item.title || '这份资料') + '」？此操作无法撤销。')) return;
      setBusy(remove, true);
      try {
        await api('/api/knowledge/' + encodeURIComponent(item.id), { method: 'DELETE' });
        state.selected.delete(item.id);
        await loadKnowledge();
        notify('资料已删除。');
      } catch (error) { notify(error.message, true); setBusy(remove, false); }
    });
    row.append(label, remove);
    container.append(row);
  }
  updateSelectedSources();
}

function publicArticleURL(value) {
  try {
    const url = new URL(value);
    if (url.protocol !== 'https:' || url.hostname !== 'mp.weixin.qq.com' || url.username || url.password || (url.port && url.port !== '443')) return null;
    return url.href;
  } catch (_) { return null; }
}

function resourceHasFilters() {
  const query = state.resources.query;
  return Boolean(query.q || query.subject || query.grade);
}

function renderPublicResources() {
  if (state.leaving) return;
  const resources = state.resources;
  const list = $('#public-resource-list');
  list.replaceChildren();
  if (!resources.items.length) {
    const empty = element('div', 'public-resource-empty');
    const mark = element('span', 'feature-icon');
    mark.append(icon('book', false));
    const filtered = resourceHasFilters();
    empty.append(mark, element('h3', '', filtered ? '没有找到匹配的资源' : '还没有收藏公众号文章'));
    empty.append(element('p', '', filtered ? '试试其他关键词，或重置学科与年级筛选。' : '粘贴可公开访问的文章链接，开始建立你的教学参考目录。这里只展示真实导入的文章。'));
    list.append(empty);
  }
  const knowledgeIds = new Set(state.knowledge.map(item => item.id));
  const knowledgeResourceIds = new Set(state.knowledge.map(item => item.resource_id).filter(Boolean));
  for (const item of resources.items) {
    const card = element('article', 'public-resource-card');
    const account = element('div', 'article-account');
    account.append(icon('book'), element('span', '', item.account || '未提供公众号名称'));
    const title = element('h3', '', item.title || '未命名文章');
    const summary = element('p', 'article-summary', item.summary || '原文未提供摘要，可打开来源文章阅读。');
    const tags = element('div', 'article-tags');
    tags.append(element('span', 'article-tag', item.subject || '未标注学科'), element('span', 'article-tag', item.grade || '未标注年级'));
    const dates = element('p', 'article-date', '导入于 ' + (dateLabel(item.fetched_at) || '时间未知'));
    if (item.published_at) dates.append(element('span', '', ' · 发布于 ' + dateLabel(item.published_at)));
    const source = publicArticleURL(item.source_url);
    let sourceNode;
    if (source) {
      sourceNode = element('a', 'article-source', '打开原文');
      sourceNode.href = source;
      sourceNode.target = '_blank';
      sourceNode.rel = 'noopener noreferrer';
      sourceNode.setAttribute('aria-label', '打开原文：' + (item.title || '未命名文章'));
      sourceNode.append(icon('arrow'));
    } else {
      sourceNode = element('span', 'article-source article-source-unavailable', '原文链接不可用');
    }
    const actions = element('div', 'article-actions');
    const added = knowledgeResourceIds.has(item.id) || knowledgeIds.has(resources.added.get(item.id));
    const add = element('button', 'button button-soft button-small' + (added ? ' article-added' : ''), added ? '已加入我的资料' : '加入我的资料');
    add.type = 'button';
    add.disabled = added;
    add.addEventListener('click', async () => {
      setBusy(add, true);
      let saved = false;
      try {
        const entry = await post('/api/resources/' + encodeURIComponent(item.id) + '/knowledge', {});
        if (!entry?.id) throw new Error('服务端未返回资料信息，请刷新后检查。');
        saved = true;
        resources.added.set(item.id, entry.id);
        const selected = state.selected.has(entry.id) || state.selected.size < 20;
        if (selected) state.selected.add(entry.id);
        await loadKnowledge();
        notify(selected ? '文章摘要与来源已加入我的资料，并已选用。' : '已加入我的资料。当前已选 20 份，请先取消部分选择。');
        renderPublicResources();
      } catch (error) {
        notify(saved ? '已加入资料，但列表刷新失败：' + error.message : error.message, true);
      } finally { setBusy(add, false); if (saved) { add.disabled = true; add.textContent = '已加入我的资料'; add.classList.add('article-added'); } }
    });
    const remove = element('button', 'icon-button');
    remove.type = 'button';
    remove.setAttribute('aria-label', '删除资源：' + (item.title || '未命名文章'));
    remove.title = '删除资源';
    remove.append(icon('trash'));
    remove.addEventListener('click', async () => {
      if (!window.confirm('删除资源「' + (item.title || '未命名文章') + '」？此操作无法撤销；已加入“我的资料”的副本会保留。')) return;
      setBusy(remove, true);
      try {
        await api('/api/resources/' + encodeURIComponent(item.id), { method: 'DELETE' });
        await loadPublicResources(resources.page);
        notify('资源已删除。');
      } catch (error) { notify(error.message, true); setBusy(remove, false); }
    });
    actions.append(add, remove);
    card.append(account, title, summary, tags, dates, sourceNode, actions);
    list.append(card);
  }
  $('#resources-total').textContent = resources.total + ' 条资源';
  $('#resource-pagination').hidden = !resources.total;
  $('#resource-page-info').textContent = '共 ' + resources.total + ' 条 · 第 ' + resources.page + ' / ' + resources.pages + ' 页';
  $('#resource-prev').disabled = resources.loading || resources.page <= 1;
  $('#resource-next').disabled = resources.loading || resources.page >= resources.pages;
}

async function loadPublicResources(page = 1, correctedPage = false) {
  if (state.leaving) return;
  const resources = state.resources;
  const loadId = ++resources.loadId;
  resources.loading = true;
  resources.page = Math.max(1, page);
  $('#resource-load-error').hidden = true;
  $('#resources-loading').hidden = false;
  $('#public-resource-list').setAttribute('aria-busy', 'true');
  $('#public-resource-list').replaceChildren();
  $('#resource-pagination').hidden = true;
  $('#resources-total').textContent = '正在加载';
  setBusy($('#search-resources'), true);
  $('#resource-prev').disabled = true;
  $('#resource-next').disabled = true;
  const params = new URLSearchParams({ ...resources.query, page: String(resources.page), page_size: '12' });
  try {
    const data = await api('/api/resources?' + params.toString());
    if (state.leaving || loadId !== resources.loadId) return;
    resources.items = Array.isArray(data.items) ? data.items : [];
    resources.total = Math.max(0, Number(data.total) || 0);
    resources.pages = Math.max(1, Number(data.pages) || 1);
    resources.page = Math.max(1, Number(data.page) || resources.page);
    resources.loaded = true;
    if (!correctedPage && resources.total && !resources.items.length && resources.page > 1) {
      await loadPublicResources(Math.min(resources.page - 1, resources.pages), true);
      return;
    }
    renderPublicResources();
  } catch (error) {
    if (state.leaving || loadId !== resources.loadId) return;
    resources.loaded = false;
    $('#resource-load-message').textContent = error.message;
    $('#resource-load-error').hidden = false;
    $('#resources-total').textContent = '加载失败';
  } finally {
    if (!state.leaving && loadId === resources.loadId) {
      resources.loading = false;
      $('#resources-loading').hidden = true;
      $('#public-resource-list').setAttribute('aria-busy', 'false');
      setBusy($('#search-resources'), false);
      $('#resource-prev').disabled = resources.page <= 1;
      $('#resource-next').disabled = resources.page >= resources.pages;
    }
  }
}

function renderResourceImports() {
  if (state.leaving) return;
  const resources = state.resources;
  $('#resource-import-feedback').hidden = !resources.attempts.length;
  const list = $('#resource-import-attempts');
  list.replaceChildren();
  const success = resources.attempts.filter(item => item.status === 'success').length;
  const failures = resources.attempts.filter(item => item.status === 'error').length;
  const done = success + failures;
  const current = resources.attempts.findIndex(item => item.status === 'working');
  $('#resource-import-progress').textContent = (resources.importing && current >= 0 ? '正在读取第 ' + (current + 1) + ' 条 · ' : '已处理 ' + done + ' / ' + resources.attempts.length + ' 条 · ') + '成功 ' + success + ' 条，失败 ' + failures + ' 条';
  resources.attempts.forEach((attempt, index) => {
    const row = element('li', 'resource-import-attempt ' + attempt.status);
    row.append(element('strong', '', (index + 1) + '. ' + (attempt.title || attempt.url)));
    row.append(element('p', '', attempt.message || '等待处理'));
    if (attempt.status === 'error') {
      const retry = element('button', 'text-button', '重试这一条');
      retry.type = 'button';
      retry.disabled = resources.importing;
      retry.addEventListener('click', () => runResourceImports([attempt]));
      row.append(retry);
    }
    list.append(row);
  });
}

async function runResourceImports(attempts) {
  const resources = state.resources;
  if (resources.importing || state.leaving) return;
  resources.importing = true;
  setBusy($('#import-resources'), true);
  ['#resource-links', '#resource-import-subject', '#resource-import-grade'].forEach(selector => { $(selector).disabled = true; });
  let success = 0;
  try {
    for (const attempt of attempts) {
      if (state.leaving) return;
      if ($('#login-dialog').open) {
        attempt.status = 'error';
        attempt.message = '请重新登录后，手动重试这一条。';
        renderResourceImports();
        continue;
      }
      attempt.status = 'working';
      attempt.message = '正在读取文章标题、摘要与来源…';
      renderResourceImports();
      try {
        const data = await post('/api/resources/import', { url: attempt.url, subject: attempt.subject, grade: attempt.grade });
        if (state.leaving) return;
        if (!data.item?.id) throw new Error('服务端未返回文章信息，请刷新列表后检查。');
        attempt.status = 'success';
        attempt.title = data.item.title;
        attempt.message = data.created ? '已收藏文章目录信息。' : '这篇文章已在资源库中，无需重复收藏。';
        success += 1;
      } catch (error) {
        if (state.leaving) return;
        attempt.status = 'error';
        attempt.message = error.message;
      }
      renderResourceImports();
    }
    if (success && !state.leaving && !$('#login-dialog').open) await loadPublicResources(1);
    if (!state.leaving) notify('本次处理完成：成功 ' + success + ' 条，失败 ' + (attempts.length - success) + ' 条。', success < attempts.length);
  } finally {
    resources.importing = false;
    if (!state.leaving) {
      setBusy($('#import-resources'), false);
      ['#resource-links', '#resource-import-subject', '#resource-import-grade'].forEach(selector => { $(selector).disabled = false; });
      renderResourceImports();
    }
  }
}

async function loadWorkspace() {
  const outcomes = await Promise.allSettled([loadTemplates(), loadHistory(), loadKnowledge()]);
  const failed = outcomes.filter(item => item.status === 'rejected');
  if (failed.length) throw new Error(failed.map(item => item.reason.message).filter((item, index, all) => all.indexOf(item) === index).join('；'));
  state.initialized = true;
  if (state.currentPage === 'knowledge') loadPublicResources();
}

async function initialize() {
  $('#connection-banner').hidden = true;
  try {
    if (await loadStatus()) await loadWorkspace();
  } catch (error) {
    $('#connection-message').textContent = error.message;
    $('#connection-banner').hidden = false;
    $('#footer-status').textContent = '服务连接异常 · 点击查看';
  }
}

function displayResult(item) {
  if (state.leaving) return;
  state.result = item;
  state.dirty = false;
  $('#result-title').value = item.title || '';
  $('#result-body').value = item.body || '';
  $('#result-empty').hidden = true;
  $('#result-loading').hidden = true;
  $('#result-content').hidden = false;
  $('#result-status').textContent = item.mode === 'manual' ? '已保存' : '已生成';
  $('#result-status').className = 'status-pill ready';
  $('#result-subtitle').textContent = '给好想法，再加一点你的经验';
  updateCharacterCount();
}

function updateCharacterCount() {
  $('#result-character-count').textContent = $('#result-body').value.length.toLocaleString('zh-CN') + ' 字';
}

function markDirty() {
  state.dirty = true;
  $('#result-status').textContent = '待保存';
  $('#result-status').className = 'status-pill dirty';
  updateCharacterCount();
}

function currentResult() {
  const title = $('#result-title').value.trim() || $('#lesson-title').value.trim() || '教案';
  const body = $('#result-body').value;
  if (!body.trim()) throw new Error('请先生成或填写教案内容。');
  return { title, body };
}

function resultLoading(busy, message) {
  if (state.leaving) return;
  state.generationBusy = busy;
  setBusy($('#generate-button'), busy);
  $('#revise-result').disabled = busy || !state.status?.ai_configured;
  $('#result-loading').hidden = !busy;
  $('#result-empty').hidden = busy || Boolean(state.result);
  $('#result-content').hidden = busy || !state.result;
  $('#result-panel')?.setAttribute('aria-busy', String(busy));
  if (busy) {
    $('#result-status').textContent = '创作中';
    $('#result-status').className = 'status-pill';
    $('#generation-progress').textContent = message;
  } else if (state.result) {
    $('#result-status').textContent = state.dirty ? '待保存' : '已生成';
    $('#result-status').className = 'status-pill ' + (state.dirty ? 'dirty' : 'ready');
  } else {
    $('#result-status').textContent = '等待创作';
  }
}

const scenarios = {
  new: { requirements: '设计一节新授课。包含情境导入、知识探究、分层练习与课堂小结，突出重点和难点，预留学生表达与思考的时间。' },
  review: { requirements: '设计一节复习课。通过知识梳理、典型题分析、易错点辨析与分层练习巩固重点，安排课堂诊断与反馈。' },
  project: { requirements: '采用项目式学习。围绕真实问题设置驱动性任务，明确小组分工、探究流程、成果形式和评价标准。' },
  class: { subject: '主题班会', requirements: '设计一节主题班会。围绕主题安排情境导入、交流分享、体验活动和行动计划，鼓励学生参与表达。' }
};

function applyScenario(name) {
  const scenario = scenarios[name];
  if (!scenario) return;
  if (scenario.subject) $('#lesson-subject').value = scenario.subject;
  const field = $('#lesson-requirements');
  if (field.value.trim() && !Object.values(scenarios).some(item => item.requirements === field.value.trim())) {
    field.value = (field.value.trim() + '\n' + scenario.requirements).slice(0, 8000);
  } else {
    field.value = scenario.requirements;
  }
  $$('[data-scenario]').forEach(button => { button.classList.toggle('selected', button.dataset.scenario === name); });
  notify('已填入场景建议，可按实际课堂继续调整。');
  $('#lesson-title').focus();
}

async function downloadResponse(response, fallback) {
  const blob = await response.blob();
  const disposition = response.headers.get('Content-Disposition') || '';
  let filename = fallback;
  const unicodeName = disposition.match(/filename\*=UTF-8''([^;]+)/i);
  const plainName = disposition.match(/filename="?([^";]+)"?/i);
  try {
    if (unicodeName) filename = decodeURIComponent(unicodeName[1]);
    else if (plainName) filename = plainName[1];
  } catch (_) { /* Use the local fallback for an invalid server filename. */ }
  filename = filename.replace(/[\\/:*?"<>|]/g, '_');
  const url = URL.createObjectURL(blob);
  const link = element('a');
  link.href = url;
  link.download = filename;
  document.body.append(link);
  link.click();
  link.remove();
  window.setTimeout(() => URL.revokeObjectURL(url), 30000);
}

function validateUpload(files) {
  if (!files.length) throw new Error('请先选择文件。');
  const limits = state.status?.limits || {};
  if (limits.max_files && files.length > limits.max_files) throw new Error('一次最多上传 ' + limits.max_files + ' 个文件。');
  const entries = Array.from(files);
  const oversized = entries.find(file => limits.max_upload_mb && file.size > limits.max_upload_mb * 1024 * 1024);
  if (oversized) throw new Error('文件「' + oversized.name + '」超过单个文件 ' + limits.max_upload_mb + ' MB 的限制。');
  const total = entries.reduce((sum, file) => sum + file.size, 0);
  if (limits.max_total_mb && total > limits.max_total_mb * 1024 * 1024) throw new Error('所选文件总大小超过每批 ' + limits.max_total_mb + ' MB，请减少文件后重试。');
}

function appendMessage(role, content) {
  $('#chat-empty')?.remove();
  const message = element('div', 'chat-message ' + role);
  message.append(element('span', 'message-label', role === 'user' ? '你' : '教伴'));
  const body = element('div', 'message-body', content);
  message.append(body);
  $('#chat-messages').append(message);
  $('#chat-messages').scrollTop = $('#chat-messages').scrollHeight;
  return { message, body };
}

function resetChat() {
  state.messages = [];
  const empty = element('div', 'chat-empty');
  empty.id = 'chat-empty';
  empty.append(element('span', '', '✦'), element('h3', '', '今天想一起讨论什么？'), element('p', '', '一个教学疑问，也能成为好课的开始。'));
  $('#chat-messages').replaceChildren(empty);
}

function parseRules(selector, listField) {
  const text = $(selector).value.trim();
  if (!text) return null;
  let rules;
  try { rules = JSON.parse(text); } catch (_) { throw new Error((listField === 'exts' ? '扩展名' : '文件名') + '分类规则不是有效 JSON，请参考输入框中的格式。'); }
  if (!Array.isArray(rules) || rules.some(rule => !rule || typeof rule.category !== 'string' || !rule.category.trim() || !Array.isArray(rule[listField]) || !rule[listField].length || rule[listField].some(value => typeof value !== 'string' || !value.trim()))) {
    throw new Error('每条规则必须包含非空 category 分类名称，以及 ' + listField + ' 字符串数组。');
  }
  if (rules.some(rule => /[\\/:*?"<>|]/.test(rule.category) || rule.category === '.' || rule.category === '..')) throw new Error('分类名称不能包含路径分隔符或特殊文件名字符。');
  return rules;
}

function invalidateFilePreview() {
  if (!state.fileBatch) return;
  state.fileBatch = null;
  state.fileItems = [];
  $('#file-preview-content').hidden = true;
  $('#files-empty').hidden = false;
  $('#file-preview-status').textContent = '待重新预览';
  $('#file-preview-status').className = 'status-pill';
  $('#file-preview-summary').textContent = '文件或规则已更改，请重新生成预览。';
}

function displayFilePreview(data) {
  state.fileBatch = data.batch_id;
  state.fileItems = Array.isArray(data.items) ? data.items : [];
  const container = $('#file-preview-list');
  container.replaceChildren();
  for (const item of state.fileItems) {
    const row = element('tr');
    const name = element('td', '', item.name);
    if (item.duplicate_of) name.append(element('span', 'duplicate-label', '内容相同的重复副本'));
    row.append(name, element('td', '', item.category || '其他'), element('td', '', sizeLabel(item.size)));
    container.append(row);
  }
  $('#files-empty').hidden = true;
  $('#file-preview-content').hidden = false;
  $('#file-preview-status').textContent = '预览完成';
  $('#file-preview-status').className = 'status-pill ready';
  $('#file-preview-summary').textContent = state.fileItems.length + ' 个文件 · ' + sizeLabel(data.total_size) + ' · ' + (Number(data.duplicate_count) || 0) + ' 个重复副本';
  $('#exclude-duplicates').checked = false;
  $('#duplicate-hint').textContent = data.duplicate_count ? '检测到 ' + data.duplicate_count + ' 个重复副本，默认全部保留。' : '未检测到内容相同的重复文件。';
}

$$('[data-nav]').forEach(button => button.addEventListener('click', () => switchPage(button.dataset.nav)));
$$('[data-go]').forEach(button => button.addEventListener('click', () => { switchPage(button.dataset.go); window.scrollTo({ top: 0, behavior: 'smooth' }); }));
$$('[data-scenario]').forEach(button => button.addEventListener('click', () => applyScenario(button.dataset.scenario)));

$('#lesson-form').addEventListener('submit', async event => {
  event.preventDefault();
  if (state.generationBusy) return;
  if (!$('#lesson-form').reportValidity()) return;
  if (state.dirty && !window.confirm('当前教案有未保存修改。是否生成新教案？')) return;
  const form = new FormData(event.currentTarget);
  const payload = Object.fromEntries(form.entries());
  payload.title = payload.title.trim();
  if (!payload.title) return notify('请填写课题名称。', true);
  payload.knowledge_ids = Array.from(state.selected);
  const oldResult = state.result;
  resultLoading(true, payload.mode === 'ai' ? 'AI 正在构思教案，通常需要一些时间，请保持页面打开。' : '正在根据课堂信息整理模板。');
  try {
    const result = await post('/api/lesson/generate', payload);
    displayResult(result);
    notify(payload.mode === 'ai' ? '教案初稿已生成，可继续编辑和改稿。' : '模板已生成，请结合课堂补充教学内容。');
    try { await loadHistory(); } catch (error) { notify('教案已生成，但历史刷新失败：' + error.message, true); }
    if (window.innerWidth <= 620) $('#result-heading').scrollIntoView({ behavior: 'smooth', block: 'start' });
  } catch (error) {
    state.result = oldResult;
    notify(error.message, true);
  } finally { resultLoading(false); }
});

$('#result-title').addEventListener('input', markDirty);
$('#result-body').addEventListener('input', markDirty);

$('#save-result').addEventListener('click', async () => {
  const button = $('#save-result');
  try {
    const data = currentResult();
    setBusy(button, true);
    state.result = await post('/api/history', { ...data, mode: 'manual' });
    state.dirty = false;
    $('#result-status').textContent = '已保存';
    $('#result-status').className = 'status-pill ready';
    notify('教案已保存到最近的教案。');
    await loadHistory();
  } catch (error) { notify(error.message, true); } finally { setBusy(button, false); }
});

$('#copy-result').addEventListener('click', async () => {
  try {
    const data = currentResult();
    const text = data.title + '\n\n' + data.body;
    if (navigator.clipboard && window.isSecureContext) {
      await navigator.clipboard.writeText(text);
    } else {
      const temporary = element('textarea');
      temporary.value = text;
      temporary.className = 'sr-only';
      document.body.append(temporary);
      temporary.select();
      const copied = document.execCommand('copy');
      temporary.remove();
      if (!copied) throw new Error('浏览器未允许自动复制，请选中正文后手动复制。');
    }
    notify('教案已复制。');
  } catch (error) { notify(error.message || '复制失败，请手动复制正文。', true); }
});

$('#export-result').addEventListener('click', async () => {
  const button = $('#export-result');
  try {
    const data = currentResult();
    const format = $('#export-format').value;
    setBusy(button, true);
    const response = await post('/api/export', { ...data, format }, { binary: true });
    await downloadResponse(response, data.title + '.' + format);
    notify('文件已准备好，正在下载。');
  } catch (error) { notify(error.message, true); } finally { setBusy(button, false); }
});

$('#revise-result').addEventListener('click', async () => {
  if (state.generationBusy) return;
  const instruction = $('#revision-instruction').value.trim();
  if (!instruction) { $('#revision-instruction').focus(); return notify('请先写下你的改稿想法。', true); }
  try {
    const current = currentResult();
    resultLoading(true, 'AI 正在根据你的要求调整教案，请保持页面打开。');
    const result = await post('/api/lesson/revise', { ...current, instruction, knowledge_ids: Array.from(state.selected) });
    displayResult(result);
    $('#revision-instruction').value = '';
    notify('教案已更新，请审阅改稿内容。');
    try { await loadHistory(); } catch (error) { notify('改稿成功，但历史刷新失败：' + error.message, true); }
  } catch (error) { notify(error.message, true); } finally { resultLoading(false); }
});

$('#lesson-template').addEventListener('change', updateTemplateActions);
$('#delete-template-button').addEventListener('click', async () => {
  const id = $('#lesson-template').value;
  if (!/^[a-f0-9]{32}$/.test(id)) return;
  const template = state.templates.find(item => item.id === id);
  if (!window.confirm('删除自定义模板「' + (template?.name || '') + '」？已有教案不受影响。')) return;
  const button = $('#delete-template-button');
  setBusy(button, true);
  try {
    await api('/api/templates/' + encodeURIComponent(id), { method: 'DELETE' });
    await loadTemplates();
    notify('自定义模板已删除。');
  } catch (error) { notify(error.message, true); } finally { setBusy(button, false); }
});
$('#import-template-button').addEventListener('click', () => $('#template-file').click());
$('#template-file').addEventListener('change', async event => {
  const input = event.currentTarget;
  const file = input.files[0];
  if (!file) return;
  const button = $('#import-template-button');
  try {
    validateUpload(input.files);
    setBusy(button, true);
    const form = new FormData();
    form.append('file', file);
    const imported = await post('/api/templates/import', form);
    await loadTemplates(imported.id || imported.template?.id);
    notify('模板已导入并选中。');
  } catch (error) { notify(error.message, true); } finally { input.value = ''; setBusy(button, false); }
});

$('#knowledge-file').addEventListener('change', async event => {
  const input = event.currentTarget;
  if (!input.files.length) return;
  try {
    validateUpload(input.files);
    input.disabled = true;
    $('#knowledge-upload-state').hidden = false;
    $('#knowledge-upload-state').textContent = '正在读取并保存资料…';
    const form = new FormData();
    form.append('file', input.files[0]);
    const item = await post('/api/knowledge', form);
    const autoSelect = Boolean(item.id) && state.selected.size < 20;
    if (autoSelect) state.selected.add(item.id);
    await loadKnowledge();
    notify(autoSelect ? '资料已上传并选用。' : '资料已上传；已选满 20 份，请取消部分选择后再选用。');
  } catch (error) { notify(error.message, true); } finally {
    input.value = '';
    input.disabled = false;
    $('#knowledge-upload-state').hidden = true;
  }
});

$('#clear-knowledge-selection').addEventListener('click', () => { state.selected.clear(); renderKnowledge(); });

$$('[data-prompt]').forEach(button => button.addEventListener('click', () => {
  if (!state.status?.ai_configured) return notify('AI 服务尚未配置，请联系服务器管理员配置后使用。');
  $('#chat-input').value = button.dataset.prompt;
  $('#chat-input').focus();
}));

$('#chat-input').addEventListener('keydown', event => {
  if (event.key === 'Enter' && !event.shiftKey && !event.isComposing) {
    event.preventDefault();
    if (!state.chatBusy) $('#chat-form').requestSubmit();
  }
});

$('#chat-form').addEventListener('submit', async event => {
  event.preventDefault();
  if (state.chatBusy || !state.status?.ai_configured) return;
  const content = $('#chat-input').value.trim();
  if (!content) return;
  state.chatBusy = true;
  setBusy($('#send-chat'), true);
  $('#clear-chat').disabled = true;
  $('#chat-input').value = '';
  const userMessage = appendMessage('user', content);
  const pending = appendMessage('assistant', '正在思考…');
  const payload = [...state.messages, { role: 'user', content }];
  try {
    const data = await post('/api/chat', { messages: payload, knowledge_ids: Array.from(state.selected) });
    const reply = data.reply || '暂未收到回复，请换一种方式提问。';
    pending.body.textContent = reply;
    state.messages = [...payload, { role: 'assistant', content: reply }].slice(-20);
    $('#chat-messages').scrollTop = $('#chat-messages').scrollHeight;
  } catch (error) {
    userMessage.message.remove();
    pending.message.remove();
    if (!$('#chat-input').value) $('#chat-input').value = content;
    notify(error.message, true);
    if (!state.messages.length) resetChat();
  } finally {
    state.chatBusy = false;
    setBusy($('#send-chat'), !state.status?.ai_configured);
    $('#clear-chat').disabled = false;
    $('#chat-input').focus();
  }
});

$('#clear-chat').addEventListener('click', () => {
  if (state.chatBusy) return;
  if (state.messages.length && !window.confirm('清空本次讨论记录？')) return;
  resetChat();
});

$('#organize-files').addEventListener('change', event => {
  const files = Array.from(event.currentTarget.files);
  $('#selected-files-note').textContent = files.length ? '已选择 ' + files.length + ' 个文件 · ' + sizeLabel(files.reduce((sum, file) => sum + file.size, 0)) : '尚未选择文件';
  invalidateFilePreview();
});
['#group-by-date', '#extension-rules', '#filename-rules'].forEach(selector => $(selector).addEventListener('input', invalidateFilePreview));

$('#files-form').addEventListener('submit', async event => {
  event.preventDefault();
  const button = $('#preview-files');
  try {
    const files = $('#organize-files').files;
    validateUpload(files);
    const rules = parseRules('#extension-rules', 'exts');
    const filenameRules = parseRules('#filename-rules', 'keywords');
    const form = new FormData();
    Array.from(files).forEach(file => form.append('files', file));
    if (rules) form.append('rules', JSON.stringify(rules));
    if (filenameRules) form.append('filename_rules', JSON.stringify(filenameRules));
    form.append('group_by_date', String($('#group-by-date').checked));
    setBusy(button, true);
    $('#file-preview-status').textContent = '整理中';
    const data = await post('/api/files/preview', form);
    displayFilePreview(data);
    notify('整理预览已生成，请确认分类后下载。');
  } catch (error) {
    $('#file-preview-status').textContent = state.fileBatch ? '已有预览' : '等待上传';
    notify(error.message, true);
  } finally { setBusy(button, false); }
});

$('#download-files').addEventListener('click', async () => {
  if (!state.fileBatch) return notify('请先生成整理预览。', true);
  const button = $('#download-files');
  setBusy(button, true);
  try {
    const response = await post('/api/files/' + encodeURIComponent(state.fileBatch) + '/download', { exclude_duplicates: $('#exclude-duplicates').checked }, { binary: true });
    await downloadResponse(response, '教伴_整理文件.zip');
    notify('整理文件已打包，正在下载 ZIP。');
  } catch (error) { notify(error.message, true); } finally { setBusy(button, false); }
});

function openSettings() { if (!$('#settings-dialog').open) $('#settings-dialog').showModal(); }
$('#open-settings').addEventListener('click', openSettings);
$('#footer-status').addEventListener('click', openSettings);
$('#close-settings').addEventListener('click', () => $('#settings-dialog').close());
$('#settings-dialog').addEventListener('click', event => { if (event.target === event.currentTarget && event.clientX < event.currentTarget.getBoundingClientRect().left) event.currentTarget.close(); });
$('#refresh-status').addEventListener('click', async () => {
  setBusy($('#refresh-status'), true);
  try {
    if (await loadStatus()) {
      if (!state.initialized) await loadWorkspace();
      notify('服务状态已更新。');
      $('#connection-banner').hidden = true;
    }
  } catch (error) { notify(error.message, true); } finally { setBusy($('#refresh-status'), false); }
});
$('#retry-connection').addEventListener('click', async () => {
  setBusy($('#retry-connection'), true);
  try { await initialize(); } finally { setBusy($('#retry-connection'), false); }
});
$('#login-dialog').addEventListener('cancel', event => { event.preventDefault(); });
$('#login-form').addEventListener('submit', async event => {
  event.preventDefault();
  const button = $('#login-button');
  $('#login-error').hidden = true;
  setBusy(button, true);
  try {
    await post('/api/login', { password: $('#login-password').value });
    $('#login-password').value = '';
    $('#login-dialog').close();
    await initialize();
  } catch (error) {
    $('#login-error').textContent = error.message;
    $('#login-error').hidden = false;
  } finally { setBusy(button, false); }
});
$('#logout-button').addEventListener('click', async () => {
  if (state.dirty && !window.confirm('当前教案有未保存修改，仍要退出登录？')) return;
  setBusy($('#logout-button'), true);
  try {
    await post('/api/logout', {});
    state.leaving = true;
    state.requestEpoch += 1;
    state.dirty = false;
    state.generationBusy = false;
    state.result = null;
    state.history = [];
    state.knowledge = [];
    state.resources.items = [];
    state.resources.attempts = [];
    state.resources.loaded = false;
    state.resources.loadId += 1;
    state.resources.added.clear();
    $('#public-resource-list').replaceChildren();
    $('#resource-import-attempts').replaceChildren();
    $('#resource-import-form').reset();
    $('#resource-filter-form').reset();
    state.selected.clear();
    state.fileBatch = null;
    state.fileItems = [];
    $('#result-title').value = '';
    $('#result-body').value = '';
    $('#revision-instruction').value = '';
    $('#result-content').hidden = true;
    $('#result-loading').hidden = true;
    $('#result-empty').hidden = false;
    $('#lesson-form').reset();
    $('#files-form').reset();
    $('#file-preview-list').replaceChildren();
    $('#file-preview-content').hidden = true;
    $('#files-empty').hidden = false;
    $('#chat-input').value = '';
    resetChat();
    renderHistory();
    renderKnowledge();
    showLogin();
    window.location.reload();
  } catch (error) { notify(error.message, true); setBusy($('#logout-button'), false); }
});
window.addEventListener('beforeunload', event => {
  if (!state.leaving && (state.dirty || state.generationBusy)) { event.preventDefault(); event.returnValue = ''; }
});

$('#resource-import-form').addEventListener('submit', event => {
  event.preventDefault();
  if (state.resources.importing) return;
  const urls = $('#resource-links').value.split(/\r?\n/).map(value => value.trim()).filter(Boolean);
  if (!urls.length) { $('#resource-links').focus(); return notify('请先粘贴文章链接。', true); }
  if (urls.length > 5) return notify('每次最多处理 5 条文章链接，请分批收藏。', true);
  const subject = $('#resource-import-subject').value.trim();
  const grade = $('#resource-import-grade').value.trim();
  state.resources.attempts = Array.from(new Set(urls)).map(url => ({ url, subject, grade, status: 'pending', message: '等待处理' }));
  runResourceImports(state.resources.attempts);
});
$('#resource-filter-form').addEventListener('submit', event => {
  event.preventDefault();
  state.resources.query = { q: $('#resource-search').value.trim(), subject: $('#resource-subject').value.trim(), grade: $('#resource-grade').value.trim() };
  loadPublicResources(1);
});
$('#clear-resource-filters').addEventListener('click', () => {
  $('#resource-filter-form').reset();
  state.resources.query = { q: '', subject: '', grade: '' };
  loadPublicResources(1);
});
$('#retry-resources').addEventListener('click', () => loadPublicResources(state.resources.page));
$('#resource-prev').addEventListener('click', () => { if (!state.resources.loading && state.resources.page > 1) loadPublicResources(state.resources.page - 1); });
$('#resource-next').addEventListener('click', () => { if (!state.resources.loading && state.resources.page < state.resources.pages) loadPublicResources(state.resources.page + 1); });

initialize();