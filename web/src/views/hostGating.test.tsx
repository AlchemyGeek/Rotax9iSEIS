import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { resetCapabilities } from "../lib/capabilities";
import { appSettings, engineLimits, fleetAnalysis, workspaceManifest, workspaceSettings } from "../lib/fixtures";

// Spec 03 v0.24 §6.4 / Spec 04 v0.7 §9.5: one build, gated by the host's
// features — never by which host it is. Three surfaces: Flights' folder
// adding and connection state, Settings → App's Storage vs Data location,
// and Settings → Engine's About line.

const BROWSER = { host: "browser", engine_version: "1.0.1", host_version: "1.0.1",
  features: { data_location: false, add_folder_by_path: false, choose_folder: true, persistent_storage_status: true, download_url: false, folder_watching: false } };
const SERVER = { host: "server", engine_version: "1.0.1", host_version: "1.0.1",
  features: { data_location: true, add_folder_by_path: true, choose_folder: false, persistent_storage_status: false, download_url: true, folder_watching: false } };

const state = vi.hoisted(() => ({ caps: null as unknown, folders: [] as unknown[], folderState: "connected", noWorkspace: false }));

vi.mock("../lib/engineClient", async () => {
  const actual = await vi.importActual<typeof import("../lib/engineClient")>("../lib/engineClient");
  const overrides: Record<string, unknown> = {
    getCapabilities: async () => state.caps,
    getActiveWorkspace: async () => ({ active: true, manifest: { ...workspaceManifest, log_folders: state.folders }, settings: workspaceSettings }),
    listFlightsWithStatus: async () => ({ rows: [] }),
    listExclusions: async () => ({ entries: [], summary: {} }),
    getImportInfo: async () => ({ imported: false }),
    getScanProgress: async () => ({ active: false }),
    folderState: async () => state.folderState,
    getAppSettings: async () => appSettings,
    getChartPresets: async () => ({ presets: [] }),
    getFleet: async () => fleetAnalysis,
    getEngineLimits: async () => engineLimits,
    getWorkspaceRules: async () => {
      if (state.noWorkspace) throw new actual.EngineRpcError("NO_ACTIVE_WORKSPACE", "no active workspace");
      return { rules: { version: "1", rules: {} }, card_topic_ids: [] };
    },
    listChangedSettings: async () => ({ settings: [] }),
    getLogChannels: async () => ({ channels: [] }),
    getStorageUsage: async () => ({ total_bytes: 3 * 1048576, other_bytes: 1000, workspace_count: 2, workspaces: [] }),
    getDataLocation: async () => ({ path: "/Users/me/SlingologyEIS", source: "default", missing: false }),
    listWorkspaces: async () => [],
    filterHealth: async () => ({ health: [], attention_count: 0 }),
  };
  const client = new Proxy(overrides, {
    get: (target, prop: string) => target[prop] ?? (async () => { throw new Error(`unmocked ${prop}`); }),
  });
  return { ...actual, getEngineClient: () => client };
});

import { Flights } from "./Flights";
import { Settings } from "./Settings";

function renderAt(path: string, el: React.ReactElement) {
  render(<MemoryRouter initialEntries={[path]}>{el}</MemoryRouter>);
}

describe("capability gating", () => {
  beforeEach(() => {
    resetCapabilities();
    state.folders = [];
    state.folderState = "connected";
    state.noWorkspace = false;
  });

  it("Settings with no workspace yet (a first run) shows the real settings, not the sample", async () => {
    state.caps = BROWSER;
    state.noWorkspace = true;
    renderAt("/settings?tab=app", <Settings />);
    await screen.findByTestId("storage-panel");
    expect(screen.queryByText(/sample/i)).toBeNull();
  });

  it("Flights: Choose folder… where the host can't open a path; Add folder where it can", async () => {
    state.caps = BROWSER;
    renderAt("/flights", <Flights />);
    expect(await screen.findByRole("button", { name: "Choose folder…" })).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Add folder" })).toBeNull();
    expect(screen.getByTestId("folder-input")).toBeTruthy();
  });

  it("Flights (server): Add folder and no folder input, as before", async () => {
    state.caps = SERVER;
    renderAt("/flights", <Flights />);
    expect(await screen.findByRole("button", { name: "Add folder" })).toBeTruthy();
    expect(screen.queryByTestId("folder-input")).toBeNull();
  });

  it("Flights: a folder the page can't supply shows Not connected — reconnect", async () => {
    state.caps = BROWSER;
    state.folders = [{ path: "My logs", folder_id: "f1", reachable: true }];
    state.folderState = "not_connected";
    renderAt("/flights", <Flights />);
    expect(await screen.findByRole("button", { name: "Not connected — reconnect" })).toBeTruthy();
  });

  it("Flights: after a browser restart, Allow access on the folder row", async () => {
    state.caps = BROWSER;
    state.folders = [{ path: "My logs", folder_id: "f1", reachable: true }];
    state.folderState = "needs_permission";
    renderAt("/flights", <Flights />);
    expect(await screen.findByRole("button", { name: "Allow access" })).toBeTruthy();
  });

  it("Settings → App: Storage in the browser host, not Data location", async () => {
    state.caps = BROWSER;
    renderAt("/settings?tab=app", <Settings />);
    const panel = await screen.findByTestId("storage-panel");
    await waitFor(() => expect(panel.textContent).toContain("3.0 MB"));
    expect(panel.textContent).toContain("may clear this data");
    expect(screen.getByRole("button", { name: "Export all workspaces…" })).toBeTruthy();
    expect(screen.getByRole("button", { name: "Delete all data on this device" })).toBeTruthy();
  });

  it("Settings → App: Data location in the server host, no Storage panel", async () => {
    state.caps = SERVER;
    renderAt("/settings?tab=app", <Settings />);
    await screen.findByText("Data location");
    expect(screen.queryByTestId("storage-panel")).toBeNull();
  });

  it("Settings → Engine: the About line names the host", async () => {
    state.caps = BROWSER;
    renderAt("/settings?tab=engine", <Settings />);
    expect((await screen.findByTestId("engine-host")).textContent).toContain("in this browser");
  });
});
