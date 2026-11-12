const $ = (id) => document.getElementById(id);

// —— 作者信息 —————————————————————————————————
// 文字在下面改；微信二维码图片放在 web/ 目录，qr 填文件名即可。
// 卡片里只放二维码，不放微信号 / 邮箱 / 主页。
const AUTHOR_INFO = {
  name: '糕头',
  tagline: 'AI × 自媒体 · 把工具做成普通人能用的样子',
  bio: '一个用 AI 工具做自媒体的独立创作者。这个转写工作台是我自己日常在用的，开发出来希望帮刚开始做内容的你省点时间。',
  qr: 'author-qr.png',
};

const CONFIG_KEYS = [
  'ffmpeg', 'oneasr_cli', 'oneasr_data_root', 'inbox_dir', 'output_dir',
  'work_dir', 'language', 'asr_engine', 'asr_model', 'aligner', 'backend',
  'output_mode',
  'cloud_asr_base_url', 'cloud_asr_api_key', 'cloud_asr_model',
  'rewrite_engine', 'rewrite_base_url', 'rewrite_api_key', 'rewrite_model',
  'port',
];

async function api(path, options) {
  const res = await fetch(path, options);
  const data = await res.json().catch(() => ({}));
  if (!res.ok || data.error) throw new Error(data.error || `HTTP ${res.status}`);
  return data;
}

const selectedFiles = new Set();
let pollTimer = null;
let batchRunning = false;
let lastDoneCount = -1;
let viewingName = null;   // null = keep showing the newest finished draft

function escapeHtml(value) {
  return String(value).replace(/[&<>"']/g, (c) => (
    { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]
  ));
}

function collectConfig() {
  const payload = {};
  CONFIG_KEYS.forEach((k) => {
    const el = $('cfg_' + k);
    if (el) payload[k] = el.value;
  });
  // Radios share one name instead of one id, so read the checked one directly.
  const mode = document.querySelector('input[name="cfg_output_mode"]:checked');
  if (mode) payload.output_mode = mode.value;
  payload.port = Number(payload.port) || 8765;
  return payload;
}

async function saveConfig(partial) {
  const payload = partial ? Object.assign(collectConfig(), partial) : collectConfig();
  return api('/api/config', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
}

async function loadConfig() {
  const cfg = await api('/api/config');
  CONFIG_KEYS.forEach((k) => {
    const el = $('cfg_' + k);
    if (el && cfg[k] !== undefined && cfg[k] !== null) el.value = cfg[k];
  });
  const mode = ['txt', 'txt_srt', 'all'].includes(cfg.output_mode) ? cfg.output_mode : 'txt_srt';
  const radio = document.querySelector(`input[name="cfg_output_mode"][value="${mode}"]`);
  if (radio) radio.checked = true;
}

function renderFiles(files) {
  // A changed inbox invalidates whatever was selected before.
  selectedFiles.clear();
  viewingName = null;
  const box = $('fileList');
  if (!files.length) {
    box.innerHTML = '<div class="empty">素材目录里还没有音视频文件</div>';
    updateSelectionUI();
    return;
  }
  box.innerHTML = files.map((f) => {
    const size = (f.size / 1048576).toFixed(1) + ' MB';
    return `<label><input type="checkbox" name="media" value="${encodeURIComponent(f.name)}">` +
           `<span>${escapeHtml(f.name)}</span><span class="size">${size}</span></label>`;
  }).join('');
  box.querySelectorAll('input[name="media"]').forEach((el) => {
    el.addEventListener('change', () => {
      const name = decodeURIComponent(el.value);
      if (el.checked) selectedFiles.add(name); else selectedFiles.delete(name);
      el.closest('label').classList.toggle('selected', el.checked);
      updateSelectionUI();
    });
  });
  updateSelectionUI();
}

function updateSelectionUI() {
  const n = selectedFiles.size;
  $('selectedCount').textContent = n ? `已选 ${n} 个文件` : '还没选文件';
  const btn = $('runBtn');
  btn.textContent = batchRunning ? '这一批正在跑…'
    : (n ? `开始转文字（${n} 个）` : '先选文件');
  btn.disabled = batchRunning || n === 0;
}

async function loadFiles() {
  const data = await api('/api/files');
  renderFiles(data.files || []);
}

async function checkEnv() {
  const s = await api('/api/status');
  const badge = $('envBadge');
  badge.textContent = s.ready ? '环境就绪' : '环境未就绪 · 展开下方配置';
  badge.style.color = s.ready ? 'var(--ok)' : 'var(--warn)';
  const lines = Object.entries(s.checks)
    .map(([k, v]) => `<div class="${v ? 'ok' : 'bad'}">${v ? '✓' : '✗'} ${k}</div>`)
    .join('');
  $('statusBox').innerHTML = lines + (s.hint ? `<div class="bad">${s.hint}</div>` : '');
  if (!s.ready) $('envCard').open = true;
  return s;
}

function showRewriteState(s) {
  const el = $('rewriteState');
  if (!el) return;
  if (s.status === 'off') {
    el.textContent = '当前：关闭 · 纯本地，不联网';
    el.style.color = 'var(--ok)';
  } else {
    el.textContent = s.configured
      ? '当前：接口已配置，但实现预留中（不会发起请求）'
      : '当前：已选接口，尚未填 Base URL / 模型名';
    el.style.color = 'var(--warn)';
  }
}

// Engine switch: cloud mode shows its config block and dims local-only fields.
function refreshEngineUI() {
  const cloud = $('cfg_asr_engine').value === 'cloud';
  // Never hide the "your audio will be uploaded" warning behind a folded panel.
  if (cloud && $('advancedSettings')) $('advancedSettings').open = true;
  $('cloudBlock').classList.toggle('hidden', !cloud);
  document.querySelectorAll('.local-only').forEach((el) => {
    el.classList.toggle('dimmed', cloud);
    el.querySelectorAll('select, input').forEach((c) => { c.disabled = cloud; });
  });
  const base = $('cfg_cloud_asr_base_url').value.trim();
  const model = $('cfg_cloud_asr_model').value.trim();
  const state = $('cloudState');
  if (!cloud) {
    state.textContent = '当前：本地引擎，音频不出本机';
    state.style.color = 'var(--ok)';
  } else if (base && model) {
    state.textContent = '当前：云端已配置，转写时将上传音频';
    state.style.color = 'var(--warn)';
  } else {
    state.textContent = '当前：已选云端，尚未填 Base URL / 模型名';
    state.style.color = 'var(--warn)';
  }
}

function showAuthorInfo() {
  $('authorName').textContent = AUTHOR_INFO.name;
  $('authorTagline').textContent = AUTHOR_INFO.tagline;
  $('authorBio').textContent = AUTHOR_INFO.bio;
  $('authorAvatar').textContent = (AUTHOR_INFO.name || '作').slice(0, 1);
  if (AUTHOR_INFO.qr) $('authorQrImg').src = AUTHOR_INFO.qr;
}

async function loadRewriteState() {
  try { showRewriteState(await api('/api/rewrite')); } catch (err) { /* offline */ }
}

function setProgress(text, running, done) {
  $('progress').textContent = text;
  $('progressBar').classList.toggle('running', !!running);
  $('progressBar').style.width = running ? '' : (done ? '100%' : '0');
}

async function pickFolder(kind, inputId, onPicked) {
  const btn = kind === 'inbox' ? $('pickInbox') : $('pickOutput');
  btn.disabled = true;
  setProgress('弹窗已经打开了，选好文件夹点「确定」就行…', false);
  try {
    const r = await api('/api/pick-folder', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ for: kind }),
    });
    if (r.error) { setProgress('打不开目录窗口：' + r.error, false); return; }
    if (r.cancelled || !r.path) { setProgress('没选文件夹，随时可以再点', false); return; }
    $(inputId).value = r.path;
    await onPicked();
  } catch (err) {
    setProgress('打不开目录窗口：' + err.message, false);
  } finally {
    btn.disabled = false;
  }
}

function showResult(r) {
  $('srtBox').textContent = r.srt || '（这次没有字幕）';
  $('txtBox').textContent = r.txt || '（这次没有文字稿）';
  $('jobDir').textContent = r.job_dir || '—';
  $('engineInfo').textContent = r.engine === 'cloud'
    ? `云端 · ${r.cloud_provider || ''}${r.timestamp_precision === 'whole_file' ? ' · 整段时间轴' : ''}`
    : '本地模型';
  $('srtPath').textContent = r.srt_path || (r.output_mode === 'txt' ? '按设置未输出' : '—');
  $('txtPath').textContent = r.txt_path || '—';
  $('elapsed').textContent = (r.elapsed ?? '—') + ' 秒';
  $('copyBtn').disabled = !r.txt;
  if (r.rewrite) showRewriteState(r.rewrite);
}

const STATUS_TEXT = {
  pending: '排队中', running: '正在转', done: '已完成',
  error: '没成功', cancelled: '已跳过',
};

function renderQueue(s) {
  const box = $('queueBox');
  if (!s.items || !s.items.length) { box.classList.add('hidden'); return; }
  box.classList.remove('hidden');
  const settled = s.items.filter((i) => ['done', 'error', 'cancelled'].includes(i.status)).length;
  $('queueSummary').textContent = s.running
    ? `第 ${Math.min(settled + 1, s.total)} / ${s.total} 个 · ${s.current || '准备中'}`
    : (s.cancelled ? `已停止 · 完成 ${s.done} 个`
      : `这一批跑完了 · 完成 ${s.done} 个${s.failed ? ` · 失败 ${s.failed} 个` : ''}`);
  $('queueBarFill').style.width = (s.total ? (settled / s.total * 100) : 0) + '%';
  $('cancelJobsBtn').disabled = !s.running;
  $('queueList').innerHTML = s.items.map((i) => {
    const state = i.status === 'done' ? `完成 ${i.elapsed}s`
      : i.status === 'error' ? `失败：${escapeHtml(i.error || '')}`
        : (STATUS_TEXT[i.status] || i.status);
    const clickable = i.status === 'done' ? ' clickable' : '';
    return `<div class="queue-row q-${i.status}${clickable}" data-name="${encodeURIComponent(i.name)}" title="${escapeHtml(i.name)}">` +
           `<span class="qdot"></span><span class="qname">${escapeHtml(i.name)}</span>` +
           `<span class="qstate">${state}</span></div>`;
  }).join('');
  $('queueList').querySelectorAll('.queue-row.clickable').forEach((el) => {
    el.addEventListener('click', () => {
      viewingName = decodeURIComponent(el.dataset.name);
      loadJobResult(viewingName);
    });
  });
}

async function loadJobResult(name) {
  try {
    const r = await api('/api/jobs/result?name=' + encodeURIComponent(name));
    showResult(r);
    setProgress(`正在看「${name}」的稿子`, false, true);
  } catch (err) {
    setProgress('这份稿子打不开：' + err.message, false);
  }
}

async function pollJobs() {
  let s;
  try { s = await api('/api/jobs'); }
  catch (err) { stopPolling(); setProgress('进度获取失败：' + err.message, false, true); return; }
  renderQueue(s);
  batchRunning = s.running;
  updateSelectionUI();
  if (s.done > lastDoneCount) {
    lastDoneCount = s.done;
    if (viewingName === null) {
      const latest = [...s.items].reverse().find((i) => i.status === 'done');
      if (latest) loadJobResult(latest.name);
    }
  }
  if (!s.running) {
    stopPolling();
    setProgress(s.cancelled ? '已停止，做完的稿子都还在'
      : '这一批跑完了！点列表里「已完成」的那行看稿子', false, true);
  } else {
    setProgress(`排队转写中 · 已完成 ${s.done} / ${s.total} 个，关掉浏览器也会继续跑`, true);
  }
}

function stopPolling() {
  if (pollTimer) { clearInterval(pollTimer); pollTimer = null; }
}

function startPolling() {
  stopPolling();
  pollTimer = setInterval(pollJobs, 1500);
  pollJobs();
}

async function startBatch() {
  const names = [...selectedFiles];
  if (!names.length || batchRunning) return;
  lastDoneCount = -1;
  viewingName = null;
  setProgress('正在把这一批排上队…', true);
  try {
    await api('/api/jobs', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ names }),
    });
    batchRunning = true;
    updateSelectionUI();
    startPolling();
  } catch (err) {
    setProgress('没能开始：' + err.message, false);
  }
}

async function restoreJobs() {
  try {
    const s = await api('/api/jobs');
    if (!s.items || !s.items.length) return;
    renderQueue(s);
    batchRunning = s.running;
    updateSelectionUI();
    if (s.running) {
      lastDoneCount = s.done;
      startPolling();
    } else {
      const latest = [...s.items].reverse().find((i) => i.status === 'done');
      if (latest) loadJobResult(latest.name);
    }
  } catch (err) { /* no backend, keep the first render */ }
}

$('refreshBtn').addEventListener('click', loadFiles);
$('runBtn').addEventListener('click', startBatch);

$('selectAllBtn').addEventListener('click', () => {
  $('fileList').querySelectorAll('input[name="media"]').forEach((el) => {
    el.checked = true;
    selectedFiles.add(decodeURIComponent(el.value));
    el.closest('label').classList.add('selected');
  });
  updateSelectionUI();
});

$('clearSelBtn').addEventListener('click', () => {
  $('fileList').querySelectorAll('input[name="media"]').forEach((el) => {
    el.checked = false;
    el.closest('label').classList.remove('selected');
  });
  selectedFiles.clear();
  updateSelectionUI();
});

$('cancelJobsBtn').addEventListener('click', async () => {
  try {
    await api('/api/jobs/cancel', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: '{}' });
    setProgress('正在收尾：当前这个做完就停', true);
  } catch (err) { setProgress('停止没成功：' + err.message, false); }
});

$('pickInbox').addEventListener('click', () => pickFolder('inbox', 'cfg_inbox_dir', async () => {
  await saveConfig({ inbox_dir: $('cfg_inbox_dir').value });
  await loadFiles();
  await checkEnv();
  setProgress('文件夹换好了', false);
}));

$('pickOutput').addEventListener('click', () => pickFolder('output', 'cfg_output_dir', async () => {
  await saveConfig({ output_dir: $('cfg_output_dir').value });
  await checkEnv();
  setProgress('保存位置换好了', false);
}));

$('applyInbox').addEventListener('click', async () => {
  try {
    await saveConfig({ inbox_dir: $('cfg_inbox_dir').value });
    await loadFiles();
    await checkEnv();
    setProgress('文件夹换好了', false);
  } catch (err) { setProgress('保存失败：' + err.message, false); }
});

$('applyOutput').addEventListener('click', async () => {
  try {
    await saveConfig({ output_dir: $('cfg_output_dir').value });
    await checkEnv();
    setProgress('保存位置换好了', false);
  } catch (err) { setProgress('保存失败：' + err.message, false); }
});

$('applyRewrite').addEventListener('click', async () => {
  try {
    await saveConfig();
    await loadRewriteState();
    setProgress('改稿引擎预留配置已保存（仍不会联网）', false);
  } catch (err) { setProgress('保存失败：' + err.message, false); }
});

$('applyCloud').addEventListener('click', async () => {
  try {
    await saveConfig();
    refreshEngineUI();
    setProgress('云端听写配置已保存', false);
  } catch (err) { setProgress('保存失败：' + err.message, false); }
});

['cfg_asr_engine'].forEach((id) => {
  $(id).addEventListener('change', async () => {
    refreshEngineUI();
    try {
      await saveConfig();
      setProgress($('cfg_asr_engine').value === 'cloud'
        ? '已切到云端：请确认你信任这个服务，音频会传出去'
        : '已切回自己电脑，音频不外传', false);
    } catch (err) { setProgress('保存失败：' + err.message, false); }
  });
});

['cfg_backend', 'cfg_asr_model', 'cfg_language', 'cfg_aligner'].forEach((id) => {
  $(id).addEventListener('change', async () => {
    try {
      await saveConfig();
      setProgress('设置已保存', false);
    } catch (err) { setProgress('保存失败：' + err.message, false); }
  });
});

// The timed pane always previews the alignment result; the tag just tells the
// truth about whether an .srt will also land on disk.
function refreshOutputModeUI() {
  const picked = document.querySelector('input[name="cfg_output_mode"]:checked');
  const mode = picked ? picked.value : 'txt_srt';
  const tag = $('srtPaneTag');
  if (tag) tag.textContent = mode === 'txt' ? '字幕 · 仅预览' : '字幕';
}

document.querySelectorAll('input[name="cfg_output_mode"]').forEach((el) => {
  el.addEventListener('change', async () => {
    refreshOutputModeUI();
    try {
      await saveConfig();
      setProgress('记下了，下次转文字就按这个给', false);
    } catch (err) { setProgress('保存失败：' + err.message, false); }
  });
});

$('saveBtn').addEventListener('click', async () => {
  try {
    await saveConfig();
    await loadFiles();
    await checkEnv();
    await loadRewriteState();
    setProgress('都存好了', false);
  } catch (err) {
    $('statusBox').innerHTML = `<div class="bad">保存失败：${err.message}</div>`;
  }
});

$('checkBtn').addEventListener('click', checkEnv);
$('copyBtn').addEventListener('click', async () => {
  const btn = $('copyBtn');
  try {
    await navigator.clipboard.writeText($('txtBox').textContent);
    btn.textContent = '已复制，去粘贴吧';
    setTimeout(() => { btn.textContent = '复制文字稿'; }, 2200);
  } catch (err) {
    setProgress('复制没成功，可以手动选中右边框里的文字', false);
  }
});

// Author card: mock data lives in AUTHOR_INFO at the top of this file.
$('authorBtn').addEventListener('click', () => {
  showAuthorInfo();
  $('authorModal').classList.remove('hidden');
});
$('authorClose').addEventListener('click', () => $('authorModal').classList.add('hidden'));
$('authorModal').addEventListener('click', (e) => {
  if (e.target === $('authorModal')) $('authorModal').classList.add('hidden');
});
document.addEventListener('keydown', (e) => {
  if (e.key === 'Escape') $('authorModal').classList.add('hidden');
});

(async function init() {
  try {
    await loadConfig();
    refreshEngineUI();
    refreshOutputModeUI();
    await loadFiles();
    await checkEnv();
    await loadRewriteState();
    await restoreJobs();
  } catch (err) {
    $('envBadge').textContent = '后端未连接';
    $('fileList').innerHTML = '<div class="empty">后端未连接，请先启动 server.py</div>';
  }
})();

// Chrome restores radio/input values on reload *after* our first render. Re-sync
// once the page settles so what the user sees always matches config.json.
window.addEventListener('load', async () => {
  try {
    await loadConfig();
    refreshEngineUI();
    refreshOutputModeUI();
  } catch (err) { /* offline, keep the first render */ }
});
