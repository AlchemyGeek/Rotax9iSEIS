import { describe, it, expect } from "vitest";
import { computeTiers, panelHasDetailStrips } from "./trendsTiers";
import { fleetAnalysis, trendsPanels } from "./fixtures";
import type { FleetAnalysis, TrendsPanel } from "../types/contract";

// Spec 12 §9.1 (Session F) — tier membership from the frozen fixture
// (real-engine-generated, not hand-authored — see lib/fixtures.ts),
// plus synthetic tier-transition cases the fixture itself can't show
// (it's a single snapshot, not a before/after).

describe("computeTiers — frozen fixture", () => {
  const { tier1, tier2, tier3 } = computeTiers(trendsPanels, fleetAnalysis);

  it("tier 1 holds exactly the panels with a change_summary row, in summary order", () => {
    expect(tier1.map((p) => p.panel)).toEqual(["limit:volts_min", "cylinder_balance", "boost_power"]);
  });

  it("tier 2 holds the fixed-order register panels, then filtered/rare limits", () => {
    expect(tier2.map((p) => p.panel)).toEqual([
      "thermal", "fuel",
      "limit:rpm_takeoff_max", "limit:fuel_press_max", "limit:rpm_idle_min", "limit:fuel_press_min", "limit:overboost",
    ]);
  });

  it("tier 3 holds every never-exceeded limit, and only those", () => {
    expect(tier3.length).toBeGreaterThan(0);
    for (const panel of tier3) {
      expect(panel.limit_id).toBeTruthy();
      for (const m of panel.metrics) {
        expect(fleetAnalysis.metrics[m.metric_id]?.readiness?.kind).toBe("no_events");
      }
    }
    // Partition is total: every rendered panel is in exactly one tier.
    expect(tier1.length + tier2.length + tier3.length).toBe(trendsPanels.length);
  });
});

function basePanel(overrides: Partial<TrendsPanel> = {}): TrendsPanel {
  return {
    panel: "limit:test_limit", limit_id: "test_limit",
    metrics: [
      { metric_id: "limit_test_limit_peak_excess", role: "primary", worsening: "higher", phrasing: null },
      { metric_id: "limit_test_limit_time_above_pct", role: "primary", worsening: "higher", phrasing: null },
    ],
    ...overrides,
  };
}

function baseFleet(overrides: Partial<FleetAnalysis> = {}): FleetAnalysis {
  return { ...fleetAnalysis, change_summary: [], ...overrides };
}

describe("computeTiers — synthetic transitions", () => {
  it("a limit with only the no_events badge is tier 3", () => {
    const panel = basePanel();
    const fleet = baseFleet({
      metrics: {
        ...fleetAnalysis.metrics,
        limit_test_limit_peak_excess: { ...fleetAnalysis.metrics["limit_oil_press_min_peak_excess"], metric_id: "limit_test_limit_peak_excess", readiness: { kind: "no_events" } },
        limit_test_limit_time_above_pct: { ...fleetAnalysis.metrics["limit_oil_press_min_time_above_pct"], metric_id: "limit_test_limit_time_above_pct", readiness: { kind: "no_events" } },
      },
    });
    const { tier1, tier2, tier3 } = computeTiers([panel], fleet);
    expect(tier1).toEqual([]);
    expect(tier2).toEqual([]);
    expect(tier3.map((p) => p.panel)).toEqual(["limit:test_limit"]);
  });

  it("a synthetic first event moves the limit from tier 3 to tier 2 as rare", () => {
    const panel = basePanel();
    const fleet = baseFleet({
      metrics: {
        ...fleetAnalysis.metrics,
        limit_test_limit_peak_excess: { ...fleetAnalysis.metrics["limit_oil_press_min_peak_excess"], metric_id: "limit_test_limit_peak_excess", readiness: { kind: "rare", count: 1 } },
        limit_test_limit_time_above_pct: { ...fleetAnalysis.metrics["limit_oil_press_min_time_above_pct"], metric_id: "limit_test_limit_time_above_pct", readiness: { kind: "rare", count: 1 } },
      },
    });
    const { tier1, tier2, tier3 } = computeTiers([panel], fleet);
    expect(tier3).toEqual([]);
    expect(tier2.map((p) => p.panel)).toEqual(["limit:test_limit"]);
    expect(tier1).toEqual([]);
  });

  it("a synthetic qualification moves the limit straight to tier 1", () => {
    const panel = basePanel();
    const fleet = baseFleet({
      change_summary: [{ metric_id: "limit_test_limit_peak_excess", rank: 0 }],
      metrics: {
        ...fleetAnalysis.metrics,
        limit_test_limit_peak_excess: { ...fleetAnalysis.metrics["limit_oil_press_min_peak_excess"], metric_id: "limit_test_limit_peak_excess" },
        limit_test_limit_time_above_pct: { ...fleetAnalysis.metrics["limit_oil_press_min_time_above_pct"], metric_id: "limit_test_limit_time_above_pct" },
      },
    });
    const { tier1, tier2, tier3 } = computeTiers([panel], fleet);
    expect(tier1.map((p) => p.panel)).toEqual(["limit:test_limit"]);
    expect(tier2).toEqual([]);
    expect(tier3).toEqual([]);
  });
});

describe("panelHasDetailStrips", () => {
  it("is true for a limit panel (always has time_above_pct)", () => {
    expect(panelHasDetailStrips(basePanel(), fleetAnalysis)).toBe(true);
  });

  it("is true for a register panel with a real whole-history fit", () => {
    const thermal = trendsPanels.find((p) => p.panel === "thermal")!;
    expect(panelHasDetailStrips(thermal, fleetAnalysis)).toBe(true);
  });

  it("is false when no metric has a fit and none is time_above_pct", () => {
    const panel: TrendsPanel = {
      panel: "x", metrics: [{ metric_id: "no_trend_metric", role: "primary", worsening: "either", phrasing: null }],
    };
    const fleet = baseFleet({
      metrics: { ...fleetAnalysis.metrics, no_trend_metric: { metric_id: "no_trend_metric", baseline: { n: 0, mean: null, std: null, min: null, max: null, confidence: { level: "VERY_LOW", n: 0 } }, trend: null, points: [], outliers: [] } },
    });
    expect(panelHasDetailStrips(panel, fleet)).toBe(false);
  });
});
