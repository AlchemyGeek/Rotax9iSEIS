import { describe, it, expect } from "vitest";
import { INLINE_HELP } from "./inlineHelp";

// Spec 14 §9 criterion 15: every item in §7.4's "Gets help" column has
// help, each one sentence, all of it in this one registry, and nothing
// else. margin_min_f / consecutive_flights are in §7.4's list but have no
// field on any topic card (engine constants; cylinder_rank ships with no
// triggers), so there is nothing to attach their help to.
const EXPECTED = [
  "reference.outlier_z_threshold", "reference.recent_window", "reference.pinning",
  "reference.contributing_flights", "reference.stratification",
  "engine.suppression", "engine.overrides",
  "trigger.enabled", "trigger.r2_min", "trigger.n_min", "trigger.baseline_deviation",
  "preview.counts",
  "journal.backfilled", "journal.change_notices",
  "flight.excluded_from_reference",
];

// Every app source file, as text (Vite inlines these at test time).
const SOURCES = import.meta.glob<string>(["../**/*.{ts,tsx}", "!../**/*.test.{ts,tsx}"], {
  query: "?raw", import: "default", eager: true,
});

describe("inline help registry", () => {
  it("has exactly the §7.4 items", () => {
    expect(Object.keys(INLINE_HELP).sort()).toEqual([...EXPECTED].sort());
  });

  it("is one sentence per item", () => {
    for (const [id, text] of Object.entries(INLINE_HELP)) {
      expect(text.endsWith("."), id).toBe(true);
      // No sentence break inside: a full stop followed by a space and more text.
      expect(/[.!?]\s+\S/.test(text), id).toBe(false);
    }
  });

  it("is used for every item, and from nowhere but the registry", () => {
    const uses = Object.values(SOURCES)
      .flatMap((s) => [...s.matchAll(/<InlineHelp id="([^"]+)"/g)].map((m) => m[1]));
    expect(new Set(uses)).toEqual(new Set(EXPECTED));
  });
});
