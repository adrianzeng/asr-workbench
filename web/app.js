const $ = (id) => document.getElementById(id);

// —— 作者信息（演示数据）————————————————————————————————
// 发布前把下面每一项替换成你自己的资料。qr 字段填二维码图片的文件名，
// 图片放到 web/ 目录即可（例：'author-qr.png'）；留空则显示占位图形。
const AUTHOR_INFO = {
  name: '糕头',
  tagline: 'AI × 自媒体 · 把工具做成普通人能用的样子',
  bio: '一个用 AI 工具做自媒体的独立创作者。这个转写工作台是我自己日常在用的，开源出来希望帮刚开始做内容的你省点时间。',
  wechat: 'demo-wechat-id',
  email: 'demo@example.com',
  site: 'https://example.com',
  qr: '', // 例：'author-qr.png'；留空显示占位
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

let selectedFile = null;

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
  selectedFile = null;
  $('runBtn').disabled = true;
  const box = $('fileList');
  if (!files.length) {
    box.innerHTML = '<div class="empty">素材目录里还没有音视频文件</div>';
    return;
  }
  box.innerHTML = files.map((f) => {
    const size = (f.size / 1048576).toFixed(1) + ' MB';
    return `<label><input type="radio" name="media" value="${encodeURIComponent(f.name)}">` +
           `<span>${f.name}</span><span class="size">${size}</span></label>`;
  }).join('');
  box.querySelectorAll('input[name="media"]').forEach((el) => {
    el.addEventListener('change', () => {
      selectedFile = decodeURIComponent(el.value);
      $('runBtn').disabled = false;
      box.querySelectorAll('label').forEach((l) => l.classList.remove('selected'));
      el.closest('label').classList.add('selected');
    });
  });
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
  $('authorWechat').textContent = AUTHOR_INFO.wechat;
  $('authorEmail').textContent = AUTHOR_INFO.email;
  $('authorSite').textContent = AUTHOR_INFO.site;
  $('authorAvatar').textContent = (AUTHOR_INFO.name || '作').slice(0, 1);
  if (AUTHOR_INFO.qr) {
    const img = document.createElement('img');
    img.src = AUTHOR_INFO.qr;
    img.alt = '作者二维码';
    $('authorQr').innerHTML = '';
    $('authorQr').appendChild(img);
  }
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

async function runTranscribe() {
  if (!selectedFile) return;
  const btn = $('runBtn');
  btn.disabled = true;
  btn.textContent = '正在听…';
  setProgress('正在听这段视频，长一点的要等几分钟，先别关页面…', true);
  try {
    const r = await api('/api/transcribe', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name: selectedFile }),
    });
    $('srtBox').textContent = r.srt || '（这次没有字幕）';
    $('txtBox').textContent = r.txt || '（这次没有文字稿）';
    $('jobDir').textContent = r.job_dir || '—';
    $('engineInfo').textContent = r.engine === 'cloud'
      ? `云端 · ${r.cloud_provider || ''}${r.timestamp_precision === 'whole_file' ? ' · 整段时间轴' : ''}`
      : '本地模型';
    $('srtPath').textContent = r.srt_path || (r.output_mode === 'txt' ? '按设置未输出' : '—');
    $('txtPath').textContent = r.txt_path || '—';
    $('elapsed').textContent = r.elapsed + ' 秒';
    $('copyBtn').disabled = !r.txt;
    if (r.rewrite) showRewriteState(r.rewrite);
    setProgress('稿子好了！右边点「复制文字稿」就能拿走', false, true);
  } catch (err) {
    setProgress('没成功：' + err.message, false);
  } finally {
    btn.textContent = '开始转文字';
    btn.disabled = !selectedFile;
  }
}

$('refreshBtn').addEventListener('click', loadFiles);
$('runBtn').addEventListener('click', runTranscribe);

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
