// Where is every simulator thread right now? Pauses each worker (FreeRTOS task = pthread) and prints its stack.
//   node probe.mjs   (Chrome with --remote-debugging-port=9333, simulator page open; build with --profiling-funcs)
const ver = await (await fetch('http://127.0.0.1:9333/json/version')).json();
const ws = new WebSocket(ver.webSocketDebuggerUrl);
await new Promise(r => ws.addEventListener('open', r));
let id = 0;
const waiting = new Map();
ws.addEventListener('message', ev => {
  const m = JSON.parse(ev.data);
  if (m.id && waiting.has(m.id)) { waiting.get(m.id)(m.result || m.error); waiting.delete(m.id); }
  if (m.method === 'Debugger.paused') {
    const names = m.params.callFrames.map(f => f.functionName).filter(n => n).slice(0, 14);
    console.log('--', m.sessionId.slice(0, 6), names.join(' < '));
  }
});
const send = (method, params = {}, sessionId) => new Promise(r => {
  const i = ++id; waiting.set(i, r); ws.send(JSON.stringify({ id: i, method, params, sessionId }));
  setTimeout(() => r('TIMEOUT'), 4000);
});
const { targetInfos } = await send('Target.getTargets', { filter: [{}] });
const page = targetInfos.find(t => t.type === 'page' && t.url.startsWith('http://127.0.0.1:8765'));
const { sessionId } = await send('Target.attachToTarget', { targetId: page.targetId, flatten: true });
ws.addEventListener('message', async ev => {
  const m = JSON.parse(ev.data);
  if (m.method === 'Target.attachedToTarget' && m.params.targetInfo.type === 'worker') {
    const s = m.params.sessionId;
    await send('Debugger.enable', {}, s);
    send('Debugger.pause', {}, s);
  }
});
console.log('auto-attach:', JSON.stringify(await send('Target.setAutoAttach', { autoAttach: true, waitForDebuggerOnStart: false, flatten: true }, sessionId)));
setTimeout(() => process.exit(0), 10000);
