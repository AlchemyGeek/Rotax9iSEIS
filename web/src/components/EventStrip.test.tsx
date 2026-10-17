import { render, screen } from "@testing-library/react";
import { describe, it, expect, vi } from "vitest";
import type { EChartsOption } from "echarts";
import { EventStrip } from "./EventStrip";
import type { EventTick, Frequency } from "../types/contract";

// Capture the option EventStrip hands to the chart — a tick's presence
// and tall/short state aren't otherwise observable without a real
// canvas (see TrendsPanelStrip.test.tsx's note).
let lastOption: EChartsOption | undefined;
vi.mock("./EChartBase", () => ({
  EChartBase: (props: { option: EChartsOption }) => {
    lastOption = props.option;
    return <div data-testid="chart-stub" />;
  },
}));

function tick(flightId: string, x: number, hasEvent: boolean): EventTick {
  return { flight_id: flightId, date: "2026-09-01", x, has_event: hasEvent };
}

describe("EventStrip", () => {
  it("one tick per eligible flight, tall ticks exactly the has_event ones", () => {
    const events: EventTick[] = [
      tick("f0", 0, false), tick("f1", 1, false), tick("f2", 2, true),
      tick("f3", 3, false), tick("f4", 4, true), tick("f5", 5, true),
    ];
    const frequency: Frequency = {
      recent: { events: 2, flights: 3 }, reference: { events: 1, flights: 3 },
      delta: 0.33, z: 1.1, qualifies: true,
    };
    render(<EventStrip events={events} frequency={frequency} highlightFlight={null} onOpenFlight={() => {}} />);

    expect(lastOption).toBeDefined();
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const series = (lastOption!.series as any[])[0];
    expect(series.data.length).toBe(events.length);

    // symbolSize's height half ([3, 16] tall vs [3, 7] short) is the
    // tall/short encoding (§8.4) — one tick per eligible flight, height
    // keyed off has_event (index 4 of each data row), not magnitude.
    const tallCount = series.data.filter((d: number[]) => series.symbolSize(d)[1] === 16).length;
    const shortCount = series.data.filter((d: number[]) => series.symbolSize(d)[1] === 7).length;
    expect(tallCount).toBe(events.filter((e) => e.has_event).length);
    expect(shortCount).toBe(events.filter((e) => !e.has_event).length);
  });

  it("renders the frequency header in words", () => {
    const events: EventTick[] = [tick("f0", 0, true)];
    const frequency: Frequency = {
      recent: { events: 2, flights: 10 }, reference: { events: 1, flights: 40 },
      delta: 0.175, z: 1.2, qualifies: false,
    };
    render(<EventStrip events={events} frequency={frequency} highlightFlight={null} onOpenFlight={() => {}} />);
    expect(screen.getByText(/exceeded on 2 of 10 recent flights · 1 of 40 earlier/)).toBeTruthy();
  });

  it("splits recent vs reference shading using frequency.recent.flights, not a separate window field", () => {
    const events: EventTick[] = Array.from({ length: 10 }, (_, i) => tick(`f${i}`, i, false));
    const frequency: Frequency = {
      recent: { events: 0, flights: 4 }, reference: { events: 0, flights: 6 },
      delta: 0, z: null, qualifies: false,
    };
    render(<EventStrip events={events} frequency={frequency} highlightFlight={null} onOpenFlight={() => {}} />);
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const series = (lastOption!.series as any[]);
    // series[0] carries the tick data; the remaining series are the
    // silent shaded-region markAreas, one per region actually present.
    const shadedAreas = series.slice(1).map((s) => s.markArea.data[0].map((d: { xAxis: number }) => d.xAxis));
    expect(shadedAreas).toContainEqual([6, 9]); // recent: last 4 flights, x 6..9
    expect(shadedAreas).toContainEqual([0, 5]); // reference: first 6 flights, x 0..5
  });
});
