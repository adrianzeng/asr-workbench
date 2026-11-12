const $ = (id) => document.getElementById(id);

const CONFIG_KEYS = [
  'ffmpeg', 'oneasr_cli', 'oneasr_data_root', 'inbox_dir', 'output_dir',
  'work_dir', 'language', 'asr_model', 'aligner', 'backend',
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

async function loadRewriteState() {
  try { showRewriteState(await api('/api/rewrite')); } catch (err) { /* offline */ }
}

function setProgress(text, running) {
  $('progress').textContent = text;
  $('progressBar').classList.toggle('running', !!running);
  $('progressBar').style.width = running ? '' : (text === '完成' ? '100%' : '0');
}

async function pickFolder(kind, inputId, onPicked) {
  const btn = kind === 'inbox' ? $('pickInbox') : $('pickOutput');
  btn.disabled = true;
  setProgress('已打开系统目录选择窗口，选好文件夹后点「确定」…', false);
  try {
    const r = await api('/api/pick-folder', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ for: kind }),
    });
    if (r.error) { setProgress('打不开目录窗口：' + r.error, false); return; }
    if (r.cancelled || !r.path) { setProgress('已取消选择', false); return; }
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
  btn.textContent = '转写中…';
  setProgress('正在抽音轨并转写，长文件需要一点时间', true);
  try {
    const r = await api('/api/transcribe', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name: selectedFile }),
    });
    $('srtBox').textContent = r.srt || '（未生成 SRT）';
    $('txtBox').textContent = r.txt || '（未生成 TXT）';
    $('jobDir').textContent = r.job_dir || '—';
    $('srtPath').textContent = r.srt_path || '—';
    $('txtPath').textContent = r.txt_path || '—';
    $('elapsed').textContent = r.elapsed + ' 秒';
    $('copyBtn').disabled = !r.txt;
    if (r.rewrite) showRewriteState(r.rewrite);
    setProgress('完成', false);
  } catch (err) {
    setProgress('失败：' + err.message, false);
  } finally {
    btn.textContent = '开始转写';
    btn.disabled = !selectedFile;
  }
}

$('refreshBtn').addEventListener('click', loadFiles);
$('runBtn').addEventListener('click', runTranscribe);

$('pickInbox').addEventListener('click', () => pickFolder('inbox', 'cfg_inbox_dir', async () => {
  await saveConfig({ inbox_dir: $('cfg_inbox_dir').value });
  await loadFiles();
  await checkEnv();
  setProgress('素材目录已更新', false);
}));

$('pickOutput').addEventListener('click', () => pickFolder('output', 'cfg_output_dir', async () => {
  await saveConfig({ output_dir: $('cfg_output_dir').value });
  await checkEnv();
  setProgress('输出目录已更新', false);
}));

$('applyInbox').addEventListener('click', async () => {
  try {
    await saveConfig({ inbox_dir: $('cfg_inbox_dir').value });
    await loadFiles();
    await checkEnv();
    setProgress('素材目录已更新', false);
  } catch (err) { setProgress('保存失败：' + err.message, false); }
});

$('applyOutput').addEventListener('click', async () => {
  try {
    await saveConfig({ output_dir: $('cfg_output_dir').value });
    await checkEnv();
    setProgress('输出目录已更新', false);
  } catch (err) { setProgress('保存失败：' + err.message, false); }
});

$('applyRewrite').addEventListener('click', async () => {
  try {
    await saveConfig();
    await loadRewriteState();
    setProgress('改稿引擎预留配置已保存（仍不会联网）', false);
  } catch (err) { setProgress('保存失败：' + err.message, false); }
});

['cfg_backend', 'cfg_asr_model', 'cfg_language', 'cfg_aligner'].forEach((id) => {
  $(id).addEventListener('change', async () => {
    try {
      await saveConfig();
      setProgress('识别设置已保存', false);
    } catch (err) { setProgress('保存失败：' + err.message, false); }
  });
});

$('saveBtn').addEventListener('click', async () => {
  try {
    await saveConfig();
    await loadFiles();
    await checkEnv();
    await loadRewriteState();
    setProgress('全部配置已保存', false);
  } catch (err) {
    $('statusBox').innerHTML = `<div class="bad">保存失败：${err.message}</div>`;
  }
});

$('checkBtn').addEventListener('click', checkEnv);
$('copyBtn').addEventListener('click', () => navigator.clipboard.writeText($('txtBox').textContent));

(async function init() {
  try {
    await loadConfig();
    await loadFiles();
    await checkEnv();
    await loadRewriteState();
  } catch (err) {
    $('envBadge').textContent = '后端未连接';
    $('fileList').innerHTML = '<div class="empty">后端未连接，请先启动 server.py</div>';
  }
})();
