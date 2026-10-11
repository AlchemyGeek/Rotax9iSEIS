import { render, screen, fireEvent, waitFor, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { Journal } from "./Journal";
import type { Annotation, FilterHealth, JournalEntry } from "../types/contract";

const state: { entries: JournalEntry[]; annotations: Annotation[]; health: FilterHealth[] } = {
  entries: [],
  annotations: [],
  health: [],
};

vi.mock("../lib/engineClient", () => ({
  getEngineClient: () => ({
    getJournal: async () => ({ entries: [...state.entries] }),
    listAnnotations: async () => ({ annotations: state.annotations }),
    filterHealth: async () => ({ health: state.health, attention_count: 0 }),
    // NavShell's own attention badges (not under test here).
    getFleet: async () => ({ shift_history: [] }),
    getActiveWorkspace: async () => ({ active: false }),
    listWorkspaces: async () => [],
    saveAnnotation: async (p: { id?: string; note: string }) => {
      const existing = state.annotations.find((a) => a.id === p.id);
      if (existing) existing.note = p.note;
      return existing;
    },
    deleteAnnotation: async (id: string) => {
      state.annotations = state.annotations.filter((a) => a.id !== id);
      const e = state.entries.find((e) => e.kind === "annotation" && e.ref_id === id);
      if (e) { e.status = "closed"; e.closed_at = "2026-10-11T00:00:00Z"; }
      return { deleted: true };
    },
    deleteFilter: async (id: string) => {
      const e = state.entries.find((e) => e.kind === "limit_filter" && e.ref_id === id);
      if (e) { e.status = "closed"; e.closed_at = "2026-10-11T00:00:00Z"; }
      return { deleted: true };
    },
    clearReference: async (metricId: string) => {
      const e = state.entries.find((e) => e.kind === "reference_pin" && e.ref_id === metricId);
      if (e) { e.status = "closed"; e.closed_at = "2026-10-11T00:00:00Z"; }
      return {};
    },
    includeFlight: async (flightId: string) => {
      const e = state.entries.find((e) => e.kind === "exclusion" && e.ref_id === flightId);
      if (e) { e.status = "closed"; e.closed_at = "2026-10-11T00:00:00Z"; }
      return {};
    },
  }),
}));

function renderJournal() {
  return render(
    <MemoryRouter>
      <Journal />
    </MemoryRouter>,
  );
}

describe("Journal", () => {
  beforeEach(() => {
    state.entries = [
      {
        id: "jnl_1", kind: "annotation", what: "checking density altitude", where: { flight_id: "f1" },
        at: "2026-10-01T00:00:00Z", status: "open", ref_id: "ann_1",
      },
      {
        id: "jnl_2", kind: "limit_filter", what: "Filter: fuel_press_max", where: { limit_id: "fuel_press_max" },
        at: "2026-10-05T00:00:00Z", status: "open", ref_id: "flt_1", note: "sender reads high",
      },
      {
        id: "jnl_3", kind: "reference_pin", what: "egt_spread", where: { metric_id: "egt_spread" },
        at: "2026-10-07T00:00:00Z", status: "open", ref_id: "egt_spread", effect: "n=9",
      },
      {
        id: "jnl_4", kind: "exclusion", what: "f2", where: { flight_id: "f2" },
        at: "2026-10-09T00:00:00Z", status: "open", ref_id: "f2", reason: "ground run, not a flight",
        effect: "changed the verdict on 1 other flight",
      },
    ];
    state.annotations = [
      { id: "ann_1", flight_id: "f1", ref: { kind: "flight" }, note: "checking density altitude", created_at: "2026-10-01T00:00:00Z" },
    ];
    state.health = [
      { filter_id: "flt_1", limit_id: "fuel_press_max", valid: true, status: "drifting", reasons: ["event frequency up"], diagnostics: [], series: [] },
    ];
  });

  it("lists entries newest first, across kinds, with live annotation text", async () => {
    renderJournal();
    await screen.findByText("Filter: fuel_press_max");
    // Entry title links all use href="#" — nav links (Flights, Settings...) don't.
    const titles = screen.getAllByRole("link")
      .filter((a) => a.getAttribute("href") === "#" && !a.textContent?.includes("→"))
      .map((a) => a.textContent);
    // jnl_4 (Oct 9) before jnl_3 (Oct 7) before jnl_2 (Oct 5) before jnl_1 (Oct 1).
    expect(titles[0]).toBe("f2");
    expect(titles[1]).toBe("egt_spread");
    expect(titles[2]).toBe("Filter: fuel_press_max");
    expect(screen.getByText("checking density altitude")).toBeTruthy();
  });

  it("pins a Drifting change notice to the top while unresolved", async () => {
    renderJournal();
    await screen.findByText(/Drifting/);
    expect(screen.getByText(/event frequency up/)).toBeTruthy();
  });

  it("filters by kind chip", async () => {
    renderJournal();
    await screen.findByText("Filter: fuel_press_max");
    fireEvent.click(screen.getByRole("button", { name: /Reference pinned/ }));
    expect(screen.getByText("egt_spread")).toBeTruthy();
    expect(screen.queryByText("Filter: fuel_press_max")).toBeNull();
  });

  it("unpinning a reference closes its entry in place (struck through, kept, not removed)", async () => {
    renderJournal();
    await screen.findByText("egt_spread");
    const row = screen.getByTestId("journal-entry-jnl_3");
    fireEvent.click(within(row).getByText("Unpin"));
    await waitFor(() => expect(within(row).getByText(/closed/)).toBeTruthy());
    // Still present, not removed.
    expect(screen.getByText("egt_spread")).toBeTruthy();
  });

  it("editing an annotation from its Journal row persists the new text", async () => {
    renderJournal();
    await screen.findByText("checking density altitude");
    fireEvent.click(screen.getByText("Edit"));
    const textarea = screen.getByRole("textbox") as HTMLTextAreaElement;
    fireEvent.change(textarea, { target: { value: "confirmed with a mechanic" } });
    fireEvent.click(screen.getByText("Save"));
    await waitFor(() => expect(screen.getByText("confirmed with a mechanic")).toBeTruthy());
  });

  it("shows the exclusion's reason and counted effect, and includes the flight again on reversal", async () => {
    renderJournal();
    await screen.findByText("f2");
    const row = screen.getByTestId("journal-entry-jnl_4");
    expect(within(row).getByText(/ground run, not a flight/)).toBeTruthy();
    expect(within(row).getByText(/changed the verdict on 1 other flight/)).toBeTruthy();
    fireEvent.click(within(row).getByText("Include again"));
    await waitFor(() => expect(within(row).getByText(/closed/)).toBeTruthy());
    expect(screen.getByText("f2")).toBeTruthy(); // still present, not removed
  });
});
