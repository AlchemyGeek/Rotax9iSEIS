import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter, Route, Routes, useParams } from "react-router-dom";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { ChartSessionProvider } from "../lib/chartSession";
import casFlight from "../fixtures/flight-cas-analysis.json";

// Spec 03 v0.16 §5.9 — Log preview: a skipped log's own page, read-only,
// with one action (Include this log). The previewed log is the synthetic
// CAS fixture (one GROUND and one IN_FLIGHT ENGINE ECU run).

(globalThis as unknown as { ResizeObserver: unknown }).ResizeObserver = class {
  observe() {}
  unobserve() {}
  disconnect() {}
};
vi.mock("../components/ChannelTimeline", () => ({ ChannelTimeline: () => null }));

const FILE = "log_20260108_120000_TEST.csv";
const entry = {
  filename: FILE, source: "auto", reason: "never left the ground", category: "ground_session",
  excluded_at: "2026-01-08T00:00:00Z", user_override: false, duration_min: 14,
};
const { includeExcludedLog, previewExcludedLog } = vi.hoisted(() => ({ includeExcludedLog: vi.fn(), previewExcludedLog: vi.fn() }));

vi.mock("../lib/engineClient", () => {
  const overrides: Record<string, unknown> = {
    previewExcludedLog,
    getChannelRegistry: async () => ({ channels: [], slot_groups: [], max_chart_slots: 6 }),
    getChartPresets: async () => ({ presets: [] }),
    getAppSettings: async () => ({}),
    listExclusions: async () => ({ entries: [entry], summary: { ground_session: 1, short_flight: 0, corrupt_log: 0, user_defined: 0 } }),
    getActiveWorkspace: async () => ({ active: true, manifest: { log_folders: [{ path: "/logs/n999xx", reachable: true }] } }),
    getExcludedLogSeries: async () => { throw new Error("no series in this test"); },
    listFlightsWithStatus: async () => ({ rows: [] }),
    includeExcludedLog,
  };
  const client = new Proxy(overrides, {
    get: (target, prop: string) => target[prop] ?? (async () => { throw new Error(`unmocked ${prop}`); }),
  });
  return { getEngineClient: () => client };
});

import { LogPreview } from "./LogPreview";
import { Flights } from "./Flights";

function FlightStub() {
  const { flightId } = useParams();
  return <div>flight page {flightId}</div>;
}

function renderAt(path: string) {
  render(
    <MemoryRouter initialEntries={[path]}>
      <ChartSessionProvider>
        <Routes>
          <Route path="/flights" element={<Flights />} />
          <Route path="/flights/:flightId" element={<FlightStub />} />
          <Route path="/logs/:logKey" element={<LogPreview />} />
        </Routes>
      </ChartSessionProvider>
    </MemoryRouter>,
  );
}

describe("Log preview", () => {
  beforeEach(() => {
    previewExcludedLog.mockReset().mockResolvedValue({ flight_analysis: casFlight, source_filename: FILE });
    includeExcludedLog.mockReset();
  });

  it("shows the header, the timeline, CAS alerts and ENGINE ECU runs by class with the blip count — nothing analysed", async () => {
    renderAt(`/logs/${encodeURIComponent(FILE)}`);
    const header = await screen.findByTestId("log-header");
    await waitFor(() => expect(header.textContent).toContain("never left the ground (auto-detected)"));
    expect(header.textContent).toContain("Folder: /logs/n999xx");
    expect(header.textContent).toContain("Aircraft: N999XX");
    expect(header.textContent).toContain("Engine hours: 20.1");
    expect(screen.getByText("Timeline")).toBeTruthy();
    const ecu = screen.getByTestId("log-ecu-runs");
    expect(ecu.textContent).toContain("on the ground, engine running (1)");
    expect(ecu.textContent).toContain("in flight (1)");
    expect(ecu.textContent).toMatch(/\d+ brief blips? not counted/);
    expect(screen.queryByText(/Insights/)).toBeNull();
    expect(screen.queryByText("Events")).toBeNull();
    expect(screen.queryByText(/Edit rules/)).toBeNull();
  });

  it("names the format, and for a resampled AXIS log the filled-row share (Spec 03 v0.22 §5.9)", async () => {
    previewExcludedLog.mockResolvedValue({ flight_analysis: casFlight, source_filename: FILE, source_format: "axis", filled_share: 0.161 });
    renderAt(`/logs/${encodeURIComponent(FILE)}`);
    const fmt = await screen.findByTestId("log-format");
    expect(fmt.textContent).toBe("Format: AXIS · resampled to 1 s, 16% of rows filled");
  });

  it("a G3X log says G3X and nothing about filling", async () => {
    previewExcludedLog.mockResolvedValue({ flight_analysis: casFlight, source_filename: FILE, source_format: "g3x_direct", filled_share: 0 });
    renderAt(`/logs/${encodeURIComponent(FILE)}`);
    expect((await screen.findByTestId("log-format")).textContent).toBe("Format: G3X");
  });

  it("Include this log asks for confirmation and a reason, includes, then opens the new flight", async () => {
    includeExcludedLog.mockResolvedValue({ filename: FILE, included: true, scan_result: { new_flight_ids: ["f_new"] } });
    renderAt(`/logs/${encodeURIComponent(FILE)}`);
    fireEvent.click(await screen.findByRole("button", { name: "Include this log" }));
    const dialog = screen.getByRole("dialog", { name: "Include this log" });
    fireEvent.change(within(dialog).getByLabelText("Reason"), { target: { value: "a real test flight" } });
    fireEvent.click(within(dialog).getByRole("button", { name: "Include" }));
    await screen.findByText("flight page f_new");
    expect(includeExcludedLog).toHaveBeenCalledWith(FILE, "a real test flight");
  });

  it("is where a skipped log's row in Flights leads", async () => {
    renderAt("/flights");
    fireEvent.click(await screen.findByText("Skipped (1)"));
    fireEvent.click(await screen.findByText(FILE));
    await screen.findByTestId("log-header");
    expect(previewExcludedLog).toHaveBeenCalledWith(FILE);
  });
});
