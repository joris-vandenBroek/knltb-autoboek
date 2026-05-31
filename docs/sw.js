const CACHE = 'padel-v34';
// index.html en manifest altijd network-first zodat updates direct zichtbaar zijn
const NETWORK_FIRST = ['/', '/index.html', '/manifest.json'];
const CACHE_FIRST   = ['/sw.js', '/logo.png', '/icon-192.png', '/icon-512.png'];
// JSON-payloads die altijd vers moeten zijn (worden ge-cache-bust via ?t=)
const ALTIJD_VERS_JSON = ['leden.json', 'reserveringen.json'];

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

  // Altijd vers: alle JSON-payloads (leden, reserveringen) + GitHub API.
  // Geen cache-hit ooit serveren — anders zie je na een annulering nog
  // steeds de oude reserveringen-lijst.
  // `cache: 'no-store'` omzeilt ook GitHub raw cdn cache die ?t=...
  // querystrings soms negeert als cache-key.
  if (ALTIJD_VERS_JSON.some(n => url.includes(n)) || url.includes('api.github.com')) {
    e.respondWith(
      fetch(e.request, { cache: 'no-store' }).catch(() => caches.match(e.request))
    );
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
