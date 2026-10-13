import { render, screen, fireEvent, within } from "@testing-library/react";
import { MemoryRouter, Routes, Route } from "react-router-dom";
import { describe, it, expect, vi } from "vitest";
import { ChartSessionProvider } from "../lib/chartSession";
import casFlight from "../fixtures/flight-cas-analysis.json";
import casInsights from "../fixtures/flight-cas-insights.json";
import casProposal from "../fixtures/cas-filter-proposal.json";

// Spec 10 D19 / Spec 03 §5.2 v0.14: ENGINE ECU runs are CAS event rows in
// the limits topic's event list. The flight is the scrubbed synthetic
// fixture (web/scripts/gen_cas_fixture.py): one GROUND run in TAXI at
// 2,550 rpm (below the lane-check band) and one IN_FLIGHT run in cruise.

(globalThis as unknown as { ResizeObserver: unknown }).ResizeObserver = class {
  observe() {}
  unobserve() {}
  disconnect() {}
};
vi.mock("../components/ChannelTimeline", () => ({ ChannelTimeline: () => null }));

const proposeFilter = vi.fn(async () => casProposal);

vi.mock("../lib/engineClient", () => {
  const overrides: Record<string, unknown> = {
    getFlight: async () => ({ flight_analysis: casFlight, insight_set: casInsights, reference_state: null, reference_changes: [] }),
    getChannelRegistry: async () => ({ channels: [], slot_groups: [], max_chart_slots: 6 }),
    getChartPresets: async () => ({ presets: [] }),
    getAppSettings: async () => ({}),
    getWorkspaceRules: async () => ({ rules: null, shipped_rules: null }),
    listAnnotations: async () => ({ annotations: [] }),
    getFlightSeries: async () => { throw new Error("no series in this test"); },
    proposeFilter: (...args: unknown[]) => (proposeFilter as (...a: unknown[]) => unknown)(...args),
  };
  // Anything else (help, aircraft summary, nav badges) fails quietly —
  // each caller already treats an unreachable server as "nothing".
  const client = new Proxy(overrides, {
    get: (target, prop: string) => target[prop] ?? (async () => { throw new Error(`unmocked ${prop}`); }),
  });
  return { getEngineClient: () => client };
});

import { FlightView } from "./FlightView";

function renderFlight() {
  render(
    <MemoryRouter initialEntries={[`/flights/${casFlight.flight_id}`]}>
      <ChartSessionProvider>
        <Routes>
          <Route path="/flights/:flightId" element={<FlightView />} />
        </Routes>
      </ChartSessionProvider>
    </MemoryRouter>,
  );
}

describe("FlightView CAS events", () => {
  it("lists both ENGINE ECU events as rows naming class and reason, with the lane-check line", async () => {
    renderFlight();
    const card = (await screen.findByText(/ENGINE ECU, 2 events/)).closest("a, div") as HTMLElement;
    expect(card).toBeTruthy();
    fireEvent.click(screen.getByText(/Show 2 events/));
    expect(screen.getByText("ENGINE ECU · TAXI · 2,550 rpm — below the lane-check band (4,000 ± 500)")).toBeTruthy();
    expect(screen.getByText("ENGINE ECU · in flight · CRUISE · 5,000 rpm")).toBeTruthy();
    expect(screen.getByTestId("lane-check-line").textContent).toBe("Lane check: not detected");
  });

  it("expands to the alert context and the flight's ECU runs by class", async () => {
    renderFlight();
    fireEvent.click(await screen.findByTestId("cas-details-toggle"));
    expect(screen.getByText(/on the ground, engine running \(1\)/)).toBeTruthy();
    expect(screen.getByText(/in flight \(1\)/)).toBeTruthy();
  });

  it("offers a duration-only filter on the alert, pre-filled from the proposal", async () => {
    renderFlight();
    fireEvent.click(await screen.findByText("Filter by duration…"));
    expect(proposeFilter).toHaveBeenCalledWith({ kind: "cas", cas_id: "ENGINE ECU" });
    const editor = (await screen.findByText(/Filter this alert/)).parentElement!.parentElement as HTMLElement;
    expect(within(editor).getAllByText(/ENGINE ECU \(alert\)/).length).toBeGreaterThan(0);
    expect(within(editor).queryByText(/A little past the limit is fine/)).toBeNull();
    expect(within(editor).getByText("Brief alerts are fine, lasting up to")).toBeTruthy();
    expect((within(editor).getByRole("spinbutton") as HTMLInputElement).value).toBe("7");
    expect(within(editor).getByText(/All flights in this workspace/)).toBeTruthy();
  });
});
