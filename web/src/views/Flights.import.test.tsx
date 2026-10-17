import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, it, expect, vi, beforeEach } from "vitest";

// Spec 02 v0.11 §7.4–7.5 / Spec 03 v0.19 §5.8 — an imported workspace on
// Flights: the Link-your-logs empty state, the Skipped panel's two import
// reasons, and arriving from the import flow with ?sync=1.

const state = { folders: [] as string[] };
const calls = vi.hoisted(() => ({ scan: vi.fn(), include: vi.fn() }));

vi.mock("../lib/engineClient", () => {
  const overrides: Record<string, unknown> = {
    getActiveWorkspace: async () => ({
      active: true,
      manifest: { id: "ws", name: "N117ZS (imported)", engine_model: "916iS", log_folders: state.folders.map((path) => ({ path, reachable: true })) },
    }),
    listFlightsWithStatus: async () => ({ rows: [] }),
    listExclusions: async () => ({
      entries: [{ filename: "other_1.csv", source: "auto", reason: "Not in the sender's workspace", category: "not_in_sender", excluded_at: "", user_override: false }],
      summary: {},
      sender_missing: [{ flight_id: "m1", date: "2026-05-01", airport_hint: "KAWO", sender_filename: "log_20260501_100000_KAWO.csv", reason: "In the sender's workspace — log not found" }],
    }),
    getImportInfo: async () => ({
      imported: true,
      provenance: { workspace_name: "N117ZS", engine_version: "1.0.0", exported_at: "", logs_included: false, anonymised: false },
      flights: [
        { flight_id: "a", date: "2026-04-08", airport_hint: "KTOA", duration_min: 42, sender_filename: "log_a.csv", found: false },
        { flight_id: "b", date: "2026-04-09", airport_hint: "KSMO", duration_min: 61, sender_filename: "log_b.csv", found: false },
      ],
    }),
    getScanProgress: async () => ({ active: false }),
    scanWorkspace: async (opts: unknown) => {
      calls.scan(opts);
      return { new_flight_ids: [], rematched_flight_ids: [], now_missing_flight_ids: [], recovered_flight_ids: [], unreachable_folders: [],
               excluded: [], reanalyzed_flight_ids: [], auto_excluded: [], pending_new_logs: [], pending_reanalysis_flight_ids: [] };
    },
    includeExcludedLog: async (f: string) => { calls.include(f); return { filename: f, included: true, scan_result: null }; },
  };
  const client = new Proxy(overrides, {
    get: (target, prop: string) => target[prop] ?? (async () => { throw new Error(`unmocked ${prop}`); }),
  });
  return { getEngineClient: () => client };
});

import { Flights } from "./Flights";

function renderAt(url: string) {
  render(<MemoryRouter initialEntries={[url]}><Flights /></MemoryRouter>);
}

describe("Flights — an imported workspace", () => {
  beforeEach(() => {
    state.folders = [];
    Object.values(calls).forEach((f) => f.mockClear());
  });

  it("with no logs linked, says so and lists the sender's flights", async () => {
    renderAt("/flights");
    const empty = await screen.findByTestId("link-logs-empty");
    expect(empty.textContent).toContain("Link your logs to see this workspace's analysis");
    expect(empty.textContent).toContain("Imported from N117ZS");
    expect(empty.textContent).toContain("2026-04-08");
    expect(empty.textContent).toContain("KSMO");
  });

  it("Skipped shows a missing sender flight (no action) and a held-out log (Include)", async () => {
    state.folders = ["/logs"];
    renderAt("/flights");
    fireEvent.click(await screen.findByText("Skipped (2)"));
    const missing = await screen.findByTestId("sender-missing-row");
    expect(missing.textContent).toContain("In the sender's workspace — log not found");
    expect(missing.textContent).toContain("log_20260501_100000_KAWO.csv");
    expect(within(missing).queryByRole("button")).toBeNull();
    expect(screen.getAllByText("Not in the sender's workspace").length).toBeGreaterThan(0);
    fireEvent.click(screen.getByText("Include"));
    await waitFor(() => expect(calls.include).toHaveBeenCalledWith("other_1.csv"));
  });

  it("arriving from the import flow runs Sync's discovery and asks", async () => {
    state.folders = ["/logs"];
    renderAt("/flights?sync=1");
    await waitFor(() => expect(calls.scan).toHaveBeenCalledWith({ analyze: false }));
  });
});
