import { useState } from "react";
import type { SliceCondition, SliceRule } from "../../types/contract";
import { PHASE_ORDER, phaseLabel } from "../../lib/phases";
import { RESEARCH_CHANNELS, channelLabel } from "../../lib/research";
import { BUTTON, INPUT, MUTED, PRIMARY, SELECT } from "./ui";

// Spec 06 §5.1 (D4): the structured slice rule — channel conditions ANDed,
// a minimum duration, a merge gap, a pad, an optional phase constraint.
// A duplicated preset opens here; the result is a plain rule object the
// host validates (the form never computes anything).

const OPS: SliceCondition["op"][] = [">=", ">", "<=", "<", "=", "between"];
const PHASES = PHASE_ORDER.filter((p) => p !== "PRE_START" && p !== "UNKNOWN");

function blankCondition(): SliceCondition {
  return { channel: "rpm", op: ">=", value: 0 };
}

export function SliceRuleEditor({ initial, onSave, onCancel }: { initial: SliceRule; onSave: (rule: SliceRule) => void; onCancel: () => void }) {
  const [name, setName] = useState(initial.name);
  const [conditions, setConditions] = useState<SliceCondition[]>(initial.conditions.length ? initial.conditions : []);
  const [minDuration, setMinDuration] = useState(String(initial.min_duration_s));
  const [mergeGap, setMergeGap] = useState(String(initial.merge_gap_s));
  const [pad, setPad] = useState(String(initial.pad_s));
  const [phaseMode, setPhaseMode] = useState<"within" | "overlap">(initial.phase?.mode ?? "within");
  const [phases, setPhases] = useState<string[]>(initial.phase?.phases ?? []);

  function setCondition(i: number, patch: Partial<SliceCondition> & { op?: SliceCondition["op"] }) {
    setConditions((cs) => cs.map((c, j) => {
      if (j !== i) return c;
      const next = { ...c, ...patch } as SliceCondition & { value?: number; min?: number; max?: number };
      if (next.op === "between") return { channel: next.channel, op: "between", min: next.min ?? 0, max: next.max ?? 0 };
      return { channel: next.channel, op: next.op, value: next.value ?? 0 };
    }));
  }

  const valid = (conditions.length > 0 || phases.length > 0) && name.trim().length > 0;

  function save() {
    onSave({
      rule_id: initial.rule_id,
      name: name.trim(),
      ...(initial.from_preset ? { from_preset: initial.from_preset } : {}),
      conditions,
      min_duration_s: Number(minDuration) || 0,
      merge_gap_s: Number(mergeGap) || 0,
      pad_s: Number(pad) || 0,
      phase: phases.length ? { mode: conditions.length ? phaseMode : "within", phases } : null,
    });
  }

  return (
    <div data-testid="slice-rule-editor" style={{ display: "flex", flexDirection: "column", gap: 10, padding: 12, background: "var(--bg)", border: "1px solid var(--border)", borderRadius: 8 }}>
      <label style={{ display: "flex", alignItems: "center", gap: 8, fontSize: 12 }}>
        <span style={{ width: 110, color: "var(--text-secondary)" }}>Rule name</span>
        <input value={name} onChange={(e) => setName(e.target.value)} style={{ ...INPUT, flexGrow: 1 }} aria-label="Rule name" />
      </label>

      <div style={{ fontSize: 12, color: "var(--text-secondary)" }}>Conditions <span style={MUTED}>(all must hold at the same time)</span></div>
      {conditions.map((c, i) => (
        <div key={i} style={{ display: "flex", alignItems: "center", gap: 6, flexWrap: "wrap" }} data-testid="rule-condition">
          <select value={c.channel} onChange={(e) => setCondition(i, { channel: e.target.value })} style={SELECT} aria-label="Channel">
            {[...new Set([c.channel, ...RESEARCH_CHANNELS])].map((ch) => <option key={ch} value={ch}>{channelLabel(ch)}</option>)}
          </select>
          <select value={c.op} onChange={(e) => setCondition(i, { op: e.target.value as SliceCondition["op"] })} style={SELECT} aria-label="Operator">
            {OPS.map((o) => <option key={o} value={o}>{o === "between" ? "between" : o.replace(">=", "≥").replace("<=", "≤")}</option>)}
          </select>
          {c.op === "between" ? (
            <>
              <input type="number" value={c.min} onChange={(e) => setCondition(i, { min: Number(e.target.value) } as Partial<SliceCondition>)} style={{ ...INPUT, width: 80 }} aria-label="Minimum" />
              <span style={MUTED}>and</span>
              <input type="number" value={c.max} onChange={(e) => setCondition(i, { max: Number(e.target.value) } as Partial<SliceCondition>)} style={{ ...INPUT, width: 80 }} aria-label="Maximum" />
            </>
          ) : (
            <input type="number" value={c.value} onChange={(e) => setCondition(i, { value: Number(e.target.value) } as Partial<SliceCondition>)} style={{ ...INPUT, width: 90 }} aria-label="Value" />
          )}
          <button type="button" onClick={() => setConditions((cs) => cs.filter((_, j) => j !== i))} style={{ ...BUTTON, padding: "3px 8px" }} aria-label="Remove condition">×</button>
        </div>
      ))}
      <div>
        <button type="button" onClick={() => setConditions((cs) => [...cs, blankCondition()])} style={BUTTON}>+ Add a condition</button>
      </div>

      <div style={{ display: "flex", gap: 14, flexWrap: "wrap", fontSize: 12 }}>
        <label style={{ display: "flex", alignItems: "center", gap: 6 }}>
          <span style={{ color: "var(--text-secondary)" }}>Lasts at least</span>
          <input type="number" min={0} value={minDuration} onChange={(e) => setMinDuration(e.target.value)} style={{ ...INPUT, width: 70 }} aria-label="Minimum duration (s)" /> s
        </label>
        <label style={{ display: "flex", alignItems: "center", gap: 6 }}>
          <span style={{ color: "var(--text-secondary)" }}>Bridge gaps under</span>
          <input type="number" min={0} value={mergeGap} onChange={(e) => setMergeGap(e.target.value)} style={{ ...INPUT, width: 70 }} aria-label="Merge gap (s)" /> s
        </label>
        <label style={{ display: "flex", alignItems: "center", gap: 6 }}>
          <span style={{ color: "var(--text-secondary)" }}>Pad each end by</span>
          <input type="number" min={0} value={pad} onChange={(e) => setPad(e.target.value)} style={{ ...INPUT, width: 70 }} aria-label="Pad (s)" /> s
        </label>
      </div>

      <div style={{ fontSize: 12, color: "var(--text-secondary)" }}>
        Phase constraint <span style={MUTED}>(optional — a rule with no conditions is a phase slice)</span>
      </div>
      <div style={{ display: "flex", gap: 6, flexWrap: "wrap", alignItems: "center" }}>
        {conditions.length > 0 && (
          <select value={phaseMode} onChange={(e) => setPhaseMode(e.target.value as "within" | "overlap")} style={SELECT} aria-label="Phase mode">
            <option value="within">only within</option>
            <option value="overlap">overlapping</option>
          </select>
        )}
        {PHASES.map((p) => {
          const on = phases.includes(p);
          return (
            <button key={p} type="button" onClick={() => setPhases((ps) => (on ? ps.filter((x) => x !== p) : [...ps, p]))}
              style={{ ...BUTTON, padding: "3px 9px", fontSize: 11, background: on ? "var(--brand-fill)" : "var(--panel-control)", color: on ? "var(--brand-tint)" : "var(--text-secondary)" }}
              aria-pressed={on}>
              {phaseLabel(p)}
            </button>
          );
        })}
      </div>

      <div style={{ display: "flex", gap: 8, justifyContent: "flex-end" }}>
        <button type="button" onClick={onCancel} style={BUTTON}>Cancel</button>
        <button type="button" onClick={save} disabled={!valid} style={{ ...PRIMARY, opacity: valid ? 1 : 0.5 }}>Use this rule</button>
      </div>
    </div>
  );
}

// One line a pilot can read, matching the engine's describe_rule.
export function describeRule(rule: SliceRule): string {
  if (rule.description) return rule.description;
  const parts = rule.conditions.map((c) => {
    const l = channelLabel(c.channel);
    if (c.op === "between") return `${l} between ${c.min} and ${c.max}`;
    return `${l} ${c.op.replace(">=", "≥").replace("<=", "≤")} ${c.value}`;
  });
  if (rule.phase) parts.push(`${rule.phase.mode === "within" ? "within" : "overlapping"} ${rule.phase.phases.map(phaseLabel).join(", ")}`);
  let s = parts.join(", ");
  if (rule.min_duration_s > 1) s += ` for ≥ ${rule.min_duration_s} s`;
  if (rule.merge_gap_s > 0) s += ` (gaps < ${rule.merge_gap_s} s bridged)`;
  return s;
}
