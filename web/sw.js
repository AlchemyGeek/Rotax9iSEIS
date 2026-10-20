// Service worker for the in-browser site (Spec 04 §9.7, step 6): the site
// opens and analyses with no network after the first visit.
//
// scripts/build_site.py writes this file into the built site with the
// release manifest prepended as `self.__EIS_MANIFEST`:
//   { release: "<hash of every file>", version: "<package version>", commit: "<git commit>",
//     files: { "<path relative to the site>": "<sha256 of that file>" } }
// It is not part of `npm run build` and never served by `slingology-eis
// serve`; the page registers it only when runtime.json says "browser".
//
// One cache per release, filled completely before this worker takes over,
// so a page is never served a mix of two releases. Files whose hash is
// unchanged are copied from the previous release's cache instead of
// downloaded again (the Pyodide runtime rarely changes). A waiting worker
// takes over only when the page asks (lib/serviceWorker.ts: when the
// engine is idle), and the page then reloads into the new release.

/* eslint-disable no-restricted-globals */
const MANIFEST = self.__EIS_MANIFEST;
const PREFIX = "eis-site-";
const CACHE = PREFIX + MANIFEST.release;
const MANIFEST_KEY = "__eis_manifest__";
const scope = () => new URL(self.registration.scope);
const abs = (path) => new URL(path, scope()).href;

async function previousReleases() {
  const found = new Map();                       // url -> { cache, rev }
  for (const name of await caches.keys()) {
    if (!name.startsWith(PREFIX) || name === CACHE) continue;
    const res = await (await caches.open(name)).match(abs(MANIFEST_KEY));
    if (!res) continue;
    const m = await res.json();
    for (const [path, rev] of Object.entries(m.files)) found.set(abs(path), { cache: name, rev });
  }
  return found;
}

async function precache() {
  const cache = await caches.open(CACHE);
  const previous = await previousReleases();
  const entries = Object.entries(MANIFEST.files);
  let next = 0;
  async function lane() {
    while (next < entries.length) {
      const [path, rev] = entries[next++];
      const url = abs(path);
      if (await cache.match(url)) continue;           // an install that was interrupted
      const prev = previous.get(url);
      if (prev && prev.rev === rev) {
        const kept = await (await caches.open(prev.cache)).match(url);
        if (kept) { await cache.put(url, kept); continue; }
      }
      const res = await fetch(url, { cache: "no-cache" });
      if (!res.ok) throw new Error(`${path}: HTTP ${res.status}`);
      await cache.put(url, res);
    }
  }
  await Promise.all(Array.from({ length: 6 }, lane));
  // Written last: a release's manifest in a cache means the cache is whole.
  await cache.put(abs(MANIFEST_KEY), new Response(JSON.stringify(MANIFEST), { headers: { "Content-Type": "application/json" } }));
}

self.addEventListener("install", (event) => {
  event.waitUntil(precache());
});

self.addEventListener("activate", (event) => {
  event.waitUntil((async () => {
    for (const name of await caches.keys()) {
      if (name.startsWith(PREFIX) && name !== CACHE) await caches.delete(name);
    }
    await self.clients.claim();
  })());
});

self.addEventListener("message", (event) => {
  if (event.data && event.data.type === "SKIP_WAITING") self.skipWaiting();
});

self.addEventListener("fetch", (event) => {
  const req = event.request;
  if (req.method !== "GET") return;
  const url = new URL(req.url);
  const base = scope();
  if (url.origin !== base.origin || !url.pathname.startsWith(base.pathname)) return;
  event.respondWith((async () => {
    const cache = await caches.open(CACHE);
    // Any page of the app is index.html (routes live after the #).
    if (req.mode === "navigate") {
      const page = await cache.match(abs("index.html"));
      if (page) return page;
    } else {
      const hit = await cache.match(url.origin + url.pathname);   // favicon?v=2 etc.
      if (hit) return hit;
    }
    return fetch(req);
  })());
});
