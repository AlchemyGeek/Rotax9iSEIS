import type { ImportMatchResult, WorkspaceExportSummary } from "../types/contract";

// Spec 03 v0.19 §5.8 — wording and the last step of the import flow.

export function plural(n: number, word: string) {
  return `${n} ${word}${n === 1 ? "" : "s"}`;
}

export function carriesText(c: WorkspaceExportSummary["carries"]): string {
  const parts = [
    c.filters && plural(c.filters, "filter"),
    c.rule_edits && plural(c.rule_edits, "rule edit"),
    c.disabled_topics && plural(c.disabled_topics, "disabled topic"),
    c.reference_exclusions && `${plural(c.reference_exclusions, "flight")} excluded from the reference`,
    c.pins && plural(c.pins, "pinned reference"),
    c.changed_settings && plural(c.changed_settings, "changed setting"),
    c.notes && plural(c.notes, "note"),
  ].filter(Boolean);
  return parts.length ? parts.join(", ") : "no decisions or settings changes";
}

export function matchText(m: ImportMatchResult): string {
  return `${m.found.length} of ${m.total} flights found · ${m.missing.length} missing · ${plural(m.extra.length, "other log")} held out`;
}

export function finishImport() {
  // The new workspace is now active: reopen the app on Flights with the
  // Sync confirmation (Spec 03 §5.1), as a switch of workspace does.
  window.location.hash = "#/flights?sync=1";
  window.location.reload();
}
