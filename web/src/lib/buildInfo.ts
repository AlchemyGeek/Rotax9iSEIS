// The build the page is running (vite.config.ts stamps __APP_BUILD__).

export const APP_BUILD = __APP_BUILD__;

/** "1.0.1 · build 9829bd1 · Oct 20, 2026, 14:30", with "· modified" when it
 * was built from uncommitted changes. */
export function describeBuild(b = APP_BUILD, locale?: string): string {
  const when = new Date(b.built_at);
  const date = Number.isNaN(when.getTime()) ? "" : when.toLocaleString(locale, { dateStyle: "medium", timeStyle: "short" });
  return [b.version, `build ${b.commit}`, date, b.modified ? "modified" : ""].filter(Boolean).join(" · ");
}
