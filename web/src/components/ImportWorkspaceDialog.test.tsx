import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { ImportWorkspaceDialog } from "./ImportWorkspaceDialog";
import { carriesText, matchText } from "../lib/importWorkspace";
import type { ImportMatchResult, WorkspaceExportSummary } from "../types/contract";

// Spec 03 v0.19 §5.8 — Import workspace: choose → summary → name → link
// logs → match result → Flights' Sync confirmation.

const SUMMARY: WorkspaceExportSummary = {
  workspace_name: "N117ZS", engine_model: "916iS", engine_version: "1.0.0", exported_at: "2026-10-15T00:00:00Z",
  flight_count: 40, date_range: ["2026-04-08", "2026-10-05"],
  carries: { filters: 4, phase_filters: 1, rule_edits: 2, disabled_topics: 0, reference_exclusions: 3, pins: 0,
             changed_settings: 1, notes: 12, journal_entries: 22 },
  logs_included: false, anonymised: false, logs_folder: null,
  engine_check: { status: "same", ok: true, message: null },
};
const MATCH: ImportMatchResult = {
  total: 40, found: Array.from({ length: 38 }, (_, i) => ({ flight_id: `f${i}`, filename: null, date: null })),
  missing: [
    { flight_id: "m1", date: "2026-05-01", airport_hint: "KAWO", sender_filename: "log_20260501_100000_KAWO.csv", reason: "" },
    { flight_id: "m2", date: "2026-05-02", airport_hint: "KPAE", sender_filename: "log_20260502_100000_KPAE.csv", reason: "" },
  ],
  extra: Array.from({ length: 12 }, (_, i) => ({ filename: `other_${i}.csv`, date: null })),
};

const state = { summary: SUMMARY, logsLinked: false };
const calls = vi.hoisted(() => ({ importWorkspace: vi.fn(), addLogFolder: vi.fn(), matchImport: vi.fn() }));

vi.mock("../lib/engineClient", () => ({
  getEngineClient: () => ({
    inspectWorkspaceExport: async () => state.summary,
    importWorkspace: async (src: unknown, name?: string) => {
      calls.importWorkspace(src, name);
      return { manifest: { id: "ws_new", name }, logs_linked: state.logsLinked };
    },
    addLogFolder: async (p: string) => { calls.addLogFolder(p); return {}; },
    matchImport: async () => { calls.matchImport(); return MATCH; },
  }),
}));

describe("ImportWorkspaceDialog", () => {
  beforeEach(() => {
    Object.values(calls).forEach((f) => f.mockClear());
    state.summary = SUMMARY;
    state.logsLinked = false;
  });

  it("shows the summary before creating anything, then names, links logs and matches", async () => {
    render(<ImportWorkspaceDialog onClose={() => {}} />);
    fireEvent.change(screen.getByLabelText("Export folder or file path"), { target: { value: "/x/N117ZS" } });
    fireEvent.click(screen.getByText("Open"));
    const summary = await screen.findByTestId("import-summary");
    expect(summary.textContent).toContain("916iS · engine 1.0.0");
    expect(summary.textContent).toContain("40 flights, 2026-04-08 to 2026-10-05");
    expect(summary.textContent).toContain("4 filters, 2 rule edits, 3 flights excluded from the reference, 1 changed setting, 12 notes");
    expect(calls.importWorkspace).not.toHaveBeenCalled();

    fireEvent.click(screen.getByText("Continue"));
    expect((screen.getByLabelText("Workspace name") as HTMLInputElement).value).toBe("N117ZS (imported)");
    fireEvent.click(screen.getByText("Create workspace"));
    await screen.findByText("Skip for now");
    expect(calls.importWorkspace).toHaveBeenCalledWith({ path: "/x/N117ZS" }, "N117ZS (imported)");

    fireEvent.change(screen.getByLabelText("Log folder path"), { target: { value: "/my/logs" } });
    fireEvent.click(screen.getByText("Add folder"));
    await waitFor(() => expect(calls.addLogFolder).toHaveBeenCalledWith("/my/logs"));
    fireEvent.click(screen.getByText("Find flights"));
    const result = await screen.findByTestId("match-result");
    expect(result.textContent).toContain("38 of 40 flights found · 2 missing · 12 other logs held out");
    expect(screen.getByText("Add another folder")).toBeTruthy();
    expect(screen.getByText("Continue")).toBeTruthy();
  });

  it("an export folder's logs are linked automatically: straight to the match result", async () => {
    state.summary = { ...SUMMARY, logs_included: true, logs_folder: "/x/N117ZS/logs" };
    state.logsLinked = true;
    render(<ImportWorkspaceDialog onClose={() => {}} />);
    fireEvent.change(screen.getByLabelText("Export folder or file path"), { target: { value: "/x/N117ZS" } });
    fireEvent.click(screen.getByText("Open"));
    await screen.findByTestId("import-summary");
    fireEvent.click(screen.getByText("Continue"));
    fireEvent.click(screen.getByText("Create workspace"));
    await screen.findByTestId("match-result");
    expect(calls.addLogFolder).not.toHaveBeenCalled();
  });

  it("an export from a newer engine is refused at the summary", async () => {
    state.summary = { ...SUMMARY, engine_check: { status: "older", ok: false, message: "This workspace needs engine 2.0.0 or later. Update the app to import it." } };
    render(<ImportWorkspaceDialog onClose={() => {}} />);
    fireEvent.change(screen.getByLabelText("Export folder or file path"), { target: { value: "/x" } });
    fireEvent.click(screen.getByText("Open"));
    expect(await screen.findByRole("alert")).toBeTruthy();
    expect(screen.getByRole("alert").textContent).toContain("needs engine 2.0.0 or later");
    expect(screen.queryByText("Continue")).toBeNull();
  });

  it("an older export imports with the notice", async () => {
    state.summary = { ...SUMMARY, engine_check: { status: "newer", ok: true, message: "Exported with engine 0.9.0; you have 1.0.0. Results reflect your newer engine and may differ." } };
    render(<ImportWorkspaceDialog onClose={() => {}} />);
    fireEvent.change(screen.getByLabelText("Export folder or file path"), { target: { value: "/x" } });
    fireEvent.click(screen.getByText("Open"));
    expect((await screen.findByRole("status")).textContent).toContain("may differ");
    expect(screen.getByText("Continue")).toBeTruthy();
  });

  it("wording helpers", () => {
    expect(matchText(MATCH)).toBe("38 of 40 flights found · 2 missing · 12 other logs held out");
    expect(carriesText({ ...SUMMARY.carries, filters: 0, rule_edits: 0, reference_exclusions: 0, changed_settings: 0, notes: 0 }))
      .toBe("no decisions or settings changes");
  });
});
