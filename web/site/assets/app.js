'use strict';
// Reader Simulator page: pick a build from builds.json, start it (builds/<id>/sim.js + sim.wasm), and manage
// its SD card, which lives in IndexedDB (one database per firmware version and device).
const $ = id => document.getElementById(id);
const MODELS = ['X4 Pro', 'X4 Classic', 'X3'];
const params = new URLSearchParams(location.search);
const store = {
  get(k, d) { try { const v = localStorage.getItem('rsim.' + k); return v === null ? d : JSON.parse(v); } catch (e) { return d; } },
  set(k, v) { try { localStorage.setItem('rsim.' + k, JSON.stringify(v)); } catch (e) { /* private mode */ } },
};
let builds = [];
let sel = store.get('sel', {});
let running = null;   // the build running in this page, if any
let runningSettings = '';
let samplesNote = '';  // shown once the simulator has started

const status = t => { $('status').textContent = t || ''; };
const cardDir = b => '/cards/' + b.id;          // working directory; the simulator's SD card is ./fs_
const cardDb = b => cardDir(b) + '/fs_';        // IDBFS names the IndexedDB database after the mount point
// The order every firmware list on this page uses: VARAGH, CrossPoint Reader, CrossInk, then the rest (as listed).
const FIRST = ['PewPewzxc/VARAGH', 'crosspoint-reader/crosspoint-reader', 'uxjulia/crossink'];
const firstRank = repo => { const i = FIRST.indexOf(repo); return i < 0 ? FIRST.length : i; };
const firmwareList = () => [...new Map(builds.map(x => [x.repo, x])).values()].sort((a, b) => firstRank(a.repo) - firstRank(b.repo));
const current = () => builds.find(b => b.repo === sel.repo && b.model === sel.model && b.ref === sel.ref);
const settings = () => $('battery').value + '/' + ($('usb').checked ? 1 : 0);
const mb = n => (n / 1e6).toFixed(1) + ' MB';

// ---- choosing a build ----
function normalise() {
  if (!builds.some(b => b.model === sel.model)) sel.model = 'X4 Pro';
  if (!builds.some(b => b.model === sel.model)) sel.model = builds[0].model;
  if (!builds.some(b => b.repo === sel.repo && b.model === sel.model)) {
    const pick = firmwareList().find(r => builds.some(b => b.repo === r.repo && b.model === sel.model));
    sel.repo = pick.repo;
  }
  if (!current()) sel.ref = builds.find(b => b.repo === sel.repo && b.model === sel.model).ref;
  store.set('sel', sel);
}

function render() {
  normalise();
  const b = current();
  $('devices').replaceChildren(...MODELS.map(m => {
    const has = builds.some(x => x.repo === sel.repo && x.model === m);
    const any = builds.some(x => x.model === m);
    const el = document.createElement('button');
    el.className = (m === sel.model ? 'on' : '') + (has ? '' : ' off');
    el.disabled = !any;
    el.innerHTML = '<b></b><span></span>';
    el.firstChild.textContent = m;
    el.lastChild.textContent = has ? 'Available' : any ? 'Other firmwares' : 'No builds yet';
    el.onclick = () => { sel.model = m; render(); };
    return el;
  }));
  const repos = firmwareList();
  $('firmwares').replaceChildren(...repos.map(r => {
    const mine = builds.filter(x => x.repo === r.repo);
    const forModel = mine.filter(x => x.model === sel.model);
    const el = document.createElement('button');
    el.className = 'fw' + (r.repo === sel.repo ? ' on' : '') + (forModel.length ? '' : ' off');
    el.innerHTML = '<div><b></b><span></span></div><span class="badge"></span>';
    el.querySelector('b').textContent = r.name;
    el.querySelector('div span').textContent = r.repo + ' · ' + (forModel.length || 'no') + ' version' + (forModel.length === 1 ? '' : 's') + ' for ' + sel.model;
    el.querySelector('.badge').textContent = [...new Set(mine.map(x => x.model))].join(', ');
    el.onclick = () => {
      sel.repo = r.repo;
      if (!forModel.length) sel.model = mine[0].model;
      render();
    };
    return el;
  }));
  $('versions').replaceChildren(...builds.filter(x => x.repo === sel.repo && x.model === sel.model).map(x => {
    const el = document.createElement('button');
    el.textContent = x.version;
    el.title = x.ref;
    el.className = x.ref === sel.ref ? 'on' : '';
    el.onclick = () => { sel.ref = x.ref; render(); };
    return el;
  }));
  const size = b.files.reduce((n, f) => n + f.size, 0);
  $('buildinfo').textContent = 'Built from ' + b.repo + ' ' + b.ref + (b.source_commit ? ' (' + b.source_commit.slice(0, 7) + ')' : '') +
    ' · ' + mb(size) + ' download, kept by the browser after the first time · licence ' + b.licence;
  $('devTitle').textContent = b.model;
  $('fwTitle').textContent = b.name + ' ' + b.version;
  if (!running) {
    $('framePreview').src = b.frame ? 'frames/' + b.frame + '.png' : '';
    $('framePreview').hidden = !b.frame;
  }
  const same = running && running.id === b.id;
  $('start').querySelector('span').textContent = !same ? 'Start' : runningSettings === settings() ? 'Restart' : 'Restart with changes';
  $('fresh').disabled = false;
  applyRealSize();
}

// ---- running a build ----
function start() {
  const b = current();
  const q = new URLSearchParams({ b: b.id, battery: $('battery').value, usb: $('usb').checked ? '1' : '0' });
  location.assign('?' + q);  // a fresh page per run: one WebAssembly instance per page
}

function deleteDb(name) {
  return new Promise(resolve => {
    const r = indexedDB.deleteDatabase(name);
    r.onsuccess = r.onerror = r.onblocked = () => resolve();
  });
}

async function boot(b) {
  if (!self.crossOriginIsolated) {
    status(window.coiError ? 'This browser blocked the page\'s helper (' + window.coiError + '). Private browsing does that: open the page in a normal tab.'
      : sessionStorage.getItem('coiReloaded') ? 'This browser cannot run the simulator here (no cross-origin isolation). Try a current Chrome, Edge, Firefox or Safari.'
      : 'Preparing the page...');
    return;
  }
  sessionStorage.removeItem('coiReloaded');
  if (params.get('fresh') === '1') {
    await deleteDb(cardDb(b));
    params.delete('fresh');
    history.replaceState(null, '', '?' + params);
  }
  running = b;
  runningSettings = settings();
  render();
  $('framePreview').hidden = true;
  $('canvas').hidden = false;
  $('loading').hidden = false;
  $('addBooks').setAttribute('aria-disabled', 'false');
  $('bookFiles').disabled = false;
  $('download').disabled = false;
  $('shotReader').disabled = $('shotScreen').disabled = false;
  const restart = sessionStorage.getItem('simRestartEnv');  // set by the simulator on sleep/wake or reboot
  sessionStorage.removeItem('simRestartEnv');
  // Keep the last drawn frame in the canvas, or screenshots taken between frames come out black.
  const getContext = HTMLCanvasElement.prototype.getContext;
  HTMLCanvasElement.prototype.getContext = function (type, attrs) {
    if (this === $('canvas') && /webgl/.test(type)) attrs = { ...attrs, preserveDrawingBuffer: true };
    return getContext.call(this, type, attrs);
  };
  window.Module = {
    canvas: $('canvas'),
    locateFile: p => 'builds/' + b.id + '/' + p,
    print: t => console.log(t),
    printErr: t => console.warn(t),
    setStatus: t => { $('loadingText').textContent = t.replace(/\(.*\)/, '') || 'Starting'; },
    onRuntimeInitialized: () => { $('loading').hidden = true; status(samplesNote); },
    onExit: () => status('The reader turned off. Press Restart to turn it on again.'),
    onAbort: what => startFailed(what),
    preRun: [() => {
      const FS = Module.FS, ENV = Module.ENV;
      ENV.VARAGH_SIM_BATTERY = String($('battery').value);
      ENV.VARAGH_SIM_USB = $('usb').checked ? '1' : '0';
      ENV.SDL_EMSCRIPTEN_KEYBOARD_ELEMENT = '#canvas';  // keys go to the reader only when it has focus
      if (b.frame) ENV.CROSSPOINT_SIM_FRAME = '/frame/' + b.frame;
      if (restart !== null) {
        for (const line of restart.split('\n')) {
          const i = line.indexOf('=');
          if (i > 0) ENV[line.slice(0, i)] = line.slice(i + 1);
        }
      }
      FS.mkdirTree(cardDb(b));
      FS.mount(Module.IDBFS, {}, cardDb(b));
      FS.chdir(cardDir(b));
      Module.addRunDependency('sd');
      FS.syncfs(true, async () => {
        try { FS.mkdir(cardDb(b) + '/books'); } catch (e) { /* exists */ }
        try { await addSamples(cardDb(b)); } catch (e) { console.warn('sample books:', e); }
        Module.removeRunDependency('sd');
        sdEnable();
      });
      if (b.frame) {
        FS.mkdirTree('/frame');
        for (const ext of ['.png', '.keys']) {
          Module.addRunDependency(ext);
          fetch('frames/' + b.frame + ext).then(r => r.arrayBuffer()).then(data => {
            FS.writeFile('/frame/' + b.frame + ext, new Uint8Array(data));
            Module.removeRunDependency(ext);
          });
        }
      }
      setInterval(() => saveCard().then(() => { if (!document.hidden) sdRender(); }), 5000);
    }],
  };
  const s = document.createElement('script');
  s.src = 'builds/' + b.id + '/sim.js';
  s.onerror = () => status('Could not load this build.');
  document.body.appendChild(s);
}

// Free books and an English dictionary (samples/manifest.json), copied once onto each SD card. Files already
// on the card are kept, so a reader's own dictionary choice (.crosspoint/dictionary.bin) stays.
async function addSamples(root) {
  const FS = Module.FS, mark = root + '/.rsim-samples';
  if (FS.analyzePath(mark).exists) return;
  const list = await (await fetch('samples/manifest.json')).json();
  let missing = 0;
  for (const f of list.files) {
    const dest = root + '/' + f.path;
    if (FS.analyzePath(dest).exists) continue;
    try {  // one file that does not download must not keep the others off the card
      const r = await fetch('samples/' + (f.src || f.path).split('/').map(encodeURIComponent).join('/'));
      if (!r.ok) throw new Error(r.status);
      FS.mkdirTree(dest.slice(0, dest.lastIndexOf('/')));
      FS.writeFile(dest, new Uint8Array(await r.arrayBuffer()));
    } catch (e) { missing++; console.warn('sample file ' + f.path + ':', e); }
  }
  if (!missing) FS.writeFile(mark, 'sample books and dictionary added\n');  // otherwise tried again next start
  samplesNote = 'Sample books and an English dictionary are on the SD card: open the books folder on the reader.';
}

// A start that fails (no memory for the simulator, a broken download) must not leave the spinner turning.
function startFailed(what) {
  if (!running) return;
  $('loading').hidden = true;
  const text = String(what && what.message || what || 'unknown error');
  status(/memory|RangeError/i.test(text)
    ? 'This device did not give the simulator enough memory (' + text + '). Close other tabs and press Restart.'
    : 'The simulator stopped: ' + text);
}
addEventListener('error', e => { if (running && !$('loading').hidden) startFailed(e.error || e.message); });
addEventListener('unhandledrejection', e => { if (running && !$('loading').hidden) startFailed(e.reason); });

function saveCard() {
  return new Promise(resolve => window.Module && Module.FS ? Module.FS.syncfs(false, resolve) : resolve());
}

// ---- SD card tools ----
async function addBooks(files) {
  const FS = Module.FS;
  for (const f of files) {
    const name = f.name.replace(/[\/\\:*?"<>|]/g, '_');
    FS.writeFile(cardDb(running) + '/books/' + name, new Uint8Array(await f.arrayBuffer()));
  }
  await saveCard();
  sdDir = 'books';
  sdRender();
  status(files.length + ' book' + (files.length === 1 ? '' : 's') + ' added to the books folder. Open Browse Files on the reader.');
}

// The SD card browser: the card of the running build, as files and folders. What is put here is on the reader's
// card straight away (same file system); it is saved to the browser with the rest of the card.
let sdDir = '';   // folder shown, relative to the card root ('' = root)
const ICON = {
  dir: '<path d="M3 6h6l2 2h10v11H3z"/>',
  file: '<path d="M6 3h8l4 4v14H6zM14 3v4h4"/>',
  get: '<path d="M12 4v11M7 10l5 5 5-5M5 20h14"/>',
  del: '<path d="M5 7h14M10 7V4h4v3M7 7l1 13h8l1-13"/>',
};
const svg = d => '<svg viewBox="0 0 24 24" aria-hidden="true">' + d + '</svg>';
const safeName = n => n.replace(/[\/\\:*?"<>|]/g, '_').replace(/^\.\.?$/, '_');
const sdRoot = () => cardDb(running);
const sdAbs = rel => sdRoot() + (rel ? '/' + rel : '');
const fmtSize = n => n < 1024 ? n + ' B' : n < 1048576 ? (n / 1024).toFixed(0) + ' KB' : (n / 1048576).toFixed(1) + ' MB';

function sdRender() {
  if (!running || !window.Module || !Module.FS) return;
  const FS = Module.FS;
  if (!FS.analyzePath(sdAbs(sdDir)).exists) sdDir = '';
  const parts = sdDir ? sdDir.split('/') : [];
  const crumbs = [['SD card', '']].concat(parts.map((p, i) => [p, parts.slice(0, i + 1).join('/')]));
  $('sdPath').replaceChildren(...crumbs.flatMap(([name, rel], i) => {
    const b = document.createElement('button');
    b.textContent = name; b.onclick = () => { sdDir = rel; sdRender(); };
    if (i === 0) return [b];
    const sep = document.createElement('span'); sep.textContent = '/';
    return [sep, b];
  }));
  let names = [];
  try { names = FS.readdir(sdAbs(sdDir)).filter(n => n !== '.' && n !== '..' && !(sdDir === '' && n === '.rsim-samples')); } catch (e) { /* gone */ }
  const items = names.map(n => {
    const st = FS.stat(sdAbs(sdDir) + '/' + n);
    return { n, dir: FS.isDir(st.mode), size: st.size };
  }).sort((a, b) => (b.dir - a.dir) || a.n.localeCompare(b.n));
  const rows = [];
  if (sdDir) {
    const li = document.createElement('li'); li.className = 'dir';
    li.innerHTML = '<span class="kind">' + svg(ICON.dir) + '</span><button class="name">..</button>';
    li.querySelector('.name').onclick = () => { sdDir = parts.slice(0, -1).join('/'); sdRender(); };
    rows.push(li);
  }
  for (const it of items) {
    const rel = (sdDir ? sdDir + '/' : '') + it.n;
    const li = document.createElement('li');
    li.className = (it.dir ? 'dir' : 'file') + (it.n.startsWith('.') ? ' hidden' : '');
    li.innerHTML = '<span class="kind">' + svg(it.dir ? ICON.dir : ICON.file) + '</span><button class="name"></button>' +
      (it.dir ? '' : '<span class="size">' + fmtSize(it.size) + '</span>' +
        '<button class="iconbtn get" title="Download">' + svg(ICON.get) + '</button>') +
      '<button class="iconbtn del" title="Delete">' + svg(ICON.del) + '</button>';
    const nb = li.querySelector('.name'); nb.textContent = it.n; nb.title = it.n;
    if (it.dir) nb.onclick = () => { sdDir = rel; sdRender(); };
    if (!it.dir) li.querySelector('.get').onclick = () => sdDownload(rel, it.n);
    li.querySelector('.del').onclick = () => sdDelete(rel, it.dir);
    rows.push(li);
  }
  if (!items.length) {
    const li = document.createElement('li'); li.className = 'sd-empty';
    li.textContent = 'This folder is empty. Drop files here or use the upload buttons.';
    rows.push(li);
  }
  $('sdList').replaceChildren(...rows);
}

async function sdUpload(files) {
  if (!running) return;
  const FS = Module.FS;
  let n = 0;
  for (const f of files) {
    // a folder upload keeps its own folders (webkitRelativePath); single files go in the folder shown
    const rel = (f.webkitRelativePath || f.name).split('/').map(safeName).join('/');
    const dest = sdAbs(sdDir) + '/' + rel;
    try {
      FS.mkdirTree(dest.slice(0, dest.lastIndexOf('/')));
      FS.writeFile(dest, new Uint8Array(await f.arrayBuffer()));
      n++;
    } catch (e) { console.warn('upload ' + rel + ':', e); }
  }
  await saveCard();
  sdRender();
  status(n + ' file' + (n === 1 ? '' : 's') + ' put on the SD card in /' + sdDir +
    (n < files.length ? ' (' + (files.length - n) + ' could not be written: the browser storage may be full)' : '') + '.');
}

function sdDownload(rel, name) {
  const data = Module.FS.readFile(sdAbs(rel));
  const a = document.createElement('a');
  a.href = URL.createObjectURL(new Blob([data]));
  a.download = name;
  a.click();
  setTimeout(() => URL.revokeObjectURL(a.href), 10000);
}

async function sdDelete(rel, dir) {
  if (!confirm('Delete ' + (dir ? 'the folder /' + rel + ' and everything in it' : '/' + rel) + ' from the SD card?')) return;
  const FS = Module.FS;
  (function rm(abs, isDir) {
    if (isDir) {
      for (const n of FS.readdir(abs)) if (n !== '.' && n !== '..') rm(abs + '/' + n, FS.isDir(FS.stat(abs + '/' + n).mode));
      FS.rmdir(abs);
    } else FS.unlink(abs);
  })(sdAbs(rel), dir);
  await saveCard();
  sdRender();
}

async function sdNewDir() {
  const name = prompt('Name of the new folder in /' + sdDir);
  if (!name || !name.trim()) return;
  try { Module.FS.mkdirTree(sdAbs(sdDir) + '/' + safeName(name.trim())); } catch (e) { status('Could not make that folder.'); return; }
  await saveCard();
  sdRender();
}

function sdEnable() {
  for (const id of ['sdUpload', 'sdUploadDir']) $(id).setAttribute('aria-disabled', 'false');
  for (const id of ['sdFiles', 'sdDir', 'sdNewDir']) $(id).disabled = false;
  sdRender();
}

const CRC = (() => {
  const t = new Uint32Array(256);
  for (let n = 0; n < 256; n++) { let c = n; for (let k = 0; k < 8; k++) c = c & 1 ? 0xEDB88320 ^ (c >>> 1) : c >>> 1; t[n] = c >>> 0; }
  return t;
})();
function crc32(d) { let c = 0xFFFFFFFF; for (let i = 0; i < d.length; i++) c = CRC[(c ^ d[i]) & 0xFF] ^ (c >>> 8); return (c ^ 0xFFFFFFFF) >>> 0; }

// Stored (uncompressed) zip; books are already compressed. files: [{name, data: Uint8Array}].
function zip(files) {
  const enc = new TextEncoder(), parts = [], central = [];
  let offset = 0;
  for (const f of files) {
    const name = enc.encode(f.name), crc = crc32(f.data), size = f.data.length;
    const h = new DataView(new ArrayBuffer(30));
    h.setUint32(0, 0x04034b50, true); h.setUint16(4, 20, true); h.setUint16(6, 0x0800, true);  // UTF-8 names
    h.setUint16(12, 0x21, true);  // 1980-01-01
    h.setUint32(14, crc, true); h.setUint32(18, size, true); h.setUint32(22, size, true); h.setUint16(26, name.length, true);
    parts.push(h, name, f.data);
    const c = new DataView(new ArrayBuffer(46));
    c.setUint32(0, 0x02014b50, true); c.setUint16(4, 20, true); c.setUint16(6, 20, true); c.setUint16(8, 0x0800, true);
    c.setUint16(14, 0x21, true);
    c.setUint32(16, crc, true); c.setUint32(20, size, true); c.setUint32(24, size, true); c.setUint16(28, name.length, true);
    c.setUint32(42, offset, true);
    central.push(c, name);
    offset += 30 + name.length + size;
  }
  const csize = central.reduce((n, p) => n + p.byteLength, 0);
  const e = new DataView(new ArrayBuffer(22));
  e.setUint32(0, 0x06054b50, true); e.setUint16(8, files.length, true); e.setUint16(10, files.length, true);
  e.setUint32(12, csize, true); e.setUint32(16, offset, true);
  return new Blob([...parts, ...central, e], { type: 'application/zip' });
}

async function downloadCard() {
  await saveCard();
  const FS = Module.FS, root = cardDb(running), files = [];
  (function walk(dir, rel) {
    for (const n of FS.readdir(dir)) {
      if (n === '.' || n === '..') continue;
      const p = dir + '/' + n, st = FS.stat(p);
      if (FS.isDir(st.mode)) walk(p, rel + n + '/');
      else files.push({ name: rel + n, data: FS.readFile(p) });
    }
  })(root, '');
  const a = document.createElement('a');
  a.href = URL.createObjectURL(zip(files));
  a.download = 'sd-card-' + running.id + '.zip';
  a.click();
  setTimeout(() => URL.revokeObjectURL(a.href), 10000);
  status(files.length + ' files saved in ' + a.download + '.');
}

async function freshCard() {
  const b = current();
  if (!confirm('Erase the SD card of ' + b.name + ' ' + b.version + ' on ' + b.model + '?\nBooks, settings and reading progress on it are deleted.')) return;
  if (running && running.id === b.id) {
    location.assign('?' + new URLSearchParams({ b: b.id, battery: $('battery').value, usb: $('usb').checked ? '1' : '0', fresh: '1' }));
    return;
  }
  await deleteDb(cardDb(b));
  status('The SD card of ' + b.name + ' ' + b.version + ' on ' + b.model + ' is empty now.');
}

// ---- gestures (X4 Pro touchscreen): real mouse events on the canvas, as a hand-made drag ----
const sleep = ms => new Promise(r => setTimeout(r, ms));
const frameKeys = {};
// The screen hole inside a box of width x height showing the whole frame (page pixels or canvas pixels).
async function screenHole(width, height) {
  const b = running;
  if (!b || !b.frame) return null;
  if (!frameKeys[b.frame]) frameKeys[b.frame] = await (await fetch('frames/' + b.frame + '.keys')).text();
  const t = frameKeys[b.frame], num = re => (t.match(re) || []).slice(1).map(Number);
  const [W, H] = num(/^size (\d+) (\d+)/m), [x, y, w, h] = num(/^screen (\d+) (\d+) (\d+) (\d+)/m);
  if (!W || !w) return null;
  // the window turns with the reader (landscape): then the screen hole is turned a quarter to the right
  const turned = (width > height) !== (W > H);
  const r = turned ? { x: H - y - h, y: x, w: h, h: w, W: H, H: W } : { x, y, w, h, W, H };
  const sx = width / r.W, sy = height / r.H;
  return { left: r.x * sx, top: r.y * sy, width: r.w * sx, height: r.h * sy };
}
async function screenRect() {
  const c = $('canvas').getBoundingClientRect(), r = await screenHole(c.width, c.height);
  return r && { ...r, left: c.left + r.left, top: c.top + r.top };
}
// ---- screenshots: the canvas as a PNG, whole or cropped to the screen hole ----
async function screenshot(screenOnly) {
  const c = $('canvas');
  let x = 0, y = 0, w = c.width, h = c.height;
  if (screenOnly) {
    const r = await screenHole(c.width, c.height);
    if (!r) return status('This build has no frame, so the whole picture is the screen: use "whole reader".');
    x = Math.round(r.left); y = Math.round(r.top); w = Math.round(r.width); h = Math.round(r.height);
  }
  const out = document.createElement('canvas');
  out.width = w; out.height = h;
  out.getContext('2d').drawImage(c, x, y, w, h, 0, 0, w, h);
  out.toBlob(blob => {
    if (!blob) return status('Could not take the screenshot. Try again.');
    const a = document.createElement('a');
    a.href = URL.createObjectURL(blob);
    a.download = running.id + (screenOnly ? '-screen-' : '-reader-') + new Date().toISOString().slice(0, 19).replace(/[T:]/g, '-') + '.png';
    a.click();
    setTimeout(() => URL.revokeObjectURL(a.href), 10000);
    status('Saved ' + a.download + '.');
  }, 'image/png');
}

function mouse(type, x, y) {
  const opts = { clientX: x, clientY: y, screenX: x, screenY: y, button: 0, buttons: type === 'mouseup' ? 0 : 1, bubbles: true, cancelable: true, view: window };
  $('canvas').dispatchEvent(new MouseEvent(type, opts));
}
async function drag(x1, y1, x2, y2, ms) {
  mouse('mousemove', x1, y1);
  mouse('mousedown', x1, y1);
  const steps = Math.max(1, Math.round(ms / 16));
  for (let i = 1; i <= steps; i++) {
    await sleep(ms / steps);
    mouse('mousemove', x1 + (x2 - x1) * i / steps, y1 + (y2 - y1) * i / steps);
  }
  mouse('mouseup', x2, y2);
}
async function gesture(g) {
  const r = await screenRect();
  if (!r || running.model !== 'X4 Pro') return status('Gestures need a running X4 Pro (the only reader with a touchscreen).');
  const cx = r.left + r.width / 2, cy = r.top + r.height / 2, dx = r.width * 0.3, dy = r.height * 0.3;
  if (g === 'left') await drag(cx + dx, cy, cx - dx, cy, 250);
  else if (g === 'right') await drag(cx - dx, cy, cx + dx, cy, 250);
  else if (g === 'up') await drag(cx, cy + dy, cx, cy - dy, 250);
  else if (g === 'down') await drag(cx, r.top + 4, cx, r.top + r.height * 0.45, 300);
  else if (g === 'hold') await drag(cx, cy, cx, cy, 900);
  $('canvas').focus();
}
for (const el of document.querySelectorAll('#gestures button')) el.onclick = () => gesture(el.dataset.g);
// Shift + arrows / Enter make gestures; caught before the simulator so it does not also see the key
const GESTURE_KEYS = { ArrowLeft: 'left', ArrowRight: 'right', ArrowUp: 'up', ArrowDown: 'down', Enter: 'hold' };
for (const type of ['keydown', 'keyup']) {
  addEventListener(type, e => {
    if (!e.shiftKey || !GESTURE_KEYS[e.key] || e.target !== $('canvas') || !running) return;
    e.stopImmediatePropagation();
    e.preventDefault();
    if (type === 'keydown' && !e.repeat) gesture(GESTURE_KEYS[e.key]);
  }, true);
}

// ---- real size ----
// Real width and height of each frame in mm (size / px_per_mm in device-frames/frames/<model>.json).
const FRAME_MM = { 'x3': [66.66, 100.63], 'x4-classic': [72.05, 116.99], 'x4-pro': [71.94, 113.95] };
const CARD_MM = [53.98, 85.6];  // ID-1 card (bank card), held upright

function applyRealSize() {
  const b = running || current();
  const pxPerMm = store.get('pxPerMm', 0);  // CSS pixels per real mm on this screen, from Measure screen
  const mm = b && FRAME_MM[b.frame];
  const on = $('realSize').checked && pxPerMm && mm;
  $('stage').classList.toggle('real', !!on);
  if (!on) return;
  const c = $('canvas'), turned = running && c.width > c.height;  // the reader can be turned sideways
  $('stage').style.setProperty('--real-w', mm[turned ? 1 : 0] * pxPerMm + 'px');
}

function showCardBox() {
  const v = +$('cardScale').value;
  $('cardBox').style.width = CARD_MM[0] * v + 'px';
  $('cardBox').style.height = CARD_MM[1] * v + 'px';
  $('cardBox').style.borderRadius = 3.18 * v + 'px';  // ID-1 corner radius
}

function measure() {
  $('cardScale').value = store.get('pxPerMm', 96 / 25.4);  // start from the browser's own (often wrong) mm
  showCardBox();
  $('measureDlg').showModal();
}

function measureClosed(ok) {
  if (ok) {
    store.set('pxPerMm', +$('cardScale').value);
    $('realSize').checked = true;
    store.set('realSize', true);
  } else if (!store.get('pxPerMm', 0)) {
    $('realSize').checked = false;
  }
  $('measureDlg').close();
  applyRealSize();
}

// ---- about ----
function credits() {
  const repos = firmwareList();
  const versionsOf = r => [...new Map(builds.filter(x => x.repo === r.repo).map(x => [x.ref, x.version])).values()];
  $('aboutStats').replaceChildren(...[[repos.length, 'firmwares'], [new Set(builds.map(x => x.repo + '@' + x.ref)).size, 'versions'],
    [new Set(builds.map(x => x.model)).size, 'readers']].map(([n, what]) => {
    const el = document.createElement('span');
    el.innerHTML = '<b></b> ';
    el.firstChild.textContent = n;
    el.append(what);
    return el;
  }));
  $('fwCredits').replaceChildren(...repos.map(r => {
    const li = document.createElement('li');
    li.innerHTML = '<div class="fw-main"><a target="_blank" rel="noopener noreferrer"></a><span class="fw-by"></span></div>' +
      '<div class="fw-versions"></div><div class="fw-meta"><span class="lic"></span><a class="fw-lic">Licence</a></div>';
    const name = li.querySelector('a');
    name.href = 'https://github.com/' + r.repo;
    name.textContent = r.name;
    li.querySelector('.fw-by').textContent = 'by ' + r.repo.split('/')[0] + ' and contributors';
    li.querySelector('.fw-versions').replaceChildren(...versionsOf(r).map(v => {
      const c = document.createElement('span');
      c.className = 'vchip';
      c.textContent = v;
      return c;
    }));
    li.querySelector('.lic').textContent = r.licence;
    li.querySelector('.fw-lic').href = 'builds/' + r.id + '/LICENSE-firmware.txt';
    return li;
  }));
}

function showView() {
  const about = location.hash === '#about';
  $('sim').hidden = about;
  $('about').hidden = !about;
  for (const a of document.querySelectorAll('.top nav a')) a.classList.toggle('on', (a.dataset.view === 'about') === about);
}

// ---- wiring ----
$('battery').value = params.get('battery') || store.get('battery', 80);
$('usb').checked = (params.get('usb') || String(store.get('usb', 0))) === '1';
$('batteryOut').value = $('battery').value + ' %';
$('battery').oninput = () => { $('batteryOut').value = $('battery').value + ' %'; store.set('battery', +$('battery').value); render(); };
$('usb').onchange = () => { store.set('usb', $('usb').checked ? 1 : 0); render(); };
$('start').onclick = start;
$('bookFiles').onchange = e => addBooks([...e.target.files]);
$('download').onclick = downloadCard;
$('shotReader').onclick = () => screenshot(false);
$('shotScreen').onclick = () => screenshot(true);
$('fresh').onclick = freshCard;
$('sdFiles').onchange = e => { sdUpload([...e.target.files]); e.target.value = ''; };
$('sdDir').onchange = e => { sdUpload([...e.target.files]); e.target.value = ''; };
$('sdNewDir').onclick = sdNewDir;
for (const ev of ['dragenter', 'dragover']) $('sd').addEventListener(ev, e => {
  if (!running) return;
  e.preventDefault(); $('sd').classList.add('drop');
});
$('sd').addEventListener('dragleave', e => { if (!$('sd').contains(e.relatedTarget)) $('sd').classList.remove('drop'); });
$('sd').addEventListener('drop', e => {
  e.preventDefault(); $('sd').classList.remove('drop');
  if (running && e.dataTransfer.files.length) sdUpload([...e.dataTransfer.files]);
});
$('realSize').checked = !!store.get('realSize', false) && !!store.get('pxPerMm', 0);
$('realSize').onchange = () => {
  store.set('realSize', $('realSize').checked);
  if ($('realSize').checked && !store.get('pxPerMm', 0)) measure();
  applyRealSize();
};
$('measure').onclick = measure;
$('cardScale').oninput = showCardBox;
$('smaller').onclick = () => { $('cardScale').stepDown(10); showCardBox(); };
$('bigger').onclick = () => { $('cardScale').stepUp(10); showCardBox(); };
$('measureDone').onclick = () => measureClosed(true);
$('measureCancel').onclick = () => measureClosed(false);
$('measureDlg').oncancel = e => { e.preventDefault(); measureClosed(false); };  // Esc
new MutationObserver(applyRealSize).observe($('canvas'), { attributes: true, attributeFilter: ['width', 'height'] });
addEventListener('hashchange', showView);
addEventListener('pagehide', () => { saveCard(); });
document.addEventListener('visibilitychange', () => { if (document.hidden) saveCard(); });
showView();

// A version is named by its release (v1.8.1-yacp.9 -> 1.8.1-yacp.9): the number inside the source is often not
// updated between releases. A build from a branch is named by the branch, with that number: dev (2.3.6).
const versionLabel = b => /^v?\d/.test(b.ref) ? b.ref.replace(/^v(?=\d)/, '') : b.version && b.version !== b.ref ? b.ref + ' (' + b.version + ')' : b.ref;

fetch('builds.json').then(r => r.json()).then(j => {
  builds = j.builds;
  for (const b of builds) b.version = versionLabel(b);
  const b = builds.find(x => x.id === params.get('b'));
  if (b) sel = { model: b.model, repo: b.repo, ref: b.ref };
  // a fresh visit opens on VARAGH, newest version, on the device used last (normalise() falls back when the
  // device has no VARAGH build); a running build keeps its own choice
  else sel = { model: sel.model, repo: FIRST[0] };
  render();
  credits();
  if (b) boot(b);
}).catch(() => status('Could not load the list of builds.'));
