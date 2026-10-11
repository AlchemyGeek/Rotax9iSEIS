import { render, screen, fireEvent, waitFor, within } from "@testing-library/react";
import { describe, it, expect, vi } from "vitest";
import type { EChartsOption } from "echarts";
import { TrendsPanelStrip, readinessText } from "./TrendsPanelStrip";
import type { FleetMetric, Readiness, Shift, UnpinPreview } from "../types/contract";

// EChartBase calls echarts.init() against a real <canvas> 2D context,
// which jsdom doesn't implement (no `canvas` package here) — every
// other test in this file only needs the surrounding badge/text DOM,
// so the chart itself is stubbed out rather than rendered for real.
// Tests that need to inspect the chart shape (the pinned option tests
// below) read the last captured `option` instead of pixels.
let lastOption: EChartsOption | undefined;
vi.mock("./EChartBase", () => ({
  EChartBase: (props: { option: EChartsOption }) => {
    lastOption = props.option;
    return <div data-testid="chart-stub" />;
  },
}));

function baseMetric(overrides: Partial<FleetMetric> = {}): FleetMetric {
  return {
    metric_id: "limit_oil_temp_max_peak_excess",
    baseline: { n: 0, mean: null, std: null, min: null, max: null, confidence: { level: "VERY_LOW", n: 0 } },
    trend: null,
    points: [],
    outliers: [],
    ...overrides,
  };
}

const READINESS_CASES: Readiness[] = [
  { kind: "filtered" },
  { kind: "building", count: 3 },
  { kind: "no_recent" },
  { kind: "no_events" },
  { kind: "rare", count: 2 },
  { kind: "insufficient" },
];

describe("TrendsPanelStrip readiness badges", () => {
  for (const readiness of READINESS_CASES) {
    it(`renders the ${readiness.kind} badge text`, () => {
      render(
        <TrendsPanelStrip
          metricId="x" metric={baseMetric({ readiness })} label="x" omMarginFraction={0.25}
          highlightFlight={null} onOpenFlight={() => {}} onOpenFlights={() => {}}
        />,
      );
      // §9.3: shown both next to the name in the header and in the
      // detail panel — "everywhere a metric is named" (R7.1).
      expect(screen.getAllByText(readinessText(readiness)).length).toBe(2);
    });
  }

  it("falls back to the building-your-reference text when there is no shift and no readiness", () => {
    render(
      <TrendsPanelStrip
        metricId="x" metric={baseMetric({ baseline: { n: 2, mean: 1, std: 0.1, min: 0.9, max: 1.1, confidence: { level: "LOW", n: 2 } } })}
        label="x" omMarginFraction={0.25}
        highlightFlight={null} onOpenFlight={() => {}} onOpenFlights={() => {}}
      />,
    );
    expect(screen.getByText(/Building your reference/)).toBeTruthy();
  });

  it("renders the normal shift read when qualifying, with no readiness badge", () => {
    const metric = baseMetric({
      baseline: { n: 20, mean: 5, std: 1, min: 3, max: 7, confidence: { level: "GOOD", n: 20 } },
      shift: {
        recent: { flight_ids: ["r1"], n: 1, hours_from: 40, hours_to: 41, mean: 10 },
        reference: { kind: "rolling", n: 19, mean: 5, std: 1, min: 3, max: 7, confidence: { level: "GOOD", n: 19 } },
        shift_z: 4.5, direction: "higher",
        comparison: { scope: "all", unmatched: 0 },
        level: { om_margin: false, filter_edge: false },
        qualifies: true,
      },
    });
    render(
      <TrendsPanelStrip
        metricId="x" metric={metric} label="x" omMarginFraction={0.25}
        highlightFlight={null} onOpenFlight={() => {}} onOpenFlights={() => {}}
      />,
    );
    expect(screen.getByText(/shift_z 4.50/)).toBeTruthy();
  });
});

// Spec 12 §5.7.1 (Session D) — visible pinned state, the pin/unpin
// confirmations, and the preview they show.

function pinnedShift(overrides: Partial<Shift["reference"]> = {}): Shift {
  return {
    recent: { flight_ids: ["r1", "r2"], n: 2, hours_from: 40, hours_to: 41, mean: 50 },
    reference: {
      kind: "pinned", n: 12, hours_from: 0, hours_to: 11, mean: 20, std: 2,
      min: 15, max: 25, confidence: { level: "GOOD", n: 12 },
      label: "after oil change", set_at: "2026-10-12T00:00:00Z",
      ...overrides,
    },
    shift_z: 15, direction: "higher",
    comparison: { scope: "all", unmatched: 0 },
    level: { om_margin: false, filter_edge: false },
    qualifies: true,
  };
}

describe("TrendsPanelStrip pinned state", () => {
  it("shows the reference-pinned badge in the header and still renders the full shift detail", () => {
    const metric = baseMetric({
      baseline: { n: 14, mean: 25, std: 5, min: 15, max: 50, confidence: { level: "GOOD", n: 14 } },
      shift: pinnedShift(),
      readiness: { kind: "pinned", label: "after oil change" },
    });
    render(
      <TrendsPanelStrip
        metricId="x" metric={metric} label="Oil temp" omMarginFraction={0.25}
        highlightFlight={null} onOpenFlight={() => {}} onOpenFlights={() => {}}
        onUnpinReference={() => {}}
      />,
    );
    expect(screen.getByText(/reference pinned · after oil change/)).toBeTruthy();
    // Full detail, not just the badge (unlike every other readiness kind).
    expect(screen.getByText(/shift_z 15.00/)).toBeTruthy();
    expect(screen.getByText("Unpin reference")).toBeTruthy();
  });

  it("draws a hard-bordered pinned reference, a neutral gap, and a pin marker", () => {
    const metric = baseMetric({ shift: pinnedShift() });
    render(
      <TrendsPanelStrip
        metricId="x" metric={metric} label="x" omMarginFraction={0.25}
        highlightFlight={null} onOpenFlight={() => {}} onOpenFlights={() => {}}
      />,
    );
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const series = lastOption!.series as any[];
    const bordered = series.find((s) => s.markArea?.itemStyle?.borderColor);
    expect(bordered).toBeTruthy();
    // Gap: reference ends at hour 11, recent starts at hour 40 — a real gap.
    const gap = series.find((s) => s.markArea && !s.markArea.itemStyle?.borderColor && s.markArea.data[0][0].xAxis === 11);
    expect(gap).toBeTruthy();
    expect(gap.markArea.data[0][1].xAxis).toBe(40);
    const marker = series.find((s) => s.markLine?.label?.formatter?.includes("reference pinned"));
    expect(marker).toBeTruthy();
    expect(marker.markLine.label.formatter).toContain("12 flights");
    expect(marker.markLine.label.formatter).toContain("after oil change");
  });

  it("draws no gap region when the pinned reference and recent window are adjacent", () => {
    const metric = baseMetric({ shift: pinnedShift({ hours_to: 40 }) }); // recent also starts at 40 — no gap
    render(
      <TrendsPanelStrip
        metricId="x" metric={metric} label="x" omMarginFraction={0.25}
        highlightFlight={null} onOpenFlight={() => {}} onOpenFlights={() => {}}
      />,
    );
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const series = lastOption!.series as any[];
    const gap = series.find((s) => s.markArea && !s.markArea.itemStyle?.borderColor && s.markArea.data[0][0].xAxis === 39);
    expect(gap).toBeFalsy();
  });

  it("draws the pinned reference at its true x-extent regardless of the current zoom (R10.4)", () => {
    // Pinned span is hours 0-11; zoom out to hours 0-100 (wider than
    // any real data) — the pinned region's own coordinates must not
    // move or clip, since markArea data is absolute, not zoom-relative.
    const metric = baseMetric({ shift: pinnedShift() });
    render(
      <TrendsPanelStrip
        metricId="x" metric={metric} label="x" omMarginFraction={0.25}
        highlightFlight={null} onOpenFlight={() => {}} onOpenFlights={() => {}}
        zoomRange={{ start: 0, end: 100 }}
      />,
    );
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const series = lastOption!.series as any[];
    const pinnedArea = series.find((s) => s.markArea?.itemStyle?.borderColor);
    expect(pinnedArea.markArea.data[0][0].xAxis).toBe(0);
    expect(pinnedArea.markArea.data[0][1].xAxis).toBe(11);
    // The chart's own dataZoom reflects the wider view, independently.
    expect((lastOption!.dataZoom as any)[0].startValue).toBe(0);
    expect((lastOption!.dataZoom as any)[0].endValue).toBe(100);
  });

  it("falls back to the formatted pin date when no label was given", () => {
    const metric = baseMetric({ shift: pinnedShift({ label: undefined }) });
    render(
      <TrendsPanelStrip
        metricId="x" metric={metric} label="x" omMarginFraction={0.25}
        highlightFlight={null} onOpenFlight={() => {}} onOpenFlights={() => {}}
      />,
    );
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const series = lastOption!.series as any[];
    const marker = series.find((s) => s.markLine?.label?.formatter?.includes("reference pinned"));
    // Locale-dependent order (en-US: "Oct 12"), but UTC-forced so it
    // never shifts a day relative to the ISO date regardless of the
    // environment's local timezone.
    expect(marker.markLine.label.formatter).toMatch(/Oct 12/);
  });

  it("draws a muted not-used region over every flight older than the pinned reference (v0.6 §5.7.1 item 1)", () => {
    const metric = baseMetric({
      points: [
        { flight_id: "old1", date: "2025-12-01", x: -20, value: 1 },
        { flight_id: "old2", date: "2025-12-15", x: -10, value: 1 },
      ],
      shift: pinnedShift(),
    });
    render(
      <TrendsPanelStrip
        metricId="x" metric={metric} label="x" omMarginFraction={0.25}
        highlightFlight={null} onOpenFlight={() => {}} onOpenFlights={() => {}}
      />,
    );
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const series = lastOption!.series as any[];
    const notUsed = series.find((s) => s.markArea && s.markArea.data[0][0].xAxis === -20 && s.markArea.data[0][1].xAxis === 0);
    expect(notUsed).toBeTruthy();
    expect(screen.getByText("▦ not used")).toBeTruthy();
  });

  it("draws no not-used region when there is no history before the pin and no gap before the window", () => {
    // hours_to: 40 matches recent.hours_from — adjacent, no between-
    // pin-and-window segment either (same condition D-1/R10.4 use).
    const metric = baseMetric({ shift: pinnedShift({ hours_to: 40 }) }); // and no points at all older than hours_from=0
    render(
      <TrendsPanelStrip
        metricId="x" metric={metric} label="x" omMarginFraction={0.25}
        highlightFlight={null} onOpenFlight={() => {}} onOpenFlights={() => {}}
      />,
    );
    expect(screen.queryByText("▦ not used")).toBeNull();
  });

  function metricForPinTests(recentN: number) {
    const inView = Array.from({ length: 12 }, (_, i) => ({ flight_id: `r${i}`, date: "2026-09-01", x: 40 + i, value: 1 }));
    const points = [{ flight_id: "old1", date: "2025-01-01", x: 0, value: 1 }, ...inView];
    const recentIds = inView.slice(0, recentN).map((p) => p.flight_id);
    return baseMetric({
      metric_id: "egt_spread",
      points,
      shift: {
        recent: { flight_ids: recentIds, n: recentN, hours_from: 40, hours_to: 40 + recentN - 1, mean: 50 },
        reference: { kind: "rolling", n: 20, mean: 20, std: 2, min: 15, max: 25, confidence: { level: "GOOD", n: 20 } },
        shift_z: 10, direction: "higher",
        comparison: { scope: "all", unmatched: 0 },
        level: { om_margin: false, filter_edge: false },
        qualifies: true,
      },
    });
  }

  it("pin confirmation shows n/hours/dates for the zoomed-in-view selection and confirms with the label", async () => {
    const metric = metricForPinTests(12);
    const onPinReference = vi.fn();
    render(
      <TrendsPanelStrip
        metricId="egt_spread" metric={metric} label="EGT spread" omMarginFraction={0.25}
        highlightFlight={null} onOpenFlight={() => {}} onOpenFlights={() => {}}
        onPinReference={onPinReference} zoomRange={{ start: 40, end: 51 }}
      />,
    );
    fireEvent.click(screen.getByText("Pin reference to these flights"));
    expect(screen.getByText(/The 12 flights in view/)).toBeTruthy();
    expect(screen.getByText(/2026-09-01/)).toBeTruthy();
    expect(screen.queryByText(/makes comparisons noisier/)).toBeNull();
    fireEvent.change(screen.getByPlaceholderText(/after oil change/), { target: { value: "my label" } });
    fireEvent.click(screen.getByText("Pin reference"));
    expect(onPinReference).toHaveBeenCalledWith(metric.points.slice(1).map((p) => p.flight_id), "my label");
  });

  it("the small-baseline caution appears only for the selection actually in play (switching to a thin recent window)", () => {
    // Zoom selection clears the n_min floor (12, button enabled); the
    // recent-window alternative is thin (6 < 10) — the caution can
    // only ever be reached through a selection the floor didn't block,
    // confirmed here by switching to it from an open dialog.
    const metric = metricForPinTests(6);
    render(
      <TrendsPanelStrip
        metricId="egt_spread" metric={metric} label="EGT spread" omMarginFraction={0.25}
        highlightFlight={null} onOpenFlight={() => {}} onOpenFlights={() => {}}
        onPinReference={() => {}} zoomRange={{ start: 40, end: 51 }}
      />,
    );
    fireEvent.click(screen.getByText("Pin reference to these flights"));
    expect(screen.queryByText(/makes comparisons noisier/)).toBeNull();
    fireEvent.click(screen.getByText("Use the recent window instead"));
    expect(screen.getByText(/The 6 flights in view/)).toBeTruthy();
    expect(screen.getByText(/A reference of 6 flights makes comparisons noisier/)).toBeTruthy();
    fireEvent.click(screen.getByText("Use the flights in view instead"));
    expect(screen.queryByText(/makes comparisons noisier/)).toBeNull();
  });

  it("disables Pin reference to these flights below n_min in the zoomed view, with the count shown", () => {
    const metric = metricForPinTests(12);
    render(
      <TrendsPanelStrip
        metricId="egt_spread" metric={metric} label="EGT spread" omMarginFraction={0.25}
        highlightFlight={null} onOpenFlight={() => {}} onOpenFlights={() => {}}
        onPinReference={() => {}} zoomRange={{ start: 40, end: 43 }} // 4 flights in view
      />,
    );
    const button = screen.getByText("Pin reference to these flights") as HTMLButtonElement;
    expect(button.disabled).toBe(true);
    expect(button.title).toMatch(/4 in view/);
  });

  it("shows the full-history notice when the zoom (or lack of one) covers every eligible flight", () => {
    const metric = metricForPinTests(12);
    render(
      <TrendsPanelStrip
        metricId="egt_spread" metric={metric} label="EGT spread" omMarginFraction={0.25}
        highlightFlight={null} onOpenFlight={() => {}} onOpenFlights={() => {}}
        onPinReference={() => {}} // zoomRange omitted entirely: unzoomed = full history
      />,
    );
    fireEvent.click(screen.getByText("Pin reference to these flights"));
    expect(screen.getByText(/All 13 flights are selected/)).toBeTruthy();
    // Switching to the recent window (a real sub-selection) drops the notice.
    fireEvent.click(screen.getByText("Use the recent window instead"));
    expect(screen.queryByText(/All .* flights are selected/)).toBeNull();
  });

  it("unpin confirmation fetches and shows the engine's preview before confirming", async () => {
    const preview: UnpinPreview = { currently_in_summary: true, would_be_in_summary: false, changes: true };
    const onUnpinReference = vi.fn();
    const onPreviewUnpin = vi.fn().mockResolvedValue(preview);
    const metric = baseMetric({ shift: pinnedShift() });
    render(
      <TrendsPanelStrip
        metricId="x" metric={metric} label="Oil temp" omMarginFraction={0.25}
        highlightFlight={null} onOpenFlight={() => {}} onOpenFlights={() => {}}
        onUnpinReference={onUnpinReference} onPreviewUnpin={onPreviewUnpin}
      />,
    );
    fireEvent.click(screen.getByText("Unpin reference"));
    expect(onPreviewUnpin).toHaveBeenCalled();
    expect(screen.getByText("Checking…")).toBeTruthy();
    await waitFor(() => screen.getByText(/no longer appear in the change summary/));
    expect(screen.getByText(/reference will again include all earlier flights/)).toBeTruthy();
    // Two "Unpin reference"s on screen now (the strip's trigger, and
    // the dialog's own confirm button) — scope to the dialog.
    fireEvent.click(within(screen.getByRole("dialog")).getByText("Unpin reference"));
    expect(onUnpinReference).toHaveBeenCalled();
  });
});
