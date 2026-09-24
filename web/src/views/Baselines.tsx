import { useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { NavShell } from "../components/NavShell";
import { SeverityBadge } from "../components/SeverityBadge";
import { fleetAnalysis as fixtureFleet, insightRules as fixtureRules } from "../lib/fixtures";
import { getEngineClient } from "../lib/engineClient";
import type { BaselineConfig, FleetAnalysis, Insight, InsightSet, InsightSeverity, RuleSet, RuleTrigger, WhatIfResult } from "../types/contract";

const client = getEngineClient();

const SEVERITY_OPTIONS: InsightSeverity[] = ["info", "watch", "warning", "limit"];
const TRIGGER_LABEL: Record<RuleTrigger["type"], string> = {
  threshold: "threshold",
  baseline_deviation: "baseline deviation",
  trend: "trend",
};

function clone<T>(x: T): T {
  return typeof structuredClone === "function" ? structuredClone(x) : JSON.parse(JSON.stringify(x));
}

function topicInsights(iset: InsightSet | undefined, topicId: string): Insight[] {
  return iset?.topics.find((t) => t.topic_id === topicId)?.insights ?? [];
}

function insightSummary(insights: Insight[]): string {
  if (insights.length === 0) return "—";
  return insights.map((i) => `${i.trigger} (${i.severity})`).join(", ");
}

// Spec 03 §5.5's diff is "added, removed, or altered severity — a diffed
// list, not just a recount" — this is that classification, shared by the
// table render and the sidebar's per-topic "changed" indicator.
function diffKind(before: Insight[], after: Insight[]): "added" | "removed" | "changed" | "same" {
  const beforeKey = before.map((i) => `${i.rule_id}:${i.severity}`).sort().join("|");
  const afterKey = after.map((i) => `${i.rule_id}:${i.severity}`).sort().join("|");
  if (beforeKey === afterKey) return "same";
  if (before.length === 0) return "added";
  if (after.length === 0) return "removed";
  return "changed";
}

const DIFF_COLOR: Record<ReturnType<typeof diffKind>, string> = {
  added: "var(--accent)",
  removed: "var(--text-tertiary)",
  changed: "var(--severity-watch)",
  same: "var(--text-tertiary)",
};

const DIFF_LABEL: Record<ReturnType<typeof diffKind>, string> = {
  added: "+ newly flagged",
  removed: "cleared",
  changed: "changed",
  same: "no change",
};

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
      style={{ width: 90, background: "var(--bg)", border: "1px solid var(--border)", borderRadius: 6, padding: "6px 8px", color: "var(--text-primary)", fontSize: 13 }}
    />
  );
}

// The rule playground (Spec 03 §5.5) — "one editor over two underlying
// documents": rules/active.json (threshold/condition/n_min per trigger,
// persisted via saveWorkspaceRules) and FleetSelection.baseline_config
// (outlier_z_threshold global + per-metric override, persisted via
// saveBaselineConfig) — because to a pilot both are "how sensitive is
// this rule," even though they're stored separately (Spec 01 §8.4 v0.8).
// Editing either re-runs whatIfRules live against every flight in the
// fleet and shows which insights would be added/removed/changed, not
// just a recount.
export function Baselines() {
  const navigate = useNavigate();
  const [fleet, setFleet] = useState<FleetAnalysis>(fixtureFleet);
  const [resolvedRules, setResolvedRules] = useState<RuleSet>(fixtureRules);
  const [shippedRules, setShippedRules] = useState<RuleSet>(fixtureRules);
  const [draftRules, setDraftRules] = useState<RuleSet>(() => clone(fixtureRules));
  const [draftBaselineConfig, setDraftBaselineConfig] = useState<BaselineConfig>(() => clone(fixtureFleet.provenance.baseline_config));
  const [usingFixture, setUsingFixture] = useState(true);
  const [loading, setLoading] = useState(true);
  const [selectedTopic, setSelectedTopic] = useState("overboost_time");
  const [whatIf, setWhatIf] = useState<WhatIfResult | null>(null);
  const [diffing, setDiffing] = useState(false);
  const [applying, setApplying] = useState(false);
  const [resetting, setResetting] = useState(false);
  const [message, setMessage] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    async function load() {
      try {
        const [rulesResult, liveFleet] = await Promise.all([client.getWorkspaceRules(), client.getFleet()]);
        if (cancelled) return;
        if (liveFleet.flight_ids.length === 0) throw new Error("empty workspace");
        setResolvedRules(rulesResult.rules);
        setShippedRules(rulesResult.shipped_rules);
        setDraftRules(clone(rulesResult.rules));
        setFleet(liveFleet);
        setDraftBaselineConfig(clone(liveFleet.provenance.baseline_config));
        setUsingFixture(false);
        if (!(selectedTopic in rulesResult.rules.rules)) {
          setSelectedTopic(Object.keys(rulesResult.rules.rules)[0] ?? "overboost_time");
        }
      } catch {
        if (!cancelled) {
          setResolvedRules(fixtureRules);
          setShippedRules(fixtureRules);
          setDraftRules(clone(fixtureRules));
          setFleet(fixtureFleet);
          setDraftBaselineConfig(clone(fixtureFleet.provenance.baseline_config));
          setUsingFixture(true);
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    }
    load();
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const rulesDirty = JSON.stringify(draftRules) !== JSON.stringify(resolvedRules);
  const baselineDirty = JSON.stringify(draftBaselineConfig) !== JSON.stringify(fleet.provenance.baseline_config);
  const dirty = rulesDirty || baselineDirty;

  // Live diff (Spec 03 §5.5) — debounced so dragging/typing doesn't fire
  // a whatIfRules round trip per keystroke.
  useEffect(() => {
    if (usingFixture || !dirty) {
      setWhatIf(null);
      return;
    }
    setDiffing(true);
    const timer = setTimeout(async () => {
      try {
        const result = await client.whatIfRules({ rules: draftRules, baseline_config: draftBaselineConfig });
        setWhatIf(result);
      } catch {
        setWhatIf(null);
      } finally {
        setDiffing(false);
      }
    }, 300);
    return () => clearTimeout(timer);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [draftRules, draftBaselineConfig, usingFixture, dirty]);

  const flightMeta = useMemo(() => {
    const map: Record<string, { date: string; engine_hours: number }> = {};
    for (const m of Object.values(fleet.metrics)) {
      for (const p of m.points) {
        if (!(p.flight_id in map)) map[p.flight_id] = { date: p.date, engine_hours: p.x };
      }
    }
    return map;
  }, [fleet]);

  const diffRows = useMemo(() => {
    if (!whatIf) return [];
    return Object.entries(whatIf.flights)
      .map(([flightId, { before, after }]) => {
        const b = topicInsights(before, selectedTopic);
        const a = topicInsights(after, selectedTopic);
        return {
          flight_id: flightId,
          meta: flightMeta[flightId],
          before: b,
          after: a,
          kind: diffKind(b, a),
        };
      })
      .sort((x, y) => (x.meta?.date ?? "").localeCompare(y.meta?.date ?? ""));
  }, [whatIf, selectedTopic, flightMeta]);

  const changedCount = diffRows.filter((r) => r.kind !== "same").length;

  async function handleApply() {
    setApplying(true);
    try {
      if (rulesDirty) {
        const res = await client.saveWorkspaceRules(draftRules);
        setResolvedRules(res.rules);
      }
      if (baselineDirty) {
        const newFleet = await client.saveBaselineConfig(draftBaselineConfig);
        setFleet(newFleet);
      }
      setWhatIf(null);
      setMessage("Applied to workspace.");
    } catch {
      setMessage("Couldn't reach the local server — nothing was applied.");
    } finally {
      setApplying(false);
    }
  }

  async function handleResetToShipped() {
    setResetting(true);
    try {
      const res = await client.resetWorkspaceRules();
      setResolvedRules(res.rules);
      setDraftRules(clone(res.rules));
      const defaultBaseline: BaselineConfig = { membership: "leave_one_out", band_kind_by_metric: {}, outlier_z_threshold: 2.0 };
      const newFleet = await client.saveBaselineConfig(defaultBaseline);
      setFleet(newFleet);
      setDraftBaselineConfig(clone(defaultBaseline));
      setWhatIf(null);
      setMessage("Reset to shipped defaults.");
    } catch {
      setMessage("Couldn't reach the local server — nothing was reset.");
    } finally {
      setResetting(false);
    }
  }

  function updateTrigger(topicId: string, index: number, patch: Partial<RuleTrigger>) {
    setDraftRules((prev) => {
      const next = clone(prev);
      Object.assign(next.rules[topicId].triggers[index], patch);
      return next;
    });
  }

  function updateOverride(topicId: string, value: number | null) {
    setDraftBaselineConfig((prev) => {
      const next = clone(prev);
      const overrides = { ...(next.outlier_z_threshold_overrides ?? {}) };
      if (value === null) delete overrides[topicId];
      else overrides[topicId] = value;
      next.outlier_z_threshold_overrides = overrides;
      return next;
    });
  }

  const topicIds = Object.keys(draftRules.rules);
  const topic = draftRules.rules[selectedTopic];
  const shippedTopic = shippedRules.rules[selectedTopic];
  const hasBaselineDeviation = topic?.triggers.some((t) => t.type === "baseline_deviation") ?? false;
  const resolvedZ = draftBaselineConfig.outlier_z_threshold_overrides?.[selectedTopic] ?? draftBaselineConfig.outlier_z_threshold;
  const overridden = draftBaselineConfig.outlier_z_threshold_overrides?.[selectedTopic] !== undefined;

  return (
    <NavShell
      right={
        <div style={{ display: "flex", gap: 8 }}>
          <button
            onClick={handleResetToShipped}
            disabled={resetting || usingFixture}
            style={{ padding: "7px 14px", borderRadius: 8, background: "transparent", border: "1px solid var(--border)", color: "var(--text-secondary)", fontSize: 12, cursor: usingFixture ? "default" : "pointer" }}
          >
            {resetting ? "Resetting…" : "Reset to shipped defaults"}
          </button>
          <button
            onClick={handleApply}
            disabled={applying || !dirty || usingFixture}
            title={usingFixture ? "not connected to a live workspace" : undefined}
            style={{ padding: "7px 14px", borderRadius: 8, background: dirty ? "var(--accent)" : "var(--panel)", border: "1px solid var(--border)", color: dirty ? "var(--bg)" : "var(--text-tertiary)", fontSize: 12, fontWeight: 600, cursor: dirty && !usingFixture ? "pointer" : "default" }}
          >
            {applying ? "Applying…" : "Apply to workspace"}
          </button>
        </div>
      }
    >
      <div style={{ width: 300, flexShrink: 0, borderRight: "1px solid var(--border)", overflowY: "auto", padding: "18px 14px" }}>
        <div style={{ fontSize: 11, fontWeight: 700, letterSpacing: 0.5, color: "var(--text-tertiary)", padding: "0 8px 8px" }}>
          GLOBAL OUTLIER Z-THRESHOLD
        </div>
        <div style={{ padding: "10px 12px", background: "var(--panel)", borderRadius: 8, marginBottom: 14, display: "flex", alignItems: "center", justifyContent: "space-between", gap: 8 }}>
          {numberInput(draftBaselineConfig.outlier_z_threshold, (v) => setDraftBaselineConfig((p) => ({ ...p, outlier_z_threshold: v })), { step: 0.1, min: 0 })}
          <span style={{ fontSize: 11, color: "var(--text-tertiary)" }} title="Spec 01 §8.4 v0.8 — one number, drives both the Trends outlier marker and the baseline_deviation insight trigger, for every metric with no override.">
            default: 2.0
          </span>
        </div>

        <div style={{ fontSize: 11, fontWeight: 700, letterSpacing: 0.5, color: "var(--text-tertiary)", padding: "0 8px 8px" }}>
          RULES {usingFixture && <span style={{ color: "var(--text-tertiary)", fontWeight: 400 }}>(sample)</span>}
        </div>
        {topicIds.map((id) => {
          const isDirtyTopic =
            JSON.stringify(draftRules.rules[id]) !== JSON.stringify(resolvedRules.rules[id]) ||
            draftBaselineConfig.outlier_z_threshold_overrides?.[id] !== fleet.provenance.baseline_config.outlier_z_threshold_overrides?.[id];
          return (
            <div
              key={id}
              onClick={() => setSelectedTopic(id)}
              style={{
                padding: "9px 12px",
                borderRadius: 8,
                marginBottom: 2,
                fontSize: 13,
                fontWeight: id === selectedTopic ? 600 : 400,
                cursor: "pointer",
                background: id === selectedTopic ? "var(--accent-15)" : "transparent",
                color: id === selectedTopic ? "var(--accent)" : "var(--text-primary)",
                display: "flex",
                alignItems: "center",
                justifyContent: "space-between",
              }}
            >
              <span>{id}</span>
              {isDirtyTopic && <span style={{ width: 6, height: 6, borderRadius: "50%", background: "var(--accent)", flexShrink: 0 }} title="edited, not yet applied" />}
            </div>
          );
        })}

        <div style={{ fontSize: 11, fontWeight: 700, letterSpacing: 0.5, color: "var(--text-tertiary)", padding: "14px 8px 8px" }}>
          FLEET SELECTION {usingFixture && <span style={{ color: "var(--text-tertiary)", fontWeight: 400 }}>(sample)</span>}
        </div>
        {/* No flight list of its own (Spec 02 §5.1/§6.3, Spec 03 v0.6 §5.5)
            — membership isn't stored, so keeping a copy here would just be
            a second place for it to drift out of sync. Links out to
            Flights instead, where the exclude toggle/reason actually
            live. */}
        <div style={{ padding: "10px 12px", background: "var(--panel)", borderRadius: 8, fontSize: 12, color: "var(--text-secondary)" }}>
          {fleet.flight_ids.length} of {fleet.flight_ids.length + fleet.excluded.length} flights included
          <br />
          <span style={{ color: "var(--text-tertiary)" }}>{fleet.excluded.length} excluded</span>
          <br />
          <a href="#" onClick={(e) => { e.preventDefault(); navigate("/flights?filter=excluded"); }} style={{ fontSize: 12 }}>
            View flights →
          </a>
        </div>

        <div style={{ fontSize: 11, fontWeight: 700, letterSpacing: 0.5, color: "var(--text-tertiary)", padding: "14px 8px 8px" }}>
          ENGINE OVERRIDES
        </div>
        <div style={{ padding: "10px 12px", background: "var(--panel)", borderRadius: 8, fontSize: 12, color: "var(--text-secondary)" }} title="engine_overrides.json is named in Spec 02 §6.4 but not designed yet — no evidence a shipped engine profile needs overriding.">
          None active — using shipped limits.
        </div>
      </div>

      <div style={{ flexGrow: 1, overflowY: "auto", padding: "20px 28px", display: "flex", flexDirection: "column", gap: 16 }}>
        {loading ? (
          <div style={{ fontSize: 13, color: "var(--text-tertiary)" }}>Loading…</div>
        ) : !topic ? (
          <div style={{ fontSize: 13, color: "var(--text-tertiary)" }}>No rule selected.</div>
        ) : (
          <>
            <div style={{ display: "flex", alignItems: "baseline", justifyContent: "space-between" }}>
              <div>
                <h1 style={{ margin: "0 0 4px", fontSize: 19, fontWeight: 700 }}>{selectedTopic}</h1>
                <div style={{ fontSize: 12, color: "var(--text-tertiary)" }}>
                  {usingFixture
                    ? "Sample rule — connect to a live workspace to edit for real."
                    : "Workspace copy — editing this never touches the shipped insight_rules.json."}
                </div>
              </div>
              <label style={{ display: "flex", alignItems: "center", gap: 6, fontSize: 12, color: "var(--text-secondary)" }}>
                <input
                  type="checkbox"
                  checked={topic.enabled}
                  onChange={(e) =>
                    setDraftRules((prev) => {
                      const next = clone(prev);
                      next.rules[selectedTopic].enabled = e.target.checked;
                      return next;
                    })
                  }
                />
                enabled
              </label>
            </div>

            {message && (
              <div style={{ padding: "8px 14px", borderRadius: 8, background: "var(--panel)", border: "1px solid var(--border)", fontSize: 12, color: "var(--text-secondary)", display: "flex", justifyContent: "space-between" }}>
                <span>{message}</span>
                <a href="#" onClick={(e) => { e.preventDefault(); setMessage(null); }} style={{ fontSize: 11, color: "var(--text-tertiary)" }}>
                  dismiss
                </a>
              </div>
            )}

            <div style={{ background: "var(--panel)", borderRadius: 12, padding: 20, display: "flex", flexDirection: "column", gap: 18 }}>
              {topic.triggers.map((trig, i) => (
                <div key={i} style={{ borderTop: i > 0 ? "1px solid var(--border)" : undefined, paddingTop: i > 0 ? 16 : 0 }}>
                  <div style={{ display: "grid", gridTemplateColumns: "160px 1fr 200px", gap: 16, alignItems: "center" }}>
                    <label style={{ fontSize: 12, color: "var(--text-secondary)" }}>Trigger type</label>
                    <div className="mono" style={{ fontSize: 13, background: "var(--bg)", border: "1px solid var(--border)", borderRadius: 6, padding: "8px 10px" }}>
                      {TRIGGER_LABEL[trig.type]}
                    </div>
                    <div />

                    {trig.type === "threshold" && trig.limit !== undefined && (
                      <>
                        <label style={{ fontSize: 12, color: "var(--text-secondary)" }}>Limit{trig.unit ? ` (${trig.unit})` : ""}</label>
                        {numberInput(trig.limit, (v) => updateTrigger(selectedTopic, i, { limit: v }))}
                        <div style={{ fontSize: 11, color: "var(--text-tertiary)" }}>
                          shipped default: {shippedTopic?.triggers[i]?.limit ?? "—"}
                        </div>
                      </>
                    )}
                    {trig.type === "threshold" && trig.limit === undefined && (
                      <>
                        <label style={{ fontSize: 12, color: "var(--text-secondary)" }}>Condition</label>
                        <div className="mono" style={{ fontSize: 12, color: "var(--text-tertiary)" }}>
                          {trig.condition}
                          {trig.tolerance_hpa !== undefined && ` (±${trig.tolerance_hpa} hPa)`}
                        </div>
                        <div style={{ fontSize: 11, color: "var(--text-tertiary)" }}>structural — not editable here</div>
                      </>
                    )}

                    {trig.type === "baseline_deviation" && (
                      <>
                        <label style={{ fontSize: 12, color: "var(--text-secondary)" }}>Sample-size gate (n_min)</label>
                        {numberInput(trig.n_min ?? 10, (v) => updateTrigger(selectedTopic, i, { n_min: v }), { min: 0 })}
                        <div style={{ fontSize: 11, color: "var(--text-tertiary)" }}>
                          shipped default: {shippedTopic?.triggers[i]?.n_min ?? 10}
                        </div>

                        <label style={{ fontSize: 12, color: "var(--text-secondary)" }}>Outlier z-threshold</label>
                        <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                          <label style={{ display: "flex", alignItems: "center", gap: 6, fontSize: 12 }}>
                            <input
                              type="checkbox"
                              checked={overridden}
                              onChange={(e) => updateOverride(selectedTopic, e.target.checked ? draftBaselineConfig.outlier_z_threshold : null)}
                            />
                            override for this metric
                          </label>
                          {overridden &&
                            numberInput(resolvedZ, (v) => updateOverride(selectedTopic, v), { step: 0.1, min: 0 })}
                        </div>
                        <div style={{ fontSize: 11, color: "var(--text-tertiary)" }}>
                          resolved: {resolvedZ} {!overridden && "(global default)"}
                        </div>
                      </>
                    )}

                    {trig.type === "trend" && (
                      <>
                        <label style={{ fontSize: 12, color: "var(--text-secondary)" }}>Direction</label>
                        <select
                          value={trig.direction}
                          onChange={(e) => updateTrigger(selectedTopic, i, { direction: e.target.value as "increasing" | "decreasing" })}
                          style={{ background: "var(--bg)", border: "1px solid var(--border)", borderRadius: 6, padding: "6px 8px", color: "var(--text-primary)", fontSize: 13, width: 130 }}
                        >
                          <option value="increasing">increasing</option>
                          <option value="decreasing">decreasing</option>
                        </select>
                        <div />

                        <label style={{ fontSize: 12, color: "var(--text-secondary)" }}>Min R²</label>
                        {numberInput(trig.r2_min ?? 0.5, (v) => updateTrigger(selectedTopic, i, { r2_min: v }), { step: 0.05, min: 0, max: 1 })}
                        <div style={{ fontSize: 11, color: "var(--text-tertiary)" }}>shipped default: {shippedTopic?.triggers[i]?.r2_min ?? 0.5}</div>

                        <label style={{ fontSize: 12, color: "var(--text-secondary)" }}>Sample-size gate (n_min)</label>
                        {numberInput(trig.n_min ?? 10, (v) => updateTrigger(selectedTopic, i, { n_min: v }), { min: 0 })}
                        <div />
                      </>
                    )}

                    <label style={{ fontSize: 12, color: "var(--text-secondary)" }}>Severity</label>
                    <select
                      value={trig.severity ?? "watch"}
                      onChange={(e) => updateTrigger(selectedTopic, i, { severity: e.target.value as InsightSeverity })}
                      style={{ background: "var(--bg)", border: "1px solid var(--border)", borderRadius: 6, padding: "6px 8px", color: "var(--text-primary)", fontSize: 13, width: 130 }}
                    >
                      {SEVERITY_OPTIONS.map((s) => (
                        <option key={s} value={s}>{s}</option>
                      ))}
                    </select>
                    <div />
                  </div>
                </div>
              ))}
              {!hasBaselineDeviation && topic.triggers.every((t) => t.type === "threshold" && t.limit === undefined) && (
                <div style={{ fontSize: 12, color: "var(--text-tertiary)" }}>
                  This rule's condition is structural (not a tunable number) — nothing to drag here, but severity is still editable.
                </div>
              )}
            </div>

            <div style={{ background: "var(--panel)", borderRadius: 12, padding: "18px 20px" }}>
              <div style={{ display: "flex", alignItems: "baseline", justifyContent: "space-between", marginBottom: 2 }}>
                <span style={{ fontSize: 13, fontWeight: 600 }}>Live impact across the fleet</span>
                <span style={{ fontSize: 12, color: "var(--accent)", fontWeight: 600 }}>
                  {usingFixture
                    ? "connect to a live workspace to see this"
                    : diffing
                    ? "computing…"
                    : !dirty
                    ? "no edits yet"
                    : `${changedCount} flight${changedCount === 1 ? "" : "s"} changed`}
                </span>
              </div>
              <div style={{ fontSize: 12, color: "var(--text-tertiary)", marginBottom: 12 }}>
                Every flight in the current fleet selection, re-evaluated under the draft above — added, removed, or changed severity, not just a count.
              </div>

              {diffRows.length > 0 && (
                <div style={{ maxHeight: 360, overflowY: "auto" }}>
                  <table>
                    <thead>
                      <tr style={{ borderBottom: "1px solid var(--border)" }}>
                        <th style={{ color: "var(--text-tertiary)", fontWeight: 500 }}>Flight</th>
                        <th style={{ color: "var(--text-tertiary)", fontWeight: 500 }}>Before</th>
                        <th style={{ color: "var(--text-tertiary)", fontWeight: 500 }}>After</th>
                        <th style={{ color: "var(--text-tertiary)", fontWeight: 500 }}>Change</th>
                      </tr>
                    </thead>
                    <tbody>
                      {diffRows.map((r) => (
                        <tr
                          key={r.flight_id}
                          style={{ borderBottom: "1px solid var(--border-subtle)", background: r.kind === "added" ? "var(--accent-06)" : "transparent" }}
                        >
                          <td
                            className="mono"
                            style={{ cursor: "pointer" }}
                            onClick={() => navigate(`/flights/${r.flight_id}`)}
                          >
                            {r.meta ? `${r.meta.date} · ${r.meta.engine_hours}h` : r.flight_id}
                          </td>
                          <td style={{ fontSize: 12, color: "var(--text-tertiary)" }}>{insightSummary(r.before)}</td>
                          <td style={{ fontSize: 12, color: r.after.length ? "var(--text-primary)" : "var(--text-tertiary)" }}>
                            {r.after.length > 0 && <SeverityBadge severity={r.after[0].severity} size="sm" />}{" "}
                            {insightSummary(r.after)}
                          </td>
                          <td style={{ color: DIFF_COLOR[r.kind], fontWeight: r.kind === "same" ? 400 : 600, fontSize: 12 }}>
                            {DIFF_LABEL[r.kind]}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </div>
          </>
        )}
      </div>
    </NavShell>
  );
}
