// Minimal service worker: cache the app shell so the dashboard installs as a PWA and opens
// offline at a tenant meeting or a council hearing where there is no signal. The cached
// sample surface means it renders something useful even with no network and no server.
// CacheStorage belongs to the whole origin, not to a service-worker scope. GitHub Pages serves the
// root dashboard and `/sensors/` from overlapping worker scopes on the same origin, so each worker
// owns a path-derived prefix and may delete only older releases bearing that exact prefix.
// Encode the complete pathname, including its boundary slashes. Stripping them would make `/`
// share an owner with `/root/`, while encoding only path segments would make nested and hyphenated
// routes ambiguous. URL pathnames are always non-empty (`/` at minimum).
const CACHE_SCOPE = encodeURIComponent(new URL(self.registration.scope).pathname);
// The terminator is part of the ownership boundary and keeps release names out of the scope key.
const CACHE_PREFIX = `swelter-shell-${CACHE_SCOPE}::`;
const CACHE_RELEASE = "v7";
const CACHE = `${CACHE_PREFIX}${CACHE_RELEASE}`;
const SHELL = [
  ".",
  "index.html",
  "styles.css",
  "observatory.css",
  "i18n-runtime.mjs",
  "app.js",
  "manifest.webmanifest",
  "icon-512.png",
  "icon.svg",
  "i18n/en.json",
  "i18n/es.json",
  "sample-surface.json",
];
const RUNTIME_MANIFEST = "vendor/messageformat/asset-manifest.json";
// Static Pages builds add demo.json; live/local deployments may omit it. Cache
// the truth contract when present without letting a 404 abort installation of
// the core offline shell.
const OPTIONAL_SHELL = ["demo.json", "basemap.geojson"];

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches.open(CACHE).then(async (cache) => {
      const response = await fetch(RUNTIME_MANIFEST);
      if (!response.ok) throw new Error(`MessageFormat runtime manifest: HTTP ${response.status}`);
      const runtimeAssets = await response.json();
      if (!Array.isArray(runtimeAssets) || runtimeAssets.some((asset) => typeof asset !== "string")) {
        throw new TypeError("MessageFormat runtime manifest must be a string array");
      }
      await cache.addAll([...SHELL, RUNTIME_MANIFEST, ...runtimeAssets]);
      await Promise.allSettled(OPTIONAL_SHELL.map((asset) => cache.add(asset)));
    }),
  );
  self.skipWaiting();
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(
        keys
          .filter((key) => key.startsWith(CACHE_PREFIX) && key !== CACHE)
          .map((key) => caches.delete(key)),
      ),
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
      fetch(event.request)
        .then(async (response) => {
          if (response && response.ok) {
            try {
              const cache = await caches.open(CACHE);
              await cache.put(event.request, response.clone());
            } catch {
              // The current response is still valid when storage is unavailable or quota is full.
            }
          }
          return response;
        })
        .catch(async () => {
          try {
            const cache = await caches.open(CACHE);
            const cached = await cache.match(event.request);
            if (cached) return cached;
          } catch {
            // CacheStorage itself can be unavailable; return the same explicit offline response.
          }
          return new Response("Offline — this endpoint needs a network connection.", {
            status: 503,
            headers: { "Content-Type": "text/plain" },
          });
        }),
    );
    return;
  }

  // App shell: stale-while-revalidate. Serve the cached copy fast, but refresh it in the
  // background so a deploy's changes reach returning visitors on their next load instead of
  // being pinned to the old assets forever.
  const cacheReady = caches.open(CACHE);
  const cachedReady = cacheReady.then((cache) => cache.match(event.request));
  const revalidation = cacheReady.then(async (cache) => {
    const response = await fetch(event.request);
    if (response && response.ok) {
      try {
        await cache.put(event.request, response.clone());
      } catch {
        // A quota or CacheStorage failure must not turn a successful network response into a 503.
        // The current navigation can still proceed; a later request can try to refresh again.
      }
    }
    return response;
  });

  // Register the lifetime extension synchronously while the fetch event is being dispatched.
  // On a hit, respond immediately from cache but keep the worker alive through the awaited put.
  // On a miss, respondWith itself owns this same revalidation promise.
  event.waitUntil(
    cachedReady.then((cached) => (cached ? revalidation.catch(() => undefined) : undefined)),
  );
  event.respondWith(
    cachedReady.then(async (cached) => {
      if (cached) return cached;
      try {
        return await revalidation;
      } catch {
        // An asset that is neither cached (not in SHELL, or never visited before going offline)
        // nor reachable over the network must resolve to a defined Response. Returning undefined
        // from respondWith would surface a raw browser error page.
        return new Response("Offline — this asset isn't cached yet.", {
          status: 503,
          headers: { "Content-Type": "text/plain" },
        });
      }
    }),
  );
});
