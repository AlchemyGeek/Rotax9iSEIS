import { render, screen, fireEvent, waitFor, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { Journal } from "./Journal";
import type { Annotation, JournalEntry } from "../types/contract";

// Spec 14 v0.10 §6 — Journal is the register of decisions in force. The
// mocked server keeps the register the way the real one does: reversing
// a decision removes its entry; editing updates it.

const state: { entries: JournalEntry[]; annotations: Annotation[] } = { entries: [], annotations: [] };
const calls = vi.hoisted(() => ({
  deleteFilter: vi.fn(), revertRuleEdit: vi.fn(), includeFlight: vi.fn(), clearReference: vi.fn(),
  deleteAnnotation: vi.fn(), saveAnnotation: vi.fn(), confirmJournalNotice: vi.fn(), updateExclusionReason: vi.fn(),
}));
const drop = (id: string) => { state.entries = state.entries.filter((e) => e.ref_id !== id && e.id !== id); };
const touch = (refId: string, patch: Partial<JournalEntry>) => {
  state.entries = state.entries.map((e) => (e.ref_id === refId ? { ...e, ...patch, updated_at: "2026-10-14T12:00:00Z" } : e));
};

vi.mock("../lib/engineClient", () => ({
  getEngineClient: () => ({
    getJournal: async () => ({ entries: state.entries.map((e) => ({ ...e })) }),
    listAnnotations: async () => ({ annotations: state.annotations }),
    listFlights: async () => [{ flight_id: "f1", header: { date: "2026-10-01", start_utc: "2026-10-01T10:00:00Z" }, quality: [], source_filename: "log_20261001_100000_TEST.csv" }],
    previewReferenceMembership: async () => ({ changed_flight_ids: ["f3", "f4"] }),
    // NavShell's own attention badges (not under test here).
    filterHealth: async () => ({ health: [], attention_count: 0 }),
    getFleet: async () => ({ shift_history: [] }),
    getActiveWorkspace: async () => ({ active: false }),
    listWorkspaces: async () => [],
    deleteFilter: async (id: string) => { calls.deleteFilter(id); drop(id); return { deleted: true }; },
    revertRuleEdit: async (id: string) => { calls.revertRuleEdit(id); drop(id); return { rules: {} }; },
    includeFlight: async (id: string) => { calls.includeFlight(id); drop(id); return {}; },
    clearReference: async (id: string) => { calls.clearReference(id); drop(id); return {}; },
    deleteAnnotation: async (id: string) => { calls.deleteAnnotation(id); drop(id); return { deleted: true }; },
    saveAnnotation: async (p: { id: string; note: string }) => {
      calls.saveAnnotation(p);
      state.annotations = state.annotations.map((a) => (a.id === p.id ? { ...a, note: p.note } : a));
      touch(p.id, { what: p.note });
      return p;
    },
    updateExclusionReason: async (fid: string, reason: string) => { calls.updateExclusionReason(fid, reason); touch(fid, { reason }); return {}; },
    confirmJournalNotice: async (id: string, notice: string) => {
      calls.confirmJournalNotice(id, notice);
      state.entries = state.entries.map((e) => (e.id === id ? { ...e, notices: [] } : e));
      return {};
    },
  }),
}));

function entry(p: Partial<JournalEntry> & Pick<JournalEntry, "id" | "kind" | "ref_id" | "what">): JournalEntry {
  return { where: null, reason: null, note: null, created_at: "2026-10-01T00:00:00Z", updated_at: "2026-10-01T00:00:00Z", effect: null, current: null, notices: [], ...p };
}

function renderJournal() {
  render(<MemoryRouter><Journal /></MemoryRouter>);
}

const row = (id: string) => screen.getByTestId(`journal-entry-${id}`);

describe("Journal — register of decisions in force", () => {
  beforeEach(() => {
    Object.values(calls).forEach((f) => f.mockClear());
    state.annotations = [
      { id: "ann_1", flight_id: "f1", ref: { kind: "insight", insight_id: "ins_1" }, note: "checking density altitude", created_at: "2026-10-02T00:00:00Z" },
    ];
    state.entries = [
      entry({
        id: "jnl_f", kind: "limit_filter", ref_id: "flt_1", what: "Filter: Fuel pressure maximum",
        where: { target: { kind: "limit", limit_id: "fuel_press_max" } }, note: "sender reads high",
        current: "up to +1.5 psi", effect: { text: "suppressing 9 events on 6 flights", zero: false },
        created_at: "2026-10-03T12:00:00Z", updated_at: "2026-10-09T12:00:00Z",
      }),
      entry({
        id: "jnl_d", kind: "disabled_topic", ref_id: "egt_spread", what: "Rule: egt_spread", where: { topic_id: "egt_spread" },
        current: "off (shipped: on)", effect: { text: "removing 11 insights on 9 flights", zero: false }, updated_at: "2026-10-08T00:00:00Z",
      }),
      entry({
        id: "jnl_r", kind: "rule_edit", ref_id: "oil_temp_peak", what: "Rule: oil_temp_peak", where: { topic_id: "oil_temp_peak" },
        current: "baseline_deviation.n_min 5 (shipped 10)", effect: { text: "adds 1 insight on 1 flight compared with shipped", zero: false },
        updated_at: "2026-10-07T00:00:00Z",
      }),
      entry({
        id: "jnl_x", kind: "exclusion", ref_id: "f2", what: "log_20261002_100000_TEST.csv", where: { flight_id: "f2" },
        reason: "ground run, not a flight", effect: { text: "currently changes no other flight's verdict", zero: true },
        notices: [{ kind: "no_effect", text: "This exclusion no longer changes any other flight's verdict." }],
        updated_at: "2026-10-06T00:00:00Z",
      }),
      entry({ id: "jnl_a", kind: "annotation", ref_id: "ann_1", what: "checking density altitude", where: { flight_id: "f1" }, updated_at: "2026-10-05T00:00:00Z" }),
      entry({
        // Spec 14 v0.7: a CAS filter's target is named "<alert> (alert)".
        id: "jnl_c", kind: "limit_filter", ref_id: "flt_2", what: "Filter: ENGINE ECU (alert)",
        where: { target: { kind: "cas", cas_id: "ENGINE ECU" } }, current: "events up to 8 s",
        effect: { text: "currently suppresses nothing", zero: true }, updated_at: "2026-09-01T00:00:00Z",
      }),
    ];
  });

  it("shows each decision once, most recently changed first, with its live effect and the zero wording", async () => {
    renderJournal();
    await screen.findByText("Filter: Fuel pressure maximum");
    const titles = screen.getAllByTestId(/^journal-entry-/).map((n) => n.getAttribute("data-testid"));
    // The no-effect notice floats first; the rest by updated_at.
    expect(titles).toEqual(["journal-entry-jnl_x", "journal-entry-jnl_f", "journal-entry-jnl_d", "journal-entry-jnl_r", "journal-entry-jnl_a", "journal-entry-jnl_c"]);
    expect(within(row("jnl_f")).getByTestId("live-effect").textContent).toBe("Suppressing 9 events on 6 flights");
    expect(within(row("jnl_c")).getByTestId("live-effect").textContent).toBe("Currently suppresses nothing");
    expect(within(row("jnl_c")).getByText("Filter: ENGINE ECU (alert)")).toBeTruthy();
    expect(within(row("jnl_r")).getByText("baseline_deviation.n_min 5 (shipped 10)")).toBeTruthy();
    expect(within(row("jnl_f")).getByText("made October 3, 2026 · changed October 9, 2026")).toBeTruthy();
  });

  it("puts a change notice on its entry; Keep it confirms and clears it", async () => {
    renderJournal();
    const x = await screen.findByTestId("journal-entry-jnl_x");
    expect(within(x).getByTestId("change-notice").textContent).toContain("no longer changes any other flight's verdict");
    fireEvent.click(within(x).getByText("Keep it"));
    await waitFor(() => expect(calls.confirmJournalNotice).toHaveBeenCalledWith("jnl_x", "no_effect"));
    await waitFor(() => expect(within(row("jnl_x")).queryByTestId("change-notice")).toBeNull());
  });

  it("removing a filter previews, removes it and leaves no entry", async () => {
    renderJournal();
    const f = await screen.findByTestId("journal-entry-jnl_f");
    fireEvent.click(within(f).getByText("Remove filter"));
    const dialog = within(f).getByRole("dialog", { name: "Remove filter" });
    expect(dialog.textContent).toContain("Its events show again — it is suppressing 9 events on 6 flights.");
    expect(dialog.textContent).toContain("All flights in this workspace — this limit");
    fireEvent.click(within(dialog).getByRole("button", { name: "Apply to all flights" }));
    await waitFor(() => expect(calls.deleteFilter).toHaveBeenCalledWith("flt_1"));
    await waitFor(() => expect(screen.queryByTestId("journal-entry-jnl_f")).toBeNull());
  });

  it("Enable removes the disabled-topic entry; Reset to shipped removes the rule entry", async () => {
    renderJournal();
    fireEvent.click(within(await screen.findByTestId("journal-entry-jnl_d")).getByText("Enable"));
    fireEvent.click(within(row("jnl_d")).getByRole("button", { name: "Apply to all flights" }));
    await waitFor(() => expect(screen.queryByTestId("journal-entry-jnl_d")).toBeNull());
    expect(calls.revertRuleEdit).toHaveBeenCalledWith("jnl_d");

    fireEvent.click(within(row("jnl_r")).getByText("Reset to shipped"));
    fireEvent.click(within(row("jnl_r")).getByRole("button", { name: "Apply to all flights" }));
    await waitFor(() => expect(screen.queryByTestId("journal-entry-jnl_r")).toBeNull());
  });

  it("Include again goes through the exclusion dialog and removes the entry", async () => {
    renderJournal();
    fireEvent.click(within(await screen.findByTestId("journal-entry-jnl_x")).getByText("Include again"));
    const dialogButtons = await screen.findAllByRole("button", { name: /Include again|Apply/i });
    fireEvent.click(dialogButtons[dialogButtons.length - 1]);
    await waitFor(() => expect(calls.includeFlight).toHaveBeenCalledWith("f2"));
    await waitFor(() => expect(screen.queryByTestId("journal-entry-jnl_x")).toBeNull());
  });

  it("editing a note or an exclusion reason updates the one entry", async () => {
    renderJournal();
    fireEvent.click(within(await screen.findByTestId("journal-entry-jnl_a")).getByText("Edit"));
    fireEvent.change(within(row("jnl_a")).getByLabelText("Note"), { target: { value: "confirmed with a mechanic" } });
    fireEvent.click(within(row("jnl_a")).getByText("Save"));
    await waitFor(() => expect(within(row("jnl_a")).getByText("confirmed with a mechanic")).toBeTruthy());
    expect(screen.getAllByTestId(/^journal-entry-jnl_a$/)).toHaveLength(1);

    fireEvent.click(within(row("jnl_x")).getByText("Edit"));
    fireEvent.change(within(row("jnl_x")).getByLabelText("Reason"), { target: { value: "sender fault" } });
    fireEvent.click(within(row("jnl_x")).getByText("Save"));
    await waitFor(() => expect(within(row("jnl_x")).getByText("Reason: sender fault")).toBeTruthy());
    expect(calls.updateExclusionReason).toHaveBeenCalledWith("f2", "sender fault");
  });

  it("groups by flight", async () => {
    renderJournal();
    await screen.findByTestId("journal-entry-jnl_f");
    fireEvent.click(screen.getByRole("button", { name: "Flight" }));
    expect(screen.getByRole("heading", { name: "2026-10-01 · log_20261001_100000_TEST.csv" })).toBeTruthy();
    expect(screen.getByRole("heading", { name: "Whole workspace" })).toBeTruthy();
  });

  it("says so in one line when nothing is in force", async () => {
    state.entries = [];
    renderJournal();
    expect(await screen.findByText("No decisions in force.")).toBeTruthy();
  });
});

// Spec 14 v0.10: no closed or backfilled entries anywhere in the app.
const SOURCES = import.meta.glob<string>(["../**/*.{ts,tsx}", "!../**/*.test.{ts,tsx}"], {
  query: "?raw", import: "default", eager: true,
});

describe("Journal vocabulary", () => {
  it("has no 'backfilled' anywhere, and no 'closed' in the Journal's code", () => {
    for (const [path, text] of Object.entries(SOURCES)) {
      expect(/backfilled/i.test(text), path).toBe(false);
    }
    const contract = SOURCES["../types/contract.ts"];
    const kinds = contract.indexOf("export type JournalEntryKind");
    const entryType = contract.indexOf("export interface JournalEntry");
    const journalCode = [
      SOURCES["../views/Journal.tsx"],
      contract.slice(kinds, kinds + 300),
      contract.slice(entryType, contract.indexOf("export interface JournalNotice") + 120),
    ];
    for (const text of journalCode) expect(/\bclosed\b/i.test(text)).toBe(false);
  });
});
