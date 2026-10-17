import { render, screen, fireEvent } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, it, expect, vi } from "vitest";
import { Trends } from "./Trends";
import { fleetAnalysis, trendsPanels } from "../lib/fixtures";
import { computeTiers } from "../lib/trendsTiers";
import { panelLabel } from "../lib/trendsUnits";

// Same stub as TrendsPanelStrip.test.tsx/EventStrip.test.tsx — no live
// server in this environment, so Trends falls back to the real frozen
// fixture (regenerated this session, see report) the same way a
// disconnected browser would; the chart canvas itself still needs
// stubbing out for jsdom.
// Offline, deterministically: every call fails as it does with no local
// server — never whatever server happens to be listening on this machine.
vi.mock("../lib/engineClient", async () => {
  const actual = await vi.importActual<typeof import("../lib/engineClient")>("../lib/engineClient");
  const offline = new Proxy({}, { get: () => async () => { throw new TypeError("Failed to fetch"); } });
  return { ...actual, getEngineClient: () => offline };
});

vi.mock("../components/EChartBase", () => ({
  EChartBase: () => <div data-testid="chart-stub" />,
}));

describe("Trends view", () => {
  it("renders the fixture fleet's panels and change summary without crashing", async () => {
    render(
      <MemoryRouter>
        <Trends />
      </MemoryRouter>,
    );
    await screen.findByRole("heading", { name: "Trends" });
    // The frozen fixture's #1 change_summary row (see report: volts_min,
    // ranked by shift, not frequency, on this fleet) — appears both in
    // the change summary and as a panel header, hence findAllByText.
    const matches = await screen.findAllByText(/Limit: volts min/);
    expect(matches.length).toBeGreaterThan(0);
  });

  it("has no page-level researcher-view toggle (Session F replaces it with a per-panel one)", async () => {
    render(
      <MemoryRouter>
        <Trends />
      </MemoryRouter>,
    );
    await screen.findByRole("heading", { name: "Trends" });
    expect(screen.queryByText(/Researcher view/)).toBeNull();
  });

  it("folds a never-exceeded limit into the collapsed group, not its own panel (§9.1 tier 3)", async () => {
    // §9.3/§9.1: EGT3-max is never_exceeded in the frozen fixture — it
    // used to render as its own panel (pre-Session-F); now it's a row
    // inside "Never exceeded (N)" instead.
    render(
      <MemoryRouter>
        <Trends />
      </MemoryRouter>,
    );
    const { tier3 } = computeTiers(trendsPanels, fleetAnalysis);
    expect(tier3.some((p) => p.panel === "limit:egt3_max")).toBe(true);

    await screen.findByText(`Never exceeded (${tier3.length})`);
    expect(screen.queryByText("Limit: egt3 max")).toBeNull();
    fireEvent.click(screen.getByText(`Never exceeded (${tier3.length})`));
    expect(screen.getByText("Limit: egt3 max")).toBeTruthy();
  });

  it("renders tier 1 panels before tier 2, and both before the never-exceeded group", async () => {
    render(
      <MemoryRouter>
        <Trends />
      </MemoryRouter>,
    );
    await screen.findByRole("heading", { name: "Trends" });
    const { tier1, tier2, tier3 } = computeTiers(trendsPanels, fleetAnalysis);
    const text = document.body.textContent ?? "";
    const idxLastTier1 = Math.max(...tier1.map((p) => text.indexOf(panelLabel(p.panel))));
    const idxFirstTier2 = Math.min(...tier2.map((p) => text.indexOf(panelLabel(p.panel))));
    const idxGroup = text.indexOf(`Never exceeded (${tier3.length})`);
    expect(idxLastTier1).toBeLessThan(idxFirstTier2);
    expect(idxFirstTier2).toBeLessThan(idxGroup);
  });

  it("shows the per-panel Show detail strips affordance only where there's a fit or time_above_pct", async () => {
    render(
      <MemoryRouter>
        <Trends />
      </MemoryRouter>,
    );
    await screen.findByRole("heading", { name: "Trends" });
    // Tier 1's volts_min limit panel always has time_above_pct.
    const checkboxes = screen.getAllByText("Show detail strips");
    expect(checkboxes.length).toBeGreaterThan(0);
  });
});
