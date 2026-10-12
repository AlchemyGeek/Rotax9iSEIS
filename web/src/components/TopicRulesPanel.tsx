import { useEffect, useMemo, useState } from "react";
import { getEngineClient } from "../lib/engineClient";
import { DIFF_COLOR, DIFF_LABEL, diffKind, topicInsights } from "../lib/ruleDiff";
import type { InsightSeverity, RuleSet, RuleTopic, RuleTrigger, TopicResult, WhatIfResult } from "../types/contract";

const client = getEngineClient();
const SEVERITIES: InsightSeverity[] = ["info", "watch", "warning", "limit"];

function clone<T>(x: T): T {
  return typeof structuredClone === "function" ? structuredClone(x) : JSON.parse(JSON.stringify(x));
}

function numberInput(value: number, onChange: (v: number) => void, opts?: { step?: number; min?: number; max?: number }) {
  return (
    <input
      type="number"
      className="mono"
      value={value}
      step={opts?.step ?? 1}
      min={opts?.min}
      max={opts?.max}
      onChange={(e) => onChange(Number(e.target.value))}
      style={{ width: 80, background: "var(--bg)", border: "1px solid var(--border)", borderRadius: 6, padding: "5px 8px", color: "var(--text-primary)", fontSize: 12 }}
    />
  );
}

function severitySelect(value: InsightSeverity | undefined, onChange: (v: InsightSeverity) => void) {
  return (
    <select
      className="mono"
      value={value ?? "watch"}
      onChange={(e) => onChange(e.target.value as InsightSeverity)}
      style={{ background: "var(--bg)", border: "1px solid var(--border)", borderRadius: 6, padding: "5px 8px", color: "var(--text-primary)", fontSize: 12 }}
    >
      {SEVERITIES.map((s) => (
        <option key={s} value={s}>{s}</option>
      ))}
    </select>
  );
}

function triggerSettingText(t: RuleTrigger): string {
  if (t.type === "threshold") {
    if (t.z != null) return `threshold · z ≤ ${t.z}`;
    if (t.condition) return `threshold · ${t.condition.replace(/_/g, " ")}`;
    return "threshold";
  }
  if (t.type === "baseline_deviation") return `baseline deviation · n ≥ ${t.n_min ?? 10}`;
  if (t.type === "trend") return `trend · R² ≥ ${t.r2_min ?? 0.5} · n ≥ ${t.n_min ?? 10}`;
  return t.type;
}

const ROW: React.CSSProperties = { display: "flex", alignItems: "center", justifyContent: "space-between", fontSize: 12, color: "var(--text-secondary)" };
const BUTTON: React.CSSProperties = { padding: "5px 12px", borderRadius: 6, fontSize: 11, cursor: "pointer" };
const RESET_LINK: React.CSSProperties = { marginLeft: 8, fontSize: 10, color: "var(--accent)", cursor: "pointer", textDecoration: "underline dotted" };

// Spec 14 §7.3 — the topic card's triggers disclosure and editor, closed
// by default. Every evaluated topic gets exactly one of these, whether
// or not it has a fired insight — this is also the insight card's own
// edit control in its open state (Spec 03 §5.2: "the insight card is
// the topic card with an insight"), so there is one implementation, not
// a second editor scoped to whichever single trigger happened to fire
// (that was v0.2's RuleEditPanel, retired by this component).
export function TopicRulesPanel({
  topicId, topic, resolvedRules, shippedRules, onApplied, onNavigateFlight, defaultOpen = false,
}: {
  topicId: string;
  topic: TopicResult;
  resolvedRules: RuleSet;
  shippedRules: RuleSet;
  onApplied: (rules: RuleSet) => void;
  onNavigateFlight: (flightId: string) => void;
  defaultOpen?: boolean;
}) {
  const [open, setOpen] = useState(defaultOpen);
  const [draftTopic, setDraftTopic] = useState<RuleTopic>(() => clone(resolvedRules.rules[topicId]));
  const [whatIf, setWhatIf] = useState<WhatIfResult | null>(null);
  const [diffing, setDiffing] = useState(false);
  const [applying, setApplying] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const savedTopic = resolvedRules.rules[topicId];

  // Resync the draft whenever the resolved rules change underneath us
  // (an apply or revert elsewhere) and this panel isn't mid-edit.
  useEffect(() => {
    if (!open) setDraftTopic(clone(savedTopic));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [savedTopic, topicId, open]);

  const dirty = JSON.stringify(draftTopic) !== JSON.stringify(savedTopic);

  // Debounced live preview (Spec 14 §7.2 item 3), unchanged from v0.2.
  useEffect(() => {
    if (!dirty) {
      setWhatIf(null);
      return;
    }
    setDiffing(true);
    const timer = setTimeout(async () => {
      try {
        const candidate: RuleSet = { ...resolvedRules, rules: { ...resolvedRules.rules, [topicId]: draftTopic } };
        const result = await client.whatIfRules({ rules: candidate });
        setWhatIf(result);
      } catch {
        setWhatIf(null);
      } finally {
        setDiffing(false);
      }
    }, 300);
    return () => clearTimeout(timer);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [draftTopic, dirty]);

  const diffRows = useMemo(() => {
    if (!whatIf) return [];
    return Object.entries(whatIf.flights).map(([flightId, { before, after }]) => ({
      flightId, kind: diffKind(topicInsights(before, topicId), topicInsights(after, topicId)),
    }));
  }, [whatIf, topicId]);
  const changedRows = diffRows.filter((r) => r.kind !== "same");

  function updateTrigger(idx: number, patch: Partial<RuleTrigger>) {
    setDraftTopic((prev) => {
      const next = clone(prev);
      if (next.triggers?.[idx]) Object.assign(next.triggers[idx], patch);
      return next;
    });
  }

  // "Reset to shipped per rule" (§7.3) — granular to the one trigger (or
  // the enabled flag) being reset, not the whole topic, so resetting one
  // field never discards an in-progress edit to another.
  function resetTriggerToShipped(idx: number) {
    const shippedTrigger = shippedRules.rules[topicId]?.triggers?.[idx];
    if (!shippedTrigger) return;
    setDraftTopic((prev) => {
      const next = clone(prev);
      if (next.triggers) next.triggers[idx] = clone(shippedTrigger);
      return next;
    });
  }

  function updateEnabled(v: boolean) {
    setDraftTopic((prev) => ({ ...clone(prev), enabled: v }));
  }

  function resetEnabledToShipped() {
    const shippedEnabled = shippedRules.rules[topicId]?.enabled ?? true;
    setDraftTopic((prev) => ({ ...clone(prev), enabled: shippedEnabled }));
  }

  function handleCancel() {
    setDraftTopic(clone(savedTopic));
    setError(null);
  }

  async function handleApply() {
    setApplying(true);
    setError(null);
    try {
      const res = await client.applyCardRuleEdit(topicId, draftTopic);
      onApplied(res.rules);
    } catch {
      setError("Couldn't reach the local server — nothing was applied.");
    } finally {
      setApplying(false);
    }
  }

  const statusByType = useMemo(() => {
    const m = new Map<string, { met: boolean | null; detail: string | null }>();
    for (const s of topic.trigger_status ?? []) m.set(s.type, s);
    return m;
  }, [topic]);

  const triggers = draftTopic.triggers ?? [];
  const enabledDirty = draftTopic.enabled !== savedTopic.enabled;

  return (
    <div style={{ marginTop: 4 }}>
      <div
        onClick={(e) => { e.preventDefault(); e.stopPropagation(); setOpen((v) => !v); }}
        style={{ fontSize: 11, color: dirty ? "var(--accent)" : "var(--text-tertiary)", cursor: "pointer" }}
      >
        {open ? "▾" : "▸"} triggers{dirty ? " (edited, not applied)" : ""}
      </div>
      {open && (
        <div
          onClick={(e) => e.stopPropagation()}
          style={{ background: "var(--bg)", border: "1px solid var(--border)", borderRadius: 8, padding: "12px 14px", marginTop: 6, display: "flex", flexDirection: "column", gap: 10 }}
        >
          <label style={ROW}>
            <span>
              enabled
              {enabledDirty && <span onClick={resetEnabledToShipped} style={RESET_LINK}>Reset to shipped</span>}
            </span>
            <input type="checkbox" checked={draftTopic.enabled} onChange={(e) => updateEnabled(e.target.checked)} />
          </label>

          {triggers.length === 0 && (
            <div style={{ fontSize: 11, color: "var(--text-tertiary)" }}>This topic has no editable triggers.</div>
          )}

          {triggers.map((t, idx) => {
            const status = statusByType.get(t.type);
            const triggerDirty = JSON.stringify(t) !== JSON.stringify(savedTopic.triggers?.[idx]);
            const structural = t.type === "threshold" && t.z == null;
            return (
              <div
                key={idx}
                style={{ display: "flex", flexDirection: "column", gap: 6, paddingTop: idx > 0 ? 8 : 0, borderTop: idx > 0 ? "1px solid var(--border)" : "none" }}
              >
                <div style={{ fontSize: 11, color: "var(--text-secondary)" }}>
                  {triggerSettingText(t)}
                  {triggerDirty && <span onClick={() => resetTriggerToShipped(idx)} style={RESET_LINK}>Reset to shipped</span>}
                </div>
                {status && (
                  <div style={{ fontSize: 11, color: "var(--text-tertiary)" }}>
                    {status.met === null ? "not met: not enough data on this flight" : status.met ? "met on this flight" : "not met on this flight"}
                    {status.detail ? ` — ${status.detail}` : ""}
                  </div>
                )}

                {t.type === "threshold" && t.z != null && (
                  <label style={ROW}>
                    <span>z (std devs from the personal model)</span>
                    {numberInput(t.z, (v) => updateTrigger(idx, { z: v }), { step: 0.1, min: 0 })}
                  </label>
                )}
                {t.type === "baseline_deviation" && (
                  <label style={ROW}>
                    <span>n_min (sample-size gate)</span>
                    {numberInput(t.n_min ?? 10, (v) => updateTrigger(idx, { n_min: v }), { min: 1 })}
                  </label>
                )}
                {t.type === "trend" && (
                  <>
                    <label style={ROW}>
                      <span>r2_min</span>
                      {numberInput(t.r2_min ?? 0.5, (v) => updateTrigger(idx, { r2_min: v }), { step: 0.05, min: 0, max: 1 })}
                    </label>
                    <label style={ROW}>
                      <span>n_min</span>
                      {numberInput(t.n_min ?? 10, (v) => updateTrigger(idx, { n_min: v }), { min: 1 })}
                    </label>
                  </>
                )}
                {structural && (
                  <label style={ROW}>
                    <span>severity (structural condition — only severity is editable)</span>
                    {severitySelect(t.severity, (v) => updateTrigger(idx, { severity: v }))}
                  </label>
                )}
              </div>
            );
          })}

          {dirty && (
            <div style={{ fontSize: 11 }}>
              {diffing ? (
                <span style={{ color: "var(--text-tertiary)" }}>Computing…</span>
              ) : whatIf ? (
                changedRows.length === 0 ? (
                  <span style={{ color: "var(--text-tertiary)" }}>On your {diffRows.length} flights: no change.</span>
                ) : (
                  <div>
                    <div style={{ color: "var(--text-secondary)", marginBottom: 4 }}>
                      On your {diffRows.length} flights: {changedRows.length} change{changedRows.length === 1 ? "" : "s"}
                      {" ("}{changedRows.filter((r) => r.kind === "added").length} newly flagged
                      {", "}{changedRows.filter((r) => r.kind === "removed").length} cleared
                      {", "}{changedRows.filter((r) => r.kind === "changed").length} changed severity).
                    </div>
                    <div style={{ display: "flex", flexDirection: "column", gap: 2, maxHeight: 120, overflowY: "auto" }}>
                      {changedRows.map((r) => (
                        <a
                          key={r.flightId}
                          href="#"
                          onClick={(e) => { e.preventDefault(); onNavigateFlight(r.flightId); }}
                          className="mono"
                          style={{ color: DIFF_COLOR[r.kind] }}
                        >
                          {r.flightId} &mdash; {DIFF_LABEL[r.kind]}
                        </a>
                      ))}
                    </div>
                  </div>
                )
              ) : null}
            </div>
          )}
          {error && <div style={{ fontSize: 11, color: "var(--severity-limit)" }}>{error}</div>}

          <div style={{ display: "flex", gap: 8 }}>
            <button onClick={handleCancel} disabled={!dirty} style={{ ...BUTTON, background: "transparent", border: "1px solid var(--border)", color: "var(--text-secondary)", cursor: dirty ? "pointer" : "default" }}>
              Cancel
            </button>
            <button
              onClick={handleApply}
              disabled={!dirty || applying}
              style={{ ...BUTTON, background: dirty ? "var(--accent)" : "var(--panel)", border: "none", color: dirty ? "var(--bg)" : "var(--text-tertiary)", fontWeight: 600, cursor: dirty && !applying ? "pointer" : "default" }}
            >
              {applying ? "Applying…" : "Apply"}
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
