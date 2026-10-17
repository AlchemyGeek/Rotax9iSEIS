import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { DataLocationGate, DataLocationPanel } from "./DataLocation";
import type { DataLocation, DataLocationAssessment } from "../types/contract";

// Spec 14 v0.12 §5.2 (acceptance 19, UI side).

const state = {
  loc: null as DataLocation | null,
  assessments: {} as Record<string, DataLocationAssessment>,
  changed: [] as unknown[],
  retried: 0,
};

const LOC: DataLocation = {
  path: "/Users/pilot/SlingologyEIS", source: "default", missing: false, workspace_count: 2,
  default_path: "/Users/pilot/SlingologyEIS", env_var: "SLINGOLOGY_EIS_HOME",
};

vi.mock("../lib/engineClient", () => ({
  getEngineClient: () => ({
    getDataLocation: async () => {
      if (!state.loc) throw new Error("no server");
      return state.loc;
    },
    assessDataLocation: async (t: string | { default: true }) => state.assessments[typeof t === "string" ? t : "default"],
    changeDataLocation: async (t: string | { default: true }) => {
      state.changed.push(t);
      return { action: "move", path: t, previous_path: LOC.path, location: { ...LOC, path: t, source: "chosen" } };
    },
    getDataLocationProgress: async () => ({ active: false }),
    retryDataLocation: async () => {
      state.retried += 1;
      return state.loc;
    },
  }),
}));

const PANEL = {};
const reload = vi.fn();

describe("DataLocationPanel", () => {
  beforeEach(() => {
    state.loc = { ...LOC };
    state.assessments = {};
    state.changed = [];
    state.retried = 0;
    reload.mockReset();
    sessionStorage.clear();
    Object.defineProperty(window, "location", { configurable: true, value: { ...window.location, reload } });
  });
  afterEach(() => vi.useRealTimers());

  it("shows the path, its source and the workspace count", async () => {
    render(<DataLocationPanel panelStyle={PANEL} titleStyle={PANEL} />);
    await screen.findByText("/Users/pilot/SlingologyEIS");
    expect(screen.getByText(/Default location · 2 workspaces/)).toBeTruthy();
    expect(screen.getByText(/Log folders stay where they are/)).toBeTruthy();
    expect(screen.queryByText("Use default location")).toBeNull();   // only once a location is chosen
  });

  it("says what will happen before anything does, then moves and reloads", async () => {
    state.assessments["/Volumes/Drive/EIS"] = {
      action: "move", path: "/Volumes/Drive/EIS", workspace_count: 2, bytes: 5 * 1024 * 1024, reason: null, code: null,
    };
    render(<DataLocationPanel panelStyle={PANEL} titleStyle={PANEL} />);
    fireEvent.click(await screen.findByText("Change…"));
    fireEvent.change(screen.getByLabelText("Data location folder"), { target: { value: "/Volumes/Drive/EIS" } });
    expect(await screen.findByText("Move your data here — 2 workspaces, 5.0 MB to copy.")).toBeTruthy();
    expect(state.changed).toEqual([]);

    fireEvent.click(screen.getByText("Move data"));
    await waitFor(() => expect(reload).toHaveBeenCalled());
    expect(state.changed).toEqual(["/Volumes/Drive/EIS"]);
    expect(JSON.parse(sessionStorage.getItem("eis.dataLocationOutcome")!).previous_path).toBe(LOC.path);
  });

  it("offers no confirm for a refused folder", async () => {
    state.assessments["/Users/pilot/Documents"] = {
      action: "refused", path: "/Users/pilot/Documents", workspace_count: null, bytes: null,
      reason: "That folder isn't empty and doesn't hold SlingologyEIS data.", code: "NOT_EMPTY",
    };
    render(<DataLocationPanel panelStyle={PANEL} titleStyle={PANEL} />);
    fireEvent.click(await screen.findByText("Change…"));
    fireEvent.change(screen.getByLabelText("Data location folder"), { target: { value: "/Users/pilot/Documents" } });
    await screen.findByText(/isn't empty/);
    expect(screen.queryByText("Move data")).toBeNull();
    expect(screen.queryByText("Use this location")).toBeNull();
  });

  it("after a reload, says where the data now lives and where the old copy is", async () => {
    sessionStorage.setItem("eis.dataLocationOutcome", JSON.stringify({ action: "move", path: "/Volumes/Drive/EIS", previous_path: LOC.path }));
    render(<DataLocationPanel panelStyle={PANEL} titleStyle={PANEL} />);
    expect(await screen.findByText(
      `Your data now lives in /Volumes/Drive/EIS. The previous copy is still in ${LOC.path}; you can delete it once you're happy.`,
    )).toBeTruthy();
    expect(sessionStorage.getItem("eis.dataLocationOutcome")).toBeNull();
  });

  it("Use default location runs the same flow against the default folder", async () => {
    state.loc = { ...LOC, path: "/Volumes/Drive/EIS", source: "chosen" };
    state.assessments.default = { action: "use_existing", path: LOC.path, workspace_count: 2, bytes: null, reason: null, code: null };
    render(<DataLocationPanel panelStyle={PANEL} titleStyle={PANEL} />);
    expect(await screen.findByText(/Chosen by you/)).toBeTruthy();
    fireEvent.click(screen.getByText("Use default location"));
    expect(await screen.findByText(/Use the data already here — 2 workspaces/)).toBeTruthy();
    fireEvent.click(screen.getByText("Use this location"));
    await waitFor(() => expect(state.changed).toEqual([{ default: true }]));
  });

  it("a location fixed by the environment can't be changed", async () => {
    state.loc = { ...LOC, path: "/data", source: "environment" };
    render(<DataLocationPanel panelStyle={PANEL} titleStyle={PANEL} />);
    expect(await screen.findByText("Set by the environment (SLINGOLOGY_EIS_HOME) · 2 workspaces")).toBeTruthy();
    expect(screen.queryByText("Change…")).toBeNull();
  });

  it("renders nothing without a local server", async () => {
    state.loc = null;
    const { container } = render(<DataLocationPanel panelStyle={PANEL} titleStyle={PANEL} />);
    await new Promise((r) => setTimeout(r, 0));
    expect(container.textContent).toBe("");
  });
});

describe("DataLocationGate", () => {
  beforeEach(() => {
    state.retried = 0;
    reload.mockReset();
    Object.defineProperty(window, "location", { configurable: true, value: { ...window.location, reload } });
  });

  it("shows the app when the location is reachable", async () => {
    state.loc = { ...LOC };
    render(<DataLocationGate><div>the app</div></DataLocationGate>);
    expect(await screen.findByText("the app")).toBeTruthy();
  });

  it("replaces every page with the notice when the chosen location is missing", async () => {
    state.loc = { ...LOC, path: "/Volumes/Gone/EIS", source: "chosen", missing: true, workspace_count: null };
    render(<DataLocationGate><div>the app</div></DataLocationGate>);
    expect(await screen.findByText("Your data location can't be reached")).toBeTruthy();
    expect(screen.getByText("/Volumes/Gone/EIS")).toBeTruthy();
    expect(screen.queryByText("the app")).toBeNull();

    fireEvent.click(screen.getByText("Try again"));
    await waitFor(() => expect(state.retried).toBe(1));
    expect(reload).not.toHaveBeenCalled();             // still missing

    state.loc = { ...state.loc, missing: false };
    fireEvent.click(screen.getByText("Try again"));
    await waitFor(() => expect(reload).toHaveBeenCalled());

    fireEvent.click(screen.getByText("Choose another location"));
    expect(screen.getByLabelText("Data location folder")).toBeTruthy();
  });
});
