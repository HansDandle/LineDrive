// Network-first: always show the live app, fall back to the cached shell when offline.
// (Cache-first served a stale home page forever after the first install.)
const CACHE = 'linedrive-v2';
const SHELL = ['/', '/static/style.css', '/static/js/app.js', '/static/manifest.json'];

self.addEventListener('install', (e) => {
  e.waitUntil(caches.open(CACHE).then((cache) => cache.addAll(SHELL)));
  self.skipWaiting();
});

self.addEventListener('activate', (e) => {
  e.waitUntil(
    caches.keys()
      .then((keys) => Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k))))
      .then(() => self.clients.claim())
  );
});

self.addEventListener('fetch', (e) => {
  if (e.request.method !== 'GET') return;
  e.respondWith(
    fetch(e.request)
      .then((resp) => {
        const url = new URL(e.request.url);
        if (resp.ok && SHELL.includes(url.pathname)) {
          const copy = resp.clone();
          caches.open(CACHE).then((cache) => cache.put(url.pathname, copy));
        }
        return resp;
      })
      .catch(() => caches.match(new URL(e.request.url).pathname))
  );
});
