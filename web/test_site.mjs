// Tests the assembled site (../site/preview served by serve_plain.py, no special headers, like GitHub Pages)
// in headless Chrome (--remote-debugging-port=9333): every build boots to its home screen and a click on a
// drawn key changes the screen; then the page controls. Writes shots/site-*.png and logs/site-test.json.
//   node test_site.mjs [base url] [build ids...]
import fs from 'node:fs';
import path from 'node:path';

const base = process.argv[2] || 'http://127.0.0.1:8766/reader-simulator/';
const only = process.argv.slice(3);
const sleep = ms => new Promise(r => setTimeout(r, ms));
const builds = (await (await fetch(base + 'builds.json')).json()).builds.filter(b => !only.length || only.includes(b.id));

async function open() {
  const t = await (await fetch('http://127.0.0.1:9333/json/new?about:blank', { method: 'PUT' })).json();
  const ws = new WebSocket(t.webSocketDebuggerUrl);
  await new Promise(r => ws.addEventListener('open', r));
  let id = 0;
  const waiting = new Map(), log = [], s = { ws, log, target: t.id };
  ws.addEventListener('message', ev => {
    const m = JSON.parse(ev.data);
    if (m.id && waiting.has(m.id)) { waiting.get(m.id)(m.result || m.error); waiting.delete(m.id); }
    if (m.method === 'Runtime.consoleAPICalled') log.push([Date.now(), m.params.args.map(a => a.value).join(' ')]);
    if (m.method === 'Runtime.exceptionThrown') log.push([Date.now(), 'EXCEPTION ' + JSON.stringify(m.params.exceptionDetails.exception?.description || m.params.exceptionDetails.text)]);
    if (m.method === 'Page.javascriptDialogOpening') s.send('Page.handleJavaScriptDialog', { accept: true });
  });
  s.send = (method, params = {}) => new Promise(r => { const i = ++id; waiting.set(i, r); ws.send(JSON.stringify({ id: i, method, params })); setTimeout(() => r({ timeout: true }), 15000); });
  s.eval = async expr => (await s.send('Runtime.evaluate', { expression: expr, returnByValue: true, awaitPromise: true })).result?.value;
  s.shot = async name => { const r = await s.send('Page.captureScreenshot', { format: 'png' }); if (r.data) fs.writeFileSync(`shots/site-${name}.png`, Buffer.from(r.data, 'base64')); return r.data || ''; };
  s.waitLog = async (re, since, ms) => { const end = Date.now() + ms; while (Date.now() < end) { const l = log.find(x => x[0] >= since && re.test(x[1])); if (l) return l[0]; await sleep(100); } return 0; };
  s.close = async () => { ws.close(); await fetch('http://127.0.0.1:9333/json/close/' + t.id); };
  await s.send('Runtime.enable'); await s.send('Page.enable'); await s.send('Network.enable');
  await s.send('Emulation.setDeviceMetricsOverride', { width: 1280, height: 1000, deviceScaleFactor: 1, mobile: false });
  return s;
}

async function clickKey(s, b, key) {
  const keys = await (await fetch(base + 'frames/' + b.frame + '.keys')).text();
  const size = keys.match(/size (\d+) (\d+)/).slice(1).map(Number);
  const k = keys.split('\n').find(l => l.startsWith('key ' + key + ' ')).split(' ').slice(2).map(Number);
  const box = JSON.parse(await s.eval('JSON.stringify(document.getElementById("canvas").getBoundingClientRect())'));
  const x = box.x + (k[0] + k[2] / 2) * box.width / size[0], y = box.y + (k[1] + k[3] / 2) * box.height / size[1];
  await s.send('Input.dispatchMouseEvent', { type: 'mouseMoved', x, y });
  await s.send('Input.dispatchMouseEvent', { type: 'mousePressed', x, y, button: 'left', clickCount: 1 });
  await sleep(150);
  await s.send('Input.dispatchMouseEvent', { type: 'mouseReleased', x, y, button: 'left', clickCount: 1 });
}

const results = [];
let first = true;
for (const b of builds) {
  const s = await open();
  await s.send('Network.clearBrowserCache');
  const t0 = Date.now();
  await s.send('Page.navigate', { url: base + '?b=' + b.id + '&battery=40&usb=0' });
  // first run of the session: coi-sw.js installs and the page reloads once
  const booted = await s.waitLog(/Entering activity|\[ACT\]|Home/, t0, 60000);
  const homeAt = await s.waitLog(/Entering activity: (Home|Lyra|.*Home)/, t0, booted ? 8000 : 1);
  await sleep(2500);
  const before = await s.shot(b.id + '-1');
  await clickKey(s, b, 'DOWN');
  await sleep(1500);
  const after = await s.shot(b.id + '-2');
  let wake = null;
  if (process.env.SLEEP) {  // hold POWER (sleep), click POWER (wake = page reload), wait for the new boot
    await clickKey(s, b, 'POWER').then(() => sleep(1)); // short press first closes menus on some firmwares
    const ts = Date.now();
    await s.send('Input.dispatchMouseEvent', { type: 'mouseMoved', x: 0, y: 0 });
    const keys = await (await fetch(base + 'frames/' + b.frame + '.keys')).text();
    const size = keys.match(/size (\d+) (\d+)/).slice(1).map(Number);
    const k = keys.split('\n').find(l => l.startsWith('key POWER ')).split(' ').slice(2).map(Number);
    const box = JSON.parse(await s.eval('JSON.stringify(document.getElementById("canvas").getBoundingClientRect())'));
    const x = box.x + (k[0] + k[2] / 2) * box.width / size[0], y = box.y + (k[1] + k[3] / 2) * box.height / size[1];
    await s.send('Input.dispatchMouseEvent', { type: 'mousePressed', x, y, button: 'left', clickCount: 1 });
    await sleep(2000);
    await s.send('Input.dispatchMouseEvent', { type: 'mouseReleased', x, y, button: 'left', clickCount: 1 });
    const slept = await s.waitLog(/deep sleep|Entering activity: Sleep/i, ts, 8000);
    await sleep(2500);
    await s.shot(b.id + '-sleep');
    const tw = Date.now();
    await clickKey(s, b, 'POWER');
    const woke = await s.waitLog(/Wake route: PowerButton|WAKE|wake/i, tw, 15000);
    await sleep(3000);
    await s.shot(b.id + '-woke');
    wake = { slept: !!slept, woke: !!woke };
  }
  const errors = s.log.filter(l => l[0] >= t0 && /EXCEPTION|Aborted|RuntimeError/.test(l[1])).map(l => l[1].slice(0, 200));
  const r = { id: b.id, boot_ms: booted ? booted - t0 : null, home_ms: homeAt ? homeAt - t0 : null,
    key_changes_screen: before !== after && after.length > 0, first_visit: first, wake, errors };
  results.push(r);
  console.log(JSON.stringify(r));
  first = false;
  await s.close();
}

// page controls, on the first build
if (!only.length || process.env.CONTROLS) {
  const b = builds[0];
  const s = await open();
  const t0 = Date.now();
  await s.send('Page.navigate', { url: base + '?b=' + b.id });
  await s.waitLog(/Entering activity/, t0, 60000);
  await sleep(2000);
  const c = {};
  const doc = await s.send('DOM.getDocument');
  const input = await s.send('DOM.querySelector', { nodeId: doc.root.nodeId, selector: '#bookFiles' });
  await s.send('DOM.setFileInputFiles', { nodeId: input.nodeId, files: [path.resolve('testdata/english.epub')] });
  await sleep(1500);
  c.add_books = await s.eval(`Module.FS.readdir('/cards/${b.id}/fs_/books').includes('english.epub')`);
  const dl = path.resolve('logs/download');
  fs.rmSync(dl, { recursive: true, force: true });
  fs.mkdirSync(dl, { recursive: true });
  await s.send('Browser.setDownloadBehavior', { behavior: 'allow', downloadPath: dl });
  await s.eval(`document.getElementById('download').click()`);
  await sleep(3000);
  c.download = fs.readdirSync(dl);
  c.battery_env = await s.eval(`Module.ENV.VARAGH_SIM_BATTERY + '/' + Module.ENV.VARAGH_SIM_USB`);
  await s.eval(`document.getElementById('fresh').click()`);  // the confirm dialog is accepted above
  const t1 = Date.now();
  await s.waitLog(/Entering activity/, t1, 30000);
  await sleep(1500);
  c.fresh_card_books = await s.eval(`Module.FS.readdir('/cards/${b.id}/fs_/books').filter(n => n[0] !== '.')`);
  c.url_after_fresh = await s.eval('location.search');
  // choosing: X3 button then first firmware chip; Start label
  c.devices = await s.eval(`[...document.querySelectorAll('#devices button')].map(x => x.innerText.replace(/\\n/g, ' '))`);
  c.firmwares = await s.eval(`document.querySelectorAll('#firmwares .fw').length`);
  c.about_credits = await s.eval(`document.querySelectorAll('#fwCredits li').length`);
  await s.send('Emulation.setDeviceMetricsOverride', { width: 390, height: 844, deviceScaleFactor: 2, mobile: true });
  await sleep(1500);
  await s.shot('phone');
  c.phone_scroll_width = await s.eval('document.documentElement.scrollWidth');
  console.log('controls', JSON.stringify(c));
  results.push({ controls: c });
  await s.close();
}
fs.writeFileSync('logs/site-test.json', JSON.stringify(results, null, 1));
process.exit(0);
