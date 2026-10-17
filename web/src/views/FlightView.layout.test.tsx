import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { describe, it, expect, vi } from "vitest";
import { ChartSessionProvider } from "../lib/chartSession";
import eventsFlight from "../fixtures/flight-events-analysis.json";
import eventsInsights from "../fixtures/flight-events-insights.json";
import rules from "../fixtures/insight-rules.json";

// Spec 03 v0.16 §5.2 / Spec 14 v0.9 §7.3 — the restructured Flight view
// on the synthetic Events fixture flight, live mode (server mocked).

(globalThis as unknown as { ResizeObserver: unknown }).ResizeObserver = class {
  observe() {}
  unobserve() {}
  disconnect() {}
};
vi.mock("../components/ChannelTimeline", () => ({ ChannelTimeline: () => null }));

const { applyCardRuleEdit } = vi.hoisted(() => ({ applyCardRuleEdit: vi.fn() }));

vi.mock("../lib/engineClient", () => {
  const overrides: Record<string, unknown> = {
    getFlight: async () => ({ flight_analysis: eventsFlight, insight_set: eventsInsights, reference_state: { excluded: false }, reference_changes: [] }),
    getChannelRegistry: async () => ({ channels: [], slot_groups: [], max_chart_slots: 6 }),
    getChartPresets: async () => ({ presets: [] }),
    getAppSettings: async () => ({}),
    getWorkspaceRules: async () => ({ rules, shipped_rules: rules }),
    listAnnotations: async () => ({ annotations: [] }),
    listFilters: async () => ({ filters: [{ filter: { id: "flt_fuel_press" }, summary: "up to +1.5 psi" }] }),
    getFlightSeries: async () => { throw new Error("no series in this test"); },
    whatIfRules: async () => ({ flights: {} }),
    applyCardRuleEdit,
  };
  const client = new Proxy(overrides, {
    get: (target, prop: string) => target[prop] ?? (async () => { throw new Error(`unmocked ${prop}`); }),
  });
  return { getEngineClient: () => client };
});

import { FlightView } from "./FlightView";

function renderFlight() {
  render(
    <MemoryRouter initialEntries={[`/flights/${eventsFlight.flight_id}`]}>
      <ChartSessionProvider>
        <Routes>
          <Route path="/flights/:flightId" element={<FlightView />} />
        </Routes>
      </ChartSessionProvider>
    </MemoryRouter>,
  );
}

async function ready() {
  renderFlight();
  await screen.findByText(/Oil temp maximum: 1 event/);
  await screen.findByTestId("filtered-group");
}

describe("Flight view layout (v0.16)", () => {
  it("has a labelled Flight facts row, an Events section between the chart and the cards, and no 'nothing to flag' line", async () => {
    await ready();
    const facts = screen.getByTestId("flight-facts");
    expect(facts.textContent).toMatch(/^Flight facts/);
    expect([...facts.querySelectorAll("[data-fact]")].map((n) => n.getAttribute("data-fact")))
      .toEqual(["fuel_burned", "cruise_nmpg", "cruise_fuel_flow", "lane_check"]);
    const main = screen.getByTestId("flight-main");
    const headings = within(main).getAllByRole("heading").map((h) => h.textContent);
    expect(headings).toEqual(["Events", "Analysis"]);
    expect(main.firstElementChild?.id).toBe("timeline");
    expect(document.body.textContent).not.toMatch(/nothing to flag/i);
  });

  it("the limit_exceedances card is its sentence and badge only — no event rows", async () => {
    await ready();
    const card = screen.getByTestId("card-limit_exceedances");
    expect(card.textContent).toContain("2 OM limits exceeded this flight (5 events, 3 within your filters); 1 alert event.");
    expect(within(card).queryAllByTestId("event-row")).toHaveLength(0);
  });

  it("collapses a topic with nothing to say to a roster line, expandable by tap", async () => {
    await ready();
    const line = screen.getByTestId("roster-coolant_temp_peak");
    expect(line.textContent).toContain("Coolant temperature data not available.");
    expect(within(line).queryByText("Edit rules…")).toBeNull();
    fireEvent.click(line);
    expect(within(screen.getByTestId("roster-coolant_temp_peak")).getByText("Edit rules…")).toBeTruthy();
  });

  it("renders no input, select or submit button while the rule editor is closed", async () => {
    await ready();
    expect(document.querySelectorAll("input, select, textarea, button[type=submit]")).toHaveLength(0);
  });

  it("opens the editor panel from a card's Edit rules… and restores the scroll position on close", async () => {
    await ready();
    const main = screen.getByTestId("flight-main");
    main.scrollTop = 240;
    const card = screen.getByTestId("card-limit_exceedances");
    fireEvent.click(within(card).getByText("Edit rules…"));
    const dialog = screen.getByRole("dialog", { name: /Edit rules/ });
    expect(dialog.querySelectorAll("input, select").length).toBeGreaterThan(0);
    main.scrollTop = 0;
    fireEvent.click(within(dialog).getByRole("button", { name: "Cancel" }));
    expect(screen.queryByRole("dialog")).toBeNull();
    await waitFor(() => expect(main.scrollTop).toBe(240));
    expect(document.querySelectorAll("input, select").length).toBe(0);
  });

  it("opens the same panel from an insight card's Edit trigger ↓", async () => {
    await ready();
    fireEvent.click(screen.getAllByText("Edit trigger ↓")[0]);
    expect(screen.getByRole("dialog", { name: /Edit rules: / })).toBeTruthy();
  });

  it("a clicked limit insight highlights its Events row", async () => {
    await ready();
    const insight = screen.getByText(/Oil temp maximum: 1 event/);
    fireEvent.click(insight);
    const row = document.querySelector('[data-event-id="oil_temp_max@2026-02-08T12:09:16"]') as HTMLElement;
    expect(row.style.background).not.toBe("");
  });
});
