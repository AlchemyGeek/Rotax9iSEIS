import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { Settings } from "./Settings";
import { appSettings, engineLimits, fleetAnalysis, workspaceManifest, workspaceSettings } from "../lib/fixtures";
import type { ChangedSetting, LogChannelRow } from "../types/contract";

// Spec 14 v0.14 §5.3 — Settings → Engine → Log channels: raw
// general-purpose channels, unassigned by default; an assignment is a
// changed setting with its Journal entry and Reset to shipped.

const CO = { channel: "co_ppm", name: "CO", unit: "ppm" };
const row = (raw: string, assigned: boolean): LogChannelRow => ({
  raw, label: `analog ${raw.split("_").pop()}`, sources: ["AXIS"], flights: 1, min: 0, max: 22,
  assignment: assigned ? CO : null, options: [CO],
});
const state = vi.hoisted(() => ({ channels: [] as LogChannelRow[], changed: [] as ChangedSetting[] }));
const calls = vi.hoisted(() => ({ setChannelAssignment: vi.fn(), resetSetting: vi.fn() }));

vi.mock("../lib/engineClient", async () => ({
  EngineRpcError: (await vi.importActual<typeof import("../lib/engineClient")>("../lib/engineClient")).EngineRpcError,
  getEngineClient: () => ({
    getAppSettings: async () => appSettings,
    getActiveWorkspace: async () => ({ active: true, manifest: workspaceManifest, settings: workspaceSettings }),
    getChartPresets: async () => ({ presets: [] }),
    getFleet: async () => fleetAnalysis,
    getEngineLimits: async () => engineLimits,
    getWorkspaceRules: async () => ({ rules: { version: "1", rules: {} }, card_topic_ids: [] }),
    listChangedSettings: async () => ({ settings: state.changed }),
    getLogChannels: async () => ({ channels: state.channels }),
    setChannelAssignment: async (raw: string, target: string | null) => {
      calls.setChannelAssignment(raw, target);
      state.channels = state.channels.map((r) => (r.raw === raw ? row(raw, target === "co_ppm") : r));
      state.changed = target
        ? [{ ref_id: `channel_assignment:${raw}`, label: "Log channels — analog 7", current: "CO (ppm)", shipped: "Not assigned", entry_id: "jnl_a7" }]
        : [];
      return { channels: state.channels };
    },
    resetSetting: async (refId: string) => {
      calls.resetSetting(refId);
      state.channels = state.channels.map((r) => row(r.raw, false));
      state.changed = [];
      return fleetAnalysis;
    },
    getDataLocation: async () => { throw new Error("not a local server"); },
    filterHealth: async () => ({ health: [], attention_count: 0 }),
    listWorkspaces: async () => [],
  }),
}));

function renderEngineTab() {
  render(<MemoryRouter initialEntries={["/settings?tab=engine"]}><Settings /></MemoryRouter>);
}

describe("Settings → Engine → Log channels", () => {
  beforeEach(() => {
    calls.setChannelAssignment.mockClear();
    calls.resetSetting.mockClear();
    state.changed = [];
  });

  it("a G3X-only workspace: says there are none", async () => {
    state.channels = [];
    renderEngineTab();
    const panel = await screen.findByTestId("log-channels");
    expect(panel.textContent).toContain("No general-purpose channels in this workspace's logs.");
    expect(panel.textContent).toContain("All flights in this workspace");
  });

  it("lists raw channels unassigned; assigning marks it changed with its Journal entry; Reset clears it", async () => {
    state.channels = [row("gp_analog_3", false), row("gp_analog_7", false)];
    renderEngineTab();
    const r7 = await screen.findByTestId("log-channel-gp_analog_7");
    expect(r7.textContent).toContain("AXIS");
    expect(r7.textContent).toContain("0 – 22");
    const select = within(r7).getByLabelText("Assignment for analog 7") as HTMLSelectElement;
    expect(select.value).toBe("");
    expect(within(r7).getByRole("option", { name: "Not assigned" })).toBeTruthy();
    expect(screen.queryByText(/Changed · shipped/)).toBeNull();

    fireEvent.change(select, { target: { value: "co_ppm" } });
    await waitFor(() => expect(calls.setChannelAssignment).toHaveBeenCalledWith("gp_analog_7", "co_ppm"));
    const mark = await screen.findByTestId("changed-channel_assignment:gp_analog_7");
    expect(mark.textContent).toContain("shipped: Not assigned");
    expect(within(mark).getByText("Journal entry →")).toBeTruthy();

    fireEvent.click(within(mark).getByText("Reset to shipped"));
    await waitFor(() => expect(calls.resetSetting).toHaveBeenCalledWith("channel_assignment:gp_analog_7"));
    await waitFor(() => expect(screen.queryByTestId("changed-channel_assignment:gp_analog_7")).toBeNull());
    expect((within(screen.getByTestId("log-channel-gp_analog_7")).getByLabelText("Assignment for analog 7") as HTMLSelectElement).value).toBe("");
  });
});
