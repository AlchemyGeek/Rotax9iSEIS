import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { describe, it, expect, vi, beforeEach } from "vitest";
import nbFixture from "../fixtures/research-notebook.json";
import { FORBIDDEN_UI_WORDS } from "../lib/research";
import { resetCapabilities } from "../lib/capabilities";

// Spec 16 D15 (Spec 06 v1.0), Spec 03 v0.34 — Research home is the
// notebooks, as cards from list_studies' card fields (Spec 16 §5.5), and the
// inbox; /research/<id> is a notebook. No hand-study creation, presets,
// question forms, Signal or Compare screens, and no .eisstudy. Every row
// comes from the mocked host; the fixture notebook is synthetic.

vi.mock("../components/EChartBase", () => ({ EChartBase: () => <div data-testid="chart-stub" /> }));

const state = vi.hoisted(() => ({
  studies: [] as Record<string, unknown>[],
  caps: { research: true } as Record<string, boolean>,
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
    listStudies: async () => { rec("list_studies", null); return { studies: state.studies }; },
    studySetTags: async (a: { study_id: string; tags: string[] }) => {
      rec("study_set_tags", a);
      state.studies = state.studies.map((x) => (x.study_id === a.study_id ? { ...x, card: { ...(x.card as object), tags: a.tags } } : x)) as typeof state.studies;
      return { study: state.studies.find((x) => x.study_id === a.study_id) };
    },
    inboxList: async () => ({ candidates: [], scan: null, sensitivity: "normal" }),
    pinsList: async () => ({ questions: [], unassigned: [], counts: {}, pins: 0, newest_open: null }),
    loadStudy: async (id: string) => {
      if (id !== nbFixture.study_id) throw new actual.EngineRpcError("NOT_FOUND", `no study ${id}`);
      return nbFixture;
    },
    listFlights: async () => [],
    downloadUrl: (p: string) => p,
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
      </Routes>
    </MemoryRouter>,
  );
}

beforeEach(() => {
  state.studies = [];
  state.caps = { research: true };
  state.calls = [];
  resetCapabilities();
});

function card(over: Record<string, unknown> = {}) {
  return { v: 1, origin: "marks", channels: ["rpm", "map_inhg", "fuel_flow_gph"], flights: 62, date_span: ["2026-04-08", "2026-11-11"],
    evidence: { log_views: 3, figures: 2, tables: 0 }, tests: ["cycling", "coupling"], outputs: "current", resolution: "watch",
    tags: ["governor", "climb"], ...over };
}

function study(id: string, updated: string, over: Record<string, unknown> = {}) {
  return { study_id: id, name: `Notebook ${id}`, author: "claude", status: "finished", question: `Question ${id}?`, updated, card: card(), ...over };
}

describe("Research home (Spec 03 v0.34)", () => {
  it("header → notebooks → inbox; the model sentence lives in the page's help", async () => {
    state.studies = [study("st-a", "2026-01-10T10:00:00Z")];
    app("/research");
    await screen.findByTestId("notebook-card");
    const order = [...document.querySelectorAll("[data-testid=notebooks], [data-testid=inbox]")].map((e) => e.getAttribute("data-testid"));
    expect(order).toEqual(["notebooks", "inbox"]);
    expect(screen.queryByTestId("research-model")).toBeNull();          // not on the page…
    fireEvent.click(screen.getByTestId("research-help"));
    expect((await screen.findByTestId("research-model")).textContent).toContain("Claude investigates; EIS measures.");   // …in the help
    expect(screen.getByTestId("research-help-body").querySelector("a")!.getAttribute("href")).toContain("concepts/research/");
  });

  it("a card carries the card's fields: origin, title, status coloured by resolution, question, channels, scope, evidence, tests, outputs, tags, author, updated", async () => {
    state.studies = [study("st-a", "2026-01-10T10:00:00Z", { name: "Full-power rpm cycle", question: "Does rpm cycle at full power?" })];
    app("/research");
    const c = await screen.findByTestId("notebook-card");
    expect(within(c).getByTestId("card-origin").textContent).toBe("✎");
    expect(within(c).getByTestId("card-origin").getAttribute("title")).toBe("From your marks");
    expect(within(c).getByTestId("card-link").textContent).toBe("Full-power rpm cycle");
    const st = within(c).getByTestId("card-status");
    expect(st.textContent).toBe("finished");
    expect((st.firstChild as HTMLElement).style.background).toBe("var(--severity-watch)");        // the resolution's colour
    expect(st.getAttribute("title")).toBe("Finished: watch");
    expect(within(c).getByTestId("card-question").textContent).toBe("Does rpm cycle at full power?");
    expect([...within(c).getByTestId("channel-tags").querySelectorAll("[data-channel]")].map((t) => t.textContent)).toEqual(["RPM", "MAP", "FF"]);
    expect(within(c).getByTestId("card-scope").textContent).toBe("62 flights · Apr–Nov");
    expect(within(c).getByTestId("card-evidence").textContent).toBe("∿ 3◫ 2");
    expect(within(c).getByTestId("card-evidence").getAttribute("title")).toBe("3 log views, 2 figures");
    expect(within(c).getAllByTestId("card-test").map((t) => t.textContent)).toEqual(["↻ cycling", "⇄ coupling"]);
    expect(within(c).getByTestId("card-outputs").getAttribute("title")).toBe("Outputs current for this workspace");
    expect(within(c).getAllByTestId("card-tag").map((t) => t.textContent)).toEqual(["governor", "climb"]);
    expect(within(c).getByTestId("card-author").textContent).toContain("Claude");
    // every glyph names itself on hover
    for (const el of [within(c).getByTestId("card-origin"), within(c).getByTestId("card-outputs"), ...within(c).getAllByTestId("card-test")]) {
      expect(el.getAttribute("title")).toBeTruthy();
    }
  });

  it("newest first; a card is a link (click anywhere, or keyboard) to the notebook", async () => {
    state.studies = [study("st-old", "2026-01-01T10:00:00Z"), study(nbFixture.study_id, "2026-01-11T10:00:00Z", { name: "Newest" }), study("st-mid", "2026-01-05T10:00:00Z")];
    app("/research");
    const cards = await screen.findAllByTestId("notebook-card");
    expect(cards.map((c) => c.dataset.study)).toEqual([nbFixture.study_id, "st-mid", "st-old"]);
    const link = within(cards[0]).getByTestId("card-link");
    expect(link.tagName).toBe("A");
    expect(link.getAttribute("href")).toBe(`/research/${nbFixture.study_id}`);
    fireEvent.click(link);
    expect(await screen.findByTestId("notebook")).toBeTruthy();
  });

  it("open and reopened notebooks show their status; pending outputs and outputs from elsewhere show on the dot", async () => {
    state.studies = [
      study("st-o", "2026-01-03T10:00:00Z", { status: "open", card: card({ resolution: null, outputs: "pending", origin: "candidate" }) }),
      study("st-r", "2026-01-02T10:00:00Z", { status: "reopened", card: card({ resolution: null, outputs: "elsewhere", origin: "imported" }) }),
      study("st-a", "2026-01-01T10:00:00Z", { status: "finished", card: card({ resolution: null, origin: "asked", channels: [], flights: 1, date_span: ["2026-10-24", "2026-10-24"], evidence: { log_views: 0, figures: 0, tables: 0 }, tests: [], tags: [] }) }),
    ];
    app("/research");
    const [o, r, a] = await screen.findAllByTestId("notebook-card");
    expect(within(o).getByTestId("card-status").textContent).toBe("open");
    expect(within(o).getByTestId("card-outputs").dataset.outputs).toBe("pending");
    expect(within(o).getByTestId("card-origin").textContent).toBe("◉");
    expect(within(r).getByTestId("card-status").textContent).toBe("reopened");
    expect(within(r).getByTestId("card-outputs").getAttribute("title")).toContain("ran elsewhere");
    expect(within(r).getByTestId("card-origin").textContent).toBe("↓");
    expect(within(a).getByTestId("card-origin").textContent).toBe("?");
    expect(within(a).getByTestId("card-scope").textContent).toBe("1 flight · Oct 24");
    expect(within(a).queryByTestId("card-evidence")).toBeNull();
    expect(within(a).queryByTestId("channel-tags")).toBeNull();
    expect((within(a).getByTestId("card-status").firstChild as HTMLElement).style.background).toBe("var(--text-secondary)");
  });

  it("no filter row up to six notebooks; a clicked tag filters the grid and can be cleared", async () => {
    state.studies = [
      study("st-1", "2026-01-03T10:00:00Z", { card: card({ tags: ["governor"] }) }),
      study("st-2", "2026-01-02T10:00:00Z", { card: card({ tags: ["oil"] }) }),
    ];
    app("/research");
    const cards = await screen.findAllByTestId("notebook-card");
    expect(screen.queryByTestId("notebook-filters")).toBeNull();
    fireEvent.click(within(cards[1]).getByTestId("card-tag"));
    expect(screen.getAllByTestId("notebook-card").map((c) => c.dataset.study)).toEqual(["st-2"]);
    expect(screen.queryByTestId("notebook")).toBeNull();                 // a tag doesn't open the notebook
    fireEvent.click(within(screen.getByTestId("notebook-filters")).getByTestId("notebook-filter-tag"));
    expect(screen.getAllByTestId("notebook-card").length).toBe(2);
  });

  it("the owner adds and removes a card's tags with +; one list with Claude's (Spec 03 v0.37)", async () => {
    state.studies = [study("st-1", "2026-01-03T10:00:00Z", { card: card({ tags: ["governor"] }) })];
    app("/research");
    const c = await screen.findByTestId("notebook-card");
    fireEvent.click(within(c).getByTestId("card-tag-add"));
    expect(screen.queryByTestId("notebook")).toBeNull();                 // + doesn't open the notebook
    const editor = screen.getByRole("dialog", { name: "Tags" });
    fireEvent.change(within(editor).getByLabelText("Add a tag"), { target: { value: "takeoff" } });
    fireEvent.click(within(editor).getByRole("button", { name: "Add" }));
    await waitFor(() => expect(within(screen.getByTestId("notebook-card")).getAllByTestId("card-tag").map((t) => t.textContent)).toEqual(["governor", "takeoff"]));
    expect(state.calls.filter((x) => x.op === "study_set_tags").at(-1)!.params).toEqual({ study_id: "st-1", tags: ["governor", "takeoff"] });
    fireEvent.click(within(screen.getByRole("dialog", { name: "Tags" })).getByRole("button", { name: "Remove “governor”" }));
    await waitFor(() => expect(within(screen.getByTestId("notebook-card")).getAllByTestId("card-tag").map((t) => t.textContent)).toEqual(["takeoff"]));
  });

  it("above six notebooks a filter row: All · Open · Finished and the tags present", async () => {
    state.studies = Array.from({ length: 7 }, (_, i) => study(`st-${i}`, `2026-01-0${i + 1}T10:00:00Z`, {
      status: i < 2 ? "open" : i === 2 ? "reopened" : "finished", card: card({ tags: i % 2 ? ["oil"] : ["governor", "climb"] }) }));
    app("/research");
    const row = await screen.findByTestId("notebook-filters");
    expect(within(row).getAllByRole("button").map((b) => b.textContent)).toEqual(["All", "Open", "Finished", "climb", "governor", "oil"]);
    fireEvent.click(within(row).getByTestId("notebook-filter-open"));
    expect(screen.getAllByTestId("notebook-card").map((c) => c.dataset.status)).toEqual(["reopened", "open", "open"]);
    fireEvent.click(within(row).getByTestId("notebook-filter-finished"));
    expect(screen.getAllByTestId("notebook-card").length).toBe(4);
    fireEvent.click(within(row).getAllByTestId("notebook-filter-tag").find((b) => b.textContent === "oil")!);
    expect(screen.getAllByTestId("notebook-card").map((c) => c.dataset.study)).toEqual(["st-5", "st-3"]);
    fireEvent.click(within(row).getByTestId("notebook-filter-all"));
    expect(screen.getAllByTestId("notebook-card").length).toBe(3);         // the tag filter still holds
  });

  it("two or three cards a row by width, one on a narrow window", async () => {
    state.studies = [study("st-a", "2026-01-10T10:00:00Z")];
    app("/research");
    await screen.findByTestId("notebook-card");
    const cols = screen.getByTestId("notebook-grid").style.gridTemplateColumns;
    // a column is at least a third of the row (so never four) and at least 300 px, but never wider than the row (so one when narrow)
    expect(cols).toContain("auto-fill");
    expect(cols).toContain("min(100%, max(300px, calc((100% - 24px) / 3)))");
  });

  it("an empty workspace: one sentence", async () => {
    app("/research");
    expect((await screen.findByTestId("notebooks-empty")).textContent).toBe("No notebooks yet. Mark a window on a flight, then ask in Claude Desktop.");
  });

  it("has no way to start a study by hand: no New study, presets or question forms", async () => {
    app("/research");
    await screen.findByText(/No notebooks yet/);
    expect(screen.queryByTestId("new-study")).toBeNull();
    expect(screen.queryByText(/Start from a preset/i)).toBeNull();
    expect(screen.queryByText(/Is this signal steady/)).toBeNull();
    expect(screen.queryByText(/Research this/)).toBeNull();
  });

  it("imports a notebook's .zip or .ipynb only", async () => {
    app("/research");
    const input = (await screen.findByTestId("import-study-input")) as HTMLInputElement;
    expect(input.accept).toBe(".zip,.ipynb");
  });

  it("an unknown study id says so instead of opening an editor", async () => {
    app("/research/new");
    expect((await screen.findByTestId("study-status")).textContent).toBe("There is no such notebook in this workspace.");
  });
});

describe("Nav gating", () => {
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
  it("the home page's own words carry no verdict (acceptance 9)", async () => {
    app("/research");
    await screen.findByText(/No notebooks yet/);
    const text = document.body.textContent!.toLowerCase();
    for (const w of FORBIDDEN_UI_WORDS) expect(text.includes(w), w).toBe(false);
  });
});
