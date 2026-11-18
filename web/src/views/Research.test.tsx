import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { describe, it, expect, vi, beforeEach } from "vitest";
import nbFixture from "../fixtures/research-notebook.json";
import { FORBIDDEN_UI_WORDS } from "../lib/research";
import { resetCapabilities } from "../lib/capabilities";

// Spec 16 D15 (Spec 06 v1.0) — Research home is the notebooks and the
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
    inboxList: async () => ({ candidates: [], scan: null, sensitivity: "normal" }),
    pinsList: async () => ({ questions: [], pins: [] }),
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

describe("Research home (Spec 16 D15)", () => {
  it("lists the notebooks with who wrote them and their finding, and states the model", async () => {
    state.studies = [
      { study_id: "st-a", name: "Full-power rpm cycle", author: "claude", status: "finished", finding: "RPM cycles every 4.4 s at full power.", updated: "2026-01-10T10:00:00Z" },
      { study_id: "st-b", name: "Oil temperature", author: "claude", status: "open", question: "Why is oil warmer since May?", pending: 2, updated: "2026-01-11T10:00:00Z" },
    ];
    app("/research");
    const rows = await screen.findAllByTestId("study-row");
    expect(rows.map((r) => r.textContent)).toEqual([
      expect.stringContaining("Full-power rpm cycle"), expect.stringContaining("Oil temperature"),
    ]);
    expect(rows[0].textContent).toContain("RPM cycles every 4.4 s");
    expect(rows[1].textContent).toContain("Why is oil warmer since May? · 2 cells pending");
    expect(screen.getByTestId("research-model").textContent).toContain("Claude investigates; EIS measures.");
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

  it("a row opens the notebook; /research/new is not a page", async () => {
    state.studies = [{ study_id: nbFixture.study_id, name: "N", author: "claude", status: "open", updated: "2026-01-10T10:00:00Z" }];
    app("/research");
    fireEvent.click(await screen.findByTestId("study-row"));
    expect(await screen.findByTestId("notebook")).toBeTruthy();
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
