// Adds the two headers WebAssembly threads need (COOP/COEP) on hosts that cannot set headers
// (GitHub Pages). Same idea as the coi-serviceworker project, written here so nothing third-party ships.
self.addEventListener('install', () => self.skipWaiting());
self.addEventListener('activate', e => e.waitUntil(self.clients.claim()));
self.addEventListener('fetch', e => {
  const req = e.request;
  if (req.cache === 'only-if-cached' && req.mode !== 'same-origin') return;
  // The page itself (HTML, scripts, styles, lists) is asked for fresh every time, so an update shows at once
  // instead of after the browser's cache runs out (GitHub Pages: 10 minutes; longer on phones). Unchanged files
  // cost a quick "not modified". The firmware builds (sim.js, sim.wasm) and the rest keep normal caching.
  const url = new URL(req.url);
  const fresh = url.origin === location.origin && (req.mode === 'navigate' || /\.(html|css|json|keys)$|\/$|\/assets\/[^/]+\.js$/.test(url.pathname));
  e.respondWith(fetch(req, fresh ? { cache: 'no-cache' } : undefined).then(res => {
    if (res.status === 0) return res;
    const headers = new Headers(res.headers);
    headers.set('Cross-Origin-Opener-Policy', 'same-origin');
    headers.set('Cross-Origin-Embedder-Policy', 'require-corp');
    headers.set('Cross-Origin-Resource-Policy', 'same-origin');
    return new Response(res.body, { status: res.status, statusText: res.statusText, headers });
  }));
});
