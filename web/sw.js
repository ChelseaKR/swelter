// Minimal service worker: cache the app shell so the dashboard installs as a PWA and opens
// offline at a tenant meeting or a council hearing where there is no signal. The cached
// sample surface means it renders something useful even with no network and no server.
const CACHE = "swelter-shell-v3";
const SHELL = [
  ".",
  "index.html",
  "styles.css",
  "app.js",
  "manifest.webmanifest",
  "icon-512.png",
  "icon.svg",
  "i18n/en.json",
  "i18n/es.json",
  "sample-surface.json",
];
// Static Pages builds add demo.json; live/local deployments may omit it. Cache
// the truth contract when present without letting a 404 abort installation of
// the core offline shell.
const OPTIONAL_SHELL = ["demo.json"];

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches.open(CACHE).then(async (cache) => {
      await cache.addAll(SHELL);
      await Promise.allSettled(OPTIONAL_SHELL.map((asset) => cache.add(asset)));
    }),
  );
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
  const url = event.request.url;

  // Live data: network-first, fall back to cache, then to a DEFINED offline response. Returning
  // undefined to respondWith would surface a raw browser error page.
  if (url.includes("/api/") || url.includes("/export")) {
    event.respondWith(
      fetch(event.request).catch(() =>
        caches.match(event.request).then(
          (cached) =>
            cached ||
            new Response("Offline — this endpoint needs a network connection.", {
              status: 503,
              headers: { "Content-Type": "text/plain" },
            }),
        ),
      ),
    );
    return;
  }

  // App shell: stale-while-revalidate. Serve the cached copy fast, but refresh it in the
  // background so a deploy's changes reach returning visitors on their next load instead of
  // being pinned to the old assets forever.
  event.respondWith(
    caches.match(event.request).then((cached) => {
      const fetched = fetch(event.request)
        .then((res) => {
          if (res && res.ok) {
            const copy = res.clone();
            caches.open(CACHE).then((c) => c.put(event.request, copy));
          }
          return res;
        })
        // Same rule as the API branch above: an asset that is neither cached (not in SHELL, or
        // never visited before going offline) nor reachable over the network must still resolve
        // to a defined Response, not `undefined` — respondWith(undefined) surfaces a raw browser
        // error instead of a graceful offline message.
        .catch(
          () =>
            cached ||
            new Response("Offline — this asset isn't cached yet.", {
              status: 503,
              headers: { "Content-Type": "text/plain" },
            }),
        );
      return cached || fetched;
    }),
  );
});
