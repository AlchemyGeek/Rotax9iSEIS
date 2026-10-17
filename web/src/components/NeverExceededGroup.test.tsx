import { render, screen, fireEvent } from "@testing-library/react";
import { describe, it, expect, vi } from "vitest";
import type { EChartsOption } from "echarts";
import { NeverExceededGroup } from "./NeverExceededGroup";
import { fleetAnalysis, trendsPanels } from "../lib/fixtures";

// Same stub as EventStrip's own test — no canvas in jsdom.
vi.mock("./EChartBase", () => ({
  EChartBase: (_props: { option: EChartsOption }) => <div data-testid="chart-stub" />,
}));

const neverExceeded = trendsPanels.filter((p) =>
  p.limit_id && p.metrics.every((m) => fleetAnalysis.metrics[m.metric_id]?.readiness?.kind === "no_events"));

describe("NeverExceededGroup", () => {
  it("renders nothing with an empty tier 3", () => {
    const { container } = render(
      <NeverExceededGroup panels={[]} fleet={fleetAnalysis} highlightFlight={null} onOpenFlight={() => {}} />,
    );
    expect(container.firstChild).toBeNull();
  });

  it("shows the count in its header and the flight count once expanded", () => {
    render(
      <NeverExceededGroup panels={neverExceeded} fleet={fleetAnalysis} highlightFlight={null} onOpenFlight={() => {}} />,
    );
    expect(screen.getByText(`Never exceeded (${neverExceeded.length})`)).toBeTruthy();
    fireEvent.click(screen.getByText(`Never exceeded (${neverExceeded.length})`));
    expect(screen.getByText(new RegExp(`${neverExceeded.length} limits never exceeded on ${fleetAnalysis.flight_ids.length} flights`))).toBeTruthy();
  });

  it("one-line rows expand to the event strip, not a full panel", () => {
    render(
      <NeverExceededGroup panels={neverExceeded} fleet={fleetAnalysis} highlightFlight={null} onOpenFlight={() => {}} />,
    );
    fireEvent.click(screen.getByText(`Never exceeded (${neverExceeded.length})`));
    // Row format is "N ticks · never exceeded on N flights" — distinct
    // from the group's own summary caption, which also contains
    // "never exceeded on N flights" but no leading tick count.
    const rows = screen.getAllByText(/ticks? · never exceeded on \d+ flight/);
    expect(rows.length).toBe(neverExceeded.length);
    expect(screen.queryByTestId("chart-stub")).toBeNull();
    // Expand the first row — now its event strip (not a full panel).
    fireEvent.click(rows[0]);
    expect(screen.getByTestId("chart-stub")).toBeTruthy();
  });
});
