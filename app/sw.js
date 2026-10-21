self.__EIS_MANIFEST = {
 "release": "669a3a8de8e4b118",
 "version": "1.0.1",
 "commit": "4d0cd1b",
 "files": {
  "Silingology-EIS-logo.png": "1b55c3a3c38dab6c",
  "SlingologyEIS_logo_transparent.png": "664ebca64925799c",
  "assets/browserClient-C8DybDhU.js": "7409c71b2badd2c2",
  "assets/engine.worker-DH7J8_d6.js": "9ce92d315e46323f",
  "assets/ibm-plex-mono-latin-400-normal-Dm_PoFIZ.woff2": "3c5a451f9ec27a35",
  "assets/ibm-plex-mono-latin-400-normal-O6-GRVqx.woff": "d3d6fff8a9eaa4bf",
  "assets/ibm-plex-mono-latin-500-normal-C_OblDzq.woff2": "756026ff72eb76fd",
  "assets/ibm-plex-mono-latin-500-normal-zoSM89R3.woff": "58dbd3853a49adb7",
  "assets/ibm-plex-mono-latin-600-normal-DeXYNBV7.woff": "8aef3f5578a71f4d",
  "assets/ibm-plex-mono-latin-600-normal-rgB1DpUr.woff2": "c4d3deb734a27e6d",
  "assets/ibm-plex-sans-latin-400-normal-CDDApCn2.woff2": "3b646991d30055a9",
  "assets/ibm-plex-sans-latin-400-normal-CYLoc0-x.woff": "828907bfd14855c8",
  "assets/ibm-plex-sans-latin-500-normal-6ng42L7E.woff2": "0717336fb31fcdcd",
  "assets/ibm-plex-sans-latin-500-normal-BgVn5rGT.woff": "8d2c7b2eca91869d",
  "assets/ibm-plex-sans-latin-600-normal-Cu4Hd6ag.woff": "7861a349af1e925a",
  "assets/ibm-plex-sans-latin-600-normal-CuJfVYMP.woff2": "8960851d691c054e",
  "assets/ibm-plex-sans-latin-700-normal-Bth3BMcD.woff": "973b42f17d4dbb83",
  "assets/ibm-plex-sans-latin-700-normal-Bxkt5Cjx.woff2": "42e7b0c143c19df9",
  "assets/index-CzmNg8tR.js": "85096d5411350d1a",
  "assets/index-CzmXDInl.css": "d9b2aaaa1d92bc2f",
  "eis-mark.png": "458def2bf9afd4cd",
  "eis_icon_square.png": "2ab227ef14a1453e",
  "engine/slingology_eis-1.0.1-py3-none-any.whl": "da30abba11d44ea6",
  "favicon-16.png": "0f9370e4b7acc27d",
  "favicon-180.png": "b0e59135daf5cef7",
  "favicon-32.png": "70d6375315536da2",
  "favicon-512.png": "a6a1b84026eef632",
  "icons.svg": "b45fa506195cfcde",
  "index.html": "8f76e041fe383e37",
  "pyodide/MANIFEST.json": "96a8ea32e11f484b",
  "pyodide/numpy-2.2.5-cp313-cp313-pyodide_2025_0_wasm32.whl": "467a88e8c79f9e10",
  "pyodide/pandas-2.3.0-cp313-cp313-pyodide_2025_0_wasm32.whl": "921a819fd1d60b69",
  "pyodide/pyodide-lock.json": "6c6ba6e257a75193",
  "pyodide/pyodide.asm.js": "da195d86c80caece",
  "pyodide/pyodide.asm.wasm": "4ee3dc1deab639b4",
  "pyodide/pyodide.mjs": "e056e624b55134dd",
  "pyodide/python_dateutil-2.9.0.post0-py2.py3-none-any.whl": "9792745fdfff19fe",
  "pyodide/python_stdlib.zip": "1cc90fccf52e5145",
  "pyodide/pytz-2025.2-py2.py3-none-any.whl": "4a449e011aa4eacf",
  "pyodide/six-1.17.0-py2.py3-none-any.whl": "f213e36bbaae4640",
  "runtime.json": "aded423d380ec74e"
 }
};

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
