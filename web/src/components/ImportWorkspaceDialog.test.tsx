import { render, screen, fireEvent } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { ImportWorkspaceDialog } from "./ImportWorkspaceDialog";
import { carriesText, matchText } from "../lib/importWorkspace";
import type { ImportMatchResult, WorkspaceExportSummary } from "../types/contract";

// Spec 03 v0.21 §5.8 — Import workspace: choose the export file (the zip
// as exported, sent to the local server as is) → summary → name → the
// zip's logs come with it and the match result shows → Flights' Sync; an
// .eisworkspace without logs gives an empty workspace.

const SUMMARY: WorkspaceExportSummary = {
  workspace_name: "N117ZS", engine_model: "916iS", engine_version: "1.0.0", exported_at: "2026-10-15T00:00:00Z",
  flight_count: 40, date_range: ["2026-04-08", "2026-10-05"],
  carries: { filters: 4, phase_filters: 1, rule_edits: 2, disabled_topics: 0, reference_exclusions: 3, pins: 0,
             changed_settings: 1, notes: 12, journal_entries: 22 },
  logs_included: true, anonymised: false, logs_folder: null, logs_in_file: 40,
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

const state = { summary: SUMMARY, logsLinked: true };
const calls = vi.hoisted(() => ({ uploadFile: vi.fn(), importWorkspace: vi.fn(), matchImport: vi.fn(), inspect: vi.fn() }));

vi.mock("../lib/engineClient", () => ({
  getEngineClient: () => ({
    uploadFile: async (f: File) => { calls.uploadFile(f.name); return { upload_id: "up1", filename: f.name, size: f.size }; },
    inspectWorkspaceExport: async (src: unknown) => { calls.inspect(src); return state.summary; },
    importWorkspace: async (src: unknown, name?: string) => {
      calls.importWorkspace(src, name);
      return { manifest: { id: "ws_new", name }, logs_linked: state.logsLinked };
    },
    matchImport: async () => { calls.matchImport(); return MATCH; },
  }),
}));

function choose(name: string) {
  fireEvent.change(screen.getByLabelText("Export file"), { target: { files: [new File(["x"], name)] } });
}

describe("ImportWorkspaceDialog", () => {
  beforeEach(() => {
    Object.values(calls).forEach((f) => f.mockClear());
    state.summary = SUMMARY;
    state.logsLinked = true;
  });

  it("the export zip as is: uploaded, summarised, then imported with its logs", async () => {
    render(<ImportWorkspaceDialog onClose={() => {}} />);
    expect(screen.queryByLabelText("Export folder or file path")).toBeNull();   // no path typing
    choose("N117ZS.zip");
    const summary = await screen.findByTestId("import-summary");
    expect(calls.uploadFile).toHaveBeenCalledWith("N117ZS.zip");
    expect(calls.inspect).toHaveBeenCalledWith({ upload_id: "up1" });
    expect(summary.textContent).toContain("916iS · engine 1.0.0");
    expect(summary.textContent).toContain("40 flights, 2026-04-08 to 2026-10-05");
    expect(summary.textContent).toContain("4 filters, 2 rule edits, 3 flights excluded from the reference, 1 changed setting, 12 notes");
    expect(summary.textContent).toContain("40 logs included — imported with the workspace");
    expect(calls.importWorkspace).not.toHaveBeenCalled();

    fireEvent.click(screen.getByText("Continue"));
    expect((screen.getByLabelText("Workspace name") as HTMLInputElement).value).toBe("N117ZS (imported)");
    fireEvent.click(screen.getByText("Create workspace"));
    const result = await screen.findByTestId("match-result");
    expect(calls.importWorkspace).toHaveBeenCalledWith({ upload_id: "up1" }, "N117ZS (imported)");
    expect(result.textContent).toContain("38 of 40 flights found · 2 missing · 12 other logs held out");
    expect(screen.getByTestId("linked-folders").textContent).toContain("40 logs from N117ZS.zip");
    expect(screen.getByText("Continue")).toBeTruthy();
  });

  it("an .eisworkspace without logs gives an empty workspace", async () => {
    state.summary = { ...SUMMARY, logs_included: false, logs_in_file: 0 };
    state.logsLinked = false;
    render(<ImportWorkspaceDialog onClose={() => {}} />);
    choose("N117ZS.eisworkspace");
    expect((await screen.findByTestId("import-summary")).textContent).toContain("No logs in this file — the workspace will start empty.");
    fireEvent.click(screen.getByText("Continue"));
    fireEvent.click(screen.getByText("Create workspace"));
    expect((await screen.findByTestId("import-empty")).textContent).toContain("created, empty");
    expect(screen.getByText("Open workspace")).toBeTruthy();
    expect(calls.matchImport).not.toHaveBeenCalled();
  });

  it("an export from a newer engine is refused at the summary", async () => {
    state.summary = { ...SUMMARY, engine_check: { status: "older", ok: false, message: "This workspace needs engine 2.0.0 or later. Update the app to import it." } };
    render(<ImportWorkspaceDialog onClose={() => {}} />);
    choose("N117ZS.zip");
    expect((await screen.findByRole("alert")).textContent).toContain("needs engine 2.0.0 or later");
    expect(screen.queryByText("Continue")).toBeNull();
  });

  it("an older export imports with the notice", async () => {
    state.summary = { ...SUMMARY, engine_check: { status: "newer", ok: true, message: "Exported with engine 0.9.0; you have 1.0.0. Results reflect your newer engine and may differ." } };
    render(<ImportWorkspaceDialog onClose={() => {}} />);
    choose("N117ZS.zip");
    expect((await screen.findByText(/may differ/)).textContent).toContain("Exported with engine 0.9.0");
    expect(screen.getByText("Continue")).toBeTruthy();
  });

  it("wording helpers", () => {
    expect(matchText(MATCH)).toBe("38 of 40 flights found · 2 missing · 12 other logs held out");
    expect(carriesText({ ...SUMMARY.carries, filters: 0, rule_edits: 0, reference_exclusions: 0, changed_settings: 0, notes: 0 }))
      .toBe("no decisions or settings changes");
  });
});
