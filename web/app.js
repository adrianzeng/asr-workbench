const $ = (id) => document.getElementById(id);

async function api(path, options) {
  const res = await fetch(path, options);
  const data = await res.json().catch(() => ({}));
  if (!res.ok || data.error) throw new Error(data.error || `HTTP ${res.status}`);
  return data;
}

let selectedFile = null;

function showTab(name) {
  document.querySelectorAll('.tab').forEach((t) => t.classList.toggle('active', t.dataset.tab === name));
  $('tab-work').classList.toggle('hidden', name !== 'work');
  $('tab-settings').classList.toggle('hidden', name !== 'settings');
}

function renderFiles(files) {
  const box = $('fileList');
  if (!files.length) {
    box.innerHTML = '<div class="empty">inbox 里还没有音视频文件</div>';
    $('runBtn').disabled = true;
    return;
  }
  box.innerHTML = files
    .map((f) => {
      const size = (f.size / 1048576).toFixed(1) + ' MB';
      return `<label><input type="radio" name="media" value="${encodeURIComponent(f.name)}">` +
             `<span>${f.name}</span><span class="size">${size}</span></label>`;
    })
    .join('');
  box.querySelectorAll('input[name="media"]').forEach((el) => {
    el.addEventListener('change', () => {
      selectedFile = decodeURIComponent(el.value);
      $('runBtn').disabled = false;
    });
  });
}

async function loadConfig() {
  const cfg = await api('/api/config');
  Object.keys(cfg).forEach((k) => {
    const el = $('cfg_' + k);
    if (el) el.value = cfg[k];
  });
  $('inboxHint').textContent = cfg.inbox_dir || './inbox';
}

async function loadFiles() {
  const data = await api('/api/files');
  renderFiles(data.files || []);
}

async function checkEnv() {
  const s = await api('/api/status');
  const ok = s.ready;
  const badge = $('envBadge');
  badge.textContent = ok ? '环境就绪' : '环境未就绪 · 去设置';
  badge.style.color = ok ? 'var(--ok)' : 'var(--warn)';
  const lines = Object.entries(s.checks)
    .map(([k, v]) => `<div class="${v ? 'ok' : 'bad'}">${v ? '✓' : '✗'} ${k}</div>`)
    .join('');
  $('statusBox').innerHTML = lines + (s.hint ? `<div class="bad">${s.hint}</div>` : '');
  return s;
}

async function runTranscribe() {
  if (!selectedFile) return;
  const btn = $('runBtn');
  btn.disabled = true;
  btn.textContent = '转写中…';
  $('progress').textContent = '正在抽音轨并转写，长文件可能需要一点时间';
  try {
    const r = await api('/api/transcribe', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name: selectedFile }),
    });
    $('srtBox').textContent = r.srt || '（未生成 SRT）';
    $('txtBox').textContent = r.txt || '（未生成 TXT）';
    $('srtPath').textContent = r.srt_path || '—';
    $('txtPath').textContent = r.txt_path || '—';
    $('elapsed').textContent = r.elapsed + ' 秒';
    $('copyBtn').disabled = !r.txt;
    $('progress').textContent = '完成';
  } catch (err) {
    $('progress').textContent = '失败：' + err.message;
  } finally {
    btn.textContent = '开始转写';
    btn.disabled = !selectedFile;
  }
}

async function saveConfig() {
  const payload = {};
  ['ffmpeg', 'oneasr_cli', 'oneasr_data_root', 'inbox_dir', 'output_dir',
   'work_dir', 'language', 'asr_model', 'aligner', 'port'].forEach((k) => {
    payload[k] = $('cfg_' + k).value;
  });
  payload.port = Number(payload.port) || 8765;
  try {
    await api('/api/config', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
    $('inboxHint').textContent = payload.inbox_dir;
    await loadFiles();
    await checkEnv();
    $('progress').textContent = '配置已保存';
  } catch (err) {
    $('statusBox').innerHTML = `<div class="bad">保存失败：${err.message}</div>`;
  }
}

document.querySelectorAll('.tab').forEach((t) => t.addEventListener('click', () => showTab(t.dataset.tab)));
$('refreshBtn').addEventListener('click', loadFiles);
$('runBtn').addEventListener('click', runTranscribe);
$('saveBtn').addEventListener('click', saveConfig);
$('checkBtn').addEventListener('click', checkEnv);
$('copyBtn').addEventListener('click', () => navigator.clipboard.writeText($('txtBox').textContent));

(async function init() {
  try {
    await loadConfig();
    await loadFiles();
    await checkEnv();
  } catch (err) {
    $('envBadge').textContent = '后端未连接';
  }
})();
