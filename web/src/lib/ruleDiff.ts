import type { Insight, InsightSet } from "../types/contract";

// Originally shared between the rule playground (Baselines.tsx, used for
// Spec 14 §9 acceptance 6's side-by-side comparison, then removed —
// step 5) and the insight card's own rule editor (RuleEditPanel.tsx,
// still here). The two having shared this one function rather than
// independent implementations is what made "the card preview equals the
// retired playground's diff" true by construction, not by coincidence.

export function topicInsights(iset: InsightSet | undefined, topicId: string): Insight[] {
  return iset?.topics.find((t) => t.topic_id === topicId)?.insights ?? [];
}

export function insightSummary(insights: Insight[]): string {
  if (insights.length === 0) return "—";
  return insights.map((i) => `${i.trigger} (${i.severity})`).join(", ");
}

export type DiffKind = "added" | "removed" | "changed" | "same";

// Spec 03 §5.5's diff is "added, removed, or altered severity — a diffed
// list, not just a recount" (rule_id + severity, matching §7.2's own
// "counting (rule_id, severity) per flight as the playground does").
export function diffKind(before: Insight[], after: Insight[]): DiffKind {
  const beforeKey = before.map((i) => `${i.rule_id}:${i.severity}`).sort().join("|");
  const afterKey = after.map((i) => `${i.rule_id}:${i.severity}`).sort().join("|");
  if (beforeKey === afterKey) return "same";
  if (before.length === 0) return "added";
  if (after.length === 0) return "removed";
  return "changed";
}

export const DIFF_COLOR: Record<DiffKind, string> = {
  added: "var(--accent)",
  removed: "var(--text-tertiary)",
  changed: "var(--severity-watch)",
  same: "var(--text-tertiary)",
};

export const DIFF_LABEL: Record<DiffKind, string> = {
  added: "+ newly flagged",
  removed: "cleared",
  changed: "changed",
  same: "no change",
};
