import { render, screen, fireEvent, waitFor, within } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { appSettings, engineLimits, fleetAnalysis, workspaceManifest, workspaceSettings } from "../lib/fixtures";
import { resetCapabilities } from "../lib/capabilities";

// Spec 16 Session F: Settings → Aircraft (the record's fields, notes,
// documents folders — greyed "extension only" without features.documents —
// and the aircraft's workspaces, a mismatched engine flagged, moved to
// another or a new aircraft) and Settings → Research (the inbox's
// sensitivity with its N-of-M meaning). Synthetic aircraft.

const state = vi.hoisted(() => ({
  documents: true,
  calls: [] as { op: string; params: unknown }[],
  sensitivity: undefined as string | undefined,
  aircraft: {} as Record<string, Record<string, unknown>>,
  notes: "" as string,
}));

function view(id: string) {
  const ac = state.aircraft[id];
  const all = { ws_a: { id: "ws_a", name: "Main", engine_model: "916iS", flight_count: 40, last_opened_at: null },
    ws_b: { id: "ws_b", name: "Bench 915", engine_model: "915iS", flight_count: 2, last_opened_at: null } } as Record<string, unknown>;
  return { aircraft: ac, notes: state.notes, engine_model: ac.engine_model,
    fields: [{ key: "registration", label: "Registration", hint: "e.g. N123AB" }, { key: "propeller", label: "Propeller", hint: "make and model" }],
    workspaces: (ac.workspaces as string[]).map((w) => all[w]) };
}

vi.mock("../lib/engineClient", async () => {
  const actual = await vi.importActual<typeof import("../lib/engineClient")>("../lib/engineClient");
  const rec = (op: string, params: unknown) => state.calls.push({ op, params });
  return {
    EngineRpcError: actual.EngineRpcError,
    getEngineClient: () => ({
      getCapabilities: async () => ({ host: "server", engine_version: "1.0.2", host_version: "1.0.2", features: { research: true, investigations: true, bench: state.documents, documents: state.documents } }),
      getAppSettings: async () => appSettings,
      getActiveWorkspace: async () => ({ active: true, manifest: workspaceManifest, settings: workspaceSettings }),
      getChartPresets: async () => ({ presets: [] }),
      getFleet: async () => fleetAnalysis,
      getEngineLimits: async () => ({ ...engineLimits, engine_version: "1.0.2" }),
      getWorkspaceRules: async () => ({ rules: { version: "1", rules: {} }, card_topic_ids: [] }),
      listChangedSettings: async () => ({ settings: [] }),
      getDataLocation: async () => { throw new Error("not a local server"); },
      filterHealth: async () => ({ health: [], attention_count: 0 }),
      listWorkspaces: async () => [],
      getWorkspaceSettings: async () => ({ active_engine_profile: "916iS", ...(state.sensitivity ? { research_sensitivity: state.sensitivity } : {}) }),
      saveWorkspaceSettings: async (s: { research_sensitivity?: string }) => { rec("save_workspace_settings", s); state.sensitivity = s.research_sensitivity; return s; },
      aircraftGet: async (id?: string) => view(id ?? "ac_one"),
      listAircraft: async () => Object.values(state.aircraft).map((a) => ({ ...a, workspaces: [] })),
      aircraftSet: async (args: { aircraft_id: string; aircraft?: Record<string, unknown>; notes?: string }) => {
        rec("aircraft_set", args);
        Object.assign(state.aircraft[args.aircraft_id], args.aircraft ?? {});
        if (args.notes !== undefined) state.notes = args.notes;
        return view(args.aircraft_id);
      },
      aircraftAssign: async (args: { workspace_id: string; aircraft_id?: string; new_aircraft?: { name: string } }) => {
        rec("aircraft_assign", args);
        const id = args.aircraft_id ?? "ac_new";
        if (args.new_aircraft) state.aircraft[id] = { id, name: args.new_aircraft.name, engine_model: "915iS", documents_dirs: [], workspaces: [] };
        for (const a of Object.values(state.aircraft)) a.workspaces = (a.workspaces as string[]).filter((w) => w !== args.workspace_id);
        (state.aircraft[id].workspaces as string[]).push(args.workspace_id);
        return view(id);
      },
    }),
  };
});

import { Settings } from "./Settings";

function renderSettings(tab: string) {
  render(<MemoryRouter initialEntries={[`/settings?tab=${tab}`]}><Routes><Route path="/settings" element={<Settings />} /></Routes></MemoryRouter>);
}

beforeEach(() => {
  state.documents = true;
  state.calls = [];
  state.sensitivity = undefined;
  state.notes = "2026-03: new propeller.";
  state.aircraft = { ac_one: { id: "ac_one", name: "Test aircraft", engine_model: "916iS", registration: "N0TEST", propeller: "", documents_dirs: ["/manuals"], workspaces: ["ws_a", "ws_b"] } };
  resetCapabilities();
});

describe("Settings → Aircraft", () => {
  it("edits the fields and the notes", async () => {
    renderSettings("aircraft");
    const reg = await screen.findByLabelText("Registration");
    expect((reg as HTMLInputElement).value).toBe("N0TEST");
    fireEvent.change(screen.getByLabelText("Propeller"), { target: { value: "Airmaster AP332" } });
    fireEvent.click(screen.getByTestId("aircraft-save"));
    await waitFor(() => expect(state.calls.find((c) => c.op === "aircraft_set")?.params).toMatchObject({ aircraft_id: "ac_one", aircraft: { propeller: "Airmaster AP332", registration: "N0TEST" } }));
    fireEvent.change(screen.getByTestId("aircraft-notes"), { target: { value: "2026-03: new propeller.\n2026-05: governor adjusted." } });
    fireEvent.click(screen.getByTestId("aircraft-notes-save"));
    await waitFor(() => expect(state.notes).toContain("governor adjusted"));
  });

  it("documents folders on a host that reads them; greyed 'extension only' where it can't", async () => {
    renderSettings("aircraft");
    const docs = await screen.findByTestId("aircraft-documents");
    expect(docs.textContent).toContain("/manuals");
    fireEvent.change(within(docs).getByLabelText("Add a documents folder"), { target: { value: "/bulletins" } });
    fireEvent.click(within(docs).getByText("Add"));
    fireEvent.click(within(docs).getByTestId("documents-save"));
    await waitFor(() => expect(state.calls.find((c) => c.op === "aircraft_set")?.params).toMatchObject({ aircraft: { documents_dirs: ["/manuals", "/bulletins"] } }));
  });

  it("without features.documents the folders are read-only and say why", async () => {
    state.documents = false;
    renderSettings("aircraft");
    await screen.findByTestId("documents-extension-only");
    const docs = screen.getByTestId("aircraft-documents");
    expect(docs.textContent).toContain("This browser can't");
    expect(within(docs).queryByLabelText("Add a documents folder")).toBeNull();
  });

  it("flags a workspace whose engine differs and moves it to a new aircraft", async () => {
    renderSettings("aircraft");
    const mismatch = await screen.findByTestId("engine-mismatch");
    expect(mismatch.textContent).toContain("This workspace's profile is Rotax 915 iS; the aircraft record says Rotax 916 iS");
    const row = mismatch.closest("[data-testid=aircraft-workspace]") as HTMLElement;
    fireEvent.click(within(row).getByTestId("workspace-move"));
    fireEvent.change(within(row).getByLabelText("Move to"), { target: { value: "new" } });
    fireEvent.change(within(row).getByLabelText("New aircraft name"), { target: { value: "915 bench" } });
    fireEvent.click(within(row).getByTestId("workspace-move-confirm"));
    await waitFor(() => expect(state.calls.find((c) => c.op === "aircraft_assign")?.params).toEqual({ workspace_id: "ws_b", new_aircraft: { name: "915 bench" } }));
    await waitFor(() => expect(screen.getAllByTestId("aircraft-workspace").length).toBe(1));
    expect(screen.queryByTestId("engine-mismatch")).toBeNull();
  });
});

describe("Settings → Research", () => {
  it("shows the three sensitivities with their N of M meaning and saves the choice", async () => {
    renderSettings("research");
    const panel = await screen.findByTestId("research-settings");
    expect(panel.textContent).toContain("8 of 10");
    expect(panel.textContent).toContain("6 of 10");
    expect(panel.textContent).toContain("4 of 10");
    await waitFor(() => expect((screen.getByTestId("sensitivity-normal") as HTMLInputElement).checked).toBe(true));
    fireEvent.click(screen.getByTestId("sensitivity-curious"));
    await waitFor(() => expect(state.sensitivity).toBe("curious"));
    expect((await screen.findByTestId("sensitivity-saved")).textContent).toContain("curious");
  });
});
