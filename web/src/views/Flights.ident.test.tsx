import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, it, expect, vi, beforeEach } from "vitest";
import type { FlightTableRow } from "../types/contract";

// Spec 16 Session F / Spec 03 §5.1: the Flights table shows each flight's
// route, local start with its zone and takeoffs/landings; the pilot names a
// flight in place (flight_set_name); Find a flight asks flights_find and
// shows its candidates best first with what matched. Synthetic flights.

const state = vi.hoisted(() => ({ names: {} as Record<string, string | null>, calls: [] as { op: string; params: unknown }[], identified: false }));

function row(id: string, date: string, extra: Partial<FlightTableRow>): FlightTableRow {
  return {
    flight_id: id, date, airport: "XAA1", duration_min: 60, engine_hours: 100, insight_count: 0, worst_severity: null,
    in_baselines: true, status: "analyzed", filename: `${id}.csv`, log_folder: "/logs", ...extra, name: state.names[id] ?? null,
  };
}

vi.mock("../lib/engineClient", () => {
  const overrides: Record<string, unknown> = {
    getActiveWorkspace: async () => ({ active: true, manifest: { id: "ws", name: "Synthetic", engine_model: "916iS", log_folders: [{ path: "/logs", reachable: true }] } }),
    listFlightsWithStatus: async () => ({ rows: [
      row("fa", "2026-01-03", { route: ["XAA1", "XBB2", "XAA1"], start_local: "2026-01-03T09:12:33-08:00", tz_abbrev: "PST", takeoffs: 3, landings: 3 }),
      row("fb", "2026-01-04", { identified: state.identified, route: [], start_local: null, takeoffs: null, landings: null }),
    ] }),
    listExclusions: async () => ({ entries: [], summary: {} }),
    getScanProgress: async () => ({ active: false }),
    scanWorkspace: async () => ({ new_flight_ids: [], rematched_flight_ids: [], now_missing_flight_ids: [], recovered_flight_ids: [], unreachable_folders: [], excluded: [], reanalyzed_flight_ids: [], auto_excluded: [], pending_new_logs: [], pending_reanalysis_flight_ids: [] }),
    identifyFlights: async () => { state.calls.push({ op: "identify", params: null }); state.identified = true; return 2; },
    flightSetName: async (id: string, name: string | null) => { state.calls.push({ op: "flight_set_name", params: [id, name] }); state.names[id] = name; return { flight_id: id, name, notes: null }; },
    flightsFind: async (description: string) => {
      state.calls.push({ op: "flights_find", params: description });
      return { description, total: 1, candidates: [{ flight_id: "fa", score: 5, matched: ["date 2026-01-03", "3 landings"], local_date: "2026-01-03", start_local: null, route: "XAA1–XBB2–XAA1", takeoffs: 3, landings: 3, name: null }],
        understood: { dates: ["2026-01-03"], months: [], weekdays: [], landings: 3, takeoffs: null, airports: {}, other_words: [] } };
    },
  };
  const client = new Proxy(overrides, { get: (t, prop: string) => t[prop] ?? (async () => { throw new Error(`unmocked ${prop}`); }) });
  return { getEngineClient: () => client };
});

import { Flights } from "./Flights";

beforeEach(() => { state.names = {}; state.calls = []; state.identified = false; });

function renderFlights() {
  render(<MemoryRouter initialEntries={["/flights"]}><Flights /></MemoryRouter>);
}

describe("Flights — route, local time, takeoffs/landings, name, find", () => {
  it("shows the route, the local start with its zone and the counts; the hint airport where no route is known", async () => {
    renderFlights();
    await waitFor(() => expect(screen.getAllByTestId("flight-route-cell").length).toBe(2));
    const [a, b] = screen.getAllByTestId("flight-route-cell").sort((x, y) => (x.textContent! < y.textContent! ? -1 : 1));
    expect(a.textContent).toContain("2026-01-03 09:12 PST · XAA1 – XBB2 – XAA1");
    expect(a.textContent).toContain("3 takeoffs · 3 landings");
    expect(b.textContent).toContain("2026-01-04 · XAA1");
    expect(b.textContent).not.toContain("takeoff");
  });

  it("names a flight in place; Escape cancels", async () => {
    renderFlights();
    await waitFor(() => expect(screen.getAllByTestId("flight-name").length).toBe(2));
    const cell = screen.getAllByTestId("flight-route-cell").find((c) => c.textContent!.includes("XBB2"))!;
    fireEvent.click(within(cell).getByTestId("flight-name"));
    const input = within(cell).getByTestId("flight-name-input");
    fireEvent.change(input, { target: { value: "Pattern work" } });
    fireEvent.keyDown(input, { key: "Enter" });
    await waitFor(() => expect(within(cell).getByTestId("flight-name").textContent).toBe("Pattern work"));
    expect(state.calls).toContainEqual({ op: "flight_set_name", params: ["fa", "Pattern work"] });
    fireEvent.click(within(cell).getByTestId("flight-name"));
    fireEvent.change(within(cell).getByTestId("flight-name-input"), { target: { value: "Other" } });
    fireEvent.keyDown(within(cell).getByTestId("flight-name-input"), { key: "Escape" });
    expect(within(cell).getByTestId("flight-name").textContent).toBe("Pattern work");
    expect(state.calls.filter((c) => c.op === "flight_set_name").length).toBe(1);
  });

  it("Find a flight lists flights_find's candidates with what matched; show all flights clears", async () => {
    renderFlights();
    await waitFor(() => expect(screen.getAllByTestId("flight-route-cell").length).toBe(2));
    fireEvent.change(screen.getByLabelText("Find a flight"), { target: { value: "Jan 3 three landings" } });
    fireEvent.submit(screen.getByTestId("flight-find"));
    await waitFor(() => expect(screen.getAllByTestId("flight-route-cell").length).toBe(1));
    expect(screen.getByTestId("flight-route-cell").textContent).toContain("matched date 2026-01-03, 3 landings");
    expect(screen.getByTestId("flight-find-summary").textContent).toContain("1 flight for “Jan 3 three landings” — read as 2026-01-03, 3 landings");
    fireEvent.click(within(screen.getByTestId("flight-find-summary")).getByText("show all flights"));
    await waitFor(() => expect(screen.getAllByTestId("flight-route-cell").length).toBe(2));
  });

  it("offers to work out the identification of flights stored before it existed", async () => {
    renderFlights();
    const line = await screen.findByTestId("identify-flights");
    expect(line.textContent).toContain("aren't worked out yet for 1 flight");
    fireEvent.click(within(line).getByRole("button"));
    await waitFor(() => expect(screen.queryByTestId("identify-flights")).toBeNull());
    expect(state.calls.some((c) => c.op === "identify")).toBe(true);
  });
});
