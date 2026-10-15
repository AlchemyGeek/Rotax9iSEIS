import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, it, expect, vi, beforeEach } from "vitest";
import type { FlightTableRow, ScanOptions } from "../types/contract";

// Spec 03 v0.17 §5.1 — adding logs, and Sync asking before it analyses.
// The mocked server keeps a tiny workspace: folders, analysed flights, and
// what's waiting (new logs in a folder, flights analysed by an older engine).

type Log = { source_key: string; filename: string };
const state: { folders: string[]; flights: FlightTableRow[]; newLogs: Log[]; stale: string[] } = {
  folders: [], flights: [], newLogs: [], stale: [],
};
const calls = vi.hoisted(() => ({ scan: vi.fn(), importFiles: vi.fn() }));

function flightRow(id: string, date: string, status: FlightTableRow["status"] = "analyzed"): FlightTableRow {
  return {
    flight_id: id, date, airport: "KAWO", duration_min: 60, engine_hours: 100, insight_count: 1, worst_severity: "watch",
    in_baselines: true, status, filename: `log_${date.replace(/-/g, "")}_120000_KAWO.csv`, log_folder: "/logs",
  };
}

function rows(): FlightTableRow[] {
  return [
    ...state.flights.map((f) => (state.stale.includes(f.flight_id!) ? { ...f, status: "needs_reanalysis" as const } : f)),
    ...state.newLogs.map((l): FlightTableRow => ({
      flight_id: null, source_key: l.source_key, date: l.filename.replace(/^log_(\d{4})(\d{2})(\d{2})_.*/, "$1-$2-$3"), airport: "—",
      duration_min: null, engine_hours: null, insight_count: null, worst_severity: null, in_baselines: null,
      status: "needs_analysis", filename: l.filename, log_folder: "/logs",
    })),
  ];
}

vi.mock("../lib/engineClient", () => {
  const overrides: Record<string, unknown> = {
    getActiveWorkspace: async () => ({
      active: true,
      manifest: { id: "ws", name: "N117ZS", engine_model: "916iS", log_folders: state.folders.map((path) => ({ path, reachable: true })) },
    }),
    listFlightsWithStatus: async () => ({ rows: rows() }),
    listExclusions: async () => ({ entries: [], summary: {} }),
    getScanProgress: async () => ({ active: false }),
    scanWorkspace: async (opts: ScanOptions = {}) => {
      calls.scan(opts);
      const empty = { new_flight_ids: [], rematched_flight_ids: [], now_missing_flight_ids: [], recovered_flight_ids: [], unreachable_folders: [], excluded: [], reanalyzed_flight_ids: [], auto_excluded: [] };
      if (opts.analyze === false) {
        return { ...empty, pending_new_logs: state.newLogs.map((l) => ({ ...l, log_folder: "/logs", relative_path: l.filename, date: null })), pending_reanalysis_flight_ids: [...state.stale] };
      }
      const take = opts.source_keys ? state.newLogs.filter((l) => opts.source_keys!.includes(l.source_key)) : state.newLogs;
      const redo = opts.flight_ids ? state.stale.filter((id) => opts.flight_ids!.includes(id)) : state.stale;
      const added = take.map((l, i) => flightRow(`new_${l.source_key}`, `2026-03-0${i + 1}`));
      state.flights.push(...added);
      state.newLogs = state.newLogs.filter((l) => !take.includes(l));
      state.stale = state.stale.filter((id) => !redo.includes(id));
      return { ...empty, new_flight_ids: added.map((f) => f.flight_id), reanalyzed_flight_ids: redo, pending_new_logs: [], pending_reanalysis_flight_ids: [] };
    },
    importFiles: async (files: { filename: string }[]) => {
      calls.importFiles(files.map((f) => f.filename));
      state.flights.push(flightRow(`up_${files[0].filename}`, "2026-04-01"));
      return { results: [{ filename: files[0].filename, classification: "new" }], flight_count: state.flights.length, fleet_key: "k" };
    },
  };
  const client = new Proxy(overrides, {
    get: (target, prop: string) => target[prop] ?? (async () => { throw new Error(`unmocked ${prop}`); }),
  });
  return { getEngineClient: () => client };
});

import { Flights, DROP_PROMPT_THRESHOLD } from "./Flights";

function renderFlights() {
  render(<MemoryRouter initialEntries={["/flights"]}><Flights /></MemoryRouter>);
}

function logFile(name: string) {
  return { name, arrayBuffer: async () => new ArrayBuffer(4) } as unknown as File;
}

describe("Flights — adding logs and Sync consent", () => {
  beforeEach(() => {
    calls.scan.mockClear();
    calls.importFiles.mockClear();
    state.folders = ["/logs"];
    state.flights = [flightRow("f1", "2026-02-01"), flightRow("f2", "2026-02-02")];
    state.newLogs = [];
    state.stale = [];
  });

  it("shows the onboarding drop panel only while the workspace has no folders", async () => {
    state.folders = [];
    renderFlights();
    expect(await screen.findByTestId("onboarding-drop")).toBeTruthy();
    expect(screen.queryByText("Add logs…")).toBeNull();
  });

  it("with a folder: no drop panel, Add logs… beside Sync", async () => {
    renderFlights();
    expect(await screen.findByText("Add logs…")).toBeTruthy();
    expect(screen.queryByTestId("onboarding-drop")).toBeNull();
    fireEvent.click(screen.getByText("Add logs…"));
    expect(screen.getByRole("menuitem", { name: "Choose log files…" })).toBeTruthy();
    expect(screen.getByRole("menuitem", { name: "Add a folder…" })).toBeTruthy();
  });

  it("Sync with nothing to do says No changes", async () => {
    renderFlights();
    fireEvent.click(await screen.findByText("Sync"));
    expect(await screen.findByText("No changes.")).toBeTruthy();
    expect(calls.scan).toHaveBeenCalledWith({ analyze: false });
  });

  it("Sync with new and stale work asks; Not now leaves Needs analysis / Needs re-analysis rows and Analyze N", async () => {
    state.newLogs = [{ source_key: "k1", filename: "log_20260310_120000_KAWO.csv" }, { source_key: "k2", filename: "log_20260311_120000_KAWO.csv" }];
    state.stale = ["f1"];
    renderFlights();
    fireEvent.click(await screen.findByText("Sync"));
    const prompt = await screen.findByRole("dialog", { name: "Analyze now?" });
    expect(prompt.textContent).toContain("Found 2 new logs and 1 flight needing re-analysis. Analyze now?");
    fireEvent.click(within(prompt).getByText("Not now"));
    expect(screen.queryByRole("dialog")).toBeNull();
    expect(screen.getAllByText("Needs analysis").length).toBeGreaterThan(0);
    expect(screen.getByRole("button", { name: "Needs analysis (2)" })).toBeTruthy();
    expect(screen.getAllByText("Needs re-analysis").length).toBeGreaterThan(0);
    expect(screen.getByRole("button", { name: "Analyze 3" })).toBeTruthy();
    // A Needs-analysis row: date from the file name, — for results.
    const pending = screen.getAllByTestId("pending-row")[0];
    expect(pending.textContent).toMatch(/^2026-03-1[01] · —/);
    // Nothing was analysed.
    expect(calls.scan).toHaveBeenCalledTimes(1);
  });

  it("Analyze now runs the batch with a progress banner; rows become Analyzed", async () => {
    state.newLogs = [{ source_key: "k1", filename: "log_20260310_120000_KAWO.csv" }];
    state.stale = ["f2"];
    renderFlights();
    fireEvent.click(await screen.findByText("Sync"));
    fireEvent.click(within(await screen.findByRole("dialog", { name: "Analyze now?" })).getByText("Analyze now"));
    expect(screen.getByTestId("flights-banner").textContent).toMatch(/Analyzing|1 new flight/);
    expect(await screen.findByText("1 new flight analyzed")).toBeTruthy();
    expect(screen.getByText("1 re-analyzed")).toBeTruthy();
    expect(calls.scan).toHaveBeenLastCalledWith({});
    expect(screen.queryAllByTestId("pending-row")).toHaveLength(0);
    expect(screen.queryByText("Needs re-analysis")).toBeNull();
    expect(screen.queryByRole("button", { name: /^Analyze \d+$/ })).toBeNull();
  });

  it("a Needs-analysis row offers Analyze this flight instead of opening the Flight view", async () => {
    state.newLogs = [{ source_key: "k9", filename: "log_20260312_120000_KAWO.csv" }];
    renderFlights();
    fireEvent.click(await screen.findByTestId("pending-row"));
    fireEvent.click(screen.getByText("Analyze this flight"));
    await waitFor(() => expect(calls.scan).toHaveBeenCalledWith({ source_keys: ["k9"], flight_ids: [] }));
    await waitFor(() => expect(screen.queryAllByTestId("pending-row")).toHaveLength(0));
  });

  it(`a single dropped file analyses at once; ${DROP_PROMPT_THRESHOLD} or more ask first`, async () => {
    renderFlights();
    const page = await screen.findByTestId("flights-page");
    await act(async () => {
      fireEvent.drop(page, { dataTransfer: { files: [logFile("log_20260401_120000_KAWO.csv")] } });
    });
    await waitFor(() => expect(calls.importFiles).toHaveBeenCalledWith(["log_20260401_120000_KAWO.csv"]));
    expect(screen.queryByRole("dialog", { name: "Analyze now?" })).toBeNull();

    const many = Array.from({ length: DROP_PROMPT_THRESHOLD }, (_, i) => logFile(`log_2026050${i + 1}_120000_KAWO.csv`));
    fireEvent.drop(page, { dataTransfer: { files: many } });
    const prompt = await screen.findByRole("dialog", { name: "Analyze now?" });
    expect(prompt.textContent).toContain(`Found ${DROP_PROMPT_THRESHOLD} new logs. Analyze now?`);
    fireEvent.click(within(prompt).getByText("Not now"));
    expect(screen.getAllByTestId("pending-row")).toHaveLength(DROP_PROMPT_THRESHOLD);
    expect(calls.importFiles).toHaveBeenCalledTimes(1);
  });
});
