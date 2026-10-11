import { render, screen } from "@testing-library/react";
import { describe, it, expect } from "vitest";
import { ChangeSummaryList } from "./ChangeSummaryList";
import { fleetAnalysis, trendsPanels } from "../lib/fixtures";
import type { FleetAnalysis } from "../types/contract";

// Spec 12 §15 — Session C vitest coverage (R6.6): coupled row rendering,
// summary ordering with a level crossing, empty state. The frozen
// fixture (fleet-analysis.json, regenerated this session — see report)
// drives the coupled-row case for real; the ordering case needs a
// controlled synthetic fleet since the real fleet's one level crossing
// (limit_volts_min_peak_excess) has nothing to out-rank in a readable way.

function noop() {}

function baseShift(overrides: Partial<FleetAnalysis["metrics"][string]["shift"]> = {}) {
  return {
    recent: { flight_ids: ["r1", "r2"], n: 2, hours_from: 40, hours_to: 50, mean: 10 },
    reference: { kind: "rolling" as const, n: 20, mean: 5, std: 1, min: 3, max: 7, confidence: { level: "GOOD" as const, n: 20 } },
    shift_z: 3.0,
    direction: "higher" as const,
    comparison: { scope: "all" as const, unmatched: 0 },
    level: { om_margin: false, filter_edge: false },
    qualifies: true,
    ...overrides,
  };
}

describe("ChangeSummaryList", () => {
  it("renders the real fixture's coupled cylinder row with its relative-to-others note", () => {
    render(
      <ChangeSummaryList fleet={fleetAnalysis} panels={trendsPanels} onOpenPanel={noop} onOpenFlights={noop} />,
    );
    const coupledRow = fleetAnalysis.change_summary.find((r) => r.panel === "cylinder_balance");
    expect(coupledRow).toBeTruthy();
    expect(screen.getByText(/relative to the other cylinders/)).toBeTruthy();
  });

  it("empty state shows the no-change message with the checked-metric count", () => {
    const fleet: FleetAnalysis = {
      ...fleetAnalysis,
      metrics: { a: { ...fleetAnalysis.metrics[Object.keys(fleetAnalysis.metrics)[0]], shift: baseShift({ qualifies: false, shift_z: 0.1 }) } },
      change_summary: [],
    };
    render(<ChangeSummaryList fleet={fleet} panels={[]} onOpenPanel={noop} onOpenFlights={noop} />);
    expect(screen.getByText(/No change detected across 1 metric/)).toBeTruthy();
  });

  it("renders a change_summary row for every qualifying metric, in the engine's given order", () => {
    // ChangeSummaryList trusts fleet.change_summary's own order (Spec 12
    // §7 ranks level crossings first, engine-side — see
    // test_change_summary_ranks_om_margin_crossing_above_larger_shift_z
    // in tests/contract/test_trends.py for that ranking rule itself);
    // this is the rendering-order contract on the React side.
    const fleet: FleetAnalysis = {
      ...fleetAnalysis,
      metrics: {
        oil_temp_peak: { ...fleetAnalysis.metrics[Object.keys(fleetAnalysis.metrics)[0]], metric_id: "oil_temp_peak", shift: baseShift({ shift_z: 1.5, level: { om_margin: true, filter_edge: false } }) },
        egt_spread: { ...fleetAnalysis.metrics[Object.keys(fleetAnalysis.metrics)[0]], metric_id: "egt_spread", shift: baseShift({ shift_z: 6.0 }) },
      },
      change_summary: [
        { metric_id: "oil_temp_peak", rank: 0 },
        { metric_id: "egt_spread", rank: 1 },
      ],
    };
    const { container } = render(<ChangeSummaryList fleet={fleet} panels={[]} onOpenPanel={noop} onOpenFlights={noop} />);
    const text = container.textContent ?? "";
    const oilIdx = text.indexOf("oil temp peak");
    const egtIdx = text.indexOf("EGT spread");
    expect(oilIdx).toBeGreaterThanOrEqual(0);
    expect(egtIdx).toBeGreaterThanOrEqual(0);
    expect(oilIdx).toBeLessThan(egtIdx);
  });
});
