// The folder the app was installed in (Spec 04 §9.5, step 6): where
// runtime.json, pyodide/ and engine/ sit beside index.html. Resolved from
// this bundle's own URL — the built scripts live in <base>/assets/ — never
// from the document's current URL, which a restored tab can report as
// something else. Vite's dev server serves the app at its root.
export function appBase(): URL {
  if (import.meta.env.DEV) return new URL("/", window.location.href);
  return new URL("../", import.meta.url);
}

/** A file of the installation, as an absolute URL. */
export function appUrl(path: string): URL {
  return new URL(path, appBase());
}
