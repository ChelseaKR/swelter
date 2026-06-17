// Minimal service worker: cache the app shell so the dashboard installs as a PWA and opens
// offline at a tenant meeting or a council hearing where there is no signal. The cached
// sample surface means it renders something useful even with no network and no server.
const CACHE = "swelter-shell-v1";
const SHELL = [
  ".",
  "index.html",
  "styles.css",
  "app.js",
  "manifest.webmanifest",
  "icon.svg",
  "i18n/en.json",
  "i18n/es.json",
  "sample-surface.json",
];

self.addEventListener("install", (event) => {
  event.waitUntil(caches.open(CACHE).then((cache) => cache.addAll(SHELL)));
  self.skipWaiting();
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k))),
    ),
  );
  self.clients.claim();
});

self.addEventListener("fetch", (event) => {
  if (event.request.method !== "GET") return;
  // Network-first for live API reads, cache-first for the static shell.
  if (event.request.url.includes("/api/") || event.request.url.includes("/export")) {
    event.respondWith(fetch(event.request).catch(() => caches.match(event.request)));
    return;
  }
  event.respondWith(
    caches.match(event.request).then((hit) => hit || fetch(event.request)),
  );
});
