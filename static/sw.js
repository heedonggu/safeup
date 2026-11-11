// 오프라인 재생: 앱 화면은 네트워크 우선·실패 시 저장본, '오프라인 저장'한 교육 자료는 저장본에서 구간(Range) 응답까지 만들어 준다.
const SHELL = 'safeclip-shell', DATA = 'safeclip-offline';
self.addEventListener('install', e => e.waitUntil(caches.open(SHELL).then(c => c.addAll(['app.html', 'assets/product.js', 'assets/extra.js', 'assets/style.css'])).then(() => self.skipWaiting())));
self.addEventListener('activate', e => e.waitUntil(self.clients.claim()));

async function fromCache(req) {
  const url = new URL(req.url), key = url.pathname.replace(/^.*?\/api\//, 'api/') + url.search;
  const hit = await (await caches.open(DATA)).match(key);
  if (!hit) return null;
  const range = req.headers.get('range');
  if (!range) return hit;
  const buf = await hit.arrayBuffer(), m = /bytes=(\d*)-(\d*)/.exec(range);
  const start = m[1] ? +m[1] : Math.max(0, buf.byteLength - +m[2]), end = m[1] && m[2] ? Math.min(+m[2], buf.byteLength - 1) : buf.byteLength - 1;
  return new Response(buf.slice(start, end + 1), { status: 206, headers: { 'Content-Type': hit.headers.get('Content-Type') || 'video/mp4', 'Content-Range': `bytes ${start}-${end}/${buf.byteLength}`, 'Accept-Ranges': 'bytes' } });
}

self.addEventListener('fetch', e => {
  const req = e.request, url = new URL(req.url);
  if (req.method !== 'GET' || url.origin !== location.origin) return;
  if (url.pathname.includes('/api/')) {
    e.respondWith(fetch(req).catch(async () => (await fromCache(req)) || new Response('{"error":"오프라인입니다."}', { status: 503, headers: { 'Content-Type': 'application/json' } })));
    return;
  }
  if (/\/(app\.html|assets\/(product\.js|extra\.js|style\.css))$/.test(url.pathname)) {
    e.respondWith(fetch(req).then(r => { const c = r.clone(); caches.open(SHELL).then(x => x.put(req, c)); return r; }).catch(() => caches.match(req, { ignoreSearch: true })));
  }
});
