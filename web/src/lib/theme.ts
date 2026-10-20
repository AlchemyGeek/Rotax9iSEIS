import { useEffect, useState } from "react";
import { applyPalette, type Theme } from "../theme/colors";

// Spec 15 §6, §9: dark or light, an app-level setting (Spec 02's app
// settings, beside units), dark by default.
//
// - The page applies it before the first paint from a copy in localStorage
//   (the engine may take seconds to answer in the browser host).
// - The app settings are the record: read once the engine answers, and
//   written when the pilot switches.
// - A switch sets `data-theme` on <html> (index.css's light tokens), swaps
//   the chart palette in place (theme/colors.ts), and remounts the views so
//   every chart rebuilds with it.

export const THEME_KEY = "slingology-eis-theme";
const listeners = new Set<(t: Theme) => void>();

export function getTheme(): Theme {
  return document.documentElement.dataset.theme === "light" ? "light" : "dark";
}

function apply(theme: Theme) {
  if (theme === "light") document.documentElement.dataset.theme = "light";
  else delete document.documentElement.dataset.theme;
  applyPalette(theme);
  document.querySelector('meta[name="theme-color"]')?.setAttribute("content", theme === "light" ? "#f4f6f8" : "#0f1214");
  try { localStorage.setItem(THEME_KEY, theme); } catch { /* private mode */ }
}

/** Before the first render: the last theme this browser showed. */
export function initTheme() {
  let saved: string | null = null;
  try { saved = localStorage.getItem(THEME_KEY); } catch { /* private mode */ }
  apply(saved === "light" ? "light" : "dark");
}

/** Show `theme` now; `persist` also records it in the app settings. */
export async function setTheme(theme: Theme, persist = true): Promise<void> {
  if (theme !== getTheme()) {
    apply(theme);
    for (const fn of listeners) fn(theme);
  }
  if (!persist) return;
  try {
    const { getEngineClient } = await import("./engineClient");
    const client = getEngineClient();
    const settings = await client.getAppSettings();
    if (settings.theme !== theme) await client.saveAppSettings({ ...settings, theme });
  } catch {
    // No engine to tell (the sample workspace): this browser still remembers it.
  }
}

/** Once the engine answers: its app settings are the record. */
export async function syncThemeFromSettings(): Promise<void> {
  try {
    const { getEngineClient } = await import("./engineClient");
    const settings = await getEngineClient().getAppSettings();
    if (settings.theme === "light" || settings.theme === "dark") await setTheme(settings.theme, false);
  } catch {
    // Keep the local copy.
  }
}

/** The theme in effect, re-rendering on a switch. */
export function useTheme(): Theme {
  const [theme, set] = useState<Theme>(getTheme);
  useEffect(() => {
    listeners.add(set);
    return () => { listeners.delete(set); };
  }, []);
  return theme;
}
