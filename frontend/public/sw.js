// tactic11 PWA service worker — v3
// Strateji:
//   - App shell (HTML/JS/CSS/font): cache-first, network ile arka plan refresh
//   - JSON API (/admin/*, /matches/*): stale-while-revalidate (offline'da
//     son snapshot okunur)
//   - Navigasyon (HTML doc): network-first, offline'da /offline-shell.html fallback
//   - Diğer GET: network-first cache fallback (eski davranış)
const CACHE = "tactic11-v3";
const OFFLINE_URL = "/offline-shell.html";

// İlk kurulumda app shell'i precache
const PRECACHE = [
  "/",
  OFFLINE_URL,
  "/manifest.webmanifest",
  "/icon.svg",
];

self.addEventListener("install", (e) => {
  self.skipWaiting();
  e.waitUntil(
    caches.open(CACHE).then((c) => c.addAll(PRECACHE).catch(() => {})),
  );
});

self.addEventListener("activate", (e) =>
  e.waitUntil(
    (async () => {
      const keys = await caches.keys();
      await Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k)));
      await self.clients.claim();
    })(),
  ),
);

function isApiRequest(url) {
  return (
    url.pathname.startsWith("/admin/")
    || url.pathname.startsWith("/matches/")
    || url.pathname.startsWith("/teams/")
    || url.pathname.startsWith("/players/")
  );
}

function isAssetRequest(req, url) {
  return (
    req.destination === "script"
    || req.destination === "style"
    || req.destination === "font"
    || req.destination === "image"
    || url.pathname.startsWith("/_next/")
  );
}

async function staleWhileRevalidate(req) {
  const cache = await caches.open(CACHE);
  const cached = await cache.match(req);
  const network = fetch(req)
    .then((res) => {
      if (res.ok) cache.put(req, res.clone()).catch(() => {});
      return res;
    })
    .catch(() => cached || Response.error());
  return cached || network;
}

async function cacheFirst(req) {
  const cache = await caches.open(CACHE);
  const cached = await cache.match(req);
  if (cached) {
    // Arka planda yenile
    fetch(req).then((res) => {
      if (res.ok) cache.put(req, res.clone()).catch(() => {});
    }).catch(() => {});
    return cached;
  }
  try {
    const res = await fetch(req);
    if (res.ok) cache.put(req, res.clone()).catch(() => {});
    return res;
  } catch (err) {
    return Response.error();
  }
}

async function networkFirstWithOffline(req) {
  try {
    const res = await fetch(req);
    const cache = await caches.open(CACHE);
    if (res.ok) cache.put(req, res.clone()).catch(() => {});
    return res;
  } catch (err) {
    const cache = await caches.open(CACHE);
    const cached = await cache.match(req);
    if (cached) return cached;
    if (req.mode === "navigate") {
      const offline = await cache.match(OFFLINE_URL);
      if (offline) return offline;
    }
    return Response.error();
  }
}

self.addEventListener("fetch", (e) => {
  if (e.request.method !== "GET") return;
  const url = new URL(e.request.url);
  // Sadece same-origin
  if (url.origin !== self.location.origin) return;

  if (isApiRequest(url)) {
    e.respondWith(staleWhileRevalidate(e.request));
    return;
  }
  if (isAssetRequest(e.request, url)) {
    e.respondWith(cacheFirst(e.request));
    return;
  }
  e.respondWith(networkFirstWithOffline(e.request));
});
