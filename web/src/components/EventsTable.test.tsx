import { fireEvent, render, screen, within } from "@testing-library/react";
import { describe, it, expect, vi } from "vitest";
import eventsFlight from "../fixtures/flight-events-analysis.json";
import eventsInsights from "../fixtures/flight-events-insights.json";
import casFlight from "../fixtures/flight-cas-analysis.json";
import casInsights from "../fixtures/flight-cas-insights.json";
import { buildEventRows, EVENT_GLYPH } from "../lib/flightEvents";
import type { CasEvent, FlightAnalysis, InsightSet } from "../types/contract";

vi.mock("../lib/engineClient", () => ({ getEngineClient: () => ({}) }));

import { EventsTable, type EventsTableProps } from "./EventsTable";

// Spec 03 v0.16 §5.2 / Spec 09 v0.19 §12.1 — the Events section. The
// "real-shaped" fixture (web/scripts/gen_cas_fixture.py, synthetic): four
// fuel-pressure events (three inside a +1.5 psi filter, one beyond it),
// one oil-temperature event, one ENGINE ECU GROUND run in TAXI.

const efa = eventsFlight as unknown as FlightAnalysis;
const eis = eventsInsights as unknown as InsightSet;

function table(fa: FlightAnalysis, iset: InsightSet, extra: Partial<EventsTableProps> = {}) {
  const rows = buildEventRows(fa, iset);
  const props: EventsTableProps = {
    rows, flightId: fa.flight_id, activeEventId: null, interactive: true, annotations: [],
    filterSummaryById: { flt_fuel_press: "up to +1.5 psi" },
    ecuRuns: fa.ecu_runs, casEvents: fa.exceedances.filter((e): e is CasEvent => (e as CasEvent).source === "cas"),
    onOpen: vi.fn(), onSaveNote: vi.fn(), onDeleteNote: vi.fn(), onFilterSaved: vi.fn(), ...extra,
  };
  render(<EventsTable {...props} />);
  return { rows, props };
}

describe("Events table", () => {
  it("is one chronological list of both sources, numbered like the chart markers", () => {
    const rows = buildEventRows(efa, eis);
    expect(rows.map((r) => r.source)).toEqual(["cas", "limit", "limit", "limit", "limit", "limit"]);
    expect(rows.map((r) => r.n)).toEqual([1, 2, 3, 4, 5, 6]);
    const times = rows.map((r) => r.elapsed_s ?? 0);
    expect([...times].sort((a, b) => a - b)).toEqual(times);
    expect(EVENT_GLYPH).toEqual({ limit: "▲", cas: "◆" });
  });

  it("collapses filtered events to one line per target, expandable; the breach is a normal row marked beyond your filter", () => {
    table(efa, eis);
    const group = screen.getByTestId("filtered-group");
    expect(group.textContent).toContain("3 Fuel pressure maximum events within your filter: up to +1.5 psi");
    // Visible rows: the ENGINE ECU event, the fuel-pressure breach, the oil-temperature event.
    let visible = screen.getAllByTestId("event-row");
    expect(visible.map((r) => r.firstElementChild?.textContent)).toEqual(["◆1", "▲5", "▲6"]);
    const breach = visible[1];
    expect(within(breach).getByText("beyond your filter")).toBeTruthy();
    expect(within(breach).getByText("+3.5 psi")).toBeTruthy();
    fireEvent.click(within(group).getByRole("button"));
    visible = screen.getAllByTestId("event-row");
    expect(visible.map((r) => r.firstElementChild?.textContent)).toEqual(["◆1", "▲2", "▲3", "▲4", "▲5", "▲6"]);
  });

  it("gives limit and CAS rows the same actions, with the right filter wording", () => {
    table(efa, eis);
    const [cas, breach, oil] = screen.getAllByTestId("event-row");
    expect(within(cas).getByText("Filter this alert…")).toBeTruthy();
    expect(within(breach).getByText("Edit filter…")).toBeTruthy();
    expect(within(oil).getByText("Filter this limit…")).toBeTruthy();
    for (const row of [cas, breach, oil]) {
      expect(within(row).getByText("Chart")).toBeTruthy();
      expect(within(row).getByText("Add a note")).toBeTruthy();
    }
    expect(within(cas).getByText("Filter this alert…").getAttribute("title")).toBe("All flights in this workspace — this alert");
    expect(within(oil).getByText("Filter this limit…").getAttribute("title")).toBe("All flights in this workspace — this limit");
    expect(within(cas).getByText(/below the lane-check band \(4,000 ± 500\)/)).toBeTruthy();
  });

  it("opens a row on the chart, and expands a CAS row to its context and the flight's runs by class", () => {
    const { props } = table(casFlight as unknown as FlightAnalysis, casInsights as unknown as InsightSet);
    const [ground, inflight] = screen.getAllByTestId("event-row");
    expect(inflight.textContent).toContain("CRUISE");
    fireEvent.click(within(ground).getByText("Chart"));
    expect(props.onOpen).toHaveBeenCalledWith(expect.objectContaining({ source: "cas", n: 1 }));
    fireEvent.click(ground);
    expect(screen.getByText(/on the ground, engine running \(1\)/)).toBeTruthy();
    expect(screen.getByText(/in flight \(1\)/)).toBeTruthy();
  });

  it("has one line when the flight has no events", () => {
    table({ ...efa, exceedances: [] }, eis);
    expect(screen.getByText("No events on this flight")).toBeTruthy();
    expect(screen.queryByRole("table")).toBeNull();
  });

  it("scrolls horizontally rather than wrapping", () => {
    table(efa, eis);
    expect(screen.getByTestId("events-scroll").style.overflowX).toBe("auto");
    expect(screen.getAllByTestId("event-row")[0].querySelector("td")!.style.whiteSpace).toBe("nowrap");
  });
});
