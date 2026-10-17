import { fireEvent, render, screen, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, it, expect, vi } from "vitest";

// Spec 03 §5.1 "Unreadable": a log the app couldn't read shows that status
// and why — not "Needs analysis", and with no "Analyze this flight" offer.

vi.mock("../lib/engineClient", () => {
  const overrides: Record<string, unknown> = {
    getActiveWorkspace: async () => ({
      active: true, manifest: { id: "ws", name: "W", engine_model: "916iS", log_folders: [{ path: "/logs", reachable: true }] },
    }),
    listFlightsWithStatus: async () => ({ rows: [{
      flight_id: null, source_key: "k1", date: "", airport: "—", duration_min: null, engine_hours: null,
      insight_count: null, worst_severity: null, in_baselines: null, status: "unreadable",
      unreadable_reason: "Format not recognised — not a Garmin G3X engine log this app can read.",
      filename: "export_from_other_avionics.csv", log_folder: "/logs",
    }, {
      flight_id: "f_axis", source_key: "k2", date: "2026-10-14", airport: "—", duration_min: 45, engine_hours: 119.6,
      insight_count: 0, worst_severity: null, in_baselines: true, status: "analyzed",
      filename: "e5d43072-axis.csv", log_folder: "/logs", source_format: "axis",
    }] }),
    listExclusions: async () => ({ entries: [], summary: {} }),
    getImportInfo: async () => ({ imported: false }),
    getScanProgress: async () => ({ active: false }),
  };
  const client = new Proxy(overrides, {
    get: (target, prop: string) => target[prop] ?? (async () => { throw new Error(`unmocked ${prop}`); }),
  });
  return { getEngineClient: () => client };
});

import { Flights } from "./Flights";

describe("Flights — an unreadable log", () => {
  it("says it's unreadable and why, with nothing to analyse", async () => {
    render(<MemoryRouter initialEntries={["/flights"]}><Flights /></MemoryRouter>);
    const row = await screen.findByTestId("unreadable-row");
    expect(row.textContent).toContain("Unreadable");
    expect(row.textContent).toContain("Format not recognised — not a Garmin G3X engine log this app can read.");
    expect(row.textContent).toContain("export_from_other_avionics.csv");
    expect(row.textContent).not.toContain("Needs analysis");
    fireEvent.click(row);
    expect(within(row).queryByText("Analyze this flight")).toBeNull();
  });

  it("names the log's format in the Source column (Spec 03 v0.22 §5.1)", async () => {
    render(<MemoryRouter initialEntries={["/flights"]}><Flights /></MemoryRouter>);
    expect((await screen.findByTestId("source-format")).textContent).toBe("AXIS");
  });
});
