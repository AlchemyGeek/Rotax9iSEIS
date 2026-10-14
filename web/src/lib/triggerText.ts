import type { RuleTrigger, TriggerStatus } from "../types/contract";

// Spec 14 §7.3 — how a trigger and its status on this flight read, shared
// by the card's read-only summary and the editor panel.
export function triggerSettingText(t: RuleTrigger): string {
  if (t.type === "threshold") {
    if (t.z != null) return `threshold · z ≤ ${t.z}`;
    if (t.condition) return `threshold · ${t.condition.replace(/_/g, " ")}`;
    return "threshold";
  }
  if (t.type === "baseline_deviation") return `baseline deviation · n ≥ ${t.n_min ?? 10}`;
  if (t.type === "trend") return `trend · R² ≥ ${t.r2_min ?? 0.5} · n ≥ ${t.n_min ?? 10}`;
  return t.type;
}

export function triggerStatusText(status: Pick<TriggerStatus, "met" | "detail">): string {
  const head = status.met === null ? "not met: not enough data on this flight" : status.met ? "met on this flight" : "not met on this flight";
  return status.detail ? `${head} — ${status.detail}` : head;
}
