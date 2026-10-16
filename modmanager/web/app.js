'use strict';
const icons = {
  overview:'<rect x="3" y="3" width="7" height="7" rx="1.5"/><rect x="14" y="3" width="7" height="7" rx="1.5"/><rect x="3" y="14" width="7" height="7" rx="1.5"/><rect x="14" y="14" width="7" height="7" rx="1.5"/>',
  games:'<path d="M7 7h10a4 4 0 0 1 4 4l1 6a2 2 0 0 1-3 2l-4-3H9l-4 3a2 2 0 0 1-3-2l1-6a4 4 0 0 1 4-4Z"/><path d="M6 10v5m-2-2.5h4m8-1h.01m3 3h.01"/>',
  mods:'<path d="m12 3 9 5-9 5-9-5 9-5Zm-9 9 9 5 9-5M3 16l9 5 9-5"/>',
  nexus:'<circle cx="12" cy="12" r="9"/><path d="m10 4 4 6 6 2-6 2-4 6 1-6-7-2 7-2-1-6Z"/>',
  updates:'<path d="M20 7v5h-5M4 17v-5h5"/><path d="M5 8a8 8 0 0 1 13-3l2 3M4 16l2 3a8 8 0 0 0 13-3"/>',
  logs:'<rect x="5" y="3" width="14" height="18" rx="2"/><path d="M9 8h6m-6 4h6m-6 4h4"/>',
  settings:'<path d="m9 3-.6 3-2.6 1-2.5 3 2 2-1 3 2.5 3 3-.5L12 21l2-3.5 3 .5 2.5-3-1-3 2-2-2.5-3-2.6-1L15 3H9Z"/><circle cx="12" cy="12" r="3"/>',
  scan:'<path d="M8 3H3v5m13-5h5v5M3 16v5h5m13-5v5h-5M7 12h10m-5-5v10"/>',
  plus:'<path d="M12 5v14M5 12h14"/>',
  arrow:'<path d="M4 12h15m-6-6 6 6-6 6"/>',
  download:'<path d="M12 3v12m-5-5 5 5 5-5M4 16v5h16v-5"/>',
  shield:'<path d="m12 3 8 3v7c0 4-8 8-8 8s-8-4-8-8V6l8-3Z"/><path d="m8 12 3 3 5-6"/>',
  folder:'<path d="M3 7V5h7l2 3h9v12H3V7Z"/>',
  trash:'<path d="M3 6h18M9 6V3h6v3M6 6l1 15h10l1-15M10 10v7m4-7v7"/>',
  close:'<path d="m6 6 12 12M18 6 6 18"/>',
  check:'<path d="m5 12 4 4L19 6"/>'
};
const icon = name => `<svg viewBox="0 0 24 24" aria-hidden="true">${icons[name] || icons.mods}</svg>`;
const esc = value => String(value ?? '').replace(/[&<>"']/g, char => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[char]));
const $ = selector => document.querySelector(selector);
let state = {games:[], mods:[], rules:[], logs:[], account:null};
let page = 'overview', filterGame = '', modSearch = '', nexusResults = null, updateResults = null;
let nexusQuery = '', nexusCategory = 'trending', nexusGame = '', busy = false, toastTimer;
const labels = {overview:'总览',games:'我的游戏',mods:'模组管理',nexus:'探索模组',updates:'更新中心',logs:'活动日志',settings:'设置'};
async function api(path, data) {
  const response = await fetch('/api/' + path, {method: data === undefined ? 'GET' : 'POST',
    headers: {'Content-Type':'application/json', 'X-ModHarbor-Token':$('meta[name="modharbor-token"]').content},
    body: data === undefined ? undefined : JSON.stringify(data)});
  const result = await response.json();
  if (!response.ok) throw new Error(result.error || '请求失败');
  return result;
}
function toast(message, error=false) {
  clearTimeout(toastTimer); $('#toast').textContent = message; $('#toast').className = error ? 'error' : '';
  $('#toast').hidden = false; toastTimer = setTimeout(() => $('#toast').hidden=true, error ? 10000 : 5000);
}
async function refresh() {
  state = await api('state');
  if (!nexusGame && state.games.length) nexusGame = state.games.find(g => g.domain)?.id || state.games[0].id;
  render();
}
function button(text, action, type='', symbol='', extra='') {
  return `<button class="button ${type}" data-action="${action}" ${extra}>${symbol ? icon(symbol) : ''}${text}</button>`;
}
function nav() {
  $('#navigation').innerHTML = Object.entries(labels).map(([id, label], i) => `${i===5?'<div class="nav-separator"></div>':''}<a href="#${id}" class="nav-link ${id===page?'active':''}" ${id===page?'aria-current="page"':''}>${icon(id)}<span>${label}</span>${id==='mods' ? `<span class="count">${state.mods.length}</span>` : ''}${id==='updates'&&updateResults?.length?`<span class="count">${updateResults.length}</span>`:''}</a>`).join('');
  $('#page-label').textContent = labels[page];
  $('#account-label').textContent = state.account ? state.account.name + (state.account.premium?' · Premium':' · Standard') : '尚未连接 Nexus Mods';
}
function heading(title, description, actions='') {
  return `<div class="page-heading"><div><div class="eyebrow">YOUR MODDING WORKSPACE</div><h1>${title}</h1><p>${description}</p></div><div class="actions">${actions}</div></div>`;
}
function empty(title, description, action='', symbol='mods') {
  return `<div class="empty full-empty">${icon(symbol)}<h3>${title}</h3><p>${description}</p>${action}</div>`;
}
function gameOptions(selected='', placeholder='所有游戏') {
  return (placeholder ? `<option value="">${placeholder}</option>`:'') + state.games.map(g => `<option value="${g.id}" ${selected===g.id?'selected':''}>${esc(g.name)}</option>`).join('');
}
function ruleOptions(gameId) {
  const game=state.games.find(g=>g.id===gameId);
  return state.rules.filter(r=>r.domain===game?.domain).map(r=>`<option value="${r.id}" ${r.id===game.rule_id?'selected':''}>${esc(r.name)}</option>`).join('');
}
function gameCard(game) {
  const mods = state.mods.filter(m => m.game_id === game.id), enabled = mods.filter(m=>m.enabled).length;
  const rule = state.rules.find(r=>r.id===game.rule_id);
  return `<article class="game-card"><div class="game-art ${esc(game.rule_id)}"><span class="art-tag">${esc(game.source)}</span><div class="art-title">${esc(game.name)}</div></div><div class="game-body"><h3>${esc(game.name)}</h3><div class="meta path-line" title="${esc(game.path)}">${icon('folder').replace('<svg ', '<svg class="tiny" ')} ${esc(game.path)}</div><div class="game-row"><span>${mods.length} 个模组 <span class="muted">· ${enabled} 已启用</span></span><span class="badge ${game.supported?'':'amber'}">${game.supported?esc(rule?.mechanism):'需确认规则'}</span></div><div class="game-row"><span>版本 ${esc(game.version)}</span><button class="link-button" data-action="manage-game" data-id="${game.id}">管理模组 →</button></div></div></article>`;
}
function logRows(logs, full=false) {
  return logs.map(log => `<div class="log-row"><span class="log-symbol ${log.level==='error'?'error':''}">${log.level==='error'?'!':log.level==='warning'?'!':'✓'}</span><div class="log-text">${esc(log.message)}</div><span class="log-time">${new Date(log.time*1000).toLocaleString('zh-CN',full?{}:{hour:'2-digit',minute:'2-digit'})}</span></div>`).join('') || '<p>还没有活动。扫描游戏，开启你的模组旅程。</p>';
}
function overview() {
  return heading('你的下一个世界，从这里开始。','发现、安装、管理。在一个地方，照顾好你的全部模组。',button('手动添加','add-game','','plus')+button('扫描游戏','scan','primary','scan')) +
  `<section class="hero"><div class="hero-copy"><span class="pill">✦ 少一点折腾，多一点游戏</span><h2>熟悉的游戏，<em>全新的可能。</em></h2><p>连接 Nexus Mods，发现属于你的游戏体验。<br>安装规则、文件备份与冲突检查，交给 ModHarbor。</p>${button('探索 Nexus 模组','go-nexus','primary','arrow')}</div><div class="hero-art" aria-hidden="true"><div class="orbit"></div><div class="satellite s1">▦</div><div class="cube">M</div><div class="satellite s2">↧</div><div class="star">✧</div></div></section>`+
  `<div class="stats">${[
    ['已发现游戏',state.games.length,'Steam 自动识别 / 手动登记','games'],
    ['已安装模组',state.mods.length,'本地缓存 · 可随时启停','mods'],
    ['正在启用',state.mods.filter(m=>m.enabled).length,'备份保护已就绪','shield'],
    ['可用更新',updateResults===null?'—':updateResults.length,updateResults===null?'前往更新中心检查':'已完成 Nexus 文件版本比较','updates']
  ].map(([label,value,note,symbol])=>`<div class="stat"><div class="stat-label">${label}${icon(symbol)}</div><div class="stat-value">${value}</div><div class="stat-note ${symbol==='shield'?'good':''}">${note}</div></div>`).join('')}</div>`+
  `<section><div class="section-head"><h2>我的游戏 <small>${state.games.length} 个已登记</small></h2><button class="link-button" data-action="go-games">查看全部 →</button></div>${state.games.length?`<div class="grid">${state.games.slice(0,3).map(gameCard).join('')}</div>`:`<div class="empty">${icon('games')}<h3>让你的游戏，来到这里</h3><p>自动扫描 Steam 游戏库，或手动添加 Epic、GOG 及其他平台的游戏目录。</p>${button('发现已安装的游戏','scan','primary','scan')}</div>`}</section>`+
  `<div class="overview-bottom"><section class="panel"><div class="panel-top"><h2>最近活动</h2><button class="link-button" data-action="go-logs">全部日志 ↗</button></div>${logRows(state.logs.slice(0,3))}</section><section class="panel nexus-panel"><div class="nexus-brand"><span>n</span> nexusmods</div><h3>${state.account?'已连接你的模组宇宙':'下一次冒险，只差一个模组。'}</h3><p>连接 Nexus 账户，浏览官方热门与新发布的模组。API Key 仅保存在当前会话内存中。</p>${button(state.account?'开始探索 ↗':'连接 Nexus Mods ↗',state.account?'go-nexus':'connect')}</section></div>`;
}
function gamesView() {
  return heading('你的游戏库','识别常见启动器的游戏记录，也可手动添加安装目录。',button('添加游戏','add-game','','plus')+button('扫描游戏','scan','primary','scan'))+
    `<div class="notice info">自动扫描 Steam 默认及附加库、Windows Epic/GOG 安装记录和 Heroic/Legendary 元数据。Steam 版本为 Build ID，其他来源读取启动器版本；未识别的游戏需手动确认规则。</div>`+
    (state.games.length?`<div class="grid">${state.games.map(gameCard).join('')}</div>`:empty('游戏库还是空的','点击扫描游戏，或添加你的第一个游戏。',button('扫描已安装游戏','scan','primary','scan'),'games'));
}
function modsView() {
  const filtered = state.mods.filter(m=>(!filterGame||m.game_id===filterGame)&&m.name.toLowerCase().includes(modSearch.toLowerCase()));
  return heading('每一个模组，都在掌握之中。','先导入，再启用。冲突会被拦截，原文件会被备份。',button('检查更新','check-updates','','updates')+button('导入 ZIP','import','primary','plus'))+
    `<div class="toolbar"><select id="mod-game" aria-label="按游戏筛选">${gameOptions(filterGame)}</select><input id="mod-search" class="input search" placeholder="筛选已安装的模组…" value="${esc(modSearch)}" aria-label="搜索模组"><span class="meta">${filtered.length} 个模组</span></div>`+
    `<div class="notice info">启用前请关闭游戏，并确认规则适用于该包。文件占用、声明依赖与冲突会自动检查；Nexus 页面中的文字要求仍需人工阅读。禁用会恢复原文件，外部修改会阻止覆盖。</div>`+
    (filtered.length?`<div class="mod-list">${filtered.map(m=>{const game=state.games.find(g=>g.id===m.game_id);return `<article class="mod-item"><div class="mod-icon">${icon('mods')}</div><div class="mod-content"><h3>${esc(m.name)} <span class="badge ${m.enabled?'':'gray'}">${m.enabled?'已启用':'未启用'}</span></h3><div class="meta"><span>${esc(game?.name)}</span><span>v${esc(m.version)}</span><span>${m.files.length} 个文件</span><span>${m.nexus_id?'Nexus #'+esc(m.nexus_id):'本地导入'}</span></div></div><div class="actions">${button('详情','mod-detail','ghost','','data-id="'+m.id+'"')}<button class="switch ${m.enabled?'on':''}" role="switch" aria-checked="${m.enabled}" aria-label="${m.enabled?'禁用':'启用'} ${esc(m.name)}" data-action="toggle" data-id="${m.id}"></button>${button('','remove','ghost danger','trash','data-id="'+m.id+'" aria-label="移除模组"')}</div></article>`;}).join('')}</div>`:empty('还没有符合条件的模组','从 Nexus 选择一个模组，或导入本地 ZIP 安装包。',button('导入本地 ZIP','import','primary','download')));
}
function nexusView() {
  return heading('为你的游戏，找到新的灵感。','来自 Nexus Mods 的官方热门、最新发布与最近更新。',button(state.account?'账户已连接':'连接 Nexus',state.account?'go-settings':'connect',state.account?'':'primary','nexus'))+
    `<div class="toolbar"><select id="nexus-game" aria-label="选择游戏">${gameOptions(nexusGame,'选择游戏')}</select><input class="input search" id="nexus-query" placeholder="筛选列表名称，或输入 MOD ID 精确查询…" value="${esc(nexusQuery)}" aria-label="MOD 名称或 ID"><select id="nexus-category" aria-label="模组列表">${[['trending','热门趋势'],['latest','最新发布'],['updated','最近更新']].map(([v,l])=>`<option value="${v}" ${nexusCategory===v?'selected':''}>${l}</option>`).join('')}</select>${button('检索模组','browse','primary','nexus')}</div>`+
    `<div class="notice">Nexus 公开 API 不提供全站名称搜索；名称仅筛选当前返回的列表，输入数字可按 MOD ID 查询。自动下载通常需要 Premium；普通用户可从官网下载 ZIP 后导入。请先阅读作者的依赖、适用版本与安装说明。</div>`+
    (nexusResults===null?empty('你的下一款模组，正在等你发现','选择游戏，连接 Nexus Mods，然后开始检索。',button(state.account?'加载热门模组':'连接 Nexus Mods',state.account?'browse':'connect','primary','nexus'),'nexus'):nexusResults.length?`<div class="grid">${nexusResults.map(m=>`<article class="panel nexus-card"><div class="section-head"><span class="nexus-mark">n</span><span class="badge gray">#${esc(m.mod_id)}</span></div><h3>${esc(m.name)}</h3><p>${esc(m.summary || '作者未提供摘要。')}</p><div class="meta">作者 ${esc(m.author || m.uploaded_by || '未知')}<br>版本 ${esc(m.version)} · 下载 ${Number(m.mod_downloads || 0).toLocaleString()}</div><div class="actions"><a class="link-button" href="https://www.nexusmods.com/${esc(state.games.find(g=>g.id===nexusGame)?.domain)}/mods/${Number(m.mod_id)}" target="_blank" rel="noopener noreferrer">作者页面 ↗</a>${button('查看文件','files','','download',`data-mod="${Number(m.mod_id)}"`)}</div></article>`).join('')}</div>`:empty('未找到匹配的模组','尝试其他筛选词，或输入 Nexus MOD ID。','', 'nexus'));
}
function updatesView() {
  return heading('让好体验，保持新鲜。','检查 Nexus 主文件的新版本；新版先导入缓存，由你确认替换。',button('检查全部更新','check-updates','primary','updates'))+
    `<div class="notice info">仅检查通过 Nexus 下载的模组。发现不同版本的主文件后，可下载新版并先禁用旧版，再启用新版；不会在游戏运行时静默替换，也不会自动迁移配置。多分支 MOD 请核对作者文件页。</div>`+
    (updateResults===null?empty('先做一次更新检查','连接 Nexus Mods 后，对已登记的 Nexus 文件比较版本。',button('检查更新','check-updates','primary','updates'),'updates'):updateResults.length?`<div class="mod-list">${updateResults.map(u=>`<article class="mod-item"><div class="mod-icon">${icon('updates')}</div><div class="mod-content"><h3>${esc(u.name)}</h3><p>v${esc(u.current)} → <span class="badge">v${esc(u.latest)}</span></p><span class="meta">${esc(u.file.name)}</span></div>${button('下载新版','download-update','primary','download',`data-id="${u.id}"`)}</article>`).join('')}</div>`:empty('当前没有检测到新版本','已完成已安装 Nexus 模组的主文件版本检查。','', 'check'));
}
function settingsView() {
  return heading('你的工作空间，你的偏好。','本地存储、账户连接与安装规则，一目了然。')+
    `<div class="settings-grid"><div><section class="panel"><div class="panel-top"><h2>Nexus Mods 连接</h2><span class="badge ${state.account?'':'gray'}">${state.account?'已连接':'未连接'}</span></div><p>在 Nexus 个人账户的 API Keys 页面获取 Personal API Key。密钥仅存于服务内存，退出后需要重新连接。</p><div class="field"><label for="api-key">Personal API Key</label><input type="password" autocomplete="off" class="input" id="api-key" placeholder="粘贴你的 Nexus API Key"><small>不会写入浏览器存储、数据库或日志。</small></div><div class="actions">${button(state.account?'更换连接':'验证并连接','save-key','primary','nexus')}${state.account?button('断开连接','disconnect'):''}<a href="https://www.nexusmods.com/users/myaccount?tab=api" target="_blank" rel="noopener noreferrer" class="link-button">获取 API Key ↗</a></div>${state.account?`<p>当前账户：${esc(state.account.name)} · ${state.account.premium?'Premium（可请求自动下载）':'Standard（可检索，下载请使用官网）'}</p>`:''}</section><section class="panel below"><div class="panel-top"><h2>本地数据与扫描</h2></div><div class="field"><label>管理器数据目录</label><div class="mono">${esc(state.data_path)}</div><small>SQLite 状态、MOD 缓存与原文件备份均保存在这里。不要在模组启用期间删除数据目录。</small></div><div class="field"><label for="extra-roots">附加 Steam 库目录</label><input class="input" id="extra-roots" placeholder="如 D:\SteamLibrary（多个路径用换行分隔）"><small>默认 Steam 路径自动扫描。这里填写库根目录，内含 steamapps 文件夹。</small></div>${button('扫描附加目录','scan-extra','','scan')}</section></div><section class="panel"><div class="panel-top"><h2>支持的安装规则</h2><span class="badge gray">${state.rules.length} 项</span></div>${state.rules.map(r=>`<div class="rule"><h3>${esc(r.name)} <span class="badge gray">${esc(r.mechanism)}</span></h3><p>${esc(r.note)}</p><div class="mono">→ ${esc(r.target)}/</div></div>`).join('')}<p>加载器须先按作者说明安装。不支持执行安装器、动态注入进程、FOMOD、7z/RAR 或自动修改插件加载顺序。</p></section></div>`;
}
function render() {
  nav();
  const views = {overview, games:gamesView, mods:modsView, nexus:nexusView, updates:updatesView, settings:settingsView,
    logs:()=>heading('每一步，都有迹可循。','最近 200 条扫描、安装、启停与错误记录。',button('刷新日志','refresh','','updates'))+`<section class="panel">${logRows(state.logs,true)}</section>`};
  $('#content').innerHTML = views[page]();
}
function showModal(title, body, actions='') {
  $('#modal-content').innerHTML = `<div class="modal-head"><h2>${title}</h2><button class="icon-button" data-action="close-modal" aria-label="关闭">×</button></div>${body}${actions?`<div class="modal-actions">${button('取消','close-modal')}${actions}</div>`:''}`;
  if (!$('#modal').open) $('#modal').showModal();
}
function addGameModal() {
  showModal('添加游戏',`<p>选取实际游戏安装目录，并明确选择这个游戏使用的部署规则。</p><div class="field"><label for="game-name">游戏名称</label><input class="input" id="game-name" placeholder="例如 Cyberpunk 2077"></div><div class="field"><label for="game-path">安装目录（运行此应用的电脑）</label><input class="input" id="game-path" placeholder="D:\SteamLibrary\steamapps\common\Cyberpunk 2077"></div><div class="field"><label for="game-rule">安装规则</label><select id="game-rule">${state.rules.map(r=>`<option value="${r.id}">${esc(r.name)}</option>`).join('')}</select><small>选择此游戏的默认规则；导入每个 MOD 时可选择同一游戏的其他安装机制。</small></div><div class="field"><label for="game-version">游戏版本 / Build ID（可选）</label><input class="input" id="game-version" placeholder="未知"></div>`,button('添加到游戏库','save-game','primary','plus'));
}
function importModal() {
  if (!state.games.length) { toast('请先扫描或添加游戏。',true); return addGameModal(); }
  showModal('导入本地 MOD',`<div class="notice info">支持 ZIP（≤ 512 MiB，解压 ≤ 2 GiB）。导入只写入缓存，不会修改游戏文件。</div><div class="field"><label for="import-game">目标游戏与规则</label><select id="import-game">${gameOptions(filterGame || state.games[0].id,'')}</select></div><div class="field"><label for="import-rule">此 MOD 的安装机制</label><select id="import-rule">${ruleOptions(filterGame || state.games[0].id)}</select></div><div class="field"><label for="archive-path">ZIP 在本机的完整路径</label><input class="input" id="archive-path" placeholder="D:\Downloads\MyMod.zip"><small>路径属于运行应用的电脑。网页模式不会上传文件至第三方服务。</small></div>`,button('校验并导入','save-import','primary','download'));
}
async function filesModal(modId) {
  const data = await api('nexus/files',{game_id:nexusGame,mod_id:modId});
  showModal('选择 MOD 文件',`<div class="field"><label for="download-rule">此 MOD 的安装机制</label><select id="download-rule">${ruleOptions(nexusGame)}</select></div><div class="notice">下载后仅导入缓存。启用前请在作者页确认游戏版本、加载器与依赖；当前只接受 ZIP 包。</div>${(data.files || []).filter(f=>f.category_id!==6&&f.category_id!==7).map(f=>`<article class="file-option"><h3>${esc(f.name)} <span class="badge gray">${esc(f.category_name || '文件')}</span></h3><p>版本 ${esc(f.version)} · ${(Number(f.size_in_bytes || f.size*1024 || 0)/1048576).toFixed(1)} MiB<br>${esc(f.file_name)}</p>${button(f.file_name?.toLowerCase().endsWith('.zip')?'下载并导入':'仅支持 ZIP','download','primary','download',`data-mod="${Number(modId)}" data-file="${Number(f.file_id)}" ${f.file_name?.toLowerCase().endsWith('.zip')?'':'disabled'}`)}</article>`).join('') || '<p>没有可下载文件。</p>'}`);
}
async function action(name, el) {
  if (name.startsWith('go-')) {location.hash=name.slice(3);return;}
  if (name==='close-modal') {$('#modal').close();return;}
  if (name==='add-game') return addGameModal();
  if (name==='import') return importModal();
  if (name==='connect') {location.hash='settings'; return;}
  if (name==='manage-game') {filterGame=el.dataset.id;location.hash='mods';return;}
  if (name==='mod-detail') {
    const mod=state.mods.find(m=>m.id===el.dataset.id), game=state.games.find(g=>g.id===mod.game_id);
    return showModal(esc(mod.name),`<p>${esc(game.name)} · v${esc(mod.version)} · ${mod.enabled?'已启用':'未启用'}</p><p>依赖：${esc(mod.dependencies.join(', ') || '未声明（仍须核对作者说明）')}<br>声明冲突：${esc(mod.conflicts.join(', ') || '无')}</p><div class="notice info">启用部署至游戏目录，禁用恢复原文件。存在外部修改时将停止恢复。</div><h3>部署文件 · ${mod.files.length}</h3>${mod.files.map(f=>`<div class="rule mono">${esc(f.path)}<p>SHA-256 ${esc(f.sha256)}</p></div>`).join('')}`);
  }
  if (name==='remove') return showModal('移除此 MOD？','<p>如果已启用，会先恢复原文件，再移除缓存与备份。此操作不会删除下载源文件。</p>',button('确认移除','confirm-remove','danger','trash',`data-id="${el.dataset.id}"`));
  if (name==='toggle') {
    const mod=state.mods.find(m=>m.id===el.dataset.id);
    if (!mod.enabled) return showModal('启用并部署 MOD',`<p>将部署 <strong>${esc(mod.name)}</strong> 的 ${mod.files.length} 个文件。遇到已有文件会先备份，管理器内的文件冲突会阻止操作。</p><div class="notice">请先关闭游戏，并阅读作者页面。第三方模组可能包含可执行代码；仅启用你信任的来源。Nexus API 无法完整提供文字依赖。</div><label class="checkbox"><input type="checkbox" id="enable-confirm">我已确认游戏版本、安装规则、作者依赖，并已关闭游戏。</label>`,button('备份并启用','confirm-enable','primary','shield',`data-id="${mod.id}"`));
  }
  if (busy) return;
  busy=true; const previous=el.innerHTML; el.disabled=true;
  try {
    if (name==='refresh') {await refresh();toast('工作空间已刷新');}
    else if (name==='scan'||name==='scan-extra') {
      toast('正在扫描本机游戏库…');
      const roots=name==='scan-extra'?$('#extra-roots').value.split(/[\n;]/).map(s=>s.trim()).filter(Boolean):[];
      const result=await api('scan',{roots});await refresh();toast(`扫描完成，发现 ${result.found} 个已安装游戏。${result.found?'':'可手动添加其他平台的游戏。'}`);
    }
    else if (name==='save-game') {
      await api('games',{name:$('#game-name').value,path:$('#game-path').value,rule_id:$('#game-rule').value,version:$('#game-version').value});$('#modal').close();await refresh();toast('游戏已添加');
    }
    else if (name==='save-import') {
      const result=await api('install',{game_id:$('#import-game').value,path:$('#archive-path').value,rule_id:$('#import-rule').value});$('#modal').close();await refresh();location.hash='mods';toast(`已导入 ${result.name}，尚未启用。`);
    }
    else if (name==='confirm-enable') {
      if (!$('#enable-confirm').checked) throw new Error('请先确认游戏版本、依赖并关闭游戏。');
      await api('toggle',{id:el.dataset.id,enabled:true});$('#modal').close();await refresh();toast('MOD 已启用，原文件已备份。');
    }
    else if (name==='toggle') {
      await api('toggle',{id:el.dataset.id,enabled:false});await refresh();toast('MOD 已禁用，原文件已恢复。');
    }
    else if (name==='confirm-remove') {
      await api('remove',{id:el.dataset.id});$('#modal').close();await refresh();toast('MOD 已移除。');
    }
    else if (name==='save-key') {
      const key=$('#api-key').value;$('#api-key').value='';
      await api('nexus/connect',{key});await refresh();toast('已连接 Nexus Mods。密钥只保留至应用退出。');
    }
    else if (name==='disconnect') {await api('nexus/disconnect',{});nexusResults=null;await refresh();toast('已断开连接并清除会话密钥。');}
    else if (name==='browse') {
      if (!state.account) throw new Error('请先在设置中连接 Nexus Mods。');
      nexusGame=$('#nexus-game').value;nexusQuery=$('#nexus-query').value;nexusCategory=$('#nexus-category').value;
      if (!nexusGame) throw new Error('请先添加并选择一个游戏。');
      toast('正在检索 Nexus Mods…');nexusResults=await api('nexus/browse',{game_id:nexusGame,query:nexusQuery,category:nexusCategory});render();
    }
    else if (name==='files') await filesModal(el.dataset.mod);
    else if (name==='download'||name==='download-update') {
      let gameId=nexusGame,modId=el.dataset.mod,fileId=el.dataset.file;
      if (name==='download-update') {const u=updateResults.find(u=>u.id===el.dataset.id);gameId=u.game_id;modId=u.nexus_id;fileId=u.file.file_id;}
      toast('正在下载并校验，请等待完成…');
      const mod=await api('nexus/download',{game_id:gameId,mod_id:modId,file_id:fileId,rule_id:name==='download'?$('#download-rule').value:state.mods.find(m=>m.id===el.dataset.id)?.rule_id});$('#modal').close();await refresh();location.hash='mods';toast(`已导入 ${mod.name}。如为更新，请先禁用旧版再启用新版。`);
    }
    else if (name==='check-updates') {
      if (!state.account) throw new Error('请先在设置中连接 Nexus Mods。');
      toast('正在检查 Nexus 主文件版本…');updateResults=await api('nexus/updates',{});await refresh();location.hash='updates';toast(`检查完成，${updateResults.length} 个可用更新。`);
    }
  } catch(error) {toast(error.message,true);}
  finally {busy=false;if(el.isConnected){el.disabled=false;el.innerHTML=previous;}}
}
document.addEventListener('click',event=>{const el=event.target.closest('[data-action]');if(el&&!el.disabled)action(el.dataset.action,el).catch(error=>toast(error.message,true));});
document.addEventListener('change',event=>{
  if(event.target.id==='import-game')$('#import-rule').innerHTML=ruleOptions(event.target.value);
  if(event.target.id==='mod-game'){filterGame=event.target.value;render();}
  if(event.target.id==='nexus-game'){nexusGame=event.target.value;nexusResults=null;render();}
  if(event.target.id==='nexus-category')nexusCategory=event.target.value;
});
document.addEventListener('input',event=>{
  if(event.target.id==='mod-search'){const pos=event.target.selectionStart;modSearch=event.target.value;render();$('#mod-search').focus();$('#mod-search').setSelectionRange(pos,pos);}
  if(event.target.id==='nexus-query')nexusQuery=event.target.value;
});
document.addEventListener('keydown',event=>{if(event.key==='Enter'&&event.target.id==='nexus-query')document.querySelector('[data-action="browse"]').click();});
$('#refresh').addEventListener('click',()=>refresh().then(()=>toast('已刷新')).catch(e=>toast(e.message,true)));
$('#settings-shortcut').addEventListener('click',()=>location.hash='settings');
window.addEventListener('hashchange',()=>{page=labels[location.hash.slice(1)]?location.hash.slice(1):'overview';render();window.scrollTo(0,0);});
page=labels[location.hash.slice(1)]?location.hash.slice(1):'overview';
$('#content').innerHTML='<div class="loading">正在连接你的本地工作空间…</div>';
refresh().catch(error=>{$('#content').innerHTML=empty('暂时无法连接本地服务',esc(error.message),button('重新连接','refresh','primary','updates'));});
