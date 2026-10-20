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
const current = () => builds.find(b => b.repo === sel.repo && b.model === sel.model && b.ref === sel.ref);
const settings = () => $('battery').value + '/' + ($('usb').checked ? 1 : 0);
const mb = n => (n / 1e6).toFixed(1) + ' MB';

// ---- choosing a build ----
function normalise() {
  if (!builds.some(b => b.model === sel.model)) sel.model = 'X4 Pro';
  if (!builds.some(b => b.model === sel.model)) sel.model = builds[0].model;
  if (!builds.some(b => b.repo === sel.repo && b.model === sel.model)) {
    const pick = builds.find(b => b.repo === 'PewPewzxc/VARAGH' && b.model === sel.model) || builds.find(b => b.model === sel.model);
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
  const repos = [...new Map(builds.map(x => [x.repo, x])).values()];
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
  const restart = sessionStorage.getItem('simRestartEnv');  // set by the simulator on sleep/wake or reboot
  sessionStorage.removeItem('simRestartEnv');
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
      setInterval(saveCard, 5000);
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
  for (const f of list.files) {
    const dest = root + '/' + f.path;
    if (FS.analyzePath(dest).exists) continue;
    const r = await fetch('samples/' + f.path.split('/').map(encodeURIComponent).join('/'));
    if (!r.ok) throw new Error(f.path + ': ' + r.status);
    FS.mkdirTree(dest.slice(0, dest.lastIndexOf('/')));
    FS.writeFile(dest, new Uint8Array(await r.arrayBuffer()));
  }
  FS.writeFile(mark, 'sample books and dictionary added\n');
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
  status(files.length + ' book' + (files.length === 1 ? '' : 's') + ' added to the books folder. Open Browse Files on the reader.');
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
async function screenRect() {
  const b = running;
  if (!b || !b.frame) return null;
  if (!frameKeys[b.frame]) frameKeys[b.frame] = await (await fetch('frames/' + b.frame + '.keys')).text();
  const t = frameKeys[b.frame], num = re => (t.match(re) || []).slice(1).map(Number);
  const [W, H] = num(/^size (\d+) (\d+)/m), [x, y, w, h] = num(/^screen (\d+) (\d+) (\d+) (\d+)/m);
  const c = $('canvas').getBoundingClientRect();
  if (!W || !w) return null;
  // the window turns with the reader (landscape): then the screen hole is turned a quarter to the right
  const turned = (c.width > c.height) !== (W > H);
  const r = turned ? { x: H - y - h, y: x, w: h, h: w, W: H, H: W } : { x, y, w, h, W, H };
  const sx = c.width / r.W, sy = c.height / r.H;
  return { left: c.left + r.x * sx, top: c.top + r.y * sy, width: r.w * sx, height: r.h * sy };
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

// ---- about ----
function credits() {
  const repos = [...new Map(builds.map(x => [x.repo, x])).values()];
  $('fwCredits').replaceChildren(...repos.map(r => {
    const li = document.createElement('li');
    const a = document.createElement('a');
    a.href = 'https://github.com/' + r.repo;
    a.textContent = r.name;
    const versions = [...new Set(builds.filter(x => x.repo === r.repo).map(x => x.ref))].join(', ');
    li.append(a, ' by ' + r.repo.split('/')[0] + ' and contributors (' + r.repo + ', ' + versions + '), licence ' + r.licence +
      '. Each build includes its licence: ');
    const l = document.createElement('a');
    l.href = 'builds/' + r.id + '/LICENSE-firmware.txt';
    l.textContent = 'LICENSE';
    li.append(l);
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
$('fresh').onclick = freshCard;
addEventListener('hashchange', showView);
addEventListener('pagehide', () => { saveCard(); });
document.addEventListener('visibilitychange', () => { if (document.hidden) saveCard(); });
showView();

fetch('builds.json').then(r => r.json()).then(j => {
  builds = j.builds;
  const b = builds.find(x => x.id === params.get('b'));
  if (b) sel = { model: b.model, repo: b.repo, ref: b.ref };
  render();
  credits();
  if (b) boot(b);
}).catch(() => status('Could not load the list of builds.'));
