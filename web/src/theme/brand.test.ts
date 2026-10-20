import { describe, it, expect } from "vitest";
import { palettes, type Palette } from "./colors";
import { PHASE_ORDER, phaseColor } from "../lib/phases";

// Spec 15 §3: the brand color is reserved out of the phase and severity
// palettes. A chromatic functional color must sit well away from it
// (CIELAB ΔE ≥ 20); a neutral grey only needs to be told apart (ΔE ≥ 8),
// since greys never share a role with the brand. The brand stays muted.

function rgb(hex: string): [number, number, number] {
  const h = hex.replace("#", "");
  return [0, 2, 4].map((i) => parseInt(h.slice(i, i + 2), 16) / 255) as [number, number, number];
}

function hslSaturation(hex: string): number {
  const [r, g, b] = rgb(hex);
  const max = Math.max(r, g, b), min = Math.min(r, g, b), l = (max + min) / 2;
  if (max === min) return 0;
  return (max - min) / (l > 0.5 ? 2 - max - min : max + min);
}

function lab(hex: string): [number, number, number] {
  const lin = (c: number) => (c <= 0.04045 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4);
  const [r, g, b] = rgb(hex).map(lin);
  const x = (0.4124 * r + 0.3576 * g + 0.1805 * b) / 0.95047;
  const y = 0.2126 * r + 0.7152 * g + 0.0722 * b;
  const z = (0.0193 * r + 0.1192 * g + 0.9505 * b) / 1.08883;
  const f = (t: number) => (t > 0.008856 ? Math.cbrt(t) : 7.787 * t + 16 / 116);
  return [116 * f(y) - 16, 500 * (f(x) - f(y)), 200 * (f(y) - f(z))];
}

function deltaE(a: string, b: string): number {
  const [p, q] = [lab(a), lab(b)];
  return Math.hypot(p[0] - q[0], p[1] - q[1], p[2] - q[2]);
}

const SOURCES = import.meta.glob<string>(["../**/*.{ts,tsx,css}", "!../**/*.test.{ts,tsx}", "!../fixtures/**"], {
  query: "?raw", import: "default", eager: true,
});

// Both themes (§9): each theme's brand values against the phase colors and
// that theme's severity colors.
const brandOf = (c: Palette) => ({ brand: c.brand, brandTint: c.brandTint });
const functionalOf = (c: Palette): Record<string, string> => ({
  ...Object.fromEntries(PHASE_ORDER.map((p) => [`phase ${p}`, phaseColor(p)])),
  "severity limit": c.severityLimit,
  "severity warning": c.severityWarning,
  "severity watch": c.severityWatch,
  "severity info": c.severityInfo,
});

describe("brand color reservation (Spec 15 §3)", () => {
  it.each(["dark", "light"] as const)("the brand stays muted (%s)", (theme) => {
    for (const hex of Object.values(brandOf(palettes[theme]))) {
      const s = hslSaturation(hex);
      expect(s).toBeGreaterThanOrEqual(0.2);
      expect(s).toBeLessThanOrEqual(0.45);
    }
  });

  it.each(["dark", "light"] as const)("no phase or severity color is near the brand (%s)", (theme) => {
    const near: string[] = [];
    for (const [bName, b] of Object.entries(brandOf(palettes[theme]))) {
      for (const [name, c] of Object.entries(functionalOf(palettes[theme]))) {
        const min = hslSaturation(c) >= 0.2 ? 20 : 8;
        const d = deltaE(b, c);
        if (d < min) near.push(`${name} ${c} is ΔE ${d.toFixed(1)} from ${bName} ${b} (needs ${min})`);
      }
    }
    expect(near).toEqual([]);
  });

  it("no hard-coded copy of an accent color outside the token files", () => {
    const banned = /4fc3b0|79,\s*195,\s*176|3d5a73|7fa3c2|127,\s*163,\s*194|#2e6f64/i;
    // The token files, and the weather-band palette: its teal is a data
    // color of its own (the "mild" band), not a borrowed accent.
    const allowed = new Set(["../index.css", "./colors.ts", "../lib/bands.ts"]);
    const hits: string[] = [];
    for (const [path, text] of Object.entries(SOURCES)) {
      if (allowed.has(path)) continue;
      text.split("\n").forEach((line, i) => { if (banned.test(line)) hits.push(`${path}:${i + 1}`); });
    }
    expect(hits).toEqual([]);
  });

  it("index.css and colors.ts agree, in both themes", () => {
    const css = SOURCES["../index.css"];
    const block = (sel: string) => css.slice(css.indexOf(sel), css.indexOf("}", css.indexOf(sel)));
    const vars = (b: string) => Object.fromEntries([...b.matchAll(/--([a-z0-9-]+):\s*([^;]+);/g)].map((m) => [m[1], m[2].trim().toLowerCase()]));
    const twins: Record<string, keyof Palette> = {
      bg: "bg", panel: "panel", "panel-control": "panelControl", border: "border", "border-subtle": "borderSubtle",
      "text-primary": "textPrimary", "text-secondary": "textSecondary", "text-tertiary": "textTertiary",
      brand: "brand", "brand-tint": "brandTint", ok: "ok",
      "severity-limit": "severityLimit", "severity-warning": "severityWarning", "severity-watch": "severityWatch", "severity-info": "severityInfo",
      "chart-rpm": "chartRpm", "chart-data": "chartData", "chart-ias": "chartIas", "chart-oil-temp": "chartOilTemp", "chart-egt-spread": "chartEgtSpread",
    };
    for (const [theme, sel] of [["dark", ":root {"], ["light", ':root[data-theme="light"] {']] as const) {
      const v = vars(block(sel));
      const off = Object.entries(twins).filter(([cssName, key]) => v[cssName] !== String(palettes[theme][key]).toLowerCase())
        .map(([cssName, key]) => `${theme} --${cssName} ${v[cssName]} vs ${key} ${palettes[theme][key]}`);
      expect(off).toEqual([]);
    }
  });

  it("the light palette has every value the dark one has", () => {
    expect(Object.keys(palettes.light).sort()).toEqual(Object.keys(palettes.dark).sort());
  });
});
