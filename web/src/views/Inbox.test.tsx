import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter, Route, Routes, useLocation } from "react-router-dom";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { resetCapabilities } from "../lib/capabilities";

// Spec 16 §6 (D5, D8) — the inbox on Research home, both tiers: candidates
// with their evidence, sensitivity and status; Run the question by hand;
// Mark nothing here / watch / acted with a note; the linked study opens;
// the install invitation where there is no bench. Synthetic candidates.

const FA = "aaaaaaaaaaaaaaaa", FB = "bbbbbbbbbbbbbbbb";
const state = vi.hoisted(() => ({ bench: true, calls: [] as { op: string; params: unknown }[], candidates: [] as Record<string, unknown>[] }));

function candidate(id: string, extra: Record<string, unknown> = {}) {
  return {
    id, key: "full_power:rpm.period", preset: "full_power", preset_name: "Full-power segment", kind: "recurring", descriptors: ["rpm.period"],
    fired: { rule: "prominent rpm period in a governed-rpm preset", hits: 8, of: 10, n: 6, m: 10 },
    summary: "Full-power segment: RPM repeats with a prominent period in 8 of the last 10 slices (median period 3.7 s, swing 170 rpm).",
    evidence: { columns: ["slice_id", "flight", "date", "source", "rpm.period_s", "rpm.swing"], rows: [
      [`${FA}:r1:600-660`, FA, "2026-01-02", "G3X", 3.7, 170], [`${FB}:r1:900-950`, FB, "2026-01-03", "AXIS", 3.6, 180]] },
    slices: [`${FA}:r1:600-660`, `${FB}:r1:900-950`], window: { flight_ids: [FA, FB] },
    status: "new", sensitivity: "normal", parameters: { n: 6, m: 10, shift_z: 3.0, group_z: 2.25 },
    created: "2026-01-04T00:00:00Z", last_seen: "2026-01-04T00:00:00Z", holds: true, study_id: null, note: null, resolved_at: null, ...extra,
  };
}

vi.mock("../lib/engineClient", async () => {
  const actual = await vi.importActual<typeof import("../lib/engineClient")>("../lib/engineClient");
  const rec = (op: string, params: unknown) => state.calls.push({ op, params });
  const overrides: Record<string, unknown> = {
    getCapabilities: async () => ({ host: state.bench ? "server" : "browser", engine_version: "1.0.2", host_version: "1.0.2", features: { research: true, investigations: true, bench: state.bench } }),
    getActiveWorkspace: async () => ({ active: true, manifest: { id: "ws", name: "Sample", log_folders: [] } }),
    listWorkspaces: async () => [],
    filterHealth: async () => ({ health: [], attention_count: 0 }),
    getFleet: async () => ({ shift_history: [] }),
    listStudies: async () => ({ studies: [] }),
    listSlicePresets: async () => ({ presets: [], phase_rules: [], engine: "916iS", status: "measured", note: null }),
    listFlights: async () => [{ flight_id: FA }, { flight_id: FB }, { flight_id: "cccccccccccccccc" }],
    inboxList: async () => {
      rec("inbox_list", null);
      const counts = { new: 0, investigating: 0, "nothing-here": 0, watch: 0, acted: 0 } as Record<string, number>;
      for (const c of state.candidates) counts[c.status as string]++;
      return { candidates: state.candidates, counts, last_scan: { at: "2026-01-04T00:00:00Z", sensitivity: "normal", flights: 3, parameters: {} } };
    },
    inboxResolve: async (args: { candidate_id: string; status: string; note: string | null }) => {
      rec("inbox_resolve", args);
      const c = state.candidates.find((x) => x.id === args.candidate_id)!;
      Object.assign(c, { status: args.status, note: args.note });
      return { candidate: c };
    },
  };
  const client = new Proxy(overrides, { get: (t, prop: string) => t[prop] ?? (async () => { throw new Error(`unmocked ${prop}`); }) });
  return { ...actual, getEngineClient: () => client };
});

import { Research } from "./Research";

function Where() {
  const loc = useLocation();
  return <div data-testid="where">{loc.pathname + loc.search}</div>;
}

function app() {
  render(
    <MemoryRouter initialEntries={["/research"]}>
      <Routes>
        <Route path="/research" element={<Research />} />
        <Route path="*" element={<Where />} />
      </Routes>
    </MemoryRouter>,
  );
}

beforeEach(() => {
  state.bench = true;
  state.calls = [];
  state.candidates = [candidate("ib-1"), candidate("ib-2", { status: "watch", study_id: "st-linked", note: "Pending the bulletin." })];
  resetCapabilities();
  sessionStorage.clear();
});

describe("the inbox on Research home (§6)", () => {
  it("lists candidates with summary, what fired, the sensitivity, status and evidence", async () => {
    app();
    const cards = await screen.findAllByTestId("inbox-candidate");
    expect(cards.length).toBe(2);
    const first = cards.find((c) => c.dataset.status === "new")!;
    expect(first.textContent).toContain("Full-power segment");
    expect(first.textContent).toContain("recurring pattern · rpm.period");
    expect(within(first).getByTestId("inbox-sensitivity").textContent).toBe(
      "prominent rpm period in a governed-rpm preset — 8 of 10 · normal sensitivity: a pattern in 6 of 10 recent slices, a shift beyond 3");
    expect(screen.getByTestId("inbox-scan").textContent).toContain("looked at 3 flights");
    fireEvent.click(within(first).getByTestId("inbox-evidence-toggle"));
    const table = within(first).getByTestId("inbox-evidence");
    expect(table.querySelectorAll("tbody tr").length).toBe(2);
    fireEvent.click(within(table).getByText("2026-01-02"));
    expect((await screen.findByTestId("where")).textContent).toBe(`/flights/${FA}?window=600-660`);
  });

  it("marks a candidate with a note; resolved ones fold away; the linked investigation opens", async () => {
    app();
    const first = (await screen.findAllByTestId("inbox-candidate")).find((c) => c.dataset.status === "new")!;
    fireEvent.click(within(first).getByTestId("inbox-mark-acted"));
    fireEvent.change(within(first).getByLabelText("Note"), { target: { value: "Governor re-adjusted" } });
    fireEvent.click(within(first).getByTestId("inbox-mark-confirm"));
    await waitFor(() => expect(state.calls.find((c) => c.op === "inbox_resolve")?.params).toMatchObject({ candidate_id: "ib-1", status: "acted", note: "Governor re-adjusted" }));
    await waitFor(() => expect(screen.getAllByTestId("inbox-candidate").length).toBe(1));
    fireEvent.click(screen.getByTestId("inbox-show-resolved"));
    expect(screen.getAllByTestId("inbox-candidate").length).toBe(2);
    const watched = screen.getAllByTestId("inbox-candidate").find((c) => c.dataset.status === "watch")!;
    expect(within(watched).getByTestId("inbox-note").textContent).toContain("Pending the bulletin.");
    fireEvent.click(within(watched).getByTestId("inbox-open-study"));
    expect((await screen.findByTestId("where")).textContent).toBe("/research/st-linked");
  });

  it("on the website (no bench) the inbox is there with the install invitation", async () => {
    state.bench = false;
    app();
    await screen.findAllByTestId("inbox-candidate");
    expect((await screen.findByTestId("inbox-install")).textContent).toContain("install EIS for Claude Desktop");
    state.bench = true;
  });

  it("with a bench there is no install invitation", async () => {
    app();
    await screen.findAllByTestId("inbox-candidate");
    await new Promise((r) => setTimeout(r, 20));
    expect(screen.queryByTestId("inbox-install")).toBeNull();
  });
});
