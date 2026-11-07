import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { describe, it, expect, vi, beforeEach } from "vitest";
import studyFixture from "../fixtures/research-study.json";
import { FORBIDDEN_UI_WORDS, seedFromEvent, seedFromFlight, seedFromTrend, stashStudySeed, takeStudySeed } from "../lib/research";
import { INLINE_HELP } from "../lib/inlineHelp";
import { resetCapabilities } from "../lib/capabilities";

// Spec 06 §12 (Session B) — Research home, the study page (editable and
// read-only, §10.2), the "Research this" seeds (§12 entry points) and the
// no-verdict guard on the page's own words (acceptance 9). Every number the
// page shows comes from the mocked host; the fixture study is synthetic.

vi.mock("../components/EChartBase", () => ({ EChartBase: () => <div data-testid="chart-stub" /> }));

const PRESETS = {
  engine: "916iS", status: "measured", note: null,
  presets: [
    { rule_id: "full_power", name: "Full-power segment", from_preset: "full_power", conditions: [{ channel: "rpm", op: ">=", value: 5550 }],
      min_duration_s: 15, merge_gap_s: 3, pad_s: 0, phase: null, description: "RPM ≥ 5550 for ≥ 15 s (gaps < 3 s bridged)", question: "What happens at takeoff power?" },
    { rule_id: "stable_cruise", name: "Stable cruise", from_preset: "stable_cruise", conditions: [{ channel: "rpm", op: "between", min: 4800, max: 5300 }],
      min_duration_s: 300, merge_gap_s: 0, pad_s: 0, phase: { mode: "within", phases: ["CRUISE"] }, description: "RPM between 4800 and 5300, within cruise, for ≥ 300 s", question: "What does steady cruise look like?" },
  ],
  phase_rules: [{ rule_id: "phase:CLIMB", name: "All climb phases", conditions: [], min_duration_s: 1, merge_gap_s: 0, pad_s: 0, phase: { mode: "within", phases: ["CLIMB"] }, description: "within climb" }],
};

const state = vi.hoisted(() => ({
  studies: [] as Record<string, unknown>[],
  docs: {} as Record<string, Record<string, unknown>>,
  caps: { research: true },
  calls: [] as { op: string; params: unknown }[],
}));

vi.mock("../lib/engineClient", async () => {
  const actual = await vi.importActual<typeof import("../lib/engineClient")>("../lib/engineClient");
  const rec = (op: string, params: unknown) => state.calls.push({ op, params });
  const overrides: Record<string, unknown> = {
    getCapabilities: async () => ({ host: "server", engine_version: "1.0.2", host_version: "1.0.2",
      features: { data_location: true, add_folder_by_path: true, choose_folder: false, persistent_storage_status: false, download_url: true, folder_watching: false, ...state.caps } }),
    getActiveWorkspace: async () => ({ active: true, manifest: { id: "ws", name: "Sample", log_folders: [] } }),
    listWorkspaces: async () => [],
    filterHealth: async () => ({ health: [], attention_count: 0 }),
    getFleet: async () => ({ shift_history: [] }),
    listStudies: async () => ({ studies: state.studies }),
    listSlicePresets: async () => PRESETS,
    listFlights: async () => [
      { flight_id: "fa", header: { date: "Day 1", start_utc: "2026-01-01T10:00:00Z" }, quality: [], source_filename: "a.csv" },
      { flight_id: "fb", header: { date: "Day 2", start_utc: "2026-01-02T10:00:00Z" }, quality: [], source_filename: "b.csv" },
    ],
    loadStudy: async (id: string) => {
      const d = state.docs[id];
      if (!d) throw new actual.EngineRpcError("NOT_FOUND", `no study ${id}`);
      return d;
    },
    buildSlices: async (args: unknown) => {
      rec("build_slices", args);
      return { slices: [
        { slice_id: "fa:r:10-60", flight: "fa", source_key: "k", kind: "rule", rule_id: "full_power", label: "Day 1 00:10", start_s: 10, end_s: 60, anchor_s: 10, context: { source: "G3X" }, quality: { duration_s: 50 }, descriptors: {} },
      ], count: 1, by_source: { G3X: 1 }, flights_with_slices: 1, flights_selected: 2, rules: PRESETS.presets.slice(0, 1), hand_slices: [], channels: ["rpm"],
      reference: "rpm", windows: {}, missing_flights: [], unreachable_flights: [], missing_channels: {}, parsed_flights: 2, cached_flights: 0, engine_version: "1.0.2", selection: { mode: "all" } };
    },
    getSliceSamples: async () => ({ anchor: "crossing", channels: ["rpm"], slices: [{ slice_id: "fa:r:10-60", flight: "fa", label: "Day 1 00:10", context: { source: "G3X" }, anchor_offset_s: 0, t: [0, 1, 2], channels: { rpm: [5600, 5700, 5650] } }] }),
    saveStudy: async (study: Record<string, unknown>) => {
      rec("save_study", study);
      const id = (study.study_id as string) ?? "st-new00000001";
      const doc = { ...studyFixture, ...study, study_id: id, tests: (study.tests as unknown[]) ?? [], slice_rules: ((study.slice_rules as unknown[]) ?? []).map((r) => (typeof r === "string" ? PRESETS.presets.find((p) => p.rule_id === r) : r)) };
      state.docs[id] = doc;
      return doc;
    },
    runStudy: async (id: string) => { rec("run_study", id); return state.docs[id]; },
    runStudyOnMyFlights: async (id: string) => {
      rec("run_study_on_my_flights", id);
      const doc = { ...studyFixture, study_id: "st-mine00000001", name: "Sample (my flights)", read_only: undefined, imported: undefined };
      delete (doc as Record<string, unknown>).read_only;
      state.docs["st-mine00000001"] = doc;
      return doc;
    },
    exportStudy: async () => ({ filename: "s.eisstudy", size: 10, download_url: "/x" }),
    downloadUrl: (p: string) => p,
    deleteStudy: async (id: string) => { rec("delete_study", id); delete state.docs[id]; return { deleted: id }; },
    noteStudyFinding: async (id: string, i: number) => { rec("note_study_finding", [id, i]); return { entry: {} }; },
    getResearchProgress: async () => ({ active: false }),
  };
  const client = new Proxy(overrides, { get: (t, prop: string) => t[prop] ?? (async () => { throw new Error(`unmocked ${prop}`); }) });
  return { ...actual, getEngineClient: () => client };
});

import { Research } from "./Research";
import { Study } from "./Study";
import { NavShell } from "../components/NavShell";

function app(path: string) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <Routes>
        <Route path="/research" element={<Research />} />
        <Route path="/research/:studyId" element={<Study />} />
        <Route path="/flights/:flightId" element={<div data-testid="flight-page" />} />
      </Routes>
    </MemoryRouter>,
  );
}

beforeEach(() => {
  state.studies = [];
  state.docs = { [studyFixture.study_id]: studyFixture as unknown as Record<string, unknown> };
  state.caps = { research: true };
  state.calls = [];
  resetCapabilities();
  sessionStorage.clear();
});

describe("Research home (§12)", () => {
  it("lists studies with their first finding, the presets with a question each, and the open questions pointer", async () => {
    state.studies = [{ study_id: studyFixture.study_id, name: studyFixture.name, updated: "2026-01-02T00:00:00Z", created: null,
      finding: studyFixture.tests[0].result.finding, tests: 1, read_only: false, flights: 6 }];
    app("/research");
    const row = await screen.findByTestId("study-row");
    expect(row.textContent).toContain("Full-power slices — sample");
    expect(row.textContent).toContain("RPM cycles every 3.8 s");
    expect((await screen.findAllByTestId("preset-card")).length).toBe(2);
    expect(screen.getByText(/What happens at takeoff power/)).toBeTruthy();
    expect(screen.getByText(/Questions this app's own research left open/)).toBeTruthy();
    expect(screen.getByText(/oil temperature rise rate in climb/)).toBeTruthy();
  });

  it("empty state names the three ways to start", async () => {
    app("/research");
    expect((await screen.findByText(/No studies yet/)).textContent).toContain("Research this");
  });

  it("a preset card opens a new study seeded with that rule", async () => {
    app("/research");
    fireEvent.click((await screen.findAllByTestId("preset-card"))[0]);
    await screen.findByTestId("study-page");
    await waitFor(() => expect(state.calls.some((c) => c.op === "build_slices")).toBe(true));
    const built = state.calls.find((c) => c.op === "build_slices")!.params as { slice_rules: unknown[] };
    expect(built.slice_rules).toEqual(["full_power"]);
    expect((await screen.findByTestId("slice-count")).textContent).toContain("1 slice from 1 of 2 flights");
  });
});

describe("Study page (§12, §8, §10.2)", () => {
  it("renders a saved study's result in the five-part contract, read against its references", async () => {
    app(`/research/${studyFixture.study_id}`);
    const card = await screen.findByTestId("test-result");
    expect(within(card).getByTestId("finding").textContent).toContain("in 5 of 6 full-power slices");
    const mags = within(card).getAllByTestId("magnitude");
    expect(mags[0].textContent).toContain("OM limit 5,800 rpm");
    expect(mags[0].textContent).toContain("170–190 rpm across the set");
    expect(mags[0].textContent).toContain("governing band ±100 rpm");
    expect(mags[0].textContent).toContain("a propeller manual");
    expect(within(card).getByTestId("caveats").textContent).toContain("swing window 12 s, lag range ±10 s");
    fireEvent.click(within(card).getByText(/Show the per-slice table/));
    expect(within(card).getByTestId("evidence-table").querySelectorAll("tbody tr").length).toBe(6);
    // The study's own lines
    expect(screen.getByTestId("slice-rule").textContent).toContain("Full-power segment");
    expect(screen.getByTestId("user-reference").textContent).toContain("governing band");
    expect(screen.queryByTestId("read-only-banner")).toBeNull();
  });

  it("asking a question and running saves then runs the study", async () => {
    app(`/research/${studyFixture.study_id}`);
    await screen.findByTestId("test-result");
    fireEvent.change(screen.getByTestId("add-question"), { target: { value: "coupling" } });
    const editor = await screen.findByTestId("test-editor");
    expect(editor.textContent).toContain("Do these two move together");
    fireEvent.click(within(editor).getByTestId("save-question"));
    expect(screen.getAllByTestId("test-result").length).toBe(2);
    fireEvent.click(screen.getByTestId("run-study"));
    await waitFor(() => expect(state.calls.map((c) => c.op)).toContain("run_study"));
    const saved = state.calls.find((c) => c.op === "save_study")!.params as { tests: { test_id: string }[] };
    expect(saved.tests.map((t) => t.test_id)).toEqual(["cycling", "coupling"]);
    expect(state.calls.findIndex((c) => c.op === "save_study")).toBeLessThan(state.calls.findIndex((c) => c.op === "run_study"));
  });

  it("a read-only study shows the sender's results under the label, disables edits, and offers Run this on my flights (acceptance 12)", async () => {
    state.docs["st-readonly0001"] = { ...studyFixture, study_id: "st-readonly0001", read_only: { label: "sender's results; none of these flights are in this workspace", sender: {} },
      imported: { at: "x", sender: {}, name: "Sample", matched: [], missing: ["fa", "fb"] } };
    app("/research/st-readonly0001");
    const banner = await screen.findByTestId("read-only-banner");
    expect(banner.textContent).toContain("Sender's results — none of these flights are in this workspace.");
    expect(screen.getByTestId("finding").textContent).toContain("RPM cycles every 3.8 s");
    expect(screen.queryByTestId("run-study")).toBeNull();
    expect(screen.queryByTestId("add-question")).toBeNull();
    expect(screen.queryByText("Edit…")).toBeNull();
    expect((screen.getByLabelText("Study name") as HTMLInputElement).disabled).toBe(true);
    expect(state.calls.some((c) => c.op === "build_slices")).toBe(false);
    fireEvent.click(screen.getByTestId("run-on-my-flights"));
    await waitFor(() => expect(state.calls.map((c) => c.op)).toContain("run_study_on_my_flights"));
    await waitFor(() => expect(screen.queryByTestId("read-only-banner")).toBeNull());
    expect((screen.getByLabelText("Study name") as HTMLInputElement).value).toBe("Sample (my flights)");
  });

  it("a hand-slice seed from Flight view suggests the full-power rule when the window covers a takeoff", async () => {
    stashStudySeed(seedFromFlight({ flightId: "fa", date: "Day 1", start_s: 100, end_s: 160, coversTakeoff: true, channels: ["rpm", "map_inhg"] }));
    app("/research/new");
    const page = await screen.findByTestId("study-page");
    expect(within(page).getByTestId("hand-slice").textContent).toContain("01:40–02:40 by hand");
    fireEvent.click(await screen.findByTestId("add-suggested-preset"));
    await waitFor(() => expect(state.calls.some((c) => (c.params as { slice_rules?: unknown[] }).slice_rules?.includes("full_power"))).toBe(true));
    expect(takeStudySeed()).toBeNull(); // consumed once
  });

  it("a finding can be noted in the Journal, which calls the host with the test index", async () => {
    app(`/research/${studyFixture.study_id}`);
    await screen.findByTestId("test-result");
    fireEvent.click(screen.getByText("Note this finding in the Journal"));
    await waitFor(() => expect(state.calls.find((c) => c.op === "note_study_finding")?.params).toEqual([studyFixture.study_id, 0]));
  });
});

describe("Research this seeds (§12 entry points)", () => {
  it("Trends: recent flights vs the rest, on the metric's channel, in the metric's slice rule", () => {
    const s = seedFromTrend({ metricId: "oil_temp_peak", label: "oil temp peak", recentFlightIds: ["f3", "f4"], allFlightIds: ["f1", "f2", "f3", "f4"] });
    expect(s.slice_rules).toEqual(["stable_cruise"]);
    expect(s.selection.split).toEqual({ by: "flights", groups: [{ label: "reference flights", flights: ["f1", "f2"] }, { label: "recent flights", flights: ["f3", "f4"] }] });
    expect(s.tests[0]).toMatchObject({ test_id: "groups", params: { descriptor: "oil_temp_f.median" } });
    expect(seedFromTrend({ metricId: "takeoff_map_inhg", label: "x", recentFlightIds: [], allFlightIds: [] }).slice_rules).toEqual(["full_power"]);
  });
  it("Event: the event's window by hand plus the limit's condition across every flight", () => {
    const s = seedFromEvent({ flightId: "fa", date: "Day 1", label: "Fuel pressure minimum", channel: "fuel_press_psi", limitType: "MIN", limitValue: 36, start_s: 300, duration_s: 4 });
    expect(s.hand_slices[0]).toMatchObject({ flight: "fa", start_s: 290, end_s: 314 });
    expect((s.slice_rules[0] as { conditions: unknown[] }).conditions).toEqual([{ channel: "fuel_press_psi", op: "<=", value: 36 }]);
    expect(s.tests[0].test_id).toBe("unusual");
  });
});

describe("Nav gating and acceptance 9/10", () => {
  it("Research is in the nav only when the host offers it", async () => {
    render(<MemoryRouter><NavShell><div /></NavShell></MemoryRouter>);
    expect(await screen.findByTestId("nav-research")).toBeTruthy();
  });
  it("…and absent on a host without the capability", async () => {
    state.caps = { research: false };
    render(<MemoryRouter><NavShell><div /></NavShell></MemoryRouter>);
    await screen.findByText("Journal");
    await waitFor(() => expect(screen.queryByTestId("nav-research")).toBeNull());
  });
  it("the page's own words carry no verdict (acceptance 9): help text and labels", () => {
    const text = Object.entries(INLINE_HELP).filter(([k]) => k.startsWith("research.")).map(([, v]) => v).join(" ").toLowerCase();
    for (const w of FORBIDDEN_UI_WORDS) expect(text.includes(w), w).toBe(false);
  });
});
