import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter, Route, Routes, useLocation, useParams } from "react-router-dom";
import { describe, it, expect, vi, beforeEach } from "vitest";
import casFlight from "../fixtures/flight-cas-analysis.json";
import nbFixture from "../fixtures/research-notebook.json";
import golden from "../fixtures/research-notebook.render.json";
import { resetCapabilities } from "../lib/capabilities";
import { ChartSessionProvider } from "../lib/chartSession";

// Spec 16 §5.3 — the Research page renders an investigation notebook: the
// export's markup (golden), code collapsed under *show code*, the log-view
// cell mounting the Flight view's chart with Open flight, the
// "flight not in this workspace" fallback, the header's state, and the
// actions gated by features.bench. The notebook and its flight are synthetic.

(globalThis as unknown as { ResizeObserver: unknown }).ResizeObserver = class { observe() {} unobserve() {} disconnect() {} };
vi.mock("../components/ChannelTimeline", () => ({ ChannelTimeline: () => <div data-testid="channel-timeline" /> }));

const FLIGHT = "5ynthet1c0f11e01";
const state = vi.hoisted(() => ({
  bench: true,
  flightHere: true,
  view: null as unknown as Record<string, unknown>,
  calls: [] as { op: string; params: unknown }[],
}));

vi.mock("../lib/engineClient", async () => {
  const actual = await vi.importActual<typeof import("../lib/engineClient")>("../lib/engineClient");
  const rec = (op: string, params: unknown) => state.calls.push({ op, params });
  const overrides: Record<string, unknown> = {
    getCapabilities: async () => ({ host: state.bench ? "server" : "browser", engine_version: "1.0.2", host_version: "1.0.2",
      features: { research: true, investigations: true, bench: state.bench } }),
    getActiveWorkspace: async () => ({ active: true, manifest: { id: "ws", name: "Sample", log_folders: [] } }),
    listWorkspaces: async () => [],
    filterHealth: async () => ({ health: [], attention_count: 0 }),
    getFleet: async () => ({ shift_history: [] }),
    listSlicePresets: async () => ({ presets: [], phase_rules: [], engine: "916iS", status: "measured", note: null }),
    listFlights: async () => [],
    loadStudy: async (id: string) => { rec("load_study", id); return state.view; },
    getFlight: async (id: string) => {
      rec("get_flight", id);
      if (!state.flightHere) throw new actual.EngineRpcError("NOT_FOUND", `no flight ${id} in this workspace`);
      return { flight_analysis: { ...casFlight, flight_id: id }, insight_set: { insights: [] } };
    },
    getChannelRegistry: async () => ({ channels: [{ id: "rpm", label: "RPM", unit: "rpm", group: "engine", companions: [] }, { id: "map_inhg", label: "MAP", unit: "inHg", group: "engine", companions: [] }], slot_groups: [], max_chart_slots: 6 }),
    getChartPresets: async () => ({ presets: [{ id: "overview", label: "Overview", channels: ["rpm"] }] }),
    getAppSettings: async () => ({}),
    getFlightSeries: async (id: string, ids: string[]) => { rec("get_flight_series", ids); return { flight_id: id, channels: Object.fromEntries(ids.map((c) => [c, { t: [0, 1], v: [1, 2] }])) }; },
    rerunStudyCells: async (id: string) => { rec("study_cells_rerun", id); return { study: {}, cells: [{ cell_id: "c3", ran: true, identical: false }, { cell_id: "c4", ran: true, identical: true }] }; },
    acceptStudyCells: async (_id: string, opts: unknown) => { rec("study_cells_accept", opts); return { study: {}, cells: [] }; },
    discardStudyCells: async (_id: string, ids: unknown) => { rec("study_cells_discard", ids ?? null); return { study: {}, cells: [] }; },
    exportStudy: async (_id: string, format: string) => { rec("export_study", format); return { filename: `n.${format}`, size: 1, download_url: "/x" }; },
    downloadUrl: (p: string) => p,
    runStudyOnMyFlights: async (id: string) => { rec("run_study_on_my_flights", id); return { ...state.view, study_id: "st-mine" }; },
    getResearchProgress: async () => ({ active: false }),
  };
  const client = new Proxy(overrides, { get: (t, prop: string) => t[prop] ?? (async () => { throw new Error(`unmocked ${prop}`); }) });
  return { ...actual, getEngineClient: () => client };
});

import { Study } from "./Study";

function FlightStub() {
  const { flightId } = useParams();
  const loc = useLocation();
  return <div data-testid="flight-page">{flightId}{loc.search}</div>;
}

function app() {
  return render(
    <MemoryRouter initialEntries={["/research/st-000000fixture"]}>
      <ChartSessionProvider>
        <Routes>
          <Route path="/research/:studyId" element={<Study />} />
          <Route path="/flights/:flightId" element={<FlightStub />} />
        </Routes>
      </ChartSessionProvider>
    </MemoryRouter>,
  );
}

beforeEach(() => {
  state.bench = true;
  state.flightHere = true;
  state.view = structuredClone(nbFixture) as unknown as Record<string, unknown>;
  state.calls = [];
  resetCapabilities();
  HTMLAnchorElement.prototype.click = () => {};
});

// The string identity is notebook.test.ts's; here the golden goes through the DOM as the page's markup does.
const norm = (html: string) => { const d = document.createElement("div"); d.innerHTML = html; return d.innerHTML; };
const g = golden as unknown as { meta_line: string; outputs_line: string; cells: Record<string, { markdown?: string; outputs?: string[] }> };

describe("the notebook on the Research page (§5.3)", () => {
  it("renders the export's markup: header, markdown, code collapsed, every output type", async () => {
    state.flightHere = false;
    app();
    const nb = await screen.findByTestId("notebook");
    const header = screen.getByTestId("notebook-header");
    expect(header.textContent).toContain("Synthetic rpm cycle");
    expect(screen.getByTestId("nb-meta").innerHTML).toBe(norm(g.meta_line));
    expect(screen.getByTestId("nb-outputs").textContent).toBe(g.outputs_line);
    expect(header.textContent).toContain("Is there a cycle in rpm at full power?");
    const md = screen.getAllByTestId("nb-cell-markdown").map((e) => e.innerHTML);
    expect(md).toEqual(["c1", "c2", "c7", "c9"].map((id) => norm(g.cells[id].markdown!)));
    // nothing in a received notebook runs: no script element, no javascript: link
    expect(nb.querySelector("script")).toBeNull();
    expect([...nb.querySelectorAll("a")].every((a) => !a.getAttribute("href")!.startsWith("javascript:"))).toBe(true);
    // code collapsed
    const code = screen.getAllByTestId("nb-cell-code");
    expect(code.length).toBe(9);
    expect(code.every((c) => !(c.querySelector("details") as HTMLDetailsElement).open)).toBe(true);
    expect(code[0].textContent).toContain("setup: binds eis to this workspace");
    // outputs as the export writes them (the log view: the stored SVG with the fallback note)
    const c4 = code.find((c) => c.dataset.cell === "c4")!;
    expect(c4.innerHTML).toContain(norm(g.cells.c4.outputs![0]));
    expect(c4.querySelector("table.eis-table caption")!.textContent).toBe("Slices");
    for (const id of ["c3", "c5", "c6", "c8", "c11"]) {
      const el = code.find((c) => c.dataset.cell === id)!;
      for (const o of g.cells[id].outputs!) expect(el.innerHTML).toContain(norm(o));
    }
    const lv = await screen.findByTestId("logview-absent");
    expect(lv.textContent).toContain("Flight not in this workspace");
    expect(screen.getByTestId("logview-static").innerHTML).toContain(norm(g.cells.c10.outputs![0]));
    // flags and pending
    expect(screen.getAllByTestId("nb-flag").map((f) => f.textContent)).toEqual([expect.stringContaining("ran elsewhere"), expect.stringContaining("read-only")]);
    expect(screen.getByTestId("nb-pending").textContent).toContain("now fine");
  });

  it("a log view whose flight is here mounts the Flight view chart; Open flight lands on that window and channels", async () => {
    app();
    const live = await screen.findByTestId("logview-live");
    expect(live.textContent).toContain("First takeoff");
    expect(within(live).getByTestId("channel-timeline")).toBeTruthy();
    await waitFor(() => expect(state.calls.some((c) => c.op === "get_flight_series" && (c.params as string[]).includes("map_inhg"))).toBe(true));
    expect(live.textContent).toContain("1 — takeoff power (6:07)");
    fireEvent.click(within(live).getByTestId("open-flight"));
    const page = await screen.findByTestId("flight-page");
    expect(page.textContent).toBe(`${FLIGHT}?window=360-420&channels=rpm%2Cmap_inhg`);
  });

  it("with a bench: Re-run, Accept, Discard, keep outputs that ran elsewhere, export zip and html", async () => {
    state.flightHere = false;
    app();
    await screen.findByTestId("notebook");
    fireEvent.click(await screen.findByTestId("nb-rerun"));
    expect((await screen.findByTestId("nb-notice")).textContent).toContain("Re-ran 2 code cells: 1 with different outputs");
    fireEvent.click(screen.getByTestId("nb-accept-all"));
    await waitFor(() => expect(state.calls.some((c) => c.op === "study_cells_accept")).toBe(true));
    fireEvent.click(screen.getByTestId("nb-discard-all"));
    await waitFor(() => expect(state.calls.some((c) => c.op === "study_cells_discard")).toBe(true));
    fireEvent.click(screen.getByTestId("nb-keep-external"));
    await waitFor(() => expect(state.calls.filter((c) => c.op === "study_cells_accept").map((c) => c.params)).toContainEqual({ source: "external" }));
    fireEvent.click(screen.getByTestId("nb-export-zip"));
    fireEvent.click(screen.getByTestId("nb-export-html"));
    await waitFor(() => expect(state.calls.filter((c) => c.op === "export_study").map((c) => c.params)).toEqual(["zip", "html"]));
  });

  it("without a bench (the website) the notebook renders with no run actions; export and Run this on my flights remain", async () => {
    state.bench = false;
    state.flightHere = false;
    app();
    await screen.findByTestId("notebook");
    await waitFor(() => expect(screen.getByText(/re-running a notebook needs EIS on your computer/)).toBeTruthy());
    expect(screen.queryByTestId("nb-rerun")).toBeNull();
    expect(screen.queryByTestId("nb-accept-all")).toBeNull();
    expect(screen.queryByText("Accept")).toBeNull();
    expect(screen.getByTestId("nb-export-html")).toBeTruthy();
    fireEvent.click(screen.getByTestId("nb-run-mine"));
    await waitFor(() => expect(state.calls.some((c) => c.op === "run_study_on_my_flights")).toBe(true));
  });
});
