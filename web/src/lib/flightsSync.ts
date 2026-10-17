// Spec 03 v0.17 §5.1 — Flights' adding-logs and Sync wording.

// One or two dropped files analyse at once; this many or more go through
// the same "Analyze now?" question as Sync.
export const DROP_PROMPT_THRESHOLD = 3;

export function plural(n: number, word: string): string {
  return `${n} ${word}${n === 1 ? "" : "s"}`;
}

// "Found 2 new logs and 3 flights needing re-analysis. Analyze now?" —
// naming only the kinds of work actually found.
export function promptText(newLogs: number, stale: number): string {
  const parts = [
    newLogs > 0 ? plural(newLogs, "new log") : "",
    stale > 0 ? `${plural(stale, "flight")} needing re-analysis` : "",
  ].filter(Boolean);
  return `Found ${parts.join(" and ")}. Analyze now?`;
}
