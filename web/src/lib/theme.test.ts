import { afterEach, describe, expect, it, vi } from "vitest";
import { colors, palettes } from "../theme/colors";

// Spec 15 §6, §9: the theme switch — tokens, chart palette, local copy,
// and the app setting.

const saved: unknown[] = [];
vi.mock("./engineClient", () => ({
  getEngineClient: () => ({
    getAppSettings: async () => ({ units: "metric", last_active_workspace_id: null, chart_presets: [], flight_chart: {}, theme: "dark" }),
    saveAppSettings: async (s: unknown) => { saved.push(s); return s; },
  }),
}));

import { getTheme, initTheme, setTheme, THEME_KEY } from "./theme";

describe("theme", () => {
  afterEach(async () => { await setTheme("dark", false); saved.length = 0; localStorage.clear(); });

  it("starts dark, with the dark chart palette", () => {
    initTheme();
    expect(getTheme()).toBe("dark");
    expect(document.documentElement.dataset.theme).toBeUndefined();
    expect(colors.bg).toBe(palettes.dark.bg);
  });

  it("switching to light sets the tokens, the chart palette, the local copy and the app setting", async () => {
    await setTheme("light");
    expect(document.documentElement.dataset.theme).toBe("light");
    expect(colors.bg).toBe(palettes.light.bg);
    expect(colors.egtCyl).toEqual(palettes.light.egtCyl);
    expect(localStorage.getItem(THEME_KEY)).toBe("light");
    expect(saved).toEqual([expect.objectContaining({ theme: "light", units: "metric" })]);   // other settings kept
  });

  it("a later visit starts in the theme this browser last showed", () => {
    localStorage.setItem(THEME_KEY, "light");
    initTheme();
    expect(getTheme()).toBe("light");
    expect(colors.panel).toBe(palettes.light.panel);
  });
});
