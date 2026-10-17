import { render, screen, fireEvent } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, it, expect, vi } from "vitest";
import type { EChartsOption } from "echarts";
import casTrends from "../fixtures/cas-trends.json";
import { NeverExceededGroup } from "../components/NeverExceededGroup";
import { computeTiers } from "../lib/trendsTiers";
import type { FleetAnalysis, FleetMetric, TrendsPanel } from "../types/contract";

// Spec 12 v0.10 G1–G3: a generated CAS panel is the event strip and its
// frequency header only; a duration filter shows as a header note; with
// no events it joins the never-exceeded group. The panel and metric are
// the scrubbed synthetic fixture (web/scripts/gen_cas_fixture.py):
// ENGINE ECU on 2 of 8 flights, a GROUND run in TAXI and an IN_FLIGHT one.

const options: EChartsOption[] = [];
// Offline, deterministically: every call fails as it does with no local
// server — never whatever server happens to be listening on this machine.
vi.mock("../lib/engineClient", async () => {
  const actual = await vi.importActual<typeof import("../lib/engineClient")>("../lib/engineClient");
  const offline = new Proxy({}, { get: () => async () => { throw new TypeError("Failed to fetch"); } });
  return { ...actual, getEngineClient: () => offline };
});

vi.mock("../components/EChartBase", () => ({
  EChartBase: (props: { option: EChartsOption }) => {
    options.push(props.option);
    return <div data-testid="chart-stub" />;
  },
}));

// Offline, Trends falls back to the bundled fleet fixture — add the CAS
// panel (filtered, with a 7 s duration filter) and its metric to it.
vi.mock("../lib/fixtures", async () => {
  const actual = await vi.importActual<typeof import("../lib/fixtures")>("../lib/fixtures");
  const fleetAnalysis = JSON.parse(JSON.stringify(actual.fleetAnalysis));
  fleetAnalysis.metrics.cas_engine_ecu_events = casTrends.metric;
  const panel = { ...casTrends.panel, filtered: true, filter_max_event_s: 7 };
  return { ...actual, fleetAnalysis, trendsPanels: [...actual.trendsPanels, panel] };
});

import { Trends } from "./Trends";

const casPanel = casTrends.panel as TrendsPanel;
const casMetric = casTrends.metric as unknown as FleetMetric;

describe("Trends CAS panel", () => {
  it("with events: strip + frequency header only, filter as a header note, ticks name class and reason", async () => {
    render(
      <MemoryRouter initialEntries={[`/trends?panel=${encodeURIComponent("cas:ENGINE ECU")}`]}>
        <Trends />
      </MemoryRouter>,
    );
    const title = (await screen.findAllByText(/Alert: ENGINE ECU/))[0];
    const panel = title.closest("div[style*='border-radius: 14px']") as HTMLElement;
    expect(panel.textContent).toContain("events ≤ 7 s filtered");
    expect(panel.textContent).toContain("occurred on 2 of 8 recent flights");
    // One chart (the event strip), no magnitude strip.
    expect(panel.querySelectorAll("[data-testid='chart-stub']").length).toBe(1);

    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const strip = options.find((o) => (o.series as any[])?.[0]?.data?.some((d: unknown[]) => String(d[5]).includes("lane-check")));
    expect(strip).toBeDefined();
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const tick = ((strip!.series as any[])[0].data as unknown[][]).find((d) => d[4]);
    expect(tick![5]).toBe("on the ground, engine running (TAXI), 7 s — below the lane-check band<br/>in flight (CRUISE), 6 s");
  });

  it("with no events: never-exceeded group, worded as never seen", () => {
    const quietMetric: FleetMetric = {
      ...casMetric,
      readiness: { kind: "no_events" } as FleetMetric["readiness"],
      events: (casMetric.events ?? []).map((e) => ({ ...e, has_event: false, cas_events: [] })),
    };
    const fleet = { metrics: { cas_engine_ecu_events: quietMetric }, change_summary: [], flight_ids: casTrends.flight_ids } as unknown as FleetAnalysis;
    const { tier3 } = computeTiers([casPanel], fleet);
    expect(tier3.map((p) => p.panel)).toEqual(["cas:ENGINE ECU"]);

    render(<NeverExceededGroup panels={tier3} fleet={fleet} highlightFlight={null} onOpenFlight={() => {}} />);
    fireEvent.click(screen.getByText("Never exceeded (1)"));
    expect(screen.getByText("1 alert never seen on 8 flights.")).toBeTruthy();
    expect(screen.getByText("Alert: ENGINE ECU")).toBeTruthy();
    expect(screen.getByText(/never seen on 8 flights/, { selector: "span" })).toBeTruthy();
  });

  it("with events and no change: tier 2, not the never-exceeded group", () => {
    const fleet = { metrics: { cas_engine_ecu_events: casMetric }, change_summary: [], flight_ids: casTrends.flight_ids } as unknown as FleetAnalysis;
    const { tier2, tier3 } = computeTiers([casPanel], fleet);
    expect(tier2.map((p) => p.panel)).toEqual(["cas:ENGINE ECU"]);
    expect(tier3).toEqual([]);
  });
});
