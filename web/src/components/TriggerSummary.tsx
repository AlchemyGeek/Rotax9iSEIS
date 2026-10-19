import { useState } from "react";
import type { RuleTopic, TopicResult } from "../types/contract";
import { triggerSettingText, triggerStatusText } from "../lib/triggerText";

// Spec 14 v0.9 §7.3 — the topic card's triggers disclosure, read-only:
// each trigger with its current value and whether it was met on this
// flight, plus the topic's enabled state. Nothing here is editable; the
// one action, Edit rules…, opens the rule editor panel.
export function TriggerSummary({ topic, rule, onEditRules }: {
  topic: TopicResult;
  rule: RuleTopic | null;
  onEditRules?: () => void;
}) {
  const [open, setOpen] = useState(false);
  const triggers = rule?.triggers ?? [];
  const statusByType = new Map((topic.trigger_status ?? []).map((s) => [s.type, s]));
  return (
    <div style={{ marginTop: 4 }} onClick={(e) => e.stopPropagation()}>
      <div style={{ display: "flex", alignItems: "center", gap: 12, fontSize: 11 }}>
        <span
          role="button"
          tabIndex={0}
          aria-expanded={open}
          onClick={(e) => { e.preventDefault(); setOpen((v) => !v); }}
          onKeyDown={(e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); setOpen((v) => !v); } }}
          style={{ color: "var(--text-tertiary)", cursor: "pointer" }}
        >
          {open ? "▾" : "▸"} triggers
        </span>
        {onEditRules && (
          <button
            type="button"
            onClick={(e) => { e.preventDefault(); onEditRules(); }}
            style={{ background: "none", border: "none", padding: 0, color: "var(--link)", textDecoration: "underline", textDecorationColor: "var(--link-underline)", textUnderlineOffset: 2, fontSize: 11, cursor: "pointer" }}
          >
            Edit rules…
          </button>
        )}
      </div>
      {open && (
        <div style={{ background: "var(--bg)", border: "1px solid var(--border)", borderRadius: 8, padding: "10px 12px", marginTop: 6, display: "flex", flexDirection: "column", gap: 6, fontSize: 11 }}>
          <div style={{ color: "var(--text-secondary)" }}>{topic.enabled === false || rule?.enabled === false ? "disabled" : "enabled"}</div>
          {rule === null && <div style={{ color: "var(--text-tertiary)" }}>Rules aren't available (no local server).</div>}
          {rule !== null && triggers.length === 0 && <div style={{ color: "var(--text-tertiary)" }}>This topic has no triggers.</div>}
          {triggers.map((t, idx) => {
            const status = statusByType.get(t.type);
            return (
              <div key={idx} style={{ paddingTop: idx > 0 ? 6 : 0, borderTop: idx > 0 ? "1px solid var(--border)" : "none" }}>
                <div style={{ color: "var(--text-secondary)" }}>{triggerSettingText(t)}{t.severity ? ` · ${t.severity}` : ""}</div>
                {status && <div style={{ color: "var(--text-tertiary)" }}>{triggerStatusText(status)}</div>}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
