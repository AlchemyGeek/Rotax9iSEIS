import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { describe, it, expect, vi, beforeEach } from "vitest";
import studyFixture from "../fixtures/research-study.json";
import { FORBIDDEN_UI_WORDS, seedFromFlight, stashStudySeed } from "../lib/research";
import { INLINE_HELP } from "../lib/inlineHelp";
import { resetCapabilities } from "../lib/capabilities";
import { binStrip } from "../components/research/SignalSection";
import { compareCsv } from "../components/research/CompareSection";
import type { CompareResult, SignalResult } from "../types/contract";

// Spec 06 v0.6 (Session C) — the study page's Signal and Compare sections,
// the starting section (§12), Flight view's entry in Signal mode, pinning
// and the CSV. Every number is the mocked host's; the signal is a
// synthetic sine, the rows are invented — no flight data.

vi.mock("../components/EChartBase", () => ({ EChartBase: () => <div data-testid="chart-stub" /> }));

const N = 300;
function synthSignal(window: { start_s: number; end_s: number } | null): SignalResult {
  const rpm = Array.from({ length: N }, (_, i) => 5000 + (i >= 100 && i < 200 ? 90 * Math.sin((2 * Math.PI * i) / 4) : 0));
  const lit = rpm.map((_, i) => i >= 104 && i < 196);
  const strips = {
    swing: rpm.map((_, i) => (lit[i] ? 180 : 0)), period_s: rpm.map((_, i) => (lit[i] ? 4 : null)),
    prominence: rpm.map((_, i) => (lit[i] ? 0.6 : 0.05)), prominent: lit,
  };
  const diag = { detrended: [1, -1, 1, -1], acf: [1, 0, -1, 0, 1], periodogram: { period_s: [2, 4, 8], power: [0.1, 0.9, 0.2] }, period_s: 4, period_ls_s: 4 };
  return {
    flight_id: "fa", duration_s: N, source: "G3X", start_time: "2026-01-01T10:00:00Z", date: "Day 1",
    channels: ["rpm", "map_inhg"], missing_channels: [], reference: "rpm",
    phases: [{ phase: "TAXI", start_s: 0, end_s: 90 }, { phase: "TAKEOFF_ROLL", start_s: 90, end_s: 210 }, { phase: "CLIMB", start_s: 210, end_s: 300 }],
    filled: [], strip_windows: { rpm: { window_s: 12, basis: "floor", flight_period_s: 4, lit_seconds: 92, lit_share: 0.307 }, map_inhg: { window_s: 12, basis: "floor", flight_period_s: 4, lit_seconds: 92, lit_share: 0.307 } },
    strips: { rpm: strips, map_inhg: strips }, prominence_min: 0.2, om_limits: { rpm: [{ kind: "om", id: "rpm_max", label: "max", value: 5800, limit_type: "MAX", unit: "rpm" }], map_inhg: [] },
    values: { rpm, map_inhg: rpm.map((v) => v / 200) },
    window: window && {
      start_s: window.start_s, end_s: window.end_s, duration_s: window.end_s - window.start_s, context: {} as never,
      descriptors: {}, windows: { rpm: { window_s: 12, lag_s: 10, basis: "period" }, map_inhg: { window_s: 12, lag_s: 10, basis: "period" } },
      diagnostics: { rpm: diag, map_inhg: { ...diag, lag_curve: [{ lag_s: -1, corr: 0.5 }, { lag_s: 0, corr: 0.9 }, { lag_s: 1, corr: 0.6 }], best_lag_s: 0 } },
      numbers: {
        rpm: [{ label: "RPM swing", value: 180, unit: "rpm", text: "180 rpm peak-to-peak", references: [{ kind: "om", label: "max", text: "OM max 5,800 rpm: the window's top reaches 5,090 rpm, 710 rpm below it" }] },
          { label: "RPM period", value: 4, unit: "s", text: "4 s", references: [] }],
        map_inhg: [{ label: "MAP with the reference", value: 0.92, unit: "", text: "correlation 0.92 at zero lag; best match at +0 s (0.92)", references: [] }],
      },
      derived_rule: { rule_id: "derived-1", name: "RPM 4,910–5,140, like Day 1 100–200 s", conditions: [{ channel: "rpm", op: "between", min: 4910, max: 5140 }],
        min_duration_s: 50, merge_gap_s: 3, pad_s: 0, phase: null, derived_from: { flight: "fa", start_s: window.start_s, end_s: window.end_s, channel: "rpm" } },
    },
  };
}

function row(id: string, flight: string, start: number, swing: number, extra: Record<string, unknown> = {}) {
  return { row_id: id, slice_id: id, flight, kind: "rule", label: "Full-power segment", start_s: start, end_s: start + 40, start_time: `2026-01-0${flight === "fa" ? 1 : 2}T10:00:00Z`,
    date: flight === "fa" ? "Day 1" : "Day 2", duration_s: 40, source: "G3X", da_ft: flight === "fa" ? 1200 : 6100, oat_c: 15, pa_ft: 100, engine_hours: 50, phases: ["TAKEOFF_ROLL", "CLIMB"],
    values: { rpm: { period_s: 3.8, period_prominence: 0.5, period_prominent: true, swing, median: 5640 }, map_inhg: { period_s: 3.8, swing: 1.2, median: 27, corr0: 0.9, lag_s: 0 } }, ...extra };
}

function synthCompare(pinned: string | null, collapse: boolean): CompareResult {
  let rows = [row("fa:r:10-50", "fa", 10, 170), row("fa:r:400-440", "fa", 400, 190), row("fb:r:20-60", "fb", 20, 80)];
  const groups = [
    { flight: "fa", date: "Day 1", start_time: rows[0].start_time, source: "G3X", count: 2, row_ids: [rows[0].row_id, rows[1].row_id], summary: { ...rows[0], row_id: "fa", slice_id: null, kind: "flight", label: "2 slices", count: 2, values: { ...rows[0].values, rpm: { ...rows[0].values.rpm, swing: 180 } } } },
    { flight: "fb", date: "Day 2", start_time: rows[2].start_time, source: "G3X", count: 1, row_ids: [rows[2].row_id], summary: { ...rows[2], row_id: "fb", slice_id: null, kind: "flight", label: "1 slices", count: 1 } },
  ];
  if (collapse) rows = groups.map((g) => g.summary) as unknown as typeof rows;
  if (pinned) {
    const pin = rows.find((r) => r.row_id === pinned)!;
    rows = rows.map((r) => ({ ...r, pinned: r.row_id === pinned, delta: { rpm: { swing: r.values.rpm.swing - pin.values.rpm.swing, period_s: 0 }, map_inhg: { corr0: 0 } } }));
  }
  return { rows, groups, collapsed: collapse, row_count: rows.length, slice_count: 3, flight_count: 2, flights_without: [{ flight: "fc", date: "Day 3", start_utc: "2026-01-03T10:00:00Z" }],
    pinned, channels: ["rpm", "map_inhg"], reference: "rpm", windows: {}, chart_x: ["date", "engine_hours", "da_ft", "oat_c"], values: [], deltas: [],
    om_limits: { rpm: [{ kind: "om", id: "rpm_max", label: "max", value: 5800, limit_type: "MAX", unit: "rpm" }] }, rules: [], hand_slices: [], by_source: { G3X: 3 },
    missing_flights: [], unreachable_flights: [], engine_version: "1.0.2", selection: { mode: "all" } } as unknown as CompareResult;
}

const PRESETS = {
  engine: "916iS", status: "measured", note: null,
  presets: [{ rule_id: "full_power", name: "Full-power segment", from_preset: "full_power", conditions: [{ channel: "rpm", op: ">=", value: 5550 }],
    min_duration_s: 15, merge_gap_s: 3, pad_s: 0, phase: null, description: "RPM ≥ 5550 for ≥ 15 s", question: "What happens at takeoff power?" }],
  phase_rules: [],
};

const state = vi.hoisted(() => ({
  docs: {} as Record<string, Record<string, unknown>>,
  calls: [] as { op: string; params: Record<string, unknown> }[],
}));

vi.mock("../lib/engineClient", async () => {
  const actual = await vi.importActual<typeof import("../lib/engineClient")>("../lib/engineClient");
  const rec = (op: string, params: unknown) => state.calls.push({ op, params: params as Record<string, unknown> });
  const overrides: Record<string, unknown> = {
    getCapabilities: async () => ({ host: "server", engine_version: "1.0.2", host_version: "1.0.2", features: { research: true, download_url: true } }),
    getActiveWorkspace: async () => ({ active: true, manifest: { id: "ws", name: "Sample", log_folders: [] } }),
    listWorkspaces: async () => [],
    filterHealth: async () => ({ health: [], attention_count: 0 }),
    getFleet: async () => ({ shift_history: [] }),
    listSlicePresets: async () => PRESETS,
    listFlights: async () => [
      { flight_id: "fa", header: { date: "Day 1", start_utc: "2026-01-01T10:00:00Z" }, quality: [], source_filename: "a.csv" },
      { flight_id: "fb", header: { date: "Day 2", start_utc: "2026-01-02T10:00:00Z" }, quality: [], source_filename: "b.csv" },
    ],
    loadStudy: async (id: string) => state.docs[id],
    buildSlices: async (args: unknown) => {
      rec("build_slices", args);
      return { slices: [], count: 3, by_source: { G3X: 3 }, flights_with_slices: 2, flights_selected: 3, rules: PRESETS.presets, hand_slices: [], channels: ["rpm"],
        reference: "rpm", windows: {}, missing_flights: [], unreachable_flights: [], missing_channels: {}, parsed_flights: 3, cached_flights: 0, engine_version: "1.0.2", selection: { mode: "all" } };
    },
    getSliceSamples: async () => ({ anchor: "crossing", channels: ["rpm"], slices: [] }),
    analyzeSignal: async (args: { window?: { start_s: number; end_s: number } | null }) => { rec("analyze_signal", args); return synthSignal(args.window ?? null); },
    compareRows: async (args: { pinned?: string | null; collapse?: boolean }) => { rec("compare_rows", args); return synthCompare(args.pinned ?? null, !!args.collapse); },
    saveStudy: async (study: Record<string, unknown>) => {
      rec("save_study", study);
      const id = (study.study_id as string) ?? "st-new00000001";
      const doc = { ...studyFixture, ...study, study_id: id, slice_rules: ((study.slice_rules as unknown[]) ?? []).map((r) => (typeof r === "string" ? PRESETS.presets.find((p) => p.rule_id === r) : r)) };
      state.docs[id] = doc;
      return doc;
    },
    getResearchProgress: async () => ({ active: false }),
  };
  const client = new Proxy(overrides, { get: (t, prop: string) => t[prop] ?? (async () => { throw new Error(`unmocked ${prop}`); }) });
  return { ...actual, getEngineClient: () => client };
});

import { Study } from "./Study";

function app(path: string) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <Routes>
        <Route path="/research/:studyId" element={<Study />} />
        <Route path="/flights/:flightId" element={<div data-testid="flight-page" />} />
      </Routes>
    </MemoryRouter>,
  );
}

beforeEach(() => {
  state.docs = { [studyFixture.study_id]: studyFixture as unknown as Record<string, unknown> };
  state.calls = [];
  resetCapabilities();
  sessionStorage.clear();
});

describe("Flight view entry: Signal mode (§9.1, §12)", () => {
  it("the seed carries the flight, the chart's channels and the zoom as the window", () => {
    const s = seedFromFlight({ flightId: "fa", date: "Day 1", start_s: 100.4, end_s: 199.6, coversTakeoff: true, channels: ["rpm", "map_inhg"] });
    expect(s.signal).toEqual({ flight: "fa", channels: ["rpm", "map_inhg"], reference: null, window: { start_s: 100, end_s: 200 } });
    expect(s.hand_slices[0]).toMatchObject({ flight: "fa", start_s: 100, end_s: 200 });
  });

  it("a study opened from a flight starts at Signal: strips, the window's numbers with the OM reference, diagnostics", async () => {
    stashStudySeed(seedFromFlight({ flightId: "fa", date: "Day 1", start_s: 100, end_s: 200, coversTakeoff: false, channels: ["rpm", "map_inhg"] }));
    app("/research/new");
    const sig = await screen.findByTestId("section-signal");
    expect(sig.dataset.open).toBe("true");
    await screen.findByTestId("strip-swing-rpm");
    expect(screen.getByTestId("strip-period-map_inhg")).toBeTruthy();
    const first = state.calls.find((c) => c.op === "analyze_signal")!.params;
    expect(first).toMatchObject({ flight_id: "fa", channels: ["rpm", "map_inhg"] });
    expect(first.window).toBeUndefined();
    await screen.findByTestId("signal-window-result");
    const winCall = state.calls.find((c) => c.op === "analyze_signal" && c.params.window)!.params;
    expect(winCall).toMatchObject({ window: { start_s: 100, end_s: 200 }, include_strips: false, include_values: false });
    expect(screen.getByTestId("signal-window").textContent).toContain("01:40–03:20");
    const nums = screen.getAllByTestId("signal-number").map((n) => n.textContent).join(" | ");
    expect(nums).toContain("180 rpm peak-to-peak");
    expect(nums).toContain("OM max 5,800 rpm");
    expect(nums).toContain("correlation 0.92 at zero lag");
    expect(screen.getByTestId("diagnostics-rpm")).toBeTruthy();
    expect(screen.getByTestId("diagnostics-map_inhg").querySelectorAll("[data-testid=chart-stub]").length).toBe(4); // trace, ACF, periodogram, lag
    for (const w of FORBIDDEN_UI_WORDS) expect(screen.getByTestId("section-signal").textContent!.toLowerCase().includes(w), w).toBe(false);
  });

  it("click-drag on the plot sets the window", async () => {
    stashStudySeed(seedFromFlight({ flightId: "fa", date: "Day 1", start_s: 100, end_s: 200, coversTakeoff: false, channels: ["rpm"] }));
    app("/research/new");
    const plot = await screen.findByTestId("signal-plot");
    // Plot area: 56 px left margin, 126 px right; a 1182 px box leaves 1000 px for 300 s.
    plot.getBoundingClientRect = () => ({ left: 0, width: 1182, top: 0, height: 200, right: 1182, bottom: 200, x: 0, y: 0, toJSON: () => ({}) });
    fireEvent.pointerDown(plot, { button: 0, clientX: 56 + 200, pointerId: 1 });
    fireEvent.pointerMove(plot, { clientX: 56 + 500, pointerId: 1 });
    fireEvent.pointerUp(plot, { clientX: 56 + 500, pointerId: 1 });
    await waitFor(() => expect(screen.getByTestId("signal-window").textContent).toContain("01:00–02:30"));
    await waitFor(() => expect(state.calls.some((c) => c.op === "analyze_signal" && (c.params.window as { start_s: number })?.start_s === 60)).toBe(true));
  });

  it("Make this a rule opens the rule form with the derived band, and saving adds it with its provenance", async () => {
    stashStudySeed(seedFromFlight({ flightId: "fa", date: "Day 1", start_s: 100, end_s: 200, coversTakeoff: false, channels: ["rpm"] }));
    app("/research/new");
    fireEvent.click(await screen.findByTestId("make-rule"));
    const editor = await screen.findByTestId("slice-rule-editor");
    expect((within(editor).getByDisplayValue("RPM 4,910–5,140, like Day 1 100–200 s") as HTMLInputElement)).toBeTruthy();
    expect(screen.getByTestId("section-compare").dataset.open).toBe("true");
    fireEvent.click(within(editor).getByText("Use this rule"));
    await waitFor(() => expect(screen.getAllByTestId("slice-rule").map((r) => r.textContent).join()).toContain("RPM 4,910–5,140"));
    fireEvent.click(screen.getByText("Save"));
    await waitFor(() => expect(state.calls.some((c) => c.op === "save_study")).toBe(true));
    const saved = state.calls.find((c) => c.op === "save_study")!.params as { slice_rules: { derived_from?: unknown }[]; signal: unknown };
    expect(saved.slice_rules[0].derived_from).toEqual({ flight: "fa", start_s: 100, end_s: 200, channel: "rpm" });
    expect(saved.signal).toEqual({ flight: "fa", channels: ["rpm"], reference: null, window: { start_s: 100, end_s: 200 } });
  });
});

describe("Compare (§9.2)", () => {
  function presetStudy() {
    stashStudySeed({ name: "Full-power segment", from: "preset", selection: { mode: "all", split: null }, slice_rules: ["full_power"], hand_slices: [],
      tests: [{ test_id: "cycling", params: {}, channels: ["rpm"] }] });
    app("/research/new");
  }

  it("a study opened from a preset starts at Compare, Signal collapsed; rows grouped by flight, flights without a slice listed", async () => {
    presetStudy();
    expect((await screen.findByTestId("section-signal")).dataset.open).toBe("false");
    expect(screen.getByTestId("section-compare").dataset.open).toBe("true");
    await waitFor(() => expect(screen.getAllByTestId("compare-row").length).toBe(3));
    expect(screen.getAllByTestId("compare-group").length).toBe(2);
    expect(screen.getByTestId("compare-counts").textContent).toContain("3 slices from 2 flights · 1 selected flight with no matching slice");
    // collapse one flight's group: its slices hide, its median row shows
    fireEvent.click(screen.getAllByLabelText("Collapse flight")[0]);
    expect(screen.getAllByTestId("compare-row").length).toBe(1);
    expect(screen.getByTestId("compare-chart")).toBeTruthy();
  });

  it("pinning a row asks the host for differences, shows Δ columns and survives save", async () => {
    presetStudy();
    await waitFor(() => expect(screen.getAllByTestId("compare-row").length).toBe(3));
    fireEvent.click(screen.getAllByTestId("pin-row")[0]);
    await waitFor(() => expect(state.calls.some((c) => c.op === "compare_rows" && c.params.pinned === "fa:r:10-50")).toBe(true));
    await waitFor(() => expect(screen.getByTestId("compare-table").textContent).toContain("Δ RPM swing"));
    const third = screen.getAllByTestId("compare-row")[2];
    expect(third.textContent).toContain("-90");
    fireEvent.click(screen.getByText("Save"));
    await waitFor(() => expect(state.calls.some((c) => c.op === "save_study")).toBe(true));
    expect((state.calls.find((c) => c.op === "save_study")!.params.compare as { pinned: string }).pinned).toBe("fa:r:10-50");
  });

  it("one row per flight asks the host to collapse; the aligned view is a tab", async () => {
    presetStudy();
    fireEvent.click(await screen.findByTestId("compare-collapse"));
    await waitFor(() => expect(state.calls.some((c) => c.op === "compare_rows" && c.params.collapse === true)).toBe(true));
    await waitFor(() => expect(screen.getAllByTestId("compare-row").length).toBe(2));
    fireEvent.click(screen.getByTestId("compare-tab-aligned"));
    expect(screen.queryByTestId("compare-table")).toBeNull();
  });

  it("the diagnostics panel shows the pinned and ticked rows' windows side by side", async () => {
    presetStudy();
    await waitFor(() => expect(screen.getAllByTestId("compare-row").length).toBe(3));
    fireEvent.click(screen.getAllByLabelText("Select for diagnostics")[2]);
    fireEvent.click(screen.getByTestId("compare-diagnostics-toggle"));
    await screen.findByTestId("compare-diagnostics");
    await waitFor(() => expect(state.calls.some((c) => c.op === "analyze_signal" && c.params.flight_id === "fb" && (c.params.window as { start_s: number }).start_s === 20)).toBe(true));
  });

  it("the CSV carries conditions, every value and, when pinned, the differences", () => {
    const csv = compareCsv(synthCompare("fa:r:10-50", false)).trim().split("\n");
    expect(csv.length).toBe(4);
    expect(csv[0]).toContain("rpm.swing");
    expect(csv[0]).toContain("rpm.delta_swing");
    expect(csv[1]).toContain('"TAKEOFF_ROLL; CLIMB"'.replace(/"/g, ""));
    expect(csv[3].split(",")[0]).toBe("fb");
  });
});

describe("Strips and help (§9.1, Spec 14 §7.4)", () => {
  it("the period strip is drawn only where the prominence passes; the swing strip everywhere", () => {
    const s = synthSignal(null).strips.rpm;
    const per = binStrip(s, "period");
    expect(per.cells.filter((c) => c != null).length).toBe(92);
    expect(per.lo).toBe(4);
    const sw = binStrip(s, "swing");
    expect(sw.cells.every((c) => c != null)).toBe(true);
  });
  it("help for the strips, the window, rule derivation and pinning exists and carries no verdict", () => {
    for (const id of ["research.strips", "research.window", "research.derived_rule", "research.pinning"] as const) {
      const t = INLINE_HELP[id].toLowerCase();
      expect(t.length).toBeGreaterThan(40);
      for (const w of FORBIDDEN_UI_WORDS) expect(t.includes(w), `${id}: ${w}`).toBe(false);
      for (const w of ["916", "rotax", "n117"]) expect(t.includes(w), `${id} is aircraft-neutral`).toBe(false);
    }
  });
});
