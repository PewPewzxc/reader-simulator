// Headless check of the browser simulator: real mouse clicks (Chrome DevTools protocol), pictures, timings.
//   node test_page.mjs [url]   (Chrome must be running with --remote-debugging-port=9333)
// Writes shots/*.png and prints the simulator's log lines that mention activities.
import fs from 'node:fs';

const url = process.argv[2] || 'http://127.0.0.1:8765/';
const list = await (await fetch('http://127.0.0.1:9333/json/list')).json();
const page = list.find(t => t.type === 'page');
const ws = new WebSocket(page.webSocketDebuggerUrl);
await new Promise(r => ws.addEventListener('open', r));
let id = 0;
const waiting = new Map();
const log = [];
const workers = [];  // pthread workers (FreeRTOS tasks), for PAUSE stacks
ws.addEventListener('message', ev => {
  const m = JSON.parse(ev.data);
  if (m.id && waiting.has(m.id)) { waiting.get(m.id)(m.result); waiting.delete(m.id); }
  if (m.method === 'Debugger.paused') {
    console.log('paused', m.sessionId ? 'worker ' + m.sessionId.slice(0, 6) : 'main', ':',
      m.params.callFrames.map(f => f.functionName).filter(n => n).slice(0, 16).join(' < '));
  }
  if (m.method === 'Target.attachedToTarget') workers.push(m.params.sessionId);
  if (m.method === 'Runtime.consoleAPICalled') {
    log.push([Date.now(), m.params.args.map(a => a.value).join(' ')]);
    if (process.env.LIVE) fs.appendFileSync('logs/live.log', (Date.now() % 1000000) + ' ' + log.at(-1)[1] + '\n');
  }
});
const send = (method, params = {}) => new Promise(r => { const i = ++id; waiting.set(i, r); ws.send(JSON.stringify({ id: i, method, params })); });
const sleep = ms => new Promise(r => setTimeout(r, ms));
const shot = async name => {
  if (process.env.LIVE) fs.appendFileSync('logs/live.log', 'SHOT ' + name + '\n');
  const r = await send('Page.captureScreenshot', { format: 'png' });
  fs.writeFileSync(`shots/${name}.png`, Buffer.from(r.data, 'base64'));
};
// frame picture point (620x982 x4-pro frame) -> page point
let box;
const click = async (fx, fy, hold = 150) => {
  const x = box.x + fx * box.w / 620, y = box.y + fy * box.h / 982;
  await send('Input.dispatchMouseEvent', { type: 'mouseMoved', x, y });
  await send('Input.dispatchMouseEvent', { type: 'mousePressed', x, y, button: 'left', clickCount: 1 });
  await sleep(hold);
  await send('Input.dispatchMouseEvent', { type: 'mouseReleased', x, y, button: 'left', clickCount: 1 });
};

await send('Runtime.enable');
await send('Page.enable');
if (process.argv[3] === 'book') await send('Debugger.enable');
if (process.env.PAUSE) await send('Target.setAutoAttach', { autoAttach: true, waitForDebuggerOnStart: false, flatten: true });
await send('Emulation.setDeviceMetricsOverride', { width: 660, height: 1030, deviceScaleFactor: 1, mobile: false });
await send('Network.enable');
await send('Network.clearBrowserCache');
if (process.env.MBPS) await send('Network.emulateNetworkConditions', { offline: false, latency: 40, downloadThroughput: process.env.MBPS * 125000, uploadThroughput: 1250000 });  // MBPS=20: a typical home line
const t0 = Date.now();
await send('Page.navigate', { url });
let home = 0;
while (!home && Date.now() - t0 < 60000) {
  await sleep(100);
  home = log.find(l => l[0] > t0 && l[1].includes('Entering activity: Home'))?.[0] || 0;
}
console.log('home screen after', home ? home - t0 : 'never', 'ms');
box = (await send('Runtime.evaluate', { expression: 'JSON.stringify((r => ({x: r.left, y: r.top, w: r.width, h: r.height}))(Module.canvas.getBoundingClientRect()))', returnByValue: true })).result.value;
box = JSON.parse(box);
await sleep(1500);
await shot('1-home');
if (process.argv[3] === 'book') {  // put a book on the SD card, open Browse Files, open the book
  const book = process.env.BOOK || 'english';  // testbooks/<name>.epub; the SD card keeps only this one
  await send('Runtime.evaluate', { expression: `fetch('testbooks/${book}.epub').then(r => r.arrayBuffer()).then(b => { try { FS.mkdir('/sd/books') } catch (e) {} for (const f of FS.readdir('/sd/books')) if (f[0] !== '.') FS.unlink('/sd/books/' + f); FS.writeFile('/sd/books/${book}.epub', new Uint8Array(b)); })`, awaitPromise: true });
  await click(200, 400);  // Browse Files
  await sleep(2000);
  await shot('b1-files');
  await click(300, 195);  // first entry: books/
  await sleep(2000);
  await shot('b2-entry');
  await click(300, 195);  // first book
  await sleep(8000);
  if (process.env.PAUSE) {
    let n = 99990;
    for (const w of workers) { ws.send(JSON.stringify({ id: --n, method: 'Debugger.enable', sessionId: w })); ws.send(JSON.stringify({ id: --n, method: 'Debugger.pause', sessionId: w })); }
    ws.send(JSON.stringify({ id: 99999, method: 'Debugger.pause' }));
    await sleep(6000);
    console.log(workers.length, 'workers');
    process.exit(0);
  }
  await shot('b3-book');
  for (const [t, l] of log) if (t > t0) console.log(t - t0, String(l).slice(0, 160));
  process.exit(0);
}
await click(596, 298);            // DOWN key on the frame
await sleep(1200);
await shot('2-after-down-key');
await click(195, 710);            // touch "Settings" on the screen
await sleep(2000);
await shot('3-after-touch-settings');
await click(310, 925);            // HOME key
await sleep(2000);
await shot('4-after-home-key');
await click(596, 128, 1500);      // POWER key held: sleep
await sleep(4000);
await shot('5-asleep');
await click(596, 128, 1500);      // POWER again: wake (the page reloads, like the reader restarting)
await sleep(6000);
await shot('6-awake');
const mem = (await send('Runtime.evaluate', { expression: 'performance.memory ? performance.memory.usedJSHeapSize : 0', returnByValue: true })).result.value;
console.log('JS heap', mem);
for (const [t, l] of log) if (t > t0) if (/ACT|SIM FRAME|rror|Wake|SLEEP|sleep/.test(l)) console.log(t - t0, l);
ws.close();
