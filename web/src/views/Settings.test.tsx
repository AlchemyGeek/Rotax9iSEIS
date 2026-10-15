import { render, screen, fireEvent, waitFor, within } from "@testing-library/react";
import { MemoryRouter, Route, Routes, useLocation } from "react-router-dom";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { Settings } from "./Settings";
import {
  appSettings, engineLimits, fleetAnalysis, workspaceManifest, workspaceSettings,
} from "../lib/fixtures";
import type { ChangedSetting } from "../types/contract";

// Spec 14 v0.13 §5 (acceptance 2): no changelog; a setting that differs
// from shipped is marked with its shipped value, links to its Journal
// entry and offers Reset to shipped. The Engine tab shows the version.

const state = { changed: [] as ChangedSetting[] };
const calls = vi.hoisted(() => ({ resetSetting: vi.fn() }));

vi.mock("../lib/engineClient", async () => ({
  EngineRpcError: (await vi.importActual<typeof import("../lib/engineClient")>("../lib/engineClient")).EngineRpcError,
  getEngineClient: () => ({
    getAppSettings: async () => appSettings,
    getActiveWorkspace: async () => ({ active: true, manifest: workspaceManifest, settings: workspaceSettings }),
    getChartPresets: async () => ({ presets: [] }),
    getFleet: async () => fleetAnalysis,
    getEngineLimits: async () => ({ ...engineLimits, engine_version: "0.30.0" }),
    getWorkspaceRules: async () => ({ rules: { version: "1", rules: {} }, card_topic_ids: [] }),
    listChangedSettings: async () => ({ settings: state.changed }),
    resetSetting: async (refId: string) => {
      calls.resetSetting(refId);
      state.changed = state.changed.filter((c) => c.ref_id !== refId);
      return fleetAnalysis;
    },
    getDataLocation: async () => { throw new Error("not a local server"); },
    // NavShell's own data (not under test here).
    filterHealth: async () => ({ health: [], attention_count: 0 }),
    listWorkspaces: async () => [],
  }),
}));

function Where() {
  const loc = useLocation();
  return <div data-testid="where">{loc.pathname + loc.search}</div>;
}

function renderSettings(tab: string) {
  render(
    <MemoryRouter initialEntries={[`/settings?tab=${tab}`]}>
      <Routes>
        <Route path="/settings" element={<Settings />} />
        <Route path="/journal" element={<Where />} />
      </Routes>
    </MemoryRouter>,
  );
}

const Z: ChangedSetting = { ref_id: "outlier_z_threshold", label: "Outlier z-threshold", current: "2.5", shipped: "2.0", entry_id: "jnl_z" };

describe("Settings — changed settings (Spec 14 v0.13)", () => {
  beforeEach(() => {
    calls.resetSetting.mockClear();
    state.changed = [];
  });

  it("shows no changelog, and nothing marked when every setting is at shipped", async () => {
    renderSettings("reference");
    await screen.findByText("Comparison");
    await waitFor(() => expect(screen.getByText("default: 2.0")).toBeTruthy());
    expect(screen.queryByText(/Changelog/)).toBeNull();
    expect(screen.queryByText(/Changed · shipped/)).toBeNull();
  });

  it("marks a changed value with its shipped value and links to its Journal entry", async () => {
    state.changed = [Z];
    renderSettings("reference");
    const mark = await screen.findByTestId("changed-outlier_z_threshold");
    expect(mark.textContent).toContain("Changed · shipped: 2.0");
    fireEvent.click(within(mark).getByText("Journal entry →"));
    expect((await screen.findByTestId("where")).textContent).toBe("/journal?entry=jnl_z");
  });

  it("Reset to shipped resets that one setting", async () => {
    state.changed = [Z, { ref_id: "recent_window", label: "Recent window", current: "20 h, 5–15 flights", shipped: "10 h, 5–15 flights", entry_id: "jnl_w" }];
    renderSettings("reference");
    const mark = await screen.findByTestId("changed-outlier_z_threshold");
    expect(screen.getByTestId("changed-recent_window").textContent).toContain("shipped: 10 h, 5–15 flights");
    fireEvent.click(within(mark).getByText("Reset to shipped"));
    await waitFor(() => expect(calls.resetSetting).toHaveBeenCalledWith("outlier_z_threshold"));
    await waitFor(() => expect(screen.queryByTestId("changed-outlier_z_threshold")).toBeNull());
    expect(screen.getByTestId("changed-recent_window")).toBeTruthy();
  });

  it("lists a changed setting without a control of its own", async () => {
    state.changed = [{ ref_id: "frequency_delta", label: "Event-frequency drift threshold", current: "0.4", shipped: "0.3", entry_id: "jnl_f" }];
    renderSettings("reference");
    const other = await screen.findByTestId("other-changed-settings");
    expect(other.textContent).toContain("Event-frequency drift threshold: 0.4");
    expect(within(other).getByTestId("changed-frequency_delta")).toBeTruthy();
  });

  it("the Engine tab shows the engine version in effect", async () => {
    renderSettings("engine");
    expect(await screen.findByText("Engine version")).toBeTruthy();
    expect(screen.getByText("0.30.0")).toBeTruthy();
  });
});
