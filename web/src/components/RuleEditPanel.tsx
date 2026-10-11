import { useEffect, useMemo, useState } from "react";
import { getEngineClient } from "../lib/engineClient";
import { DIFF_COLOR, DIFF_LABEL, diffKind, topicInsights } from "../lib/ruleDiff";
import type { RuleSet, RuleTopic, RuleTrigger, WhatIfResult } from "../types/contract";

const client = getEngineClient();

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

const ROW: React.CSSProperties = { display: "flex", alignItems: "center", justifyContent: "space-between", fontSize: 12, color: "var(--text-secondary)" };
const BUTTON: React.CSSProperties = { padding: "5px 12px", borderRadius: 6, fontSize: 11, cursor: "pointer" };

// Spec 14 §7.2 — the insight card's own rule editor, replacing the
// retired playground. Uses the exact same evaluate_insights-backed
// what_if_rules RPC and the exact same diffKind/DIFF_LABEL client-side
// classification (lib/ruleDiff.ts) the playground used, so the preview
// here and the playground's own diff can't disagree about the same
// edit (acceptance 6) — there's only one code path for both.
export function RuleEditPanel({
  topicId, triggerType, resolvedRules, shippedRules, onApplied, onCancel, onNavigateFlight,
}: {
  topicId: string;
  triggerType: RuleTrigger["type"];
  resolvedRules: RuleSet;
  shippedRules: RuleSet;
  onApplied: (rules: RuleSet) => void;
  onCancel: () => void;
  onNavigateFlight: (flightId: string) => void;
}) {
  const [draftTopic, setDraftTopic] = useState<RuleTopic>(() => clone(resolvedRules.rules[topicId]));
  const [whatIf, setWhatIf] = useState<WhatIfResult | null>(null);
  const [diffing, setDiffing] = useState(false);
  const [applying, setApplying] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const dirty = JSON.stringify(draftTopic) !== JSON.stringify(resolvedRules.rules[topicId]);

  // Debounced live preview (Spec 14 §7.2 item 3) — same 300ms debounce
  // the playground used, for the same reason: dragging/typing a value
  // shouldn't fire a what_if_rules round trip per keystroke.
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

  function updateTrigger(patch: Partial<RuleTrigger>) {
    setDraftTopic((prev) => {
      const next = clone(prev);
      const idx = (next.triggers ?? []).findIndex((t) => t.type === triggerType);
      if (idx >= 0) Object.assign(next.triggers![idx], patch);
      return next;
    });
  }

  function resetToShipped() {
    setDraftTopic(clone(shippedRules.rules[topicId]));
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

  const trigger = (draftTopic.triggers ?? []).find((t) => t.type === triggerType);
  if (!trigger) return null;

  return (
    <div style={{ background: "var(--bg)", border: "1px solid var(--border)", borderRadius: 8, padding: "12px 14px", marginTop: 6, display: "flex", flexDirection: "column", gap: 10 }}>
      <div style={{ fontSize: 11, fontWeight: 700, letterSpacing: 0.4, color: "var(--text-tertiary)" }}>
        EDIT RULE &middot; {topicId.replace(/_/g, " ")} &middot; {triggerType.replace(/_/g, " ")}
      </div>

      {triggerType === "threshold" && trigger.z != null && (
        <label style={ROW}>
          <span>z (std devs from the personal model)</span>
          {numberInput(trigger.z, (v) => updateTrigger({ z: v }), { step: 0.1, min: 0 })}
        </label>
      )}
      {triggerType === "threshold" && trigger.z == null && (
        <div style={{ fontSize: 11, color: "var(--text-tertiary)" }}>This threshold has no numeric setting editable from the card.</div>
      )}
      {triggerType === "baseline_deviation" && (
        <label style={ROW}>
          <span>n_min (sample-size gate)</span>
          {numberInput(trigger.n_min ?? 10, (v) => updateTrigger({ n_min: v }), { min: 1 })}
        </label>
      )}
      {triggerType === "trend" && (
        <>
          <label style={ROW}>
            <span>r2_min</span>
            {numberInput(trigger.r2_min ?? 0.5, (v) => updateTrigger({ r2_min: v }), { step: 0.05, min: 0, max: 1 })}
          </label>
          <label style={ROW}>
            <span>n_min</span>
            {numberInput(trigger.n_min ?? 10, (v) => updateTrigger({ n_min: v }), { min: 1 })}
          </label>
        </>
      )}

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
        <button onClick={resetToShipped} style={{ ...BUTTON, background: "transparent", border: "1px solid var(--border)", color: "var(--text-secondary)" }}>
          Reset to shipped
        </button>
        <button onClick={onCancel} style={{ ...BUTTON, background: "transparent", border: "1px solid var(--border)", color: "var(--text-secondary)" }}>
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
  );
}
