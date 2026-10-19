import { describe, it, expect } from "vitest";
import { colors } from "./colors";
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

const BRAND = { brand: colors.brand, brandTint: colors.brandTint };
const FUNCTIONAL: Record<string, string> = {
  ...Object.fromEntries(PHASE_ORDER.map((p) => [`phase ${p}`, phaseColor(p)])),
  "severity limit": colors.severityLimit,
  "severity warning": colors.severityWarning,
  "severity watch": colors.severityWatch,
  "severity info": colors.severityInfo,
};

describe("brand color reservation (Spec 15 §3)", () => {
  it("the brand stays muted", () => {
    for (const hex of Object.values(BRAND)) {
      const s = hslSaturation(hex);
      expect(s).toBeGreaterThanOrEqual(0.2);
      expect(s).toBeLessThanOrEqual(0.45);
    }
  });

  it("no phase or severity color is near the brand", () => {
    const near: string[] = [];
    for (const [bName, b] of Object.entries(BRAND)) {
      for (const [name, c] of Object.entries(FUNCTIONAL)) {
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
});
