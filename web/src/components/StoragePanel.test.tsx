import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { useEffect } from "react";
import { describe, it, expect, vi } from "vitest";
import { AppReset, resetApp } from "../lib/appReset";

// Spec 14 v0.17 §5.2.1: after Delete all data on this device the app goes
// to the first-run state itself — no reload.

const calls = vi.hoisted(() => ({ deleteAll: vi.fn(), reset: vi.fn() }));

vi.mock("../lib/engineClient", () => ({
  getEngineClient: () => ({
    getStorageUsage: async () => ({ total_bytes: 2_700_000, other_bytes: 1, workspace_count: 2, workspaces: [{ id: "a", name: "A", bytes: 1 }] }),
    deleteAllData: async () => { calls.deleteAll(); },
  }),
}));
vi.mock("../lib/appReset", async () => {
  const actual = await vi.importActual<typeof import("../lib/appReset")>("../lib/appReset");
  return { ...actual, resetApp: () => { calls.reset(); actual.resetApp(); } };
});

import { StoragePanel } from "./StoragePanel";

describe("Delete all data", () => {
  it("asks with the workspace count, deletes, and resets the app to Flights without a reload", async () => {
    window.location.hash = "#/settings?tab=app";
    render(<StoragePanel panelStyle={{}} titleStyle={{}} />);
    const panel = await screen.findByTestId("storage-panel");
    await waitFor(() => expect(panel.textContent).toContain("2.6 MB · per workspace"));
    fireEvent.click(screen.getByRole("button", { name: "Delete all data on this device" }));
    expect(screen.getByRole("dialog", { name: "Delete all data" }).textContent).toContain("Delete 2 workspaces");
    fireEvent.click(screen.getByRole("button", { name: "Delete" }));
    await waitFor(() => expect(calls.reset).toHaveBeenCalled());
    expect(calls.deleteAll).toHaveBeenCalled();
    expect(window.location.hash).toBe("#/flights");
  });

  it("AppReset mounts its pages afresh on resetApp, so they reload what's stored", () => {
    let mounts = 0;
    function Page() {
      useEffect(() => { mounts++; }, []);
      return <div>page</div>;
    }
    render(<AppReset><Page /></AppReset>);
    expect(mounts).toBe(1);
    act(() => resetApp());
    expect(mounts).toBe(2);
  });
});
