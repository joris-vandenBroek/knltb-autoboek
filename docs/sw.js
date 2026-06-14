const CACHE = 'padel-v54';
const STATIC = ['/sw.js', '/logo.png', '/icon-192.png', '/icon-512.png'];

self.addEventListener('install', e => {
  e.waitUntil(caches.open(CACHE).then(c => c.addAll(STATIC)));
  self.skipWaiting();
});

self.addEventListener('activate', e => {
  e.waitUntil(caches.keys().then(keys =>
    Promise.all(keys.filter(k => k !== CACHE).map(k => caches.delete(k)))
  ));
  self.clients.claim();
});

self.addEventListener('fetch', e => {
  const url = e.request.url;

  // Statische assets: cache-first
  if (STATIC.some(p => url.endsWith(p))) {
    e.respondWith(
      caches.match(e.request).then(cached => cached || fetch(e.request))
    );
    return;
  }

  // index.html / manifest: network-first, fallback cache
  if (url.endsWith('/') || url.includes('/index.html') || url.includes('/manifest.json')) {
    e.respondWith(
      fetch(e.request).then(resp => {
        caches.open(CACHE).then(c => c.put(e.request, resp.clone()));
        return resp;
      }).catch(() => caches.match(e.request))
    );
    return;
  }

  // leden.json: cache-first (verandert zelden)
  if (url.includes('leden.json')) {
    e.respondWith(
      caches.match(e.request).then(cached => cached ||
        fetch(e.request).then(resp => {
          caches.open(CACHE).then(c => c.put(e.request, resp.clone()));
          return resp;
        })
      )
    );
    return;
  }

  // Al het andere (reserveringen, wachtrij, GitHub API): altijd netwerk
  e.respondWith(fetch(e.request));
});
