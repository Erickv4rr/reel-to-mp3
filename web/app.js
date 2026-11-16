'use strict';

const $ = id => document.getElementById(id);
const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
const icon = (name, cls = '') => `<svg class="${cls}"><use href="#i-${name}"/></svg>`;
const IG = /instagram\.com\//i;

let state = null;
let files = [];
let jobs = [];
let query = '';
let current = null;      // name of the file in the player
const seenDone = new Set();

// ------------------------------------------------------------------ helpers

async function api(path, body) {
  const opts = body === undefined ? {} : { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) };
  const r = await fetch(path, opts);
  const data = await r.json().catch(() => ({}));
  if (!r.ok) throw Object.assign(new Error(data.error || 'Something went wrong.'), { data });
  return data;
}

function toast(text, kind = 'ok') {
  const el = document.createElement('div');
  el.className = 'toast ' + kind;
  el.innerHTML = icon(kind === 'err' ? 'alert' : 'check') + `<span>${esc(text)}</span>`;
  $('toasts').append(el);
  setTimeout(() => { el.classList.add('out'); setTimeout(() => el.remove(), 250); }, kind === 'err' ? 5000 : 2800);
}

const fmtTime = s => {
  if (!isFinite(s) || s < 0) return '0:00';
  s = Math.round(s);
  return Math.floor(s / 60) + ':' + String(s % 60).padStart(2, '0');
};
const fmtSize = b => b >= 1048576 ? (b / 1048576).toFixed(1) + ' MB' : Math.max(1, Math.round(b / 1024)) + ' KB';
function fmtDate(t) {
  const d = new Date(t * 1000), now = new Date();
  const day = 86400000, start = new Date(now.getFullYear(), now.getMonth(), now.getDate()).getTime();
  if (d.getTime() >= start) return 'Today';
  if (d.getTime() >= start - day) return 'Yesterday';
  return d.toLocaleDateString([], { month: 'short', day: 'numeric', year: d.getFullYear() === now.getFullYear() ? undefined : 'numeric' });
}
const baseName = n => n.replace(/\.mp3$/i, '').replace(/\s*\[[A-Za-z0-9_-]{6,}\]$/, '');
const titleOf = f => f.title || baseName(f.name);
const coverUrl = f => f.cover ? `/api/cover/${encodeURIComponent(f.name)}?v=${f.mtime}` : '';

function setRangeFill(el) {
  const p = (el.value - el.min) / (el.max - el.min) * 100;
  el.style.setProperty('--p', p + '%');
}

// ------------------------------------------------------------------ state & settings

async function loadState() {
  state = await api('/api/state');
  $('version').textContent = 'v' + state.version;
  $('qualityText').textContent = state.settings.bitrate;
  $('folderPath').textContent = state.folder;
  $('folderPath').title = state.folder;
  $('cookies').innerHTML = state.browsers.map(b => `<option value="${esc(b)}">${b === 'none' ? 'Not needed' : esc(b[0].toUpperCase() + b.slice(1))}</option>`).join('');
  $('cookies').value = state.settings.cookies;
  markBitrate();
  cookieNote();
  if (state.platform === 'mac') $('pasteKey').textContent = '⌘';
  if (state.update) {
    $('updateVersion').textContent = state.update.version;
    $('update').hidden = false;
  }
}

function markBitrate() {
  for (const b of $('bitrate').children) b.classList.toggle('on', b.dataset.v === state.settings.bitrate);
}

function cookieNote() {
  const b = $('cookies').value, mac = state.platform === 'mac';
  let t = '';
  if (b === 'safari') t = 'Safari needs permission first: System Settings → Privacy & Security → Full Disk Access → turn on Reel to MP3.';
  else if (!mac && ['chrome', 'edge', 'brave'].includes(b)) t = 'Close that browser completely first. If it still fails, log into Instagram in Firefox or Opera and pick that one instead.';
  else if (b !== 'none') t = `If it fails, close ${b[0].toUpperCase() + b.slice(1)} completely and retry.`;
  $('cookieNote').textContent = t;
}

async function saveSettings(body, okText) {
  try {
    const r = await api('/api/settings', body);
    state.settings = r.settings;
    state.folder = r.folder;
    $('folderPath').textContent = r.folder;
    $('folderPath').title = r.folder;
    $('qualityText').textContent = r.settings.bitrate;
    markBitrate();
    if (!r.cancelled && okText) toast(okText);
    if ('pick' in body && !r.cancelled) refreshFiles(true);
  } catch (e) { toast(e.message, 'err'); }
}

function openSettings() { $('settings').hidden = false; $('closeSettings').focus(); }
function closeSettings() { $('settings').hidden = true; }

$('openSettings').onclick = openSettings;
$('qualityChip').onclick = openSettings;
$('closeSettings').onclick = closeSettings;
$('settings').addEventListener('mousedown', e => { if (e.target === $('settings')) closeSettings(); });
$('changeFolder').onclick = () => saveSettings({ pick: true }, 'Save folder changed');
$('bitrate').onclick = e => {
  const b = e.target.closest('button');
  if (b && b.dataset.v !== state.settings.bitrate) saveSettings({ bitrate: b.dataset.v }, `Quality set to ${b.dataset.v} kbps`);
};
$('cookies').onchange = () => { cookieNote(); saveSettings({ cookies: $('cookies').value }); };
$('releases').onclick = () => api('/api/open-url', { url: `https://github.com/${state.repo}/releases` }).catch(() => {});
$('updateGet').onclick = () => api('/api/open-url', { url: state.update.url }).catch(() => {});

// ------------------------------------------------------------------ converting

function setMsg(t) { $('msg').textContent = t || ''; }

async function convert(text) {
  text = (text ?? $('url').value).trim();
  setMsg('');
  if (!text) { setMsg('Paste a Reel link first.'); $('url').focus(); return; }
  if (!IG.test(text)) { setMsg("That isn't an Instagram link."); return; }
  $('go').disabled = true;
  try {
    const r = await api('/api/download', { urls: text });
    $('url').value = '';
    toast(r.jobs.length > 1 ? `Converting ${r.jobs.length} Reels…` : 'Converting…');
    pollJobs(true);
  } catch (e) { setMsg(e.message); }
  finally { $('go').disabled = false; }
}

$('convertForm').onsubmit = e => { e.preventDefault(); convert(); };
$('url').addEventListener('input', () => setMsg(''));
$('paste').onclick = async () => {
  try {
    const { text } = await api('/api/clipboard');
    const t = (text || '').trim();
    if (!t) { setMsg('Your clipboard is empty. Copy a Reel link first.'); return; }
    $('url').value = t;
    if (IG.test(t)) convert(t); else setMsg("The clipboard doesn't contain an Instagram link.");
  } catch { setMsg("Couldn't read the clipboard."); }
};

// Paste anywhere in the window (outside a text box) converts right away.
document.addEventListener('paste', e => {
  if (e.target.closest('input, select, textarea')) return;
  const t = (e.clipboardData.getData('text') || '').trim();
  if (IG.test(t)) { e.preventDefault(); convert(t); }
});

// Drag a link onto the window.
document.addEventListener('dragover', e => { e.preventDefault(); document.body.classList.add('drop'); });
document.addEventListener('dragleave', e => { if (!e.relatedTarget) document.body.classList.remove('drop'); });
document.addEventListener('drop', e => {
  e.preventDefault();
  document.body.classList.remove('drop');
  const t = (e.dataTransfer.getData('text/uri-list') || e.dataTransfer.getData('text') || '').trim();
  if (IG.test(t)) convert(t); else if (t) setMsg("That isn't an Instagram link.");
});

// ------------------------------------------------------------------ queue

const STAGES = { queued: 'Waiting…', starting: 'Getting the Reel…', downloading: 'Downloading', converting: 'Converting to MP3…' };

function renderQueue() {
  $('queuePanel').hidden = jobs.length === 0;
  $('queue').innerHTML = jobs.map(j => {
    const name = j.title || j.url.replace(/^https?:\/\/(www\.)?/, '');
    const thumb = j.thumbnail ? `<img src="${esc(j.thumbnail)}" alt="" referrerpolicy="no-referrer" onerror="this.remove()">` : '';
    let sub, bar = '', actions = '';
    if (j.status === 'running') {
      const pct = j.stage === 'downloading' && j.percent != null ? Math.round(j.percent) : null;
      sub = esc(STAGES[j.stage] || 'Working…') + (pct != null ? ` ${pct}%` : '');
      bar = `<div class="bar ${pct == null ? 'indeterminate' : ''}"><i style="width:${pct ?? 0}%"></i></div>`;
    } else if (j.status === 'done') {
      sub = icon('check', 'status-icon') + 'Saved to your library';
      actions = `<button class="icon-btn" data-play-file="${esc(j.file)}" title="Play">${icon('play')}</button>
                 <button class="icon-btn" data-dismiss="${j.id}" title="Dismiss">${icon('x')}</button>`;
    } else {
      sub = icon('alert', 'status-icon') + esc(j.error);
      actions = `<button class="icon-btn" data-retry="${j.id}" title="Try again">${icon('retry')}</button>
                 <button class="icon-btn" data-dismiss="${j.id}" title="Dismiss">${icon('x')}</button>`;
    }
    return `<div class="row job ${j.status}">
      <div class="thumb">${icon('music')}${thumb}</div>
      <div class="t-main">
        <div class="t-title" title="${esc(j.url)}">${esc(name)}</div>
        <div class="t-sub">${sub}</div>${bar}
      </div>
      <div class="t-side">${actions}</div>
    </div>`;
  }).join('');
}

$('queue').onclick = async e => {
  const b = e.target.closest('button');
  if (!b) return;
  if (b.dataset.retry) { await api('/api/retry', { id: b.dataset.retry }).catch(err => toast(err.message, 'err')); pollJobs(true); }
  if (b.dataset.dismiss) { await api('/api/dismiss', { id: b.dataset.dismiss }).catch(() => {}); pollJobs(true); }
  if (b.dataset.playFile) play(b.dataset.playFile);
};
$('clearJobs').onclick = async () => { await api('/api/clear-jobs', {}).catch(() => {}); pollJobs(true); };

let jobTimer = null;
let firstPoll = true;  // jobs already finished when the window opened don't get a toast
async function pollJobs(now) {
  clearTimeout(jobTimer);
  if (!now) await new Promise(r => setTimeout(r, 0));
  try {
    const r = await api('/api/jobs');
    jobs = r.jobs;
    let finished = false;
    for (const j of jobs) {
      if (j.status !== 'running' && !seenDone.has(j.id)) {
        seenDone.add(j.id);
        if (j.status === 'done' && !firstPoll) {
          finished = true;
          toast(`Saved “${j.title || j.file}”`);
          // It's in the library now, so tidy it out of "In progress" shortly.
          setTimeout(() => api('/api/dismiss', { id: j.id }).then(() => pollJobs(true)).catch(() => {}), 4000);
        }
      }
    }
    firstPoll = false;
    renderQueue();
    if (finished) refreshFiles(true);
  } catch { /* server restarting */ }
  jobTimer = setTimeout(pollJobs, jobs.some(j => j.status === 'running') ? 600 : 2500);
}

// ------------------------------------------------------------------ library

let filesSig = '';
async function refreshFiles(force) {
  try {
    const r = await api('/api/files');
    const sig = r.folder + '|' + r.files.map(f => f.name + f.mtime).join('|');
    if (!force && sig === filesSig) return;
    filesSig = sig;
    files = r.files;
    renderLibrary();
  } catch { /* ignore */ }
}

function visibleFiles() {
  if (!query) return files;
  const q = query.toLowerCase();
  return files.filter(f => (titleOf(f) + ' ' + (f.artist || '') + ' ' + f.name).toLowerCase().includes(q));
}

function renderLibrary() {
  const list = visibleFiles();
  $('count').textContent = files.length ? files.length : '';
  $('empty').hidden = files.length > 0;
  $('noResults').hidden = !(files.length && !list.length);
  $('library').innerHTML = list.map(f => {
    const cover = coverUrl(f);
    const playing = f.name === current;
    const sub = [f.artist, f.duration ? fmtTime(f.duration) : null].filter(Boolean).map(esc).join(' · ');
    return `<div class="row track ${playing ? 'playing' : ''}" data-name="${esc(f.name)}" tabindex="0">
      <div class="thumb">${cover ? `<img src="${cover}" alt="" loading="lazy">` : icon('music')}
        <div class="overlay">${icon(playing && !$('audio').paused ? 'pause' : 'play')}</div></div>
      <div class="t-main">
        <div class="t-title">${esc(titleOf(f))}</div>
        <div class="t-sub">${sub || esc(fmtSize(f.size))}</div>
      </div>
      <div class="t-side">
        <div class="t-actions">
          <button class="icon-btn" data-act="reveal" title="${state && state.platform === 'mac' ? 'Show in Finder' : 'Show in folder'}">${icon('reveal')}</button>
          <button class="icon-btn danger" data-act="delete" title="Move to ${state && state.platform === 'mac' ? 'Trash' : 'Recycle Bin'}">${icon('trash')}</button>
        </div>
        <div class="t-meta">${esc(fmtDate(f.mtime))}<br>${esc(fmtSize(f.size))}</div>
      </div>
    </div>`;
  }).join('');
}

$('library').onclick = async e => {
  const row = e.target.closest('.track');
  if (!row) return;
  const name = row.dataset.name;
  const act = e.target.closest('[data-act]')?.dataset.act;
  if (act === 'reveal') return api('/api/reveal', { name }).catch(err => toast(err.message, 'err'));
  if (act === 'delete') {
    try {
      await api('/api/delete', { name });
      if (current === name) stop();
      toast(`Moved to ${state.platform === 'mac' ? 'Trash' : 'Recycle Bin'}`);
      refreshFiles(true);
    } catch (err) { toast(err.message, 'err'); }
    return;
  }
  if (name === current) togglePlay(); else play(name);
};
$('library').addEventListener('keydown', e => {
  if (e.key === 'Enter' && e.target.classList.contains('track')) { e.preventDefault(); e.target.click(); }
});
$('search').addEventListener('input', () => { query = $('search').value.trim(); renderLibrary(); });
$('openFolder').onclick = () => api('/api/open-folder', {}).catch(err => toast(err.message, 'err'));

// ------------------------------------------------------------------ player

const audio = $('audio');
let seeking = false;

function play(name) {
  const f = files.find(x => x.name === name);
  if (!f) { refreshFiles(true).then(() => files.some(x => x.name === name) && play(name)); return; }
  current = name;
  audio.src = '/files/' + encodeURIComponent(name);
  audio.play().catch(() => {});
  $('player').hidden = false;
  $('pTitle').textContent = titleOf(f);
  $('pArtist').textContent = f.artist || 'Instagram';
  const cover = coverUrl(f);
  $('pArt').style.backgroundImage = cover ? `url("${cover}")` : '';
  $('pArt').innerHTML = cover ? '' : icon('music');
  if ('mediaSession' in navigator) {
    navigator.mediaSession.metadata = new MediaMetadata({
      title: titleOf(f), artist: f.artist || 'Instagram',
      artwork: cover ? [{ src: cover, sizes: '512x512', type: 'image/jpeg' }] : [],
    });
  }
  renderLibrary();
}

function stop() {
  audio.pause();
  audio.removeAttribute('src');
  audio.load();
  current = null;
  $('player').hidden = true;
  renderLibrary();
}

function togglePlay() {
  if (!current) { const f = visibleFiles()[0]; if (f) play(f.name); return; }
  audio.paused ? audio.play().catch(() => {}) : audio.pause();
}

function step(dir) {
  const list = visibleFiles();
  if (!list.length) return;
  const i = list.findIndex(f => f.name === current);
  if (dir < 0 && audio.currentTime > 3) { audio.currentTime = 0; return; }
  const next = list[(i + dir + list.length) % list.length];
  play(next.name);
}

function syncPlayIcon() {
  $('pPlay').innerHTML = icon(audio.paused ? 'play' : 'pause');
  const row = current && [...document.querySelectorAll('.track')].find(r => r.dataset.name === current);
  if (row) row.querySelector('.overlay').innerHTML = icon(audio.paused ? 'play' : 'pause');
}

audio.addEventListener('play', syncPlayIcon);
audio.addEventListener('pause', syncPlayIcon);
audio.addEventListener('ended', () => step(1));
audio.addEventListener('loadedmetadata', () => { $('pDur').textContent = fmtTime(audio.duration); });
audio.addEventListener('timeupdate', () => {
  if (seeking || !audio.duration) return;
  $('pSeek').value = Math.round(audio.currentTime / audio.duration * 1000);
  setRangeFill($('pSeek'));
  $('pCur').textContent = fmtTime(audio.currentTime);
});
$('pSeek').addEventListener('input', () => {
  seeking = true;
  setRangeFill($('pSeek'));
  if (audio.duration) $('pCur').textContent = fmtTime($('pSeek').value / 1000 * audio.duration);
});
$('pSeek').addEventListener('change', () => {
  if (audio.duration) audio.currentTime = $('pSeek').value / 1000 * audio.duration;
  seeking = false;
});
$('pPlay').onclick = togglePlay;
$('pPrev').onclick = () => step(-1);
$('pNext').onclick = () => step(1);

function setVolume(v) {
  audio.volume = v / 100;
  audio.muted = v == 0;
  $('pVol').value = v;
  setRangeFill($('pVol'));
  $('pMute').innerHTML = icon(audio.muted ? 'mute' : 'volume');
  try { localStorage.setItem('volume', v); } catch { }
}
let lastVol = 90;
$('pVol').addEventListener('input', () => setVolume(+$('pVol').value));
$('pMute').onclick = () => {
  if (audio.muted || audio.volume === 0) setVolume(lastVol || 80);
  else { lastVol = +$('pVol').value; setVolume(0); }
};
try { setVolume(+(localStorage.getItem('volume') ?? 90)); } catch { setVolume(90); }

if ('mediaSession' in navigator) {
  navigator.mediaSession.setActionHandler('play', () => audio.play());
  navigator.mediaSession.setActionHandler('pause', () => audio.pause());
  navigator.mediaSession.setActionHandler('previoustrack', () => step(-1));
  navigator.mediaSession.setActionHandler('nexttrack', () => step(1));
}

// ------------------------------------------------------------------ keyboard

document.addEventListener('keydown', e => {
  const typing = e.target.closest('input[type=text], input[type=search], select, textarea');
  if (e.key === 'Escape' && !$('settings').hidden) { closeSettings(); return; }
  if ((e.ctrlKey || e.metaKey) && e.key === ',') { e.preventDefault(); openSettings(); return; }
  if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'f') { e.preventDefault(); $('search').focus(); return; }
  if (typing) return;
  if (e.key === ' ' && !e.target.closest('button')) { e.preventDefault(); togglePlay(); }
  if (e.key === 'ArrowRight' && e.altKey) step(1);
  if (e.key === 'ArrowLeft' && e.altKey) step(-1);
});

// ------------------------------------------------------------------ start

(async function start() {
  try { await loadState(); } catch { setMsg("Couldn't start. Close Reel to MP3 and open it again."); }
  await refreshFiles(true);
  pollJobs(true);
  setInterval(() => refreshFiles(false), 5000);
  $('url').focus();
})();
