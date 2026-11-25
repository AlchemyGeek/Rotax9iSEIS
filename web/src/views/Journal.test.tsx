import { render, screen, fireEvent, waitFor, within } from "@testing-library/react";
import { MemoryRouter, Route, Routes, useLocation } from "react-router-dom";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { Journal } from "./Journal";
import type { Annotation, JournalEntry, JournalSection } from "../types/contract";

// Spec 14 §6 — Journal is the register of decisions in force. The mocked
// server keeps the register the way the real one does: reversing a
// decision removes its entry; editing updates it. §6.4 (v0.20): it also
// sends the sections in order of consequence with their totals, as the
// engine does, so the page computes nothing.

const state: { entries: JournalEntry[]; annotations: Annotation[]; fail: string | null } = { entries: [], annotations: [], fail: null };
const calls = vi.hoisted(() => ({
  deleteFilter: vi.fn(), revertRuleEdit: vi.fn(), includeFlight: vi.fn(), clearReference: vi.fn(),
  deleteAnnotation: vi.fn(), saveAnnotation: vi.fn(), confirmJournalNotice: vi.fn(), updateExclusionReason: vi.fn(),
  resetSetting: vi.fn(), forgetStudyFinding: vi.fn(),
}));
const drop = (id: string) => { state.entries = state.entries.filter((e) => e.ref_id !== id && e.id !== id); };
const touch = (refId: string, patch: Partial<JournalEntry>) => {
  state.entries = state.entries.map((e) => (e.ref_id === refId ? { ...e, ...patch, updated_at: "2026-10-14T12:00:00Z" } : e));
};

// The engine's sections (host._JOURNAL_SECTIONS), totals as it phrases them.
const ORDER: [string, string, JournalEntry["kind"][], boolean][] = [
  ["filters", "Limit filters", ["limit_filter"], true],
  ["exclusions", "Excluded flights", ["exclusion"], true],
  ["settings", "Changed settings and rule edits", ["changed_setting", "rule_edit"], true],
  ["topics", "Disabled topics", ["disabled_topic"], true],
  ["pins", "Pinned reference", ["reference_pin"], true],
  ["findings", "Research findings", ["study_finding"], true],
  ["annotations", "Annotations", ["annotation"], false],
];
function sections(): JournalSection[] {
  const out = ORDER.map(([key, label, kinds, open]) => {
    const mine = state.entries.filter((e) => kinds.includes(e.kind));
    return { key, label, kinds, count: mine.length, total: `${mine.length} · total of ${key}`, flights: 0, open, entry_ids: mine.map((e) => e.id) };
  }).filter((s) => s.count);
  if (out.length === 1) out[0].open = true;
  return out;
}

vi.mock("../lib/engineClient", async () => ({
  EngineRpcError: (await vi.importActual<typeof import("../lib/engineClient")>("../lib/engineClient")).EngineRpcError,
  getEngineClient: () => ({
    getJournal: async () => {
      if (state.fail) {
        const { EngineRpcError } = await vi.importActual<typeof import("../lib/engineClient")>("../lib/engineClient");
        throw new EngineRpcError("INTERNAL_ERROR", state.fail);
      }
      return { entries: state.entries.map((e) => ({ ...e })), sections: sections() };
    },
    listAnnotations: async () => ({ annotations: state.annotations }),
    listFlights: async () => [{ flight_id: "f1", header: { date: "2026-10-01", start_utc: "2026-10-01T10:00:00Z" }, quality: [], source_filename: "log_20261001_100000_TEST.csv" }],
    previewReferenceMembership: async () => ({ changed_flight_ids: ["f3", "f4"] }),
    // NavShell's attention badges and the limit-filter manager (not under test here).
    filterHealth: async () => ({ health: [], attention_count: 0 }),
    listFilters: async () => ({ filters: [] }),
    getFleet: async () => ({ shift_history: [] }),
    getActiveWorkspace: async () => ({ active: false }),
    listWorkspaces: async () => [],
    deleteFilter: async (id: string) => { calls.deleteFilter(id); drop(id); return { deleted: true }; },
    revertRuleEdit: async (id: string) => { calls.revertRuleEdit(id); drop(id); return { rules: {} }; },
    includeFlight: async (id: string) => { calls.includeFlight(id); drop(id); return {}; },
    clearReference: async (id: string) => { calls.clearReference(id); drop(id); return {}; },
    resetSetting: async (id: string) => { calls.resetSetting(id); drop(id); return {}; },
    forgetStudyFinding: async (id: string) => { calls.forgetStudyFinding(id); drop(id); return { removed: true }; },
    deleteAnnotation: async (id: string) => { calls.deleteAnnotation(id); drop(id); return { deleted: true }; },
    saveAnnotation: async (p: { id: string; note: string }) => {
      calls.saveAnnotation(p);
      state.annotations = state.annotations.map((a) => (a.id === p.id ? { ...a, note: p.note } : a));
      touch(p.id, { what: p.note, title: p.note });
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

function Where() {
  const l = useLocation();
  return <span data-testid="where">{l.pathname}</span>;
}
function renderJournal(at = "/journal") {
  render(<MemoryRouter initialEntries={[at]}><Routes><Route path="/journal" element={<Journal />} /><Route path="*" element={<Where />} /></Routes></MemoryRouter>);
}

const row = (id: string) => screen.getByTestId(`journal-entry-${id}`);
const open = (id: string) => fireEvent.click(within(row(id)).getByTestId("journal-line"));
function choose(id: string, label: string) {
  fireEvent.click(within(row(id)).getByTestId("journal-menu"));
  fireEvent.click(screen.getByRole("menuitem", { name: label }));
}
const sectionKeys = () => screen.getAllByTestId(/^journal-section-(?!total)/).map((n) => n.getAttribute("data-testid")!.replace("journal-section-", ""));

describe("Journal — register of decisions in force (Spec 14 §6.4 v0.20)", () => {
  beforeEach(() => {
    Object.values(calls).forEach((f) => f.mockClear());
    state.fail = null;
    state.annotations = [
      { id: "ann_1", flight_id: "f1", ref: { kind: "insight", insight_id: "ins_1" }, note: "checking density altitude", created_at: "2026-10-02T00:00:00Z" },
    ];
    state.entries = [
      entry({
        id: "jnl_f", kind: "limit_filter", ref_id: "flt_1", what: "Filter: Fuel pressure maximum", title: "Fuel pressure maximum",
        where: { target: { kind: "limit", limit_id: "fuel_press_max" } }, note: "sender reads high",
        current: "up to +1.5 psi", effect: { text: "suppressing 9 events on 6 flights", zero: false, short: "9 events · 6 flights" },
        created_at: "2026-10-03T12:00:00Z", updated_at: "2026-10-09T12:00:00Z",
      }),
      entry({
        id: "jnl_d", kind: "disabled_topic", ref_id: "egt_spread", what: "Rule: egt_spread", title: "Cylinder balance (EGT spread)", where: { topic_id: "egt_spread" },
        current: "off (shipped: on)", effect: { text: "removing 11 insights on 9 flights", zero: false, short: "11 insights · 9 flights" }, updated_at: "2026-10-08T00:00:00Z",
      }),
      entry({
        id: "jnl_r", kind: "rule_edit", ref_id: "oil_temp_peak", what: "Rule: oil_temp_peak", title: "Oil temperature peak", where: { topic_id: "oil_temp_peak" },
        current: "baseline_deviation.n_min 5 (shipped 10)", effect: { text: "adds 1 insight on 1 flight compared with shipped", zero: false, short: "+1 insight · 1 flight" },
        updated_at: "2026-10-07T00:00:00Z",
      }),
      entry({
        id: "jnl_x", kind: "exclusion", ref_id: "f2", what: "log_20261002_100000_TEST.csv", title: "log_20261002_100000_TEST.csv", where: { flight_id: "f2" },
        reason: "ground run, not a flight", effect: { text: "currently changes no other flight's verdict", zero: true, short: "changes no verdict" },
        notices: [{ kind: "no_effect", text: "This exclusion no longer changes any other flight's verdict." }],
        updated_at: "2026-10-06T00:00:00Z",
      }),
      entry({ id: "jnl_a", kind: "annotation", ref_id: "ann_1", what: "checking density altitude", title: "checking density altitude", where: { flight_id: "f1" }, updated_at: "2026-10-05T00:00:00Z" }),
      entry({
        id: "jnl_c", kind: "limit_filter", ref_id: "flt_2", what: "Filter: ENGINE ECU (alert)", title: "ENGINE ECU (alert)",
        where: { target: { kind: "cas", cas_id: "ENGINE ECU" } }, current: "events up to 8 s",
        effect: { text: "currently suppresses nothing", zero: true, short: "hides nothing" }, updated_at: "2026-09-01T00:00:00Z",
      }),
    ];
  });

  it("groups the entries by kind in order of consequence, each section with its total, one line per entry", async () => {
    renderJournal();
    await screen.findByText("Fuel pressure maximum");
    expect(sectionKeys()).toEqual(["filters", "exclusions", "settings", "topics", "annotations"]);
    expect(within(screen.getByTestId("journal-section-filters")).getByTestId("journal-section-total").textContent).toBe("2 · total of filters");
    // A line: glyph · title (no kind prefix) · the effect's short phrase · date.
    const f = row("jnl_f");
    expect(within(f).getByTestId("journal-title").textContent).toBe("Fuel pressure maximum");
    expect(within(f).getByTestId("live-effect").textContent).toBe("9 events · 6 flights");
    expect(within(f).getByTestId("journal-glyph").getAttribute("title")).toBe("Limit filter");
    // Zero: grey with a hollow dot, the cue to remove.
    expect(within(row("jnl_c")).getByTestId("live-effect").getAttribute("data-zero")).toBe("true");
    // Nothing expanded until asked; the value only on expand.
    expect(screen.queryByTestId("journal-expanded")).toBeNull();
    expect(screen.queryByText("up to +1.5 psi")).toBeNull();
    // Annotations are collapsed; their header opens them.
    expect(screen.queryByTestId("journal-entry-jnl_a")).toBeNull();
    fireEvent.click(within(screen.getByTestId("journal-section-annotations")).getByRole("button", { name: /Annotations/ }));
    expect(screen.getByTestId("journal-entry-jnl_a")).toBeTruthy();
  });

  it("a line opens in place: the value in mono, the full effect, the scope, the note in quotes, the dates", async () => {
    renderJournal();
    await screen.findByTestId("journal-entry-jnl_f");
    open("jnl_f");
    const x = within(row("jnl_f")).getByTestId("journal-expanded");
    expect(within(x).getByTestId("journal-value").className).toBe("mono");
    expect(within(x).getByTestId("journal-value").textContent).toBe("up to +1.5 psi");
    expect(x.textContent).toContain("Suppressing 9 events on 6 flights");
    expect(x.textContent).toContain("All flights in this workspace — this limit");
    expect(within(x).getByTestId("journal-note").textContent).toBe("“sender reads high”");
    expect(x.textContent).toContain("made October 3, 2026 · changed October 9, 2026");
    open("jnl_f");
    expect(within(row("jnl_f")).queryByTestId("journal-expanded")).toBeNull();
  });

  it("change notices come first, in their own block, with their one action; Keep it clears it", async () => {
    renderJournal();
    const block = await screen.findByTestId("journal-notices");
    const n = within(block).getByTestId("change-notice");
    expect(n.textContent).toContain("log_20261002_100000_TEST.csv");
    expect(n.textContent).toContain("no longer changes any other flight's verdict");
    fireEvent.click(within(n).getByText("Keep it"));
    await waitFor(() => expect(calls.confirmJournalNotice).toHaveBeenCalledWith("jnl_x", "no_effect"));
    await waitFor(() => expect(screen.queryByTestId("journal-notices")).toBeNull());
  });

  it("removing a filter from the ⋯ menu previews, removes it and leaves no entry", async () => {
    renderJournal();
    await screen.findByTestId("journal-entry-jnl_f");
    choose("jnl_f", "Remove filter");
    const dialog = within(row("jnl_f")).getByRole("dialog", { name: "Remove filter" });
    expect(dialog.textContent).toContain("Its events show again — it is suppressing 9 events on 6 flights.");
    expect(dialog.textContent).toContain("All flights in this workspace — this limit");
    fireEvent.click(within(dialog).getByRole("button", { name: "Apply to all flights" }));
    await waitFor(() => expect(calls.deleteFilter).toHaveBeenCalledWith("flt_1"));
    await waitFor(() => expect(screen.queryByTestId("journal-entry-jnl_f")).toBeNull());
  });

  it("Enable removes the disabled-topic entry; Reset to shipped removes the rule entry", async () => {
    renderJournal();
    await screen.findByTestId("journal-entry-jnl_d");
    choose("jnl_d", "Enable");
    fireEvent.click(within(row("jnl_d")).getByRole("button", { name: "Apply to all flights" }));
    await waitFor(() => expect(screen.queryByTestId("journal-entry-jnl_d")).toBeNull());
    expect(calls.revertRuleEdit).toHaveBeenCalledWith("jnl_d");

    choose("jnl_r", "Reset to shipped");
    fireEvent.click(within(row("jnl_r")).getByRole("button", { name: "Apply to all flights" }));
    await waitFor(() => expect(screen.queryByTestId("journal-entry-jnl_r")).toBeNull());
  });

  it("Include again goes through the exclusion dialog and removes the entry", async () => {
    renderJournal();
    await screen.findByTestId("journal-entry-jnl_x");
    choose("jnl_x", "Include again");
    const dialogButtons = await screen.findAllByRole("button", { name: /Include again|Apply/i });
    fireEvent.click(dialogButtons[dialogButtons.length - 1]);
    await waitFor(() => expect(calls.includeFlight).toHaveBeenCalledWith("f2"));
    await waitFor(() => expect(screen.queryByTestId("journal-entry-jnl_x")).toBeNull());
  });

  it("editing a note or an exclusion reason updates the one entry", async () => {
    renderJournal();
    await screen.findByTestId("journal-entry-jnl_x");
    fireEvent.click(within(screen.getByTestId("journal-section-annotations")).getByRole("button", { name: /Annotations/ }));
    choose("jnl_a", "Edit");
    fireEvent.change(within(row("jnl_a")).getByLabelText("Note"), { target: { value: "confirmed with a mechanic" } });
    fireEvent.click(within(row("jnl_a")).getByText("Save"));
    await waitFor(() => expect(within(row("jnl_a")).getByTestId("journal-title").textContent).toBe("confirmed with a mechanic"));
    expect(screen.getAllByTestId(/^journal-entry-jnl_a$/)).toHaveLength(1);

    choose("jnl_x", "Edit");
    fireEvent.change(within(row("jnl_x")).getByLabelText("Reason"), { target: { value: "sender fault" } });
    fireEvent.click(within(row("jnl_x")).getByText("Save"));
    await waitFor(() => expect(within(row("jnl_x")).getByTestId("journal-reason").textContent).toBe("“sender fault”"));
    expect(calls.updateExclusionReason).toHaveBeenCalledWith("f2", "sender fault");
  });

  it("groups by flight and by date", async () => {
    renderJournal();
    await screen.findByTestId("journal-entry-jnl_f");
    fireEvent.click(screen.getByRole("button", { name: "by flight" }));
    expect(screen.getByRole("heading", { name: "2026-10-01 · log_20261001_100000_TEST.csv" })).toBeTruthy();
    expect(screen.getByRole("heading", { name: "Whole workspace" })).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "by date" }));
    const heads = screen.getAllByRole("heading", { level: 2 }).map((h) => h.textContent);
    expect(heads.indexOf("October 9, 2026")).toBeLessThan(heads.indexOf("September 1, 2026"));
  });

  it("search finds entries by title, reason, note or flight, across closed sections", async () => {
    renderJournal();
    await screen.findByTestId("journal-entry-jnl_f");
    const box = screen.getByLabelText("Search the Journal");
    fireEvent.change(box, { target: { value: "ground run" } });
    expect(screen.getAllByTestId(/^journal-entry-/).map((n) => n.getAttribute("data-testid"))).toEqual(["journal-entry-jnl_x"]);
    fireEvent.change(box, { target: { value: "density" } });           // in the collapsed Annotations
    expect(screen.getAllByTestId(/^journal-entry-/).map((n) => n.getAttribute("data-testid"))).toEqual(["journal-entry-jnl_a"]);
    fireEvent.change(box, { target: { value: "log_20261001" } });       // by flight
    expect(screen.getAllByTestId(/^journal-entry-/).map((n) => n.getAttribute("data-testid"))).toEqual(["journal-entry-jnl_a"]);
    fireEvent.change(box, { target: { value: "nothing like this" } });
    expect(screen.getByText("Nothing in the Journal matches “nothing like this”.")).toBeTruthy();
  });

  it("no kind chips and no Limit filters tab; the filters section links Manage limit filters →", async () => {
    renderJournal();
    await screen.findByTestId("journal-entry-jnl_f");
    expect(screen.queryByRole("button", { name: /^All \(/ })).toBeNull();
    expect(screen.queryByRole("button", { name: /^Limit filters \(/ })).toBeNull();     // the old tab
    fireEvent.click(within(screen.getByTestId("journal-section-filters")).getByTestId("journal-manage-filters"));
    expect(await screen.findByTestId("journal-filters-manager")).toBeTruthy();
    fireEvent.click(screen.getByText("← Back to the Journal"));
    expect(await screen.findByTestId("journal-entry-jnl_f")).toBeTruthy();
  });

  it("?filters=1 opens the filter manager, also as a link followed with the page open", async () => {
    renderJournal("/journal?filters=1");
    expect(await screen.findByTestId("journal-filters-manager")).toBeTruthy();
    fireEvent.click(screen.getByText("← Back to the Journal"));
    expect(await screen.findByTestId("journal-entry-jnl_f")).toBeTruthy();
    expect(screen.queryByTestId("journal-filters-manager")).toBeNull();
  });

  it("shows the server's error instead of an empty page when the Journal can't be read", async () => {
    state.fail = "AttributeError: stale server";
    renderJournal();
    expect((await screen.findByRole("alert")).textContent).toContain("your decisions are still saved");
    expect(screen.getByText("AttributeError: stale server")).toBeTruthy();
    expect(screen.queryByText("No decisions in force.")).toBeNull();
    state.fail = null;
  });

  it("says so in one line when nothing is in force, with no notices block or controls", async () => {
    state.entries = [];
    renderJournal();
    expect(await screen.findByText("No decisions in force.")).toBeTruthy();
    expect(screen.queryByTestId("journal-notices")).toBeNull();
    expect(screen.queryByLabelText("Search the Journal")).toBeNull();
  });
});

describe("Journal — a research finding (Spec 14 §6.1 v0.20)", () => {
  beforeEach(() => {
    Object.values(calls).forEach((f) => f.mockClear());
    state.fail = null;
    state.annotations = [];
    state.entries = [
      entry({
        id: "jnl_s", kind: "study_finding", ref_id: "st-1:summary", what: "RPM swings 180 rpm at full power on 94 of 100 slices.",
        title: "Wobble: rpm swings after each takeoff", finding: "RPM swings 180 rpm at full power on 94 of 100 slices.",
        summary: "Found: the swing.\n\nWhat it means: the governor.", where: { study_id: "st-1", study_name: "Wobble: rpm swings after each takeoff" },
      }),
    ];
  });

  it("is the notebook title and the one-line finding; the summary and Open the notebook are behind the expand", async () => {
    renderJournal();
    const r = await screen.findByTestId("journal-entry-jnl_s");
    expect(within(r).getByTestId("journal-title").textContent).toBe("Wobble: rpm swings after each takeoff");
    expect(within(r).getByTestId("live-effect").textContent).toBe("RPM swings 180 rpm at full power on 94 of 100 slices.");
    expect(within(r).getByTestId("journal-title").style.fontWeight).toBe("400");      // body weight, not the summary in bold
    expect(within(r).queryByTestId("journal-summary")).toBeNull();
    open("jnl_s");
    expect(within(r).getByTestId("journal-summary").textContent).toContain("What it means: the governor.");
    choose("jnl_s", "Open the notebook");
    expect((await screen.findByTestId("where")).textContent).toBe("/research/st-1");
  });

  it("Remove from Journal leaves the notebook as it was", async () => {
    renderJournal();
    await screen.findByTestId("journal-entry-jnl_s");
    choose("jnl_s", "Remove from Journal");
    const dialog = within(row("jnl_s")).getByRole("dialog", { name: "Remove from Journal" });
    expect(dialog.textContent).toContain("the notebook keeps it");
    fireEvent.click(within(dialog).getByRole("button", { name: "Remove from Journal" }));
    await waitFor(() => expect(calls.forgetStudyFinding).toHaveBeenCalledWith("st-1:summary"));
    await waitFor(() => expect(screen.queryByTestId("journal-entry-jnl_s")).toBeNull());
  });
});

// Spec 14 v0.10: no closed or backfilled entries anywhere in the app.
const SOURCES = import.meta.glob<string>(["../**/*.{ts,tsx}", "!../**/*.test.{ts,tsx}"], {
  query: "?raw", import: "default", eager: true,
});
// This file is in views/, so the page is keyed "./Journal.tsx" (not "../views/…").
const PAGE = SOURCES["./Journal.tsx"] ?? SOURCES["../views/Journal.tsx"];

describe("Journal vocabulary", () => {
  it("has no 'backfilled' anywhere, and no 'closed' in the Journal's code", () => {
    expect(PAGE).toContain("export function Journal");
    for (const [path, text] of Object.entries(SOURCES)) {
      expect(/backfilled/i.test(text), path).toBe(false);
    }
    const contract = SOURCES["../types/contract.ts"];
    const kinds = contract.indexOf("export type JournalEntryKind");
    const entryType = contract.indexOf("export interface JournalEntry");
    const journalCode = [
      PAGE,
      contract.slice(kinds, kinds + 300),
      contract.slice(entryType, contract.indexOf("export interface JournalNotice") + 120),
    ];
    for (const text of journalCode) expect(/\bclosed\b/i.test(text)).toBe(false);
  });

  it("type: nothing under 13 px, and one accent — the notices block's", () => {
    const page = PAGE;
    const sizes = [...page.matchAll(/fontSize: (\d+)/g)].map((m) => Number(m[1]));
    expect(Math.min(...sizes)).toBeGreaterThanOrEqual(13);
    expect(page.match(/--severity-warning/g)?.length).toBeGreaterThan(0);
    expect(/--brand-tint|--brand-fill/.test(page)).toBe(false);
  });
});


describe("Journal — changed settings (Spec 14 v0.13)", () => {
  beforeEach(() => {
    Object.values(calls).forEach((f) => f.mockClear());
    state.fail = null;
    state.annotations = [];
    state.entries = [
      entry({
        id: "jnl_z", kind: "changed_setting", ref_id: "outlier_z_threshold", what: "Setting: Outlier z-threshold", title: "Outlier z-threshold",
        where: { setting: "outlier_z_threshold", tab: "reference" }, current: "2.5 (shipped: 2.0)",
        effect: { text: "removes 3 insights on 2 flights compared with shipped", zero: false, short: "−3 insights · 2 flights" },
      }),
    ];
  });

  it("shows the setting with its current and shipped value and live effect, and Reset to shipped removes it", async () => {
    renderJournal();
    await screen.findByText("Outlier z-threshold");
    const r = row("jnl_z");
    expect(within(r).getByTestId("journal-glyph").getAttribute("title")).toBe("Changed setting");
    expect(within(r).getByTestId("live-effect").textContent).toBe("−3 insights · 2 flights");
    open("jnl_z");
    expect(within(r).getByText(/2\.5 \(shipped: 2\.0\)/)).toBeTruthy();
    expect(within(r).getByText(/removes 3 insights on 2 flights compared with shipped/i)).toBeTruthy();
    expect(within(r).getByText("All flights in this workspace — every metric")).toBeTruthy();

    choose("jnl_z", "Reset to shipped");
    const dialog = await screen.findByRole("dialog", { name: "Reset to shipped" });
    expect(within(dialog).getByText(/goes back to its shipped value/)).toBeTruthy();
    fireEvent.click(within(dialog).getByText("Apply to all flights"));
    await waitFor(() => expect(calls.resetSetting).toHaveBeenCalledWith("outlier_z_threshold"));
    await waitFor(() => expect(screen.queryByTestId("journal-entry-jnl_z")).toBeNull());
  });

  it("opened from a Settings mark, focuses that entry, opened", async () => {
    renderJournal("/journal?entry=jnl_z");
    await screen.findByText("Outlier z-threshold");
    expect(row("jnl_z").getAttribute("data-focused")).toBe("true");
    expect(within(row("jnl_z")).getByTestId("journal-expanded")).toBeTruthy();
  });
});
