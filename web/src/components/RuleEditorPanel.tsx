import { useEffect, useMemo, useState } from "react";
import { getEngineClient } from "../lib/engineClient";
import { DIFF_COLOR, DIFF_LABEL, diffKind, topicInsights } from "../lib/ruleDiff";
import { triggerSettingText, triggerStatusText } from "../lib/triggerText";
import type { InsightSeverity, RuleSet, RuleTopic, RuleTrigger, TopicResult, WhatIfResult } from "../types/contract";
import { InlineHelp } from "./InlineHelp";
import { ScopeCaption } from "./ScopeCaption";
import { APPLY_LABEL } from "../lib/scope";

const client = getEngineClient();
const SEVERITIES: InsightSeverity[] = ["info", "watch", "warning", "limit"];

function clone<T>(x: T): T {
  return typeof structuredClone === "function" ? structuredClone(x) : JSON.parse(JSON.stringify(x));
}

const INPUT: React.CSSProperties = { background: "var(--bg)", border: "1px solid var(--border)", borderRadius: 6, padding: "5px 8px", color: "var(--text-primary)", fontSize: 12 };

function numberInput(value: number, onChange: (v: number) => void, opts?: { step?: number; min?: number; max?: number; label?: string }) {
  return (
    <input
      type="number"
      className="mono"
      aria-label={opts?.label}
      value={value}
      step={opts?.step ?? 1}
      min={opts?.min}
      max={opts?.max}
      onChange={(e) => onChange(Number(e.target.value))}
      style={{ ...INPUT, width: 80 }}
    />
  );
}

const ROW: React.CSSProperties = { display: "flex", alignItems: "center", justifyContent: "space-between", gap: 10, fontSize: 12, color: "var(--text-secondary)" };
const BUTTON: React.CSSProperties = { padding: "6px 12px", borderRadius: 6, fontSize: 12, cursor: "pointer" };
const RESET_LINK: React.CSSProperties = { marginLeft: 8, fontSize: 10, color: "var(--link)", cursor: "pointer", textDecoration: "underline dotted" };

// Spec 14 v0.9 §7.3 — the rule editor panel: a side sheet over the Flight
// view, opened from a topic card's *Edit rules…* or an insight card's
// *Edit trigger ↓*. It knows its topic and the flight it was opened from.
// The §7.2 flow is unchanged from the card editor it replaces (v0.4–v0.8's
// TopicRulesPanel): debounced fleet-wide preview, Apply writes
// rules/active.json and a Journal entry (server side), Cancel discards,
// Reset to shipped per rule, the enabled toggle, scope captions. It is
// the one editor; nothing on the Flight view outside it takes input.
export function RuleEditorPanel({
  topicId, topic, title, originFlightId, originFlightLabel, resolvedRules, shippedRules, enable = false,
  onApplied, onClose, onNavigateFlight,
}: {
  topicId: string;
  topic: TopicResult;
  title: string;
  originFlightId: string;
  originFlightLabel: string;
  resolvedRules: RuleSet;
  shippedRules: RuleSet;
  // Opened from a disabled topic's *Enable*: start with enabled: true, so
  // the panel previews the re-enable before anything is applied.
  enable?: boolean;
  onApplied: (rules: RuleSet) => void;
  onClose: () => void;
  onNavigateFlight: (flightId: string) => void;
}) {
  const savedTopic = resolvedRules.rules[topicId];
  const [draftTopic, setDraftTopic] = useState<RuleTopic>(() => ({ ...clone(savedTopic), ...(enable ? { enabled: true } : {}) }));
  const [whatIf, setWhatIf] = useState<WhatIfResult | null>(null);
  const [diffing, setDiffing] = useState(false);
  const [applying, setApplying] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const dirty = JSON.stringify(draftTopic) !== JSON.stringify(savedTopic);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") onClose(); };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  // Debounced live preview (Spec 14 §7.2 item 3).
  useEffect(() => {
    if (!dirty) {
      setWhatIf(null);
      return;
    }
    setDiffing(true);
    const timer = setTimeout(async () => {
      try {
        const candidate: RuleSet = { ...resolvedRules, rules: { ...resolvedRules.rules, [topicId]: draftTopic } };
        setWhatIf(await client.whatIfRules({ rules: candidate }));
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
  // The originating flight first, then the rest.
  const changedRows = diffRows
    .filter((r) => r.kind !== "same")
    .sort((a, b) => Number(b.flightId === originFlightId) - Number(a.flightId === originFlightId));
  const originRow = diffRows.find((r) => r.flightId === originFlightId);

  function updateTrigger(idx: number, patch: Partial<RuleTrigger>) {
    setDraftTopic((prev) => {
      const next = clone(prev);
      if (next.triggers?.[idx]) Object.assign(next.triggers[idx], patch);
      return next;
    });
  }

  // Reset to shipped per rule — one trigger (or the enabled flag) at a
  // time, never discarding an in-progress edit to another.
  function resetTriggerToShipped(idx: number) {
    const shippedTrigger = shippedRules.rules[topicId]?.triggers?.[idx];
    if (!shippedTrigger) return;
    setDraftTopic((prev) => {
      const next = clone(prev);
      if (next.triggers) next.triggers[idx] = clone(shippedTrigger);
      return next;
    });
  }

  function resetEnabledToShipped() {
    const shippedEnabled = shippedRules.rules[topicId]?.enabled ?? true;
    setDraftTopic((prev) => ({ ...clone(prev), enabled: shippedEnabled }));
  }

  async function handleApply() {
    setApplying(true);
    setError(null);
    try {
      const res = await client.applyCardRuleEdit(topicId, draftTopic);
      onApplied(res.rules);
      onClose();
    } catch {
      setError("Couldn't reach the local server — nothing was applied.");
    } finally {
      setApplying(false);
    }
  }

  const statusByType = new Map((topic.trigger_status ?? []).map((s) => [s.type, s]));
  const triggers = draftTopic.triggers ?? [];
  const enabledDirty = draftTopic.enabled !== savedTopic.enabled;

  return (
    <>
      <div onClick={onClose} style={{ position: "fixed", inset: 0, background: "rgba(0,0,0,0.35)", zIndex: 40 }} />
      <aside
        role="dialog"
        aria-modal="true"
        aria-label={`Edit rules: ${title}`}
        style={{
          position: "fixed", top: 0, right: 0, bottom: 0, zIndex: 41,
          width: "min(440px, 100vw)", boxSizing: "border-box", overflowY: "auto",
          background: "var(--panel)", borderLeft: "1px solid var(--border)", boxShadow: "-8px 0 24px rgba(0,0,0,0.35)",
          padding: "18px 20px", display: "flex", flexDirection: "column", gap: 12,
        }}
      >
        <div style={{ display: "flex", alignItems: "flex-start", justifyContent: "space-between", gap: 10 }}>
          <div>
            <div style={{ fontSize: 15, fontWeight: 700 }}>{title}</div>
            <div style={{ fontSize: 11, color: "var(--text-tertiary)", marginTop: 2 }}>Rules · opened from the flight of {originFlightLabel}</div>
          </div>
          <button type="button" aria-label="Close" onClick={onClose} style={{ background: "none", border: "none", color: "var(--text-tertiary)", fontSize: 18, cursor: "pointer", lineHeight: 1 }}>×</button>
        </div>
        <ScopeCaption scope="topic" />

        <label style={ROW}>
          <span>
            enabled<InlineHelp id="trigger.enabled" />
            {enabledDirty && <span onClick={resetEnabledToShipped} style={RESET_LINK}>Reset to shipped</span>}
          </span>
          <input type="checkbox" aria-label="enabled" checked={draftTopic.enabled} onChange={(e) => setDraftTopic((prev) => ({ ...clone(prev), enabled: e.target.checked }))} />
        </label>

        {triggers.length === 0 && <div style={{ fontSize: 11, color: "var(--text-tertiary)" }}>This topic has no editable triggers.</div>}

        {triggers.map((t, idx) => {
          const status = statusByType.get(t.type);
          const triggerDirty = JSON.stringify(t) !== JSON.stringify(savedTopic.triggers?.[idx]);
          const structural = t.type === "threshold" && t.z == null;
          return (
            <div key={idx} style={{ display: "flex", flexDirection: "column", gap: 6, paddingTop: 10, borderTop: "1px solid var(--border)" }}>
              <div style={{ fontSize: 11, color: "var(--text-secondary)" }}>
                {triggerSettingText(t)}
                {t.type === "baseline_deviation" && <InlineHelp id="trigger.baseline_deviation" />}
                {triggerDirty && <span onClick={() => resetTriggerToShipped(idx)} style={RESET_LINK}>Reset to shipped</span>}
              </div>
              {status && <div style={{ fontSize: 11, color: "var(--text-tertiary)" }}>{triggerStatusText(status)}</div>}
              {t.type === "threshold" && t.z != null && (
                <label style={ROW}>
                  <span>z (std devs from the personal model)</span>
                  {numberInput(t.z, (v) => updateTrigger(idx, { z: v }), { step: 0.1, min: 0, label: "z" })}
                </label>
              )}
              {t.type === "baseline_deviation" && (
                <label style={ROW}>
                  <span>n_min (sample-size gate)<InlineHelp id="trigger.n_min" /></span>
                  {numberInput(t.n_min ?? 10, (v) => updateTrigger(idx, { n_min: v }), { min: 1, label: "n_min" })}
                </label>
              )}
              {t.type === "trend" && (
                <>
                  <label style={ROW}>
                    <span>r2_min<InlineHelp id="trigger.r2_min" /></span>
                    {numberInput(t.r2_min ?? 0.5, (v) => updateTrigger(idx, { r2_min: v }), { step: 0.05, min: 0, max: 1, label: "r2_min" })}
                  </label>
                  <label style={ROW}>
                    <span>n_min<InlineHelp id="trigger.n_min" /></span>
                    {numberInput(t.n_min ?? 10, (v) => updateTrigger(idx, { n_min: v }), { min: 1, label: "n_min" })}
                  </label>
                </>
              )}
              {structural && (
                <label style={ROW}>
                  <span>severity (structural condition — only severity is editable)</span>
                  <select
                    className="mono"
                    aria-label="severity"
                    value={t.severity ?? "watch"}
                    onChange={(e) => updateTrigger(idx, { severity: e.target.value as InsightSeverity })}
                    style={INPUT}
                  >
                    {SEVERITIES.map((s) => <option key={s} value={s}>{s}</option>)}
                  </select>
                </label>
              )}
            </div>
          );
        })}

        {dirty && (
          <div style={{ fontSize: 11, borderTop: "1px solid var(--border)", paddingTop: 10 }}>
            {diffing ? (
              <span style={{ color: "var(--text-tertiary)" }}>Computing…</span>
            ) : whatIf ? (
              <div>
                <div style={{ color: "var(--text-secondary)", marginBottom: 4 }} data-testid="origin-flight-preview">
                  This flight: {originRow ? DIFF_LABEL[originRow.kind] : "not in the preview"}.
                </div>
                {changedRows.length === 0 ? (
                  <span style={{ color: "var(--text-tertiary)" }}>On your {diffRows.length} flights: no change.</span>
                ) : (
                  <>
                    <div style={{ color: "var(--text-secondary)", marginBottom: 4 }}>
                      On your {diffRows.length} flights: {changedRows.length} change{changedRows.length === 1 ? "" : "s"}
                      {" ("}{changedRows.filter((r) => r.kind === "added").length} newly flagged
                      {", "}{changedRows.filter((r) => r.kind === "removed").length} cleared
                      {", "}{changedRows.filter((r) => r.kind === "changed").length} changed severity).
                      <InlineHelp id="preview.counts" />
                    </div>
                    <div style={{ display: "flex", flexDirection: "column", gap: 2, maxHeight: 200, overflowY: "auto" }}>
                      {changedRows.map((r) => (
                        <a
                          key={r.flightId}
                          href="#"
                          onClick={(e) => { e.preventDefault(); onNavigateFlight(r.flightId); }}
                          className="mono"
                          style={{ color: DIFF_COLOR[r.kind], fontWeight: r.flightId === originFlightId ? 700 : 400 }}
                        >
                          {r.flightId}{r.flightId === originFlightId ? " (this flight)" : ""} &mdash; {DIFF_LABEL[r.kind]}
                        </a>
                      ))}
                    </div>
                  </>
                )}
              </div>
            ) : null}
          </div>
        )}
        {error && <div style={{ fontSize: 11, color: "var(--severity-limit)" }}>{error}</div>}

        <div style={{ display: "flex", gap: 8, marginTop: "auto", paddingTop: 10 }}>
          <button type="button" onClick={onClose} style={{ ...BUTTON, background: "transparent", border: "1px solid var(--border)", color: "var(--text-secondary)" }}>
            Cancel
          </button>
          <button
            type="button"
            onClick={handleApply}
            disabled={!dirty || applying}
            style={{ ...BUTTON, background: dirty ? "var(--brand)" : "var(--panel-control)", border: "none", color: dirty ? "var(--on-brand)" : "var(--text-tertiary)", fontWeight: 600, cursor: dirty && !applying ? "pointer" : "default" }}
          >
            {applying ? "Applying…" : APPLY_LABEL.topic}
          </button>
        </div>
      </aside>
    </>
  );
}
