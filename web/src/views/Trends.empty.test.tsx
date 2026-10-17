import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, it, expect, vi } from "vitest";

// A workspace with no flights shows an empty state, not the sample data
// (which is only for when no local server answers).

vi.mock("../components/EChartBase", () => ({
  EChartBase: () => <div data-testid="chart-stub" />,
}));

vi.mock("../lib/engineClient", () => {
  const overrides: Record<string, unknown> = {
    getFleet: async () => ({
      fleet_key: "k", flight_ids: [], excluded: [], metrics: {}, models: [], quality: [], change_summary: [], shift_history: [],
      provenance: { baseline_config: { membership: "leave_one_out" } },
    }),
    getTrendsPanels: async () => ({ panels: [] }),
    filterHealth: async () => ({ health: [], attention_count: 0 }),
    getActiveWorkspace: async () => ({ active: true, manifest: { id: "ws", name: "Empty", log_folders: [] } }),
    listWorkspaces: async () => [],
    getAircraftSummary: async () => ({ idents: [], raw_idents: [], aliases: [] }),
  };
  const client = new Proxy(overrides, {
    get: (target, prop: string) => target[prop] ?? (async () => { throw new Error(`unmocked ${prop}`); }),
  });
  return { getEngineClient: () => client };
});

import { Trends } from "./Trends";

describe("Trends — an empty workspace", () => {
  it("says there's nothing to trend yet, with no sample panels", async () => {
    render(<MemoryRouter initialEntries={["/trends"]}><Trends /></MemoryRouter>);
    expect((await screen.findByTestId("trends-empty")).textContent).toContain("No flights in this workspace yet");
    expect(screen.queryByText(/sample data/)).toBeNull();
    expect(screen.getByText(/0 flights/)).toBeTruthy();
  });
});
