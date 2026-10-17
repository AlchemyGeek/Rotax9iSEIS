import type { DataLocationAssessment, DataLocationChange } from "../types/contract";

// Spec 14 v0.12 §5.2 — wording for the data-location flow
// (behaviour: Spec 02 v0.10 §5.8.1).

// A successful change reloads the app so every page reopens on the new
// root; the outcome message survives the reload under this key.
export const OUTCOME_KEY = "eis.dataLocationOutcome";

export function plural(n: number, word: string) {
  return `${n} ${word}${n === 1 ? "" : "s"}`;
}

function formatBytes(bytes: number) {
  if (bytes < 1024 * 1024) return `${Math.max(1, Math.round(bytes / 1024))} KB`;
  if (bytes < 1024 ** 3) return `${(bytes / 1024 ** 2).toFixed(1)} MB`;
  return `${(bytes / 1024 ** 3).toFixed(1)} GB`;
}

export function assessmentText(a: DataLocationAssessment): string {
  switch (a.action) {
    case "move":
      return `Move your data here — ${plural(a.workspace_count ?? 0, "workspace")}, ${formatBytes(a.bytes ?? 0)} to copy.`;
    case "use_existing":
      return `Use the data already here — ${plural(a.workspace_count ?? 0, "workspace")}. Your current data stays where it is.`;
    case "start_fresh":
      return "Start fresh here — this folder becomes a new, empty data location.";
    default:
      return a.reason ?? "This folder can't be used.";
  }
}

export function outcomeText(c: Pick<DataLocationChange, "action" | "path" | "previous_path">): string {
  if (c.action === "move") {
    return `Your data now lives in ${c.path}. The previous copy is still in ${c.previous_path}; you can delete it once you're happy.`;
  }
  if (c.action === "use_existing") return `Now using the data in ${c.path}. Your previous data is unchanged.`;
  return `Starting fresh in ${c.path}.`;
}
