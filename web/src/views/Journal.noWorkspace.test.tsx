import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, it, expect, vi } from "vitest";

// A first run with no workspace yet (the browser host's usual start, or a
// server on a configured, empty data location): Journal is empty and says
// why — not "Couldn't load the Journal… restart the server".

vi.mock("../lib/engineClient", async () => {
  const actual = await vi.importActual<typeof import("../lib/engineClient")>("../lib/engineClient");
  const overrides: Record<string, unknown> = {
    getJournal: async () => { throw new actual.EngineRpcError("NO_ACTIVE_WORKSPACE", "no active workspace — create one first"); },
    listAnnotations: async () => ({ annotations: [] }),
    listFlights: async () => [],
    getCapabilities: async () => ({ host: "browser", engine_version: "1.0.1", host_version: "1.0.1", features: {} }),
    filterHealth: async () => ({ health: [], attention_count: 0 }),
    listWorkspaces: async () => [],
    getActiveWorkspace: async () => ({ active: false }),
  };
  const client = new Proxy(overrides, {
    get: (target, prop: string) => target[prop] ?? (async () => { throw new Error(`unmocked ${prop}`); }),
  });
  return { ...actual, getEngineClient: () => client };
});

import { Journal } from "./Journal";

describe("Journal with no workspace yet", () => {
  it("is empty and says to create a workspace, with no load error", async () => {
    render(<MemoryRouter initialEntries={["/journal"]}><Journal /></MemoryRouter>);
    expect((await screen.findByTestId("journal-no-workspace")).textContent).toContain("No workspace yet");
    expect(screen.queryByText(/Couldn't load the Journal/)).toBeNull();
  });
});
