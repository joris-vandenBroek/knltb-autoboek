const CACHE = 'padel-v16';
// index.html en manifest altijd network-first zodat updates direct zichtbaar zijn
const NETWORK_FIRST = ['/', '/index.html', '/manifest.json'];
const CACHE_FIRST   = ['/sw.js', '/logo.png', '/icon-192.png', '/icon-512.png'];

self.addEventListener('install', e => {
  e.waitUntil(
    caches.open(CACHE).then(c => c.addAll(CACHE_FIRST))
  );
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

  // Altijd vers: leden.json en GitHub API
  if (url.includes('leden.json') || url.includes('api.github.com')) {
    e.respondWith(fetch(e.request).catch(() => caches.match(e.request)));
    return;
  }

  // index.html / manifest: network-first, fallback cache
  if (NETWORK_FIRST.some(p => url.endsWith(p))) {
    e.respondWith(
      fetch(e.request).then(resp => {
        const clone = resp.clone();
        caches.open(CACHE).then(c => c.put(e.request, clone));
        return resp;
      }).catch(() => caches.match(e.request))
    );
    return;
  }

  // Afbeeldingen/icons: cache-first
  e.respondWith(
    caches.match(e.request).then(cached => cached || fetch(e.request))
  );
});
