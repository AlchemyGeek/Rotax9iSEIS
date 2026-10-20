import { appBase, appUrl } from "./appBase";

// The static site's offline cache (Spec 04 §9.7, step 6). Registered only
// when runtime.json says "browser" and the build is a site build (sw.js is
// written by scripts/build_site.py; `vite` dev and server mode have none).
//
// Updates: the browser fetches sw.js on each visit; a new release installs
// in the background into its own cache. Once it is whole and the engine is
// idle, the page lets it take over and reloads, so the visit runs the new
// release. After the reload the page tells the user once ("Updated to
// version X") — a change of release seen in the cache's manifest.

export const RELEASE_SEEN = "slingology-eis-site-release";
const MANIFEST_KEY = "__eis_manifest__";
const IDLE_POLL_MS = 3000;

export interface SiteRelease { release: string; version: string; commit?: string }

/** Whether this page load is served by the offline cache (a later visit). */
export function servedFromDevice(): boolean {
  return typeof navigator !== "undefined" && !!navigator.serviceWorker?.controller;
}

/** The release the cache holds, if the site is cached. */
export async function cachedRelease(): Promise<SiteRelease | null> {
  try {
    const res = await caches.match(appUrl(MANIFEST_KEY).href);
    if (!res) return null;
    const m = await res.json();
    return { release: m.release, version: m.version, commit: m.commit };
  } catch {
    return null;
  }
}

/**
 * The once-only update notice: the version to announce, or null. The first
 * cached release is recorded silently (a first visit isn't an update).
 */
export async function takeUpdateNotice(): Promise<string | null> {
  const now = await cachedRelease();
  if (!now) return null;
  let seen: SiteRelease | null = null;
  try { seen = JSON.parse(localStorage.getItem(RELEASE_SEEN) ?? "null"); } catch { /* private mode */ }
  try { localStorage.setItem(RELEASE_SEEN, JSON.stringify(now)); } catch { /* private mode */ }
  if (!seen || seen.release === now.release) return null;
  // Same package version, new build: name the build — the commit, as
  // Settings → App's "This build" does.
  return seen.version === now.version ? `${now.version} (build ${now.commit || now.release.slice(0, 7)})` : now.version;
}

/** Register the site's worker; `isBusy` holds a switch while an operation runs. */
export async function registerSiteWorker(isBusy: () => boolean): Promise<void> {
  if (import.meta.env.DEV || typeof navigator === "undefined" || !("serviceWorker" in navigator)) return;
  let reg: ServiceWorkerRegistration;
  try {
    reg = await navigator.serviceWorker.register(appUrl("sw.js").href, { scope: appBase().href });
  } catch {
    return;                                    // no sw.js (not a site build), or blocked: online-only
  }
  const hadController = !!navigator.serviceWorker.controller;
  let switching = false;
  navigator.serviceWorker.addEventListener("controllerchange", () => {
    // Only a switch this page asked for reloads it; a first visit's worker
    // claiming the page changes nothing the page has already loaded.
    if (switching) window.location.reload();
  });
  const takeOver = (waiting: ServiceWorker) => {
    if (!hadController) return;                // first install activates by itself
    const attempt = () => {
      if (isBusy()) { setTimeout(attempt, IDLE_POLL_MS); return; }
      switching = true;
      waiting.postMessage({ type: "SKIP_WAITING" });
    };
    attempt();
  };
  if (reg.waiting) takeOver(reg.waiting);
  reg.addEventListener("updatefound", () => {
    const installing = reg.installing;
    installing?.addEventListener("statechange", () => {
      if (installing.state === "installed" && reg.waiting) takeOver(reg.waiting);
    });
  });
}
